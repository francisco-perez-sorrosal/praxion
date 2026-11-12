---
id: dec-509
draft_id: dec-draft-674623da
title: "The step loop's iteration budget counts a marked step's whole review cycle"
status: accepted
category: behavioral
date: 2026-11-11
summary: "A driven step the light-review trigger marks adds three iterations to the budget, not one: the first review, the revision it asks for and the second review, the most review requests a series can issue before a human stop. The budget becomes every request the steps' own bounds allow, so a plan that is never revised meets a step's own stop before the budget's, and only revised series can spend the budget, which is what dec-429 meant it to bound."
tags: [step-loop, iteration-budget, light-review, agility, spawn-budget]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - scripts/_step_loop_action.py
  - scripts/_step_loop_review.py
  - scripts/test_loop_state_bound.py
  - skills/software-planning/references/coordination-details.md
affected_reqs: []
supersedes_in_part: [dec-429]
---

## Context

dec-429 derived the loop's budget from the plan: the attempt cap for each driven step, plus 1 for each driven step the light-review trigger marks. The review state machine (`_step_loop_review.py`) allows more than one review request per series before it stops for a human:

1. the first review;
2. the revision it asks for;
3. the second review.

A second `revise` verdict is `review-revised-twice`, a human stop. So a marked step whose review asks for one revision spends three review-side iterations against a budget of one. That is the most ordinary path a forced review takes.

The budget has run out, or nearly, in most pipelines since the loop shipped:

| Pipeline | Iterations used of budget |
|---|---|
| loop-gate-followups | 30 of 30 |
| gate-repairs | 18 of 18 |
| project-gating | 28 of 28 |
| apply-rule-moves | 38 of 38 |
| install-refresh | 21 of 26 |
| audience-split | 13 of 14 |
| hand-path-instructions | 14 of 17, after five of twelve steps |

Each time, the remaining steps ran outside the loop, under the same gates but by hand, so the orchestrator lost the driver's commits, records and stops. In hand-path-instructions, steps 2, 4 and 5 each took four iterations: one implement, two reviews and one revision. None used a second attempt, and no plan was revised. Even the driver's own review tests keep a second plan step in their fixture "to keep the budget wide enough for a review loop".

## Decision

A driven step the trigger marks adds `REVIEW_CYCLE` = 3 iterations, the most review requests one series issues before a human stop, in place of 1. The budget is then every request the steps' own bounds allow. A plan that is never revised meets a step's own stop (`attempts-exhausted`, `review-revised-twice`, `revision-failed`) before the budget's. Only plan revisions, each opening a fresh series, can spend the budget. The rest of dec-429 stands: the unit, the counter, quality first, and the budget derived from the plan alone.

## Considered Options

### Keep 1 per marked step and move steps outside the loop when it runs out
Rejected. This is today's practice. It turns the budget stop into a routine event rather than a re-plan signal, and it moves the riskiest steps, the ones marked for review, out of the driver that records them.

### Count reviews outside the budget
Rejected. A review is an agent start, and dec-429 counts every start as an iteration. Excluding them would hide the loop's real consumption from `spawn_count.py`'s `iterations` tally.

## Consequences

- A plan with marked steps gets a larger budget: 2 more iterations per marked step. A replan-heavy pipeline still stops on the budget, as dec-429 intended.
- The cap-then-surface rule is unchanged. Each step's own stops still bound it.

## Prior Decision

dec-429 clause 2 ("plus 1 for each driven step the light-review trigger marks") is narrowed to plus the review cycle of 3. Its other clauses stand.
