---
id: dec-draft-99b3a8b9
title: Driver-emitted spawns are budgeted as iterations against a plan-derived budget; spawn_count reports them apart from charged spawns
status: proposed
category: behavioral
date: 2026-10-05
summary: Inside the step loop an iteration is one driver request that started an agent (implement, revise or review); the budget is the attempt cap per driven step plus one per review-triggered step, derived from the plan; spawn_count.py reads the task's iteration ledger and reports those agents as iterations, not charged spawns; quality bounds the loop (cap then surface, never grind); cost is observed per record (turns), never capped in dollars; the authoritative statement is coordination-details § Spawn Budget.
tags: [spawn-budget, iterations, step-loop, spawn-count, quality-first, calibration]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - scripts/spawn_count.py
  - scripts/_step_loop_state.py
  - skills/software-planning/references/coordination-details.md
affected_reqs: [REQ-26, REQ-36]
supersedes_in_part: [dec-394]
dissent: []
---

## Context

dec-394, as narrowed by dec-412 and dec-413, charges every first start that states the task slug against Standard 16 / Full 32. Under the driver, every fresh attempt is such a start, so a well-run loop would spend the pipeline budget on attempts that the per-step cap already bounds. The two limits would contradict each other. The user: "I don't want to be constrained for budget, but also not spend unnecessary tokens; quality should be the guide."

The test is not architectural: no component is added, and no responsibility moves between components. `spawn_count.py` keeps counting; it learns one more input.

## Decision

1. **Unit.** Inside the loop, an iteration is one request the driver emitted that started an agent, of any kind (implement, revise, light review). A request reported as not started costs none.
2. **Budget.** It is derived, never hand-set: `ATTEMPT_CAP` × the driven (implementer) steps, plus 1 for each driven step the light-review trigger marks. The driver stops at exit 3 when the iterations used reach the budget while a step is unfinished. Precedence: completion over human stops over the budget stop. The stop is a re-tier or split signal; the verifier is never skipped to meet it.
3. **Counter.** `spawn_count.py` reads `.ai-work/<slug>/ITERATION_LEDGER.jsonl`. Agents recorded there with a `request` key are reported under `iterations` and excluded from `charged`. Without a ledger, the output is unchanged.
4. **Quality first.** The per-step cap, then a human; never grind. Cost is observed: each ledger record carries `turns` and `max_turns`. Nothing is capped in dollars.
5. **One site.** The statement lives in `coordination-details.md § Spawn Budget`. The always-loaded envelope bullet and the attempt-cap paragraph point to it.

## Considered Options

### Option 1 — Keep charged-spawn semantics
- **Cons:** the pipeline budget and the attempt cap contradict each other; a correct loop looks over budget.

### Option 2 — Iterations as the unit, counter unchanged
- **Cons:** the verdict needs mental subtraction; a tool whose verdict must be corrected by hand is a lie.

### Option 3 — Counter reads the ledger (chosen)
- **Pros:** honest verdicts; one unit per mechanism.
- **Cons:** the counter now depends on the ledger file; a driver spawn counts as charged until it is recorded (read the count outside the loop).

## Consequences

**Positive:** the pipeline budget again covers the agents a human plans (research, design, planning, verification). The loop's consumption is bounded by its own plan-derived budget.

**Negative:** the review allowance makes the budget depend on review annotations in the plan, which the plan-local trigger keeps plan-derived. A replan does not grow the budget, so repeated replans surface as a budget stop. That is intended.

## Prior Decision

dec-394 clause 2 (a first start per `agent_id` is a charged spawn) is narrowed: a first start that the step-loop driver requested and recorded in the iteration ledger is an iteration, counted against the loop's derived budget. Clauses 1, 3 and 4, and the numbers set by dec-412, stand.
