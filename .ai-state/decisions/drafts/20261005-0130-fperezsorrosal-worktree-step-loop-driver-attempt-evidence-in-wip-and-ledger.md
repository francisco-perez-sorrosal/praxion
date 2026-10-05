---
id: dec-draft-61d28fbc
title: Attempt evidence — the WIP Attempts line names the driver's request, the ledger records every agent return with its request, step digest and turns, and an outstanding attempt reads in-flight
status: proposed
category: behavioral
date: 2026-10-05
summary: The Attempts grammar gains an optional request=<id> token written ahead by the driver; parse_attempts with the ledger's recorded request ids yields OutstandingAttempt, which the verdict policy reads as in-flight instead of attempts-exhausted; the ledger gains optional request, step_digest, turns and max_turns plus the stop reasons partial and conflict; a plan revision opens a new attempt series keyed by the step digest; reconcile() gains assume_recorded so the driver's gate verdict equals the post-record verdict.
tags: [attempt-cap, iteration-ledger, reconciler, wip, step-loop, in-flight]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - scripts/_loop_fields.py
  - scripts/_step_verdict.py
  - scripts/reconcile_pipeline_state.py
  - scripts/iteration_ledger.py
  - skills/software-planning/references/document-templates.md
affected_reqs: [REQ-08, REQ-09, REQ-10, REQ-11, REQ-12, REQ-18, REQ-19, REQ-21, REQ-31, REQ-37]
supersedes_in_part: [dec-427, dec-426]
dissent: []
---

## Context

A write-ahead `count=2` makes today's reconciler read `attempts-exhausted` while attempt 2 is still running. The cap rule fires on any count at the cap, and the reconciler cannot tell a running capped attempt from an ended one. The ledger records only the reconciler's verdict and the stop reasons `completed`, `turn-cap`, `blocked` and `no-marker`. So it cannot say which request a record answers, which plan revision the attempt worked from, or how many turns it took. `[PARTIAL]` and `[CONFLICT]` returns are folded into `no-marker`.

## Decision

1. **Grammar.** `- Attempts: Step <id> count=<n>[ request=<id>][ [BLOCKED] replan: <text>]`. Normative in the `_loop_fields.py` docstring, rendered by one function there. Only the step-loop driver writes `request=`.
2. **One fact, one place.** WIP records what started; the ledger records what ended. `parse_attempts(wip, recorded_requests)` returns `OutstandingAttempt(count, request)` when the named request has no ledger record, else `Attempt`. A line without the token is always `Attempt`, so WIPs written without the driver read exactly as today.
3. **Verdict.** In `_step_verdict.py`, an outstanding attempt on a step not verified complete reads `in-flight`, with evidence naming the request and the underlying verdict. The cap rule applies only to ended attempts.
4. **Reconciler.** It reads the task ledger's request ids. `reconcile(..., assume_recorded=frozenset())` returns the verdict as it will read once those requests are recorded. The driver's gate calls it, so the ledger and the gate agree. `outcome_source: run` marks a check decided by the driver's own `Result:` line (`by=step-loop`). `--json` prints the verdict array in every case, with unnamed `Attempts:` lines on stderr in both modes (exit 2 kept).
5. **Ledger.** One record per agent return, of any kind. Optional keys `request`, `step_digest`, `turns` and `max_turns`; `STOP_REASONS` gains `partial` and `conflict`; `v` stays 1, because the reader already tolerates growth.
6. **Series.** A step's current series is its ledger records whose `step_digest` equals the plan block's current digest. A revision opens a fresh series, written as `count=1 request=s<id>-p<k>-a1-implement`, and reverting the text restores the old series.

The architectural test does not apply: the reconciler, the grammar module, the verdict module and the ledger all exist already, and no responsibility moves between them. The reconciler gains an input.

## Considered Options

### Option 1 — The driver holds the in-flight distinction privately
- **Cons:** the reconciler and `/resume-pipeline` still misread a running attempt; a second truth; a private state file.

### Option 2 — A rewritable in-flight flag on the WIP line
- **Cons:** the same fact in two places (the flag and the ledger); a crash between the rewrite and the append leaves them disagreeing.

### Option 3 — Started in WIP, ended in the ledger (chosen)
- **Pros:** no flag to rewrite; legacy WIPs unaffected by construction.
- **Cons:** the reconciler now reads the ledger.

## Consequences

**Positive:** REQ-09 and REQ-11 hold mechanically, REQ-18 by construction, and REQ-37 because no legacy line carries the token. `/resume-pipeline` sees `in-flight` and is told, by a two-line note, that a step with an outstanding step-loop request belongs to `step_loop.py next`.

**Negative:** a step exhausted outside the loop (a legacy line) reopens only when its line is removed, because no digest records its revision.

## Prior Decision

From dec-427:

- **Clause 1:** the grammar gains the optional request token.
- **Clause 5:** the cap precedence now applies only to ended attempts; an outstanding driver attempt reads `in-flight`.
- **Clause 6:** `outcome_source: run` is now used, as that clause reserved.

From dec-426, clause 2: the record shape grows four optional keys and two stop reasons, and records cover every agent return the driver processes.

All other clauses stand.
