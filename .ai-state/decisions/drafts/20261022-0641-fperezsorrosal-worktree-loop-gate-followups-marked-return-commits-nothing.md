---
id: dec-draft-6250d858
title: "A [CONFLICT] or [BLOCKED] return commits nothing and stops; status and next read one state"
status: proposed
category: behavioral
date: 2026-10-22
summary: "record never commits or ticks a step whose return carries [CONFLICT] or [BLOCKED], keeps every edit, records a null commit and stops naming the uncommitted files; status's per-step verdict comes from the same series state next acts on"
tags: [step-loop, markers, status]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/_step_loop_record.py
  - scripts/_step_loop_state.py
  - scripts/_step_loop_action.py
  - scripts/_step_loop_cli.py
  - scripts/_step_loop_render.py
affected_reqs: [REQ-09, REQ-10, REQ-11]
---

# A [CONFLICT] or [BLOCKED] return commits nothing and stops; status and next read one state

## Context

td-478. On a [CONFLICT] return whose check passed, the driver committed the step's declared files and ticked the step, leaving HEAD inconsistent (9ac62fd6 carried a new signature without its call site). The series state already read the step as marked, while `status` showed the reconciler's word, so after a plan revision `status` said verified-complete while `next` re-issued the step.

## Decision

`record` gates the commit and the tick on the resolved marker: [CONFLICT] or [BLOCKED] never commits or ticks, every edit stays in the tree, the ledger record carries a null commit, and the loop stops naming the step, the marker and each uncommitted file. The step stays open until its block is revised; the revision opens a fresh series at attempt 1 whose prompt names the kept edits. The conflicting attempt counts in its series and in the loop's iterations. `status`'s per-step `verdict` is derived by the same function from the same series state `next` acts on. [BLOCKED] is included by the user's default answer to the spec question: the state already reads both markers alike. [PARTIAL] keeps the check-decides rule.

## Considered Options

### Marker gates the commit; one state for status and next (chosen)

### Keep committing; make the state read a committed marked step as verified

Rejected: HEAD would still hold a scope its agent called incomplete.

### Restore the attempt's edits on a marked return

Rejected: silently discards work the next series needs.

## Consequences

- Positive: HEAD never holds an incomplete scope; one derivation of a step's state.
- Negative: edits linger in the tree while the loop is stopped; the stop names them.
