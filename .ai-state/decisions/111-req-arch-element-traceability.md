---
id: dec-111
title: Bidirectional REQ↔architectural-element traceability convention
status: accepted
category: behavioral
date: 2026-05-01
summary: 'Establish a bidirectional cross-reference convention between SDD specs and LikeC4 elements — `architectural_elements: [...]` in SPEC frontmatter, `metadata.req_ids: [...]` on LikeC4 elements — and extend the traceability YAML/matrix with a fourth column. No new tooling; the LikeC4 MCP `query-by-metadata` already supports the lookup.'
tags: [aac, dac, traceability, sdd, likec4, conventions, architecture-docs]
made_by: agent
agent_type: systems-architect
pipeline_tier: standard
affected_files:
  - skills/spec-driven-development/SKILL.md
  - skills/spec-driven-development/references/spec-format-guide.md
  - agents/verifier.md
re_affirmed_by:
  - dec-112
---

## Context

SDD specs (`.ai-state/specs/SPEC_*.md`) name behavioral requirements with `REQ-NN` IDs and a traceability matrix mapping each REQ to test files and implementation files. LikeC4 architectural elements name structural components (services, modules, deployment nodes) with metadata blocks. The two systems describe the same product from different angles — behavior on one side, structure on the other — but no convention links them.

The gap is operationally visible: when a code-touching change lands, no agent can answer "which architectural components carry REQ-NN?" without ad-hoc grep, and no agent can answer "which behavioral requirements does the `auth.service` element implement?" at all. The architect-validator agent (dec-100) verifies the code↔DSL↔ADR triangle but has no surface for behavior↔structure traceability. The future Idea 10 sentinel check ("traceability orphans") cannot fire without this convention being in place.

The substrate is already shipped. The LikeC4 MCP exposes `query-by-metadata { key, value, matchMode }` which indexes element metadata server-side; the SDD skill already holds `traceability.yml` (ephemeral) and the archived SPEC matrix (persistent) as the single sources of truth for REQ→test/impl mapping. What is missing is the **convention** that says where the cross-reference lives, on which side, and how downstream tools (verifier matrix, sentinel check, architect-validator) read it.

## Decision

Adopt a **bidirectional** traceability convention that records the same mapping on both sides. Each side names the other in its own language; downstream tools read whichever side fits the question being asked.

### Surface 1 — LikeC4 element metadata

Each LikeC4 element that implements one or more behavioral requirements declares them in its metadata block:

```c4
component AuthService {
  metadata {
    code_module = "src/auth/service.py"
    req_ids = "REQ-01, REQ-03, REQ-07"
  }
}
```

`req_ids` is a comma-separated list of `REQ-NN` IDs from the spec that owns the requirement. Whitespace around commas is tolerated; downstream parsers must split on `,` and trim.

**Lookup pattern (already supported, no new tooling):**

- "Which elements carry REQ-03?" → `query-by-metadata { key: "req_ids", value: "REQ-03", matchMode: "contains" }`
- "Does this element have any REQ links?" → `query-by-metadata { key: "req_ids", matchMode: "exists" }`

The `contains` match mode matters: a single element typically implements multiple REQs, so values are stored as comma-separated and matched as substrings rather than as exact lists.

### Surface 2 — SPEC frontmatter

Each archived SPEC declares the architectural elements that implement its requirements in YAML frontmatter:

```yaml
---
spec_name: auth-flow
created: 2026-04-15T10:00:00Z
status: completed
complexity: medium
architectural_elements:
  - auth.service
  - auth.session_store
  - api.gateway
---
```

`architectural_elements` is a YAML list of LikeC4 element IDs (the dot-qualified id form that the MCP returns). The list is **per-spec, not per-REQ** — fine-grained REQ↔element mapping is the LikeC4 side's responsibility.

**Lookup pattern:** parse the SPEC frontmatter (existing skill operation), then call `read-element { id, project }` per listed element to fetch full structure.

### Surface 3 — Traceability YAML / matrix (verifier extension)

The existing `traceability.yml` and the archived SPEC's traceability matrix gain an optional fourth column: **Architectural Element**. The YAML schema extends as follows:

```yaml
requirements:
  REQ-01:
    tests:
      - tests/auth/test_session.py::test_expired_token_returns_401
    implementation:
      - src/auth/session.py::validate()
    architectural_elements:    # NEW — optional
      - auth.service
      - auth.session_store
```

The verifier renders this into the matrix:

| Requirement | Test(s) | Implementation | Architectural Element(s) | Status |
|-------------|---------|----------------|--------------------------|--------|
| REQ-01 | tests/.../test_expired_token_returns_401 | src/auth/session.py::validate() | auth.service, auth.session_store | PASS |

