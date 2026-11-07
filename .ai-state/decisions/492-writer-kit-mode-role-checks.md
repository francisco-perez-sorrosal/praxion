---
id: dec-492
draft_id: dec-draft-1e989780
title: "Writer kits grade each mode with pure form checks a habit record fails"
status: accepted
category: behavioral
date: 2026-11-06
summary: "Each covered mode of the test-engineer and the systems-architect gets at least one role check, built from an existing constructor, whose pass needs a form only the definition states: the acceptance-design sections, a paired TEST_RESULTS step section, the [PARTIAL]-first plan title, and the spec- and feature-mode required headings."
tags: [eval, adherence, role-checks, test-engineer, systems-architect]
made_by: agent
agent_type: systems-architect
branch: lean-writers
pipeline_tier: full
affected_files:
  - eval/src/praxion_evals/adherence/catalog.py
  - eval/src/praxion_evals/adherence/checks_process.py
---

## Context

A paired run can see a lean regression only on a check a session cannot pass by habit. The git move showed checks the model passed with no rule present. The acceptance driver's habit records are graded with an empty plugin copy, so a script-backed check reads `errored` there. `check_test_results_shape.py` exits 0 on a free-form `All tests pass.` record. The systems-architect's shared `adr_row` clauses are not applicable when no fragment is written, so they cannot be a mode's binding check.

## Decision

- **Test-engineer.** The two acceptance-design checks (the closed input set, and the five `ACCEPTANCE_TESTS.md` sections) are re-gated from the prompt to the task's mode. A new paired-mode check requires `TEST_RESULTS.md` to carry a step section with its `Command` and `Result` lines (`steps_carry_fields`).
- **Systems-architect.** It keeps `adr_row` unchanged and gains three checks: `SYSTEMS_PLAN.md` opened with `[PARTIAL]` within its first three tool calls and ending unmarked (both modes); the spec-mode Goal, Acceptance Criteria and Behavioral Specification with an Observable Surface; and the feature-mode six required sections.
- **Every new check** is pure and reuses an existing constructor and its canary. Each binds on every task of its mode the role is not stopped early on.
- **C5 and C2 stay scored.** Their expected vacuity is stated in `eval/EVAL_PLAN.md` before any run, not exempted.

## Considered Options

- **Pure form checks (chosen).** They fail on a habit record and reach a verdict without scripts.
- **Script-backed checks** (`check_test_results_shape.py`, `extract_spec.py --check`). Rejected: one passes a free-form record by habit, and both read `errored` on the habit path.
- **Absence checks** (no ADR draft in spec mode, no outer-loop test in paired mode). Rejected: a pass that is an absence is not REQ-03's habit proof, and each extra scored check adds discordance noise to the flip rule.

## Consequences

- The paired results check reads the step heading and two field names, not every key the shape validator reads.
- The spec's full grammar stays the extract script's job.
- A session that habitually writes Praxion's exact headings would still pass. The optional paid floor run (stated in the estimate) is the user's way to confirm before the paired run relies on a check.
