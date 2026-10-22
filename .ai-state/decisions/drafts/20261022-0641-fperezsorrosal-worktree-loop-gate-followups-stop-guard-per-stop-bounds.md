---
id: dec-draft-60ae24db
title: "The step-loop Stop guard bounds its per-Stop transcript reading by count, bytes and its own deadline, and lets the stop through at a bound"
status: proposed
category: behavioral
date: 2026-10-22
summary: "The outstanding-request probe examines transcripts newest first, at most 64 files and 16 MiB, before a 5 s deadline; reaching a bound before a hold lets the stop through"
tags: [step-loop, hooks, stop-guard]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/_step_loop_outstanding.py
  - hooks/guard_step_loop_stop.py
  - scripts/test_loop_outstanding.py
affected_reqs: [REQ-12, REQ-13, REQ-14]
supersedes_in_part: [dec-465]
---

# The step-loop Stop guard bounds its per-Stop transcript reading by count, bytes and its own deadline, and lets the stop through at a bound

## Context

td-480. A stale task with an unrecorded request widened the guard's window to every transcript of the session, with no deadline of its own under the 10 s registration. No test pinned the 64-character slug from the accepted side.

## Decision

Transcripts are examined newest first; at most 64 files, at most 16 MiB in total, before a 5 s monotonic deadline from the probe's start. A bound reached before a hold returns not-held, so the stop proceeds (today's behaviour without the guard). The outside-a-loop path, the hold message and the fail-open contract are unchanged. An inner test pins a 64-character task name as read and a 65-character one as skipped.

## Considered Options

### Bounds plus newest-first (chosen)

### Ignore requests older than a fixed age

Rejected: an age is a guess about sessions; the bounds cap cost directly.

## Consequences

- Positive: a Stop's cost is bounded whatever the task directory holds.
- Negative: an ended agent beyond the bounds is not held; the orchestrator-side rule of the step-loop skill still applies.

## Prior Decision

dec-465 decision 3 read every transcript of the session modified since the oldest outstanding request's prompt. This decision narrows that clause with the three bounds and the newest-first order; the rest of dec-465 stands.
