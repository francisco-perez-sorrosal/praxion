---
id: dec-467
draft_id: dec-draft-db4e6884
title: "The step-loop gate runs each pocket detached under the pocket's own declared bound, keeps a cut-off run's evidence and feeds it to the next attempt"
status: accepted
category: architectural
date: 2026-10-22
summary: "Scope runs move into a new pocket-run module: detached, re-attachable across record calls, bounded per pocket (override, declared gate-timeout-seconds, default 540 s); a cut-off run is red, names its pocket and keeps every failure seen; the next attempt's prompt carries that evidence; green blocks summarise the selection"
tags: [step-loop, gate, test-selection, timeout, evidence]
made_by: agent
agent_type: systems-architect
branch: worktree-loop-gate-followups
pipeline_tier: full
affected_files:
  - scripts/_step_loop_pocket_runs.py
  - scripts/_step_loop_io.py
  - scripts/_step_loop_record.py
  - scripts/_step_loop_record_gate.py
  - scripts/_step_loop_gate.py
  - scripts/_step_loop_render.py
  - scripts/_step_loop_files.py
  - scripts/_step_loop_cli.py
  - eval/pyproject.toml
  - skills/step-loop/SKILL.md
affected_reqs: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-08]
supersedes_in_part: [dec-386]
superseded_in_part_by: [dec-475]
---

# The step-loop gate runs each pocket detached under the pocket's own declared bound, keeps a cut-off run's evidence and feeds it to the next attempt

## Context

td-463 and td-479. The gate ran every scope invocation under one 540 s bound (`RUN_TIMEOUT_SECONDS`). The eval pocket's whole suite takes 822 s, so an eval-pocket step whose own check passed failed on the clock; a timed-out run collapsed the whole merged scope to `Result: none (timed out)`, dropping the failures other pockets and the cut-off run itself had shown; and the next attempt's prompt carried only that line (Step 40 of lean-spawn-continuation used both attempts and a plan revision for one real red). The step-loop skill bounds each `record` call at 600 s and promises that a cut-off call, run again, resumes, so a run longer than one call can never finish if a re-run starts it over. Green blocks carried the whole derived-scope argv and exceeded the 1,024-byte shape ceiling.

## Decision

1. A new shell module, `scripts/_step_loop_pocket_runs.py`, owns scope runs: each invocation starts detached (its own session), output to `.ai-work/<slug>/gate/<request>/<n>.log`, a start stamp and an exit file written on completion. A re-run `record` re-attaches to the same request's runs; a finished run is read, never re-run.
2. Each pocket's bound comes from, in order, `PRAXION_STEP_LOOP_POCKET_TIMEOUTS`, the pocket's `[tool.praxion.step-loop] gate-timeout-seconds`, then 540 s. A malformed source is skipped with a warning; a bound always exists. The bound is enforced from the recorded start when a later `record` attaches, so a re-attach honours the original deadline; nothing kills a run between calls, so a hung run of an abandoned request lives until a `record` attaches (td-492). A kill first confirms the process group is the run's own launcher. The root pocket declares 1,500 s and the eval pocket 1,200 s.
3. `record` waits at most `PRAXION_STEP_LOOP_GATE_WAIT_SECONDS` per call (480 s by default; a non-finite value falls back to the default); a run still inside its bound past that raises the refusal `gate-running` (nothing written, request pending), the `agent-running` channel.
4. A run is a sum type (finished, cut off, not started). A cut-off run is red whatever it saw; pytest invocations the gate runs carry `-v -rfE` (a bare `-rf` drops `ERROR` lines when a pocket's config carries `-ra`), so failures seen before a cut are read from the log. Every pocket run keeps its counts and failures; the block's red lines are `Cut off:` and `Failed:`, and a red check's failures join the scope's in the bounded `Failed:` list, each named with its pocket.
5. The next attempt's prompt gains a `gate-evidence` slot read by the driver from the earlier attempt's driver block (bounded, newest kept, cut marker). The orchestrator writes nothing.
6. Green and red driver blocks replace the derived scope's `Command:` lines with one `Scope:` line per pocket run and one `Derived from:` line naming up to three files and a count; full argv is the first line of each run's log.

## Considered Options

### Option 1 -- declared per-pocket bound, detached re-attachable runs (chosen)

Pros: fits a pocket that legitimately takes longer; survives the 600 s record call; deterministic bound from a file. Cons: one more module and a per-request run directory.

### Option 2 -- a bound derived from recorded durations

Pros: no declaration. Cons: the bound depends on history, so the gate is not a function of the tree; a slow regression raises its own bound.

### Option 3 -- one larger global bound

Pros: one constant. Cons: 822 s cannot finish inside one 600 s record call, so a bigger constant alone never lets an eval step pass; it also slows every hung run's detection.

## Consequences

- Positive: an eval-pocket step passes on its counts; a cut-off run names its pocket and keeps its evidence; the next attempt starts from that evidence; green blocks fit the shape ceiling.
- Negative: `record` may need more than one call for a long scope (the skill's existing re-run rule covers it); a per-request run directory under `.ai-work/`; verbose pytest output in logs.
- The check command keeps today's in-process run and bound.

## Disconfirmation

- **Falsifier:** if a re-run `record` ever starts a pocket run that had already finished for the same request, or a cut-off run's gate reads green, the design is wrong.
- **Steelmanned runner-up:** run `record` itself in the background and let the orchestrator wait for its notification; no re-attach logic. Rejected because it changes the orchestrator's procedure for every step and moves the long wait into the main session's notification handling, while the re-attach keeps the skill's existing contract.
- **Reversal trigger:** if the harness raises the foreground Bash ceiling above the longest pocket's bound, the detached runs can collapse back into in-process runs with per-pocket bounds.

## Prior Decision

dec-386 fixed a green section as the command, one `Result:` line, the duration and topology lines. This decision narrows its "command" element for driver blocks: the derived scope is summarised per pocket and the argv moves to the run log, because the argv of a widened scope alone exceeds the section ceiling dec-386 set. The rest of dec-386 stands.
