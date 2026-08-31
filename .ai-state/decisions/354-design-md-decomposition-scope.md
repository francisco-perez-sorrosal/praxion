---
id: dec-354
title: DESIGN.md decomposition is scoped to §3b; §3a is gate-bound and stays whole
status: accepted
category: implementation
date: 2026-08-31
summary: Sub-anchor DESIGN.md §3b (prose-owned, ~19.9K tokens, no mechanical consumer) and leave §3a intact, because four gates bind §3a as a single table.
tags: [architecture-docs, design-md, context-cost, gates, planning]
made_by: agent
agent_type: implementation-planner
branch: worktree-adr-living-view
pipeline_tier: standard
affected_files:
  - .ai-state/DESIGN.md
  - scripts/check_architecture_projection.py
  - agents/sentinel.md
  - .ai-state/TEST_TOPOLOGY.md
---

## Context

`CONTEXT_REVIEW.md` R1 requires that `.ai-state/DESIGN.md` §3 "gain stable `###` sub-anchors at a
granularity where any single sub-read is ≲2,000 tokens", on the argument that a checkpointed living
view nobody can afford to read is net-negative. The orchestrator declared R1 in scope for this
pipeline and ordered it before checkpoint work. `SYSTEMS_PLAN.md` separately declares DESIGN.md's
read cost explicitly out of scope ("trustworthy, not cheap").

Measured at `a7bf86aa`, §3 is 91,857 chars and splits unevenly:

| Subsection | chars | ≈ tokens | Consumers |
|---|---|---|---|
| §3a Structural components | 14,351 | ~3,800 | `check_architecture_projection.py` (sentinel AC13), sentinel AC01/AC09, `TEST_TOPOLOGY.md` `subsystems` binding (TT01) |
| §3b Capabilities | 75,535 | ~19,900 | **none** — sentinel AC09 states explicitly that "§3b capabilities are not §3a structural components — do not demand they appear" |

So the token problem is 84% located in the half that no gate parses, and the gated half is
already under the review's own 2,000-token-per-sub-read target once §3a is reached directly.

## Decision

Decompose **§3b only**: split its single 34-row capability table into themed `#### 3b.N` subsections
each ≲2,000 tokens, preserving every cell's text byte-for-byte, and add a §3-head table of contents
plus a grep-first navigation note. **Leave §3a whole.**

R1 is therefore delivered in substance (~19.9K of the ~23.7K-token read cost becomes selectively
addressable) without teaching four gates a new shape. §3a's residual decomposition is recorded as
surfaced tech debt, not attempted here.

## Considered Options

### A. Decompose §3 wholesale, as R1 literally states

- **Pro**: satisfies the review's wording exactly; the whole section becomes selectively readable.
- **Con**: fragmenting §3a's table breaks `check_architecture_projection.py`'s parse and the three
  sentinel checks plus TT01 that resolve against it. Four gates would have to be taught a new shape
  inside a pipeline whose subject is the decision log, not the architecture-doc parser. That is a
  cross-cutting refactor mid-pipeline — the same scope-creep the architect refused for `td-150`.

### B. Decompose §3b only (**chosen**)

- **Pro**: removes 84% of the read cost at zero gate risk; §3b is prose-owned by contract, so the
  edit cannot produce drift any check is entitled to notice.
- **Pro**: byte-for-byte cell preservation makes the change mechanically verifiable (set equality of
  extracted cells pre/post), which a rewrite would not be.
- **Con**: §3a stays a 3.8K-token monolith. Accepted: it is under the granularity the review asks
  for as soon as a reader can jump straight to it, which the new ToC provides.

### C. Do nothing — honour `SYSTEMS_PLAN`'s out-of-scope declaration

- **Pro**: strictly surgical; nothing downstream depends on R1 (`check_design_checkpoint.py` reads
  frontmatter and greps for `dec-NNN` citations — it never reads §3 prose).
- **Con**: leaves the checkpoint decorating a document whose dominant section is unreadable at any
  affordable budget, which is the review's stated objection and the orchestrator's stated scope.

## Consequences

**Positive**

- The living view becomes selectively readable for the section that carries 84% of its bulk.
- No gate changes; `check_architecture_projection.py --json` staying clean is the step's own test.
- The verification is mechanical (cell-set equality), not a judgment call about whether prose survived.

**Negative**

- §3a remains undecomposed, so "any single §3 sub-read is ≲2,000 tokens" is not literally true.
- The plan now carries one step that serves the context shadow rather than the systems plan, which
  a later reader could mistake for scope creep — hence this record.

## Disconfirmation

- **Falsifier**: a consumer that parses §3b as a single markdown table. If one exists, option B
  breaks it and the step must be reverted; the evidence for its absence is sentinel AC09's explicit
  exemption plus `check_architecture_projection.py` reading only §3a.
- **Steelmanned runner-up**: option C. `SYSTEMS_PLAN` is the authoritative design input and it drew
  the scope line deliberately; the checkpoint's correctness genuinely does not depend on read cost,
  and every token spent on document ergonomics inside a schema pipeline is a token not spent on the
  migration, which is where this change's real risk lives.
- **Reversal trigger**: if §3a crosses ~2,000 tokens' worth of rows *and* a reader-cost complaint
  recurs, re-open — but then as a dedicated pass that teaches the four gates a nested shape, not as
  a step inside an unrelated pipeline.

## Relationship to the Checkpoint Decision

This record does **not** supersede or re-affirm `dec-draft-c5d81484` (the living view is `DESIGN.md`
plus a checkpoint plus a validator, no generated artifact) — that decision's scope boundary,
"trustworthy, not cheap", is unchanged in substance and was not re-examined. This is a separate,
narrower decision about how much document-ergonomics work rides along with the checkpoint pipeline,
recorded because the measurement behind it (§3a is gate-bound, §3b is not) will be re-derived by
anyone who next tries to decompose `DESIGN.md`. No reciprocal edge is set, deliberately.
