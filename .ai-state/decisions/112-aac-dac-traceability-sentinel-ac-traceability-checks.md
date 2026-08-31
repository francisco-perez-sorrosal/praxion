---
id: dec-112
title: Sentinel AC-dimension extension — three conditional-activation checks for fence integrity, model↔markdown agreement, and traceability orphans
status: re-affirmation
category: behavioral
date: 2026-05-01
summary: Extend the sentinel's existing AC dimension with three conditional-activation checks (AC10 fence integrity, AC11 model↔markdown agreement, AC12 traceability orphans) mirroring the TT dimension's activation pattern. Reuses scripts/aac_fence_validator.py and the LikeC4 MCP query-by-metadata; introduces no new tooling. AC12 depends on the bidirectional convention defined in dec-111.
tags: [aac, dac, sentinel, architectural-coherence, traceability, validation, conditional-activation]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - agents/sentinel.md
re_affirms: dec-111
superseded_in_part_by:
  - dec-323
---

## Context

The sentinel's Architecture Completeness (AC) dimension currently holds nine checks (AC01–AC09) covering existence, internal consistency, file-path resolution, and developer-guide subset semantics for the architect doc and the developer guide. With the v1+v1.1 AaC substrate now shipped — fence convention (dec-098), architect-validator agent (dec-100), golden-rule enforcement (dec-108), AaC CI pipeline (dec-106), and the LikeC4-querying skill — three ecosystem-level audit checks remain unwritten:

1. **Fence integrity** — `aac:generated` / `aac:authored` fences in `**/ARCHITECTURE.md` and `docs/architecture.md` could be stripped, malformed, or unbalanced. The architect-validator catches this per-PR; the sentinel's role is the periodic audit safety net.
2. **Model↔markdown agreement** — components named in ARCHITECTURE.md should correspond to elements in the LikeC4 model (or, fallback, raw `.c4` files). The architect-validator's Phase 3 catches drift on PRs that touch architectural slices; the sentinel's role is to catch drift that lands via PRs that did not touch the slice (e.g., a refactor renamed a module, the markdown was not updated, no `.c4` file changed).
3. **Traceability orphans** — once the bidirectional REQ↔architectural-element convention (dec-111) lands, REQs with no architectural element and elements with no REQ become detectable. Without a periodic audit, drift between the two sides accumulates silently between PRs.

The three checks share a common shape: each operates on a substrate that may or may not be present in a given project (fences, LikeC4 model, populated traceability metadata). The TT (Test Topology) dimension already established the conditional-activation idiom — skip the entire dimension when its substrate is absent, emit one INFO note, never WARN/FAIL for absence. The same idiom fits these three checks per substrate.

These checks must reuse existing scripts and MCP tools, not introduce new logic. `scripts/aac_fence_validator.py` is the canonical fence checker (dec-098); `query-by-metadata` is the canonical metadata lookup; the bidirectional convention from dec-111 is the substrate AC12 reads.

## Decision

Add three checks to the sentinel's AC dimension, each with an explicit conditional-activation rule. The dimension's existing skip-condition (AC01–AC04 vs AC05–AC09) extends to cover the three new checks.

### AC10 — Fence integrity (Type: A)

**Rule:** every `**/ARCHITECTURE.md` and `docs/architecture.md` file has structurally valid `aac:generated` / `aac:authored` / `aac:end` fences (balanced, well-formed, required attributes present).

**Activation trigger:** at least one `**/ARCHITECTURE.md` or `docs/architecture.md` file exists in the project.

**Implementation:** for each in-scope markdown file, invoke `python3 scripts/aac_fence_validator.py <file>` (the canonical fence checker shipped with dec-098). Map fence-validator output to AC10 outcomes:
- Validator FAIL (`unbalanced-fence`, `missing-required-attribute`, `source-path-not-found`, malformed attributes) → AC10 FAIL with the original code in evidence.
- Validator WARN (`likec4-unavailable` for source-content drift) → AC10 WARN.
- Validator PASS → AC10 PASS for that file.

