---
id: dec-draft-6039d490
title: praxion-self-eval-v1 harness — flat 2-level module layout at v1; deep checks/ sub-package deferred
status: proposed
category: implementation
date: 2026-05-26
summary: harness/ uses flat families/ with no checks/mechanical/ or checks/llm/ sub-directories at v1; the 4-level directory sketch in SYSTEMS_PLAN.md is a future-state guide, not a v1 constraint.
tags: [eval, eval-praxion, module-layout, simplicity-first]
made_by: agent
agent_type: implementation-planner
branch: worktree-praxion-self-eval-v1
pipeline_tier: standard
affected_files:
  - eval/src/praxion_evals/harness/families/
  - eval/src/praxion_evals/harness/checks/
re_affirms: dec-draft-e1f01781
---

## Context

The systems-architect's SYSTEMS_PLAN.md §Architecture shows a full 4-level directory layout for
the `harness/` package:

```
harness/
  families/
    family1_pipeline_fidelity.py
    family2_bc_adherence.py
  checks/
    mechanical/
      frontmatter.py
      supersession.py
      sections.py
      traceability.py
      affected_reqs.py
    llm/
      option_depth.py
      bc_adherence.py
      decision_proportionality.py
```

The acceptance criteria (AC-10) specifies named test coverage for each check category, but does
not mandate a specific directory depth. The implementation-planner must decide: implement the full
4-level layout at v1, or implement a flat 2-level layout and defer the depth.

## Decision

Implement a flat 2-level layout at v1: `harness/families/family1_*.py` and
`harness/families/family2_*.py` contain all check logic inline (or as private functions within
the family module). No `harness/checks/` sub-package at v1.

The `checks/` sub-package depth is deferred as a future refactor step if/when check reuse across
families justifies the extraction.

## Considered Options

### Option 1 — Full 4-level layout at v1

Create `harness/checks/mechanical/` and `harness/checks/llm/` sub-packages with individual
check modules (frontmatter.py, supersession.py, etc.) as shown in the architect's sketch.

- Pros: matches the architect's full directory vision; each check is independently navigable.
- Cons: requires 7+ new files (5 mechanical + 2 llm + `__init__.py` files) with minimal LOC each;
  no check is shared between families in v1 (Family 1 and Family 2 have completely disjoint check
  sets); adds 3 empty `__init__.py` files to the commit footprint at Step 2 with no functionality.
  This is premature modularization at the cost of a larger, harder-to-review diff.

### Option 2 — Flat 2-level layout at v1 (chosen)

Family modules contain all check logic directly (mechanical checks as private functions prefixed
`_check_`; LLM-judged checks as private methods). No `checks/` sub-package until check reuse
justifies it.

- Pros: Step 2 creates 5 new files instead of 12+; each family module is a single coherent unit
  a reviewer can read top-to-bottom; no empty `__init__.py` stubs; Simplicity First.
- Cons: if a future family (e.g., v2 LEARNINGS-distillation family) reuses mechanical checks from
  Family 1, the extraction refactor must happen then. At v1, there is exactly one consumer of each
  check, so extraction serves no DRY purpose.

## Consequences

**Positive:**
- Smaller, more reviewable diff at Steps 2 and 4a/6a.
- Each family module is complete and self-contained — a reader sees all the checks for that family
  in one file.
- The `checks/` sub-package layout is still the documented future-state target; extraction is a
  clean refactor step when check reuse arrives.

**Negative:**
- Family modules may grow toward the 400-LOC guideline if check logic is verbose. Implementer
  should watch for this and extract to helper functions within the family module before hitting
  the 800-line ceiling.
- A future contributor may expect the `checks/` sub-package based on the architect's sketch and
  be surprised by its absence. Mitigated by a `# TODO: extract to checks/ sub-package when check
  reuse across families exists` comment at the top of each family module.
