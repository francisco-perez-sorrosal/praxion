---
id: dec-draft-8954ef47
title: Pilot strategy — trunk-only at this pipeline; defer behavioral pilot to first consumer project
status: proposed
category: architectural
date: 2026-04-28
summary: Land the test-topology trunk artifacts (schema, sentinel dimension, ledger class, document conventions) without activating any behavioral pilot in Praxion; the first behavioral pilot occurs in the first consumer project that adopts the protocol.
tags: [test-topology, pilot, scope, dogfood, behavioral-activation]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - .ai-state/TEST_TOPOLOGY.md
  - skills/testing-strategy/references/test-topology.md
  - agents/sentinel.md
  - rules/swe/agent-intermediate-documents.md
  - .github/workflows/test.yml
  - memory-mcp/pyproject.toml
  - memory-mcp/tests/
---

## Context

The researcher (`RESEARCH_FINDINGS.md` §E.3) recommended `memory-mcp` as the M2 behavioral pilot subsystem (largest pocket, cross-pocket coupling case present, discrete subsystems map to ~5 logical groups). The user's coordinator-to-architect directive in `HANDOFF_CONSTRAINTS.md` §S2 split this into three trade-off candidates and made the decision the architect's call:

1. **Pilot here (memory-mcp)** — dogfood the protocol on the largest Praxion pocket; surface protocol bugs early; validate the schema against real cross-pocket coupling.
2. **Defer behavioral pilot** — ship trunk schema, sentinel dimension, and document conventions in Praxion; do not activate per-step group selection here; first behavioral pilot lands in a consumer project.
3. **Hybrid** — ship trunk + sentinel + command in Praxion; declare a minimal `TEST_TOPOLOGY.md` (1–2 groups per pocket) so the schema is exercised end-to-end; do not enforce step-tier selection during regular Praxion development; consumer projects activate full behavior.

Two pieces of empirical evidence weigh heavily on the decision:

- Praxion's full test fleet runs in **~35 seconds aggregate naive wall-clock** (researcher §0). With xdist parallelization across pockets via the GitHub Actions matrix, the wall-clock floor is bounded by the slowest pocket — `task-chronograph-mcp` at 17.8 s — not the sum. Step-tier selection's *time-saved* ROI in absolute seconds is small at this scale.
- `memory-mcp` has **8 pre-existing test failures** at this checkout (researcher §A.8; likely environmental, missing `.ai-state/decisions/` fixtures in the worktree). The user's directive states: "Block M2 on resolution of those failures." So picking either option 1 or option 3 with memory-mcp activation drags failure resolution into this pipeline as a hard precondition.

The user's directive also explicitly states: **"default to dogfood is not sufficient justification."** A non-trivial reasoning record is required.

## Decision

**Adopt option 2 — defer behavioral pilot. Ship trunk-only at this pipeline.**

Concretely:

- This pipeline lands: the trunk schema reference file, the Python leaf reference additions, the rule edits (`topology-drift` debt class, `.ai-state/TEST_TOPOLOGY.md` listed in the permanent-artifact tree), the sentinel TT01–TT05 dimension definitions, the document-schema additive extensions to `IMPLEMENTATION_PLAN.md` / `WIP.md` / `TEST_RESULTS.md`, the architecture-doc additions in both `.ai-state/ARCHITECTURE.md` and `docs/architecture.md`, and all seven open-question ADRs.
- This pipeline does NOT land: a populated `.ai-state/TEST_TOPOLOGY.md`, a memory-mcp group decomposition, additions to any `pyproject.toml` (no `pytest-xdist` install), CI matrix changes, marker tagging on existing tests, behavioral activation in implementer / test-engineer / verifier, or resolution of the 8 memory-mcp pre-existing failures (those become an unrelated tech-debt-ledger item filed independently).
- The first consumer project that adopts the i-am plugin and runs a Standard-tier feature pipeline will be the M2 candidate. Their architect re-runs the trade-off framing with their data; their planner decomposes M2; their implementer + test-engineer activate group selection.

## Considered Options

### Option 1 — Pilot here (memory-mcp)

**Pros:**
- Schema validated against real cross-pocket coupling immediately (the `test_inject_memory.py` → `hooks/inject_memory.py` bridge).
- Praxion as reference implementation gains a populated `.ai-state/TEST_TOPOLOGY.md` consumers can study.
- 8 memory-mcp failures get resolved (positive externality).
- Refactor trigger machinery (TT04 runtime drift) gets a real test corpus on which to fire.

**Cons:**
- ROI on raw runtime is marginal — the slowest pocket is task-chronograph-mcp (17.8 s), not memory-mcp (1.7 s). Even a perfect step-tier selection on memory-mcp saves <1 s per pipeline.
- Pulls 8 unrelated test failures into this pipeline's critical path. Diagnosing and resolving them is implementer work that the architect explicitly should not do (`HANDOFF_CONSTRAINTS.md` §S2: "Architect must NOT diagnose or attempt to fix the 8 memory-mcp failures inside this pipeline").
- Risk of premature optimization: tuning the schema against one project's pocket layout could embed Praxion-isms that later prove leaky.
- The cross-pocket coupling case is *one* of many possible patterns. Validating the schema on memory-mcp's pattern does not validate it on patterns Praxion does not happen to have (Go modules, JS monorepo build graphs, etc.).

### Option 2 — Defer behavioral pilot (chosen)