Absent `architectural_elements:` for a REQ means "no architectural elements declared yet"; this is **not** an UNTESTED-equivalent state — it is a separate dimension and produces no PASS/FAIL noise on existing matrix rows. The orphan check (Idea 10's AC12) is the consumer that turns absence into a finding.

### Population responsibility

| Stage | Who | Action |
|-------|-----|--------|
| Plan-time | systems-architect | Adds `metadata.req_ids` to LikeC4 elements when authoring/updating `.c4` files for a feature; uses the spec's REQ IDs as already drafted in `SYSTEMS_PLAN.md` |
| Plan-time | systems-architect / implementation-planner | Sets `architectural_elements:` in SPEC frontmatter (added at archival or back-filled when LikeC4 IDs are known) |
| Per-step | implementer / test-engineer | Optionally appends `architectural_elements:` per REQ in `traceability.yml` when the mapping is known at test/impl time |
| Verification | verifier | Reads YAML; renders the fourth column into `VERIFICATION_REPORT.md` |
| Audit | sentinel (AC12, separate ADR) | Cross-checks both surfaces for orphans |

**No new tooling.** Population is convention-driven: agents add the metadata when they know it. The `query-by-metadata` MCP tool already does the indexed lookup. The verifier's matrix rendering is a one-column extension to existing logic. The architect-validator can later (out of scope) add a model→spec drift check.

### Drift class — accepted as inherent to bidirectional schemes

A bidirectional convention has one side getting out of sync with the other. We accept this trade-off because (a) the unidirectional alternatives leave one half of the orphan space invisible (see Considered Options), and (b) Idea 10's orphan check turns drift into a sentinel finding rather than letting it accumulate silently. The drift surface is the exact problem the sentinel check is designed to detect.

## Considered Options

### Option 1 — Unidirectional: LikeC4 metadata only

`metadata.req_ids` on LikeC4 elements; SPEC frontmatter unchanged.

**Pros:** Single source of truth; no drift surface; `query-by-metadata` is already the canonical lookup mechanism.

**Cons:** Cannot answer "which structural components implement this spec?" without iterating every element's metadata. SPEC files become opaque to architectural questions. Orphan-detection misses one direction entirely: a REQ with no `req_ids` cross-reference looks identical to a REQ that intentionally has no architectural element (an internal helper, a config change). The sentinel cannot distinguish "spec author forgot" from "intentionally not mapped".

### Option 2 — Unidirectional: SPEC frontmatter only

`architectural_elements:` in SPEC frontmatter; LikeC4 elements carry no REQ metadata.

**Pros:** SPECs are self-describing; matrix rendering is straightforward.

**Cons:** Symmetric to Option 1 — cannot answer "which REQs does this element carry?" without iterating every SPEC. The LikeC4 MCP's indexed query is unused. Element-side orphans (a service with no REQ link in any spec) are invisible.

### Option 3 — Bidirectional (chosen)

Both surfaces carry the cross-reference; the orphan check (Idea 10's AC12) makes drift detectable.

**Pros:** Either side answers either question without iterating the other corpus. Both orphan classes (REQs with no element, elements with no REQ) become detectable. The `query-by-metadata` MCP is exercised. SPEC frontmatter remains a quick scan-target for architectural-element-by-spec questions.

**Cons:** Drift surface — the two sides can disagree silently between sentinel runs. Mitigated by Idea 10's traceability-orphan check (AC12) which fires only when both substrates are present. Adoption requires authors to update both sides; we accept this cost because the sentinel check makes it a tracked debt class rather than a silent quality issue.

### Option 4 — New helper script wrapping `query-by-metadata`

Add `scripts/spec_arch_xref.py` as a Python wrapper.

**Pros:** Uniform interface for non-MCP-equipped environments; could cache responses.

**Cons:** The MCP tool already exists and is the canonical interface; wrapping it adds a layer that has to be kept in sync with the MCP. The seed brief explicitly settled this: "convention, not new tooling." Rejected as bloat.

## Consequences

**Positive:**

- "Which components carry REQ-NN?" becomes a one-call MCP query; "which REQs does this component carry?" becomes a one-call MCP query.
- The verifier's matrix gains an architectural dimension without reshaping its existing structure.
- The sentinel's traceability-orphan check (Idea 10's AC12) has a substrate to operate against.
- The architect-validator's future scope expansion (model→spec drift) has a defined input surface.
- The LikeC4 MCP's indexed metadata lookup is exercised — the substrate finally pays off.

**Negative:**

- Drift surface between the two sides; mitigated by the AC12 orphan check.
- Authors must update both sides when a feature ships. Mitigated by the per-stage population responsibility table; orphan findings provide post-hoc detection when an author misses one side.
- SPEC frontmatter parsing now has an additional optional field; downstream parsers must handle absence gracefully.

**Operational:**

- The SDD skill's `SKILL.md` + `references/spec-format-guide.md` document both surfaces with a "Bidirectional Traceability" subsection. The traceability YAML schema gains the optional `architectural_elements:` field.
- The verifier's Phase 4 prompt extends the traceability matrix render to four columns when `architectural_elements:` is present; back-compat: matrix renders three columns when absent.
- Token-budget impact: minimal. Both surfaces are on-demand (the SDD skill's references load on activation; the MCP tool is session-injected). No always-loaded surface changes.
- The convention is the substrate Idea 10's sentinel AC12 check operates on. Authoring AC12 in parallel with this ADR's SDD-skill convention is safe (the check spec only invokes existing schema), but the check has zero work to do until at least one feature populates both surfaces.

## Prior Decision

This ADR does not supersede or re-affirm a prior decision. It composes with `dec-098` (AaC fence contract) and `dec-100` (architect-validator charter): the fence contract makes the markdown layer mechanically detectable; the architect-validator verifies code↔DSL↔ADR; this ADR adds behavior↔structure as the fourth edge of an emerging traceability mesh.
