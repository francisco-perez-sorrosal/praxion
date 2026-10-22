---
id: dec-472
draft_id: dec-draft-4502a925
title: "status --json reports each step's attempt cap and the orientation reads it; the mirrored constant is retired"
status: accepted
category: behavioral
date: 2026-10-22
summary: "Each status row gains attempt_cap (2, or a goal step's iteration budget); the post-compaction orientation renders attempts against it and drops its copy of ATTEMPT_CAP and the parity test"
tags: [step-loop, orientation, status]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/_step_loop_cli.py
  - hooks/inject_compaction_orientation.py
affected_reqs: [REQ-15]
supersedes_in_part: [dec-464]
---

# status --json reports each step's attempt cap and the orientation reads it; the mirrored constant is retired

## Context

td-481. `status --json` carried no per-step cap, so the orientation hook mirrored the driver's cap under a parity test, and a goal step's attempts rendered against 2 rather than its budget.

## Decision

Each `steps[]` row gains `attempt_cap` from the same per-step bound the driver uses. The hook renders attempts against it, and the count alone when the key is absent (an older driver). The mirror and its parity test are deleted.

## Considered Options

### Emit the cap per step (chosen)

### Keep the mirror and add a goal-budget mirror

Rejected: two copies to drift instead of one.

## Consequences

- Positive: a goal step renders against its own budget; a cap change needs no hook edit.
- Negative: none beyond an additive key.

## Prior Decision

dec-464 decision 3 mirrored the cap in the hook as a known consequence and named this follow-up. This decision narrows that clause; the rest of dec-464 stands.
