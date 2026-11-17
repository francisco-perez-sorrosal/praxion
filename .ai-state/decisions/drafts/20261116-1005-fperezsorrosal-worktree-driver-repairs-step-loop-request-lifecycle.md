---
id: dec-draft-edd3724f
title: The step-loop request lifecycle is read as one sum type, and a record in flight holds an OS lock
status: proposed
category: architectural
date: 2026-11-16
summary: The driver reads a step's outstanding request against the plan as one sum type; a withdrawal takes the request back and issues nothing (outcome withdrawn); a misplaced next stops; a record call holds an flock that the Stop guard and a second record probe, in a new leaf module _step_loop_recording.py.
tags: [step-loop, driver, request-lifecycle, stop-guard, concurrency]
made_by: agent
agent_type: systems-architect
branch: worktree-driver-repairs
pipeline_tier: full
affected_files:
  - scripts/_step_loop_action.py
  - scripts/_step_loop_record.py
  - scripts/_step_loop_cli.py
  - scripts/_step_loop_outstanding.py
  - scripts/_step_loop_recording.py
  - scripts/step_loop.py
  - skills/step-loop/SKILL.md
  - skills/step-loop/references/stop-recoveries.md
affected_reqs: [REQ-01, REQ-02, REQ-03, REQ-04, REQ-19, REQ-20, REQ-21, REQ-26, REQ-42]
---

## Context

A request the driver issued and no agent started could not be taken back: `record --not-started` restored the attempts line and then issued the same request at once, so the loop never held a moment with no request out, the only moment a plan block may be amended. A step inserted ahead of an outstanding request was issued beside it, leaving two requests out and every later call stopped. Separately, a `record` call outlives the Bash tool's 600-second ceiling (its commit runs the repository's hooks under a 600-second bound after a 480-second gate wait), and the Stop guard, seeing an agent ended and unrecorded, demanded a second `record` that would race the first on the ledger.

## Decision

1. The outstanding request is read once, in `_step_loop_action.py`, as `NoneOut | Several | Malformed | Miscounted | Current | Superseded`. `next` reissues only `Current`; `Superseded` (another step now comes first, or the step's series moved on) stops under `request-outstanding`, naming the request and the record call that takes it back; `Miscounted` (the id's attempt differs from the line's count) stops under `attempts-disagree`; `Several` and `Malformed` keep `loop-state-defect`.
2. A withdrawal finds its request from the attempts reading, not from the plan's next action, and prints a new outcome `withdrawn` (exit 0) with no `request` and a `then` naming `next`.
3. `record` holds `fcntl.flock` on `gate/<request>/record.lock` for its whole call, and removes that file as it lets go (only while it is still the file the call holds; a call that takes the lock keeps it only while the file is still the one at the path), so a refused or finished `record` leaves no file behind: three standing tests assert that a refused record changes nothing. The task is read again under the lock. A second `record` of the request exits `record-running` and writes nothing; the Stop guard's probe (through `_step_loop_outstanding.py`) lets a stop through while the lock is held. The kernel drops the lock when the process dies. The lock lives in a new stdlib-only leaf module, `_step_loop_recording.py`.

## Considered Options

### Reissue the outstanding request whatever the plan says

Fewer new causes. Rejected: it runs a step the person just put behind another, and the record lands the work out of the order asked for.

### Refuse a misplaced `next` with an error envelope

Writes nothing. Rejected: the person who must choose between withdrawing and recording gets no handoff.

### A pid marker file for the record in flight

Portable. Rejected: a pid can be reused and a marker survives a killed process, so a staleness rule of our own would be needed; the OS lock has exactly the lifetime of the holder.

### Shorten the record call under 600 seconds

Addresses the tool's limit directly. Rejected for this change: cutting the commit mid-hook leaves an index lock, and the spec asks for visibility of a record in flight, not a shorter call.

## Consequences

Positive: no documented call sequence leaves two requests out; a plan can be amended between a withdrawal and `next` with no hand edit; the guard never demands a running record; a dead record leaves nothing to clean.

Negative: four new stop causes and one new outcome and error code in the relay's vocabulary; three standing unit tests that pinned the old withdrawal re-pin under answered Spec Questions; a block revised while its own series' first request is out still reissues against the revised block (the attempts line carries no step digest).

## Disconfirmation

- **Falsifier**: a documented sequence of `next`, `record` and `status` calls after which `WIP.md` names two outstanding requests, or the Stop guard holds a stop while a `record` of the same request is running.
- **Steelmanned runner-up**: reissue the outstanding request and key the record on its own step, so a plan change at the wrong moment costs nothing at all; the work lands under its own unchanged block, and the inserted step runs next. It is simpler for the relay (no new cause) and loses nothing when the inserted step does not depend on the outstanding one.
- **Reversal trigger**: relays in practice meet `request-outstanding` mostly for insertions whose new step is independent of the outstanding one, so the stop costs a human turn for nothing; then switch to the reissue with an `outstanding-out-of-order` warning.
