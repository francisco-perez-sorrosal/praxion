---
id: dec-430
draft_id: dec-draft-5a49f9df
title: The light-review trigger is plan-local — the planner turns the brief's uncertainty flags and one-way doors into review force; the driver reads only review and tier H
status: accepted
category: behavioral
date: 2026-10-05
summary: The intra-step light review fires when a step carries review force or tier H and not review off; the task-wide Uncertainty Flag below 7 and one-way-door steps no longer auto-signal at step completion, because the planner marks the steps they bear on with review force at planning time, which makes the trigger deterministic, visible at the pre-mortem gate and derivable from the plan alone.
tags: [light-review, intra-step-review, planner, step-loop, trigger]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - skills/software-planning/references/intra-step-review.md
  - agents/implementation-planner.md
  - skills/software-planning/SKILL.md
  - rules/swe/swe-agent-coordination-protocol.md
  - scripts/_plan_steps.py
affected_reqs: [REQ-26, REQ-28]
dissent: []
---

## Context

The light-review trigger has three auto-signals. Two of them are not decidable by deterministic code:

- the brief's task-wide Uncertainty Flag below 7, which would mark every step of most Standard/Full pipelines;
- one-way doors, which the planner prompt says are "noted in the step description" and pattern-matched by the orchestrator.

In practice the orchestrator applied judgment, which reviewed 3 of 21 steps in the step-schema pipeline. The driver cannot apply judgment, and its iteration budget must be derivable from the plan.

## Decision

The trigger the driver (and a hand-run orchestrator) evaluates is per step:

- `review: off` → no review;
- `review: force` or `tier: H` → review.

The planner turns an uncertainty flag below 7 into `review: force` on the steps that bear on that signal, and marks a one-way-door step `review: force`. Four sites state the trigger, and all change in one step so that they agree when committed:

- `intra-step-review.md`'s trigger table;
- the planner prompt's risk-tag rows, with no net line growth;
- `skills/software-planning/SKILL.md`;
- the always-loaded pipeline-rules row in `rules/swe/swe-agent-coordination-protocol.md`, which reads "Step carrying `review: force` or `tier: H` (the planner maps Uncertainty Flag < 7 and one-way doors to `force`)", about +3 tokens.

Only the trigger-predicate reference lists signals; the other sites name the two tags and the mapping duty.

## Considered Options

### Option 1 — The driver reads the brief's flag and pattern-matches one-way doors
- **Cons:** every step is reviewed whenever any signal is below 7; a text pattern is not deterministic; the budget would depend on the brief.

### Option 2 — Plan-local trigger (chosen)
- **Pros:** deterministic; reviewable at the pre-mortem gate; reviews only where the risk lies; the iteration budget is derived from the plan alone.
- **Cons:** a planner that forgets the mapping silently drops a review the auto-signal used to add.

## Consequences

The pre-mortem gate is where a missing `review: force` is caught. Steps run outside the loop use the same per-step reading, so there is one trigger definition.
