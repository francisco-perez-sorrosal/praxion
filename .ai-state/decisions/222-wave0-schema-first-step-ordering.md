---
id: dec-222
title: Wave 0 step ordering — schema first, backend section as parallel extension
status: accepted
category: implementation
date: 2026-06-05
summary: Decompose Wave 0 as schema definition → examples (foldable) → backend abstraction section (parallel-group with test) → namespace + inventory rows; schema step anchors all downstream waves.
tags: [wave0, step-ordering, sia-praxion-fit, run-store, schema, implementation-planner]
made_by: agent
agent_type: implementation-planner
branch: worktree-sia-praxion-fit-research
pipeline_tier: standard
affected_files:
  - skills/agent-evals/references/run-ledger-schema.md
  - tests/test_run_store_backend.py
  - rules/eval/eval-data-governance.md
  - rules/swe/agent-intermediate-documents.md
---

## Context

Wave 0 (the storage spine) produces three S0.x deliverables from `SYSTEMS_PLAN.md §Implementation
Sequencing`. Each could be authored as a single monolithic commit or as a sequence of smaller
increments. The decomposition question is: does the backend abstraction section of the schema
belong in S0.1 or S0.2, and does the backend unit test run before or after the section exists?

The architect's sequencing (`S0.1 schema first → S0.2 backend abstraction → S0.3 namespace`)
maps naturally to Praxion's known-good-increment principle, but S0.2's only deliverable in Wave 0
is a **Markdown section in the same file as S0.1** (no Python class yet). This raises the
question: is it meaningful to split S0.1 and S0.2 into separate steps, or should they merge?

## Decision

Split into separate steps, with S0.2 (backend section) running as a **parallel group** with the
corresponding unit test:

- **Step 1**: S0.1 schema — author `run-ledger-schema.md` with the descriptor YAML, EVAL_RESULTS
  frontmatter, EVAL_LOG column set, verifier reuse reference, and back-link. Also update
  `agent-evals/SKILL.md` satellite-files listing.
- **Step 2**: S0.1 examples — minimal-valid examples for EVAL_RESULTS and EVAL_LOG row. May fold
  into Step 1 at implementer discretion (same commit is acceptable).
- **Step 3** `[parallel-group: A]`: S0.2 backend — add `## Run-Store Backend Abstraction` section
  to Step 1 file (four backends, five ops, `local-home` proof, invariance self-test).
- **Step 4** `[parallel-group: A]`: S0.2 test — `tests/test_run_store_backend.py` (schema
  convention tests: YAML parseable, URI pattern matches, no `backend:` field in descriptor).
- **Step 5**: Integration checkpoint after parallel group A.
- **Steps 6–8**: S0.3 (namespace + inventory rows) sequentially; final integration checkpoint.

The backend section is authoritatively part of S0.2 per the architect's sequencing, but since
it is an additive section in the S0.1 file (no new file, no new Python class), it fits in a
single focused commit that is independently reviewable from the schema definition.

## Considered Options

### A — One monolithic Step: author all of run-ledger-schema.md in a single commit
- Pros: fewer commits; schema and backend section never diverge.
- Cons: mixes the invariant contract definition (eight fields, field constraints, dual lifecycle)
  with the dispatch abstraction (four backends, five ops, proof pattern) in one reviewable unit.
  Harder to bisect if a claim is wrong; doesn't demonstrate known-good-increment discipline.

### B — Schema first, then backend section as a separate sequential step (no parallel test)
- Pros: clean split; schema exists before backend details.
- Cons: unit test waits for backend section to be sequential-complete before running;
  loses the RED→GREEN shaping benefit of TDD.

### C — Schema first, backend section + test as parallel-group (CHOSEN)
- Pros: clean split; test-engineer can write a RED skeleton against the schema (Step 1)
  while implementer authors the backend section; both converge at integration checkpoint.
  Demonstrates the `local-home` reference-impl proof via a test, not just prose.
- Cons: minor coordination overhead for a small parallel group.

## Consequences

- **Positive:** the schema step (Step 1) is independently commitable and reviewable as the
  Wave 0 anchor. The parallel group (Steps 3+4) confirms the abstraction's claims via a test
  before Wave 1 consumers depend on them.
- **Negative:** eight steps instead of three; risk of over-decomposition for what is
  mostly documentation work. Mitigated by: Step 2 being explicitly foldable into Step 1,
  reducing to at most 7 distinct commits.
- **Constraint**: the test in Step 4 is a schema-convention test (parses the Markdown artifact
  and asserts documented claims), NOT a test of a Python class. If the team later decides to
  also produce a Python helper, that step requires a separate planning decision.
