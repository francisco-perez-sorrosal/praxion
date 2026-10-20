---
id: dec-draft-dc3dfb3d
title: During a step loop the post-compaction orientation reports the driver's position and the outstanding request's record command, read from the driver's status
status: proposed
category: architectural
date: 2026-10-20
summary: "Narrows dec-387's role-neutral clause. When the newest task is under the step-loop driver, hooks/inject_compaction_orientation.py runs the driver's read-only status --json from its own plugin tree and renders a two-line digest (the selected step, its state and attempts, iterations, a stop's cause, and the outstanding request with its record command, placeholders kept) in place of WIP.md's current-step and next-action lines; on a driver read failure it says the position could not be read and names status. status --json gains two additive keys, selected_step and then. Outside a step loop the block is byte-identical to today's."
tags: [step-loop, hooks, compaction, orientation, td-466]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-hardening
pipeline_tier: standard
affected_files:
  - hooks/inject_compaction_orientation.py
  - scripts/_step_loop_cli.py
affected_reqs: [REQ-07, REQ-08, REQ-09]
supersedes: null
superseded_by: null
re_affirms: null
re_affirmed_by: null
retired_by: null
supersedes_in_part: dec-387
superseded_in_part_by: null
dissent: null
---

## Context

After a compaction during a 49-step loop the orientation reported "Step 1 of 49" with 33 steps ticked: it reads `WIP.md`'s hand-maintained `## Current Step`, which the step-loop driver never updates (td-466). The driver holds the true position and answers it read-only through `status`. dec-387 fixed the orientation block as role-neutral, naming no orchestration action, so one text serves a main and a subagent window; td-466 asks the block to name the outstanding request's record command, which is an orchestration action. The specification phase settled whether the orientation may carry that command by accepting it, attributed to the driver, under the existing withheld-word filter.

Activation: no — the option set was fixed by the ledger row and the spec's round-0 answer; the remaining choice (who owns position) is recorded below.

## Decision

1. Position moves from `WIP.md` to the driver for driver-run tasks. A task is under the driver when its `WIP.md` names a request on an `Attempts:` line or it has an `ITERATION_LEDGER.jsonl` (a file test, so a non-loop pipeline pays nothing).
2. In that mode the hook runs `python3 <plugin root>/scripts/step_loop.py status <slug> --json --worktree-root <root>` (6 s subprocess timeout, stdout parsed whatever the exit code), and renders at most two lines: the selected step with its state, attempts against the driver's attempt cap (see 3) and iterations used, or the loop complete, or the stop's cause; and, when a request is outstanding, its id and the driver's record command with `<agentId>` and the marker placeholders kept. `WIP.md`'s current-step and next-action lines are not emitted. The handoff pointer stays first among the pointers; the 1,024-byte cap and exit-0 contract stand.
3. `status --json` adds `selected_step` and `then` (null when not applicable), so the hook never re-derives position or retypes the command. One value is mirrored rather than read: `status --json` carries no per-step attempt cap, so the hook keeps its own copy of the driver's `ATTEMPT_CAP`, held equal to it by a parity test. The known consequence is that a goal step, whose cap is its own iteration budget, renders its attempts against that copy, not its budget. The follow-up is for `status_object` to emit each step's cap, which the hook then reads in place of the copy.
4. If the driver cannot be read, the block says so and names the `status` command; it never falls back to `WIP.md`'s position.
5. The withheld-word filter (spawn, commit, proceed to verification) applies to every rendered line; a line that trips it is replaced by its location form.

## Considered Options

### Read the driver's status (chosen)

Pros: one owner of position; the command comes from the driver. Cons: one subprocess per compaction in loop mode; the role-neutral clause narrows.

### Make the driver keep `## Current Step` current

Pros: fixes the source; every reader benefits. Cons: the driver writes `WIP.md` on every `record` (a second writer of a hand-kept section), and the hook would still not know the outstanding request's command.

### Re-derive position inside the hook

Pros: no subprocess. Cons: a second implementation of the driver's state machine.

## Consequences

- Positive: a resumed session is pointed at the step the driver will act on and at the command that takes back an outstanding agent.
- Negative: if a subagent's own compaction fires this hook (unverified; Claude Code documents `SubagentStart` separately), a running implementer could see the record command; running it is refused as `agent-running`, so the cost is a wasted call. `hooks/precompact_state.py` still snapshots `WIP.md`'s first lines into `PIPELINE_STATE.md`, which may carry the stale position; the digest's line names the driver as the position to trust (residual, recorded).

## Disconfirmation

- **Falsifier:** a compaction in loop mode whose block names `WIP.md`'s current step, or a block outside a loop that differs from today's by a byte, or a block over 1,024 bytes.
- **Steelmanned runner-up:** keeping `## Current Step` current from the driver fixes the defect at its source, for every reader at once (the precompact snapshot, a human opening `WIP.md`), with no new connection from a hook to the driver. It loses because the outstanding request's record command is not in `WIP.md` either, so the hook would still need the driver for the second half of td-466, and a driver that edits a hand-kept section creates a second writer of the same text.
- **Reversal trigger:** if `status` proves too slow for the hook's budget (more than one `Unavailable` line observed in a real loop), or if the precompact snapshot's stale position misleads a session, move position into a driver-maintained section of `WIP.md`.

## Prior Decision

dec-387 (partially superseded) fixed the post-compaction block as role-neutral, naming no orchestration action anywhere, so one text is correct in a main and a subagent window. What changes: in loop mode only, the block names the outstanding request's record command, attributed to the driver with its placeholders; the hook's own wording still carries no orchestration verb and the withheld-word filter still applies. The handoff-first pointer order, the byte cap, the exit-0 contract and the rest of dec-387 stand.
