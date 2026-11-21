---
id: dec-draft-3d2d9a77
title: Widened pockets wait for a checkpoint the step-loop driver runs before complete
status: proposed
category: architectural
date: 2026-11-21
summary: A driven step with a check skips every pocket the test scope widens, records a Deferred line, and a new checkpoint action runs each waiting pocket's whole suite once before complete; the waiting set is derived from the results file and the iteration ledger, never stored.
tags: [step-loop, gate, test-scope, checkpoint]
made_by: agent
agent_type: systems-architect
branch: worktree-per-step-gate
pipeline_tier: standard
affected_files:
  - scripts/_step_loop_checkpoint.py
  - scripts/_step_loop_record_gate.py
  - scripts/_step_loop_io.py
  - scripts/_step_loop_action.py
  - scripts/_step_loop_state.py
  - scripts/_step_loop_cli.py
  - scripts/step_loop.py
  - scripts/_step_schema.py
  - scripts/check_test_results_shape.py
  - skills/step-loop/SKILL.md
affected_reqs: [REQ-01, REQ-03, REQ-05, REQ-06, REQ-07, REQ-08, REQ-10, REQ-11, REQ-12, REQ-13, REQ-14]
---

## Context

Every driven step's gate ran each pocket the test scope selected, and a pocket the resolver widened ran its whole suite at every step that reached it (in this repository a runner-configuration change widens the root pocket, about half an hour). The resolver must not change: it never narrows. The driver keeps no private state; every call re-derives from the plan, `WIP.md`, the iteration ledger, `TEST_RESULTS.md` and git.

## Decision

1. The gate of a non-goal step with a readable `Check:` does not run a pocket the resolver answers with a full selection; it writes `Deferred: <root> (widened): whole suite waits for the checkpoint` in the step's block, before the `Result:` lines. Steps with no readable check and goal steps gate as before.
2. A new component, `scripts/_step_loop_checkpoint.py`, owns the deferral grammar, the derivation of the waiting pockets (`waiting_pockets`: committed deferrals since each pocket's last green checkpoint block) and the checkpoint run.
3. The pure action core gains a `Checkpoint` action when every step is done and a pocket waits. `run_next` runs it with the gate's detached run machinery: green prints `complete`, red stops `checkpoint-red` naming the waiting steps, unfinished answers `gate-running`.
4. The waiting set is derived, never stored; `status --json` and every stop envelope carry it only when non-empty. Checkpoint evidence is a step-free `## Checkpoint <root> at <head7>` block the shape checker accepts.

Behavioral clauses carried here (not architectural on their own): no plan-declared earlier checkpoint; a step without a check and a goal step keep today's gate.

## Considered Options

### Derived waiting set (chosen) vs a state file
A state file is a second writer whose write must be ordered against the commit; the derived set reuses the request-keyed replay the driver already has. Cost: a scan of the results file per call, and reliance on blocks being appended in time order.

### Checkpoint as an action (chosen) vs inside the last `record` vs left to the orchestrator
Inside the last `record` misses loops whose last step ran outside the loop and resumed sessions; leaving it to the orchestrator keeps the per-step cost saving but loses the meaning of `complete` and the per-pocket attribution.

## Consequences

Positive: a step with a check pays for its check and its narrow pockets only; each widened suite runs once per loop; `complete` still means every reached pocket passed whole. Negative: a defect in a widened pocket surfaces at the loop's end and is attributed to a set of steps, not one; `next` can now answer `gate-running`; a remedy must be committed for the checkpoint to run again.

## Disconfirmation

- **Falsifier:** red checkpoints that name three or more waiting steps occur in most loops that defer, and the person cannot tell from the stop which step broke the pocket; or the checkpoint's runs routinely outlast their pocket's bound where the per-step widened gate did not.
- **Steelmanned runner-up:** keep the gate as it is and leave widened pockets to the orchestrator's pre-verification checkpoint, which already runs every pocket whole. No new action, no new stop, no derivation; the saving per step is the same. It loses only the guarantee that `complete` means the reached pockets passed, and the attribution, both of which the orchestrator could reconstruct by hand.
- **Reversal trigger:** if the falsifier holds over two pipelines that defer, add a plan-declared checkpoint (additive) or retire the action in favour of the runner-up.