**Pros:**
- Surgical scope: only the trunk artifacts ship in this pipeline. The behavioral pathway becomes a future-pipeline concern, separable from the current scope.
- Praxion's value as a reference implementation is in the **schema and convention**, not in a dogfooded activation. A clean, well-articulated trunk + Python leaf + sentinel definition + ADR set is the artifact consumers will copy. A populated `TEST_TOPOLOGY.md` for memory-mcp would mostly be a curiosity to them, since their projects have different pockets and different coupling patterns.
- Sidesteps the 8 memory-mcp failures entirely. They are filed as an unrelated debt item; whoever is willing to diagnose them can, on a separate pipeline.
- Smaller change surface = lower risk of integration regression in the sentinel, ledger, and verifier paths.
- The schema's correctness is *still* validated — by the hypothetical Go module worked example (HR1's acceptance test). That validation is more rigorous than activating against memory-mcp would have been, because Go is an outside-the-codebase reality check rather than an inside-the-codebase confirmation bias.
- The trunk-only milestone is genuinely useful on its own. Even without behavioral activation in any project, Praxion gains: a shared vocabulary (group, tier, integration_boundaries, parallel_safe), a sentinel dimension family, a debt class, and ADR records of seven design decisions. None of those depend on a populated topology to be valuable.

**Cons:**
- The protocol is not field-tested in any actual project until M2 lands somewhere. A schema bug could go undetected for weeks or months.
- Praxion's developers do not get the (admittedly small) wall-clock savings during the gap.
- The refactor trigger (TT04) cannot fire until *some* project has populated runtime envelope data — but this is fine, since TT04 has a documented self-deactivation clause for the cold-start case.
- A populated reference implementation is genuinely useful for documentation purposes. The compromise: the SYSTEMS_PLAN's "Hypothetical Go module worked example" plus the Python leaf reference's `pyproject.toml` snippet provide a documentation artifact a consumer can read end-to-end.

### Option 3 — Hybrid (minimal Praxion topology, no behavioral activation)

**Pros:**
- The schema gets a tiny amount of real-data exercise (1–2 groups per pocket) without forcing memory-mcp failure resolution.
- A populated `.ai-state/TEST_TOPOLOGY.md` exists for downstream readers.
- No behavioral activation, so no developer-experience disruption.

**Cons:**
- "1–2 groups per pocket" recapitulates today's pocket layout — the very anti-pattern the researcher's §D.6 objection warned against. A "memory-mcp-unit + memory-mcp-integration" topology is coverage-equivalent to today's CI matrix and adds the maintenance burden of a separate file with zero new information.
- Sentinel TT04 (runtime drift) cannot meaningfully fire on 2-group topologies — the envelope is "the whole pocket." That degrades to today's per-pocket runtime tracking, which the metrics collector already does without TT04.
- The hybrid creates a partially-populated artifact that consumers might mistake for a complete reference, when in fact it is intentionally minimal. Educational risk.
- The hybrid does not actually exercise the load-bearing case (`integration_boundaries` across pockets). Without that, the schema's most innovative field is untested in any project.
- Adds N small edits across pockets (marker registration, group definition, mark-on-touch) without unlocking any behavioral benefit. Cost without commensurate value.

## Consequences

### Positive

- This pipeline's deliverable list is shorter, more focused, and more verifiable. The acceptance criteria are bounded by "do the trunk artifacts pass the Go-portability test, do the sentinel/ledger/document-schema additions land cleanly, do the ADRs articulate the seven decisions" — all observable in the systems-architect's and implementation-planner's outputs without running tests on any pocket.
- The 8 memory-mcp failures are handled at the right level: as a separate, owner-named item in the tech-debt ledger, not bundled into a feature pipeline they have nothing to do with. This is also the user's directive.
- The architecture-doc Test Topology section can honestly mark Built and Designed components: the schema/sentinel/ledger surfaces are Built; the populated topology and behavioral activation are Designed (i.e., the design is complete, but no project has materialized them yet). This dual marking is exactly what `docs/architecture.md`'s "code-verified" semantics demand — not a hand-waved promise.
- The four-behavior contract's "stay surgical" and "simplicity first" principles are honored. The behavioral pilot is a real piece of work (per-step group derivation, marker tagging, fixture parallelization, CI matrix expansion, verifier validation) that does not survive the user's "ROI is marginal at Praxion's scale" finding.

### Negative

- The protocol is undertested until M2 ships somewhere. A consumer project's first behavioral pilot is the field test. Risk: a schema bug that only surfaces under behavioral activation is deferred until then. Mitigation: the schema is conservative (additive fields, opt-in `expected_runtime_envelope`, conditional sentinel checks for cold start, one-hop closure); a buggy schema is recoverable by ADR-supersession at M2 without breaking M1 artifacts.
- Praxion does not gain wall-clock savings during the gap. Acknowledged; the wall-clock savings at Praxion's scale are <1 s per pipeline, well below cognitive-load and review-overhead noise floors. This is exactly the "ROI marginal" finding cited above.
- Future readers might wonder why Praxion ships a test-topology protocol it does not itself use. The architecture-doc Test Topology section's Built/Designed marker is the answer; the SYSTEMS_PLAN and this ADR are the long-form rationale.

### Reversibility

This decision is partially reversible. If a consumer project's M2 surfaces critical schema gaps, a follow-up Praxion pipeline can absorb the corrections (additive registry rows, additive trunk fields with default values, sentinel-dimension refinements). The decision NOT to dogfood at M1 cannot be un-made retroactively, but a future "let's pilot this in Praxion now" decision is always open — it just needs a fresh trade-off pass with whatever the new evidence is.

The 8 memory-mcp test failures, if resolved on a separate pipeline before any consumer project ships M2, would unlock a future "now we can pilot it here" possibility — but that is not a precondition for anything in the current decision.

## Prior Decision

None — this is a new decision, not a supersession.