**Skip condition:** no `**/ARCHITECTURE.md` or `docs/architecture.md` files exist. Emit a single AC-dimension INFO note: "No `ARCHITECTURE.md` files present; AC10 skipped."

**Severity tier:** AC10 FAIL → Important (a structurally invalid fence breaks the architect-validator's Phase 5 input contract); AC10 WARN → Suggested.

**Boundary against architect-validator:** the architect-validator runs per-PR on architectural-touch slices (`docs/diagrams/**`, `**/*.c4`, `**/ARCHITECTURE.md`, `.ai-state/decisions/**`, `fitness/**`). AC10 is the periodic safety net for fences that drift via paths the slice gate misses. They are intentionally redundant; the slice gate is fast-path enforcement, the sentinel is comprehensive backup.

### AC11 — Model↔markdown agreement (Type: L)

**Rule:** components named in `**/ARCHITECTURE.md` and `docs/architecture.md` correspond to LikeC4 elements (model side); elements declared in the LikeC4 model appear in ARCHITECTURE.md when their `metadata.published = true` (or equivalent visibility tag) — orphans on either side are findings.

**Activation trigger (compound):**
- (model side present) `list-projects` via the LikeC4 MCP returns ≥1 project, OR `find docs/diagrams -name '*.c4'` returns ≥1 file
- AND (markdown side present) at least one `**/ARCHITECTURE.md` or `docs/architecture.md` file exists.

Both substrates must be present. When only one is present, AC11 emits an INFO note ("AC11 skipped — `<missing side>` substrate absent") and does not run.

**Implementation:**

1. **MCP-preferred path:** call `read-project-summary` per project to obtain the element list. For markdown-side components, parse the component table inside `aac:generated` fences or, when authored, read Section 3 component names from `.ai-state/ARCHITECTURE.md` (and `docs/architecture.md`).
2. **Fallback (no MCP):** `find docs/diagrams -name '*.c4'` + grep-based element extraction. Emit one WARN: `validator-unable-to-query-likec4-mcp` per affected substep, then continue.
3. Compute the symmetric diff:
   - **Model→markdown gap:** elements in the LikeC4 model with no corresponding markdown component → WARN per orphan.
   - **Markdown→model gap:** components in markdown with no corresponding LikeC4 element → WARN per orphan.

**Skip condition:** either substrate absent (per activation trigger). Emit one AC-dimension INFO note.

**Severity tier:** AC11 outputs are WARN by default (Important when count ≥ 5; Suggested when count < 5). FAIL is reserved for parse failures (malformed `.c4` files, malformed component tables) — treated as evidence-collection failures rather than coherence findings.

**Boundary against architect-validator:** the architect-validator's Phase 3 (Model→Code drift) compares the LikeC4 model against the **import graph**; AC11 compares the LikeC4 model against the **markdown component list**. Different inputs, different question. Both are needed: code may match the model while markdown lags; markdown may match the model while code drifts.

### AC12 — Traceability orphans (Type: L)

**Rule:** REQ IDs cited in `.ai-state/specs/SPEC_*.md` are cross-referenced by at least one LikeC4 element via `metadata.req_ids` (and vice versa: LikeC4 elements with `metadata.req_ids: [REQ-NN, ...]` reference REQ IDs that exist in some archived SPEC).

**Activation trigger (compound, three substrates required):**
- `.ai-state/specs/` exists with at least one `SPEC_*.md` file
- AND (LikeC4 model present) `list-projects` returns ≥1 project OR `find docs/diagrams -name '*.c4'` returns ≥1 file
- AND (bidirectional convention populated) at least one of: any LikeC4 element returns from `query-by-metadata { key: "req_ids", matchMode: "exists" }`, OR any SPEC frontmatter contains `architectural_elements:`

The third clause is the "convention-populated" gate. AC12 is **only meaningful** when the convention from dec-111 has been adopted by at least one feature; without it, every REQ is an orphan and the noise floor is the entire spec corpus.

**Implementation:**

1. Collect all REQ IDs from `.ai-state/specs/SPEC_*.md` files (parse the spec's `## Requirements` section for `### REQ-NN:` headers, or read frontmatter `architectural_elements:` and the matrix's first column).
2. For each REQ, call `query-by-metadata { key: "req_ids", value: "REQ-NN", matchMode: "contains" }`. Empty result → REQ is a structural orphan (no architectural element claims it).
3. For the inverse direction: call `query-by-metadata { key: "req_ids", matchMode: "exists" }` to enumerate elements with a `req_ids` declaration. For each, parse the comma-separated REQ list and verify each REQ ID exists in some archived SPEC. A REQ ID claimed by an element but not present in any spec → element is a citation orphan.
4. **MCP-unavailable fallback:** grep `.c4` files directly for `req_ids = "..."` and parse manually. Emit one WARN: `validator-unable-to-query-likec4-mcp`, then continue with the grep-based result.

**Skip condition:** any of the three activation substrates absent. Emit a single AC-dimension INFO note that names which substrate is missing: "AC12 skipped — `<no specs | no LikeC4 model | bidirectional convention not yet populated>`."

**Severity tier:** AC12 outputs are WARN. Threshold for severity escalation: ≥10% of REQs orphaned across all archived specs → Important; otherwise Suggested. The threshold prevents one missing element from drowning the report; the percentage-based scaling lets the audit grow with the project.

**Tech-debt ledger integration:** AC12 findings DO NOT automatically file ledger rows — the orphan signal is information at the audit level. Operators decide whether each orphan represents debt or a deliberate gap (an internal helper component, a non-architectural REQ). This is consistent with the consumer-contract framing for sentinel findings.

### Conditional-activation idiom (mirrors TT)

The dimension preamble extends to cover all three new checks. The existing AC01–AC04 / AC05–AC09 skip-conditions remain unchanged; AC10–AC12 add three independent activation triggers that operate per-check rather than per-dimension.

The dimension's existing preamble in `agents/sentinel.md`:

> Conditional activation: skip AC01-AC04 checks when `.ai-state/ARCHITECTURE.md` does not exist and project has fewer than 3 interacting components. Skip AC05-AC09 checks when neither `.ai-state/ARCHITECTURE.md` nor `docs/architecture.md` exists.

extends with:

> Skip AC10 when no `**/ARCHITECTURE.md` and no `docs/architecture.md` files exist. Skip AC11 when either the LikeC4 model substrate or the markdown substrate is absent. Skip AC12 when archived specs are absent OR the LikeC4 model is absent OR no LikeC4 element declares `metadata.req_ids` and no SPEC declares `architectural_elements:` (the bidirectional convention has not yet been populated).

Each skip emits one AC-dimension INFO note naming the missing substrate. No WARN/FAIL for absence — same discipline TT established.

## Considered Options

### Option 1 — Three sub-dimensions instead of three checks

Promote AaC checks into a separate "Architecture as Code" (AaC) dimension parallel to AC.

**Pros:** Clean separation of "how the architecture is documented" (AC) from "how the architecture-as-code substrate behaves" (AaC).

**Cons:** Adds a new top-level dimension to sentinel's report scorecard, requiring scorecard column changes, log-format changes, and consumer updates. The three checks naturally fit AC's existing surface — they all answer "is the architectural ecosystem coherent?" — and the substrate is shared with AC01–AC09. Rejected as bloat.

### Option 2 — Single composite check (AC10) covering all three

One LLM-judged check that consumes fences, MCP queries, and orphan analysis as inputs.

**Pros:** Smaller surface in `agents/sentinel.md`; one LLM batch.

**Cons:** Each input substrate has a different activation trigger (fences require markdown; orphans require specs + model + populated convention). Conflating them produces ambiguous skip semantics — does "skipped" mean "no fences" or "no specs"? Each check needs its own evidence, its own severity, its own ledger interaction. Rejected as imprecise.

### Option 3 — Three separate checks (chosen)

AC10/AC11/AC12 as independent checks, each with its own activation trigger.

**Pros:** Explicit per-check skip semantics; per-check severity tuning; reuses existing tooling without new logic; mirrors the TT dimension's already-validated conditional-activation pattern.

**Cons:** Three rows in the AC table instead of one. Mitigated: the AC table is already nine rows; three more is proportional. Numbering is sequential — AC10/AC11/AC12 — no need to renumber.

### Option 4 — Defer AC12 until convention adoption is observed

Ship AC10 + AC11 now; ship AC12 only after a feature has populated both substrates.

**Pros:** AC12 has zero work to do at v1; deferring would mean fewer checks to maintain.

**Cons:** AC12's spec is small (the activation trigger handles "no work" gracefully — emits an INFO note and exits). Deferring it means a future ADR re-opens this design space; bundling it now closes the loop in one decision. The substrate dependency on dec-111 is intentional and tracked via this ADR's `re_affirms`.

## Consequences

**Positive:**

- The sentinel becomes the periodic audit safety net for the AaC substrate that the architect-validator already enforces per-PR.
- Fence stripping (the dec-098 ADR's named risk) becomes a periodic-audit finding even when it lands via a PR that bypasses the architectural-touch slice gate.
- Model↔markdown drift accumulates visibly rather than silently.
- The bidirectional convention from dec-111 has a sentinel consumer that turns drift into tracked findings.
- All three checks reuse existing scripts and MCP tools — no new code paths, no new dependencies.

**Negative:**

- AC11's symmetric-diff logic is LLM-judged and may produce false positives when component-name conventions differ between markdown and the LikeC4 model. Mitigated by the WARN-default severity (the operator triages).
- AC12 is silent until the convention is populated — operators may forget the check exists. Mitigated by the INFO note surfacing the activation gate on every sentinel run.
- Three new LLM batches in the sentinel's Pass 2 (one per check). Existing turn-budget management already handles batch-skip; the dimension's degrade-gracefully discipline carries through.

**Operational:**

- The AC dimension preamble in `agents/sentinel.md` extends with three new skip-condition clauses (per-check activation). The check catalog table gains three rows.
- Token-budget impact on sentinel.md: ~30 lines added to the AC dimension table + ~15 lines to the preamble. The agent prompt size remains within the T03 ceiling (under 400 lines target). No always-loaded surface change.
- AC11/AC12 use the LikeC4 MCP when available. The MCP-unavailable fallback is the same `find docs/diagrams -name '*.c4'` + grep pattern the architect-validator already uses; no new fallback logic.
- AC12 reads `metadata.req_ids` per the convention the bidirectional ADR establishes. If that convention is later modified (e.g., per-REQ architectural_elements granularity), AC12's parsing logic changes to match; the activation trigger is robust to either schema.
- Implementation can author the AC10–AC12 spec in `agents/sentinel.md` immediately — the activation triggers protect the checks from firing prematurely, so they are inert until the convention is adopted by at least one feature.

## Prior Decision

This ADR re-affirms dec-111 — the bidirectional REQ↔architectural-element traceability convention. AC12 is the consumer the convention was designed to feed: without the convention, AC12's third activation clause never fires and the check is permanently inert. With the convention, AC12 turns the drift surface introduced by bidirectional schemes into a tracked, periodic-audit finding.

The convention and the sentinel check are intentionally bundled (dec-111 + this ADR) because shipping one without the other leaves a half-built capability. The convention without AC12 has no audit feedback loop; AC12 without the convention has no substrate to audit. This ADR's `re_affirms` cross-reference makes the dependency explicit; the finalize protocol will rewrite the reference to `dec-NNN` at merge-to-main.
