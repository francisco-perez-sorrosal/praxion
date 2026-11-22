---
name: step-loop
description: "Run a pipeline's implementer steps through the step-loop driver after the pre-mortem gate, given a task slug: relay each spawn request to the Agent tool and each return to the driver."
argument-hint: "<task-slug>"
allowed-tools: [Agent, "Bash(step_loop.py:*)", "Bash(python3 scripts/step_loop.py:*)"]
---

# Step Loop

Relay the step-loop driver's requests for the task slug `$ARGUMENTS`. The driver picks each step, writes its prompt, gates the return on ground truth, commits it and records it. Inside the loop you pass messages and decide nothing.

## Rules

- Pass the spawn request to the Agent tool unchanged.
- Call `record` when the agent's completion notification arrives. A return that carries a terminal marker, together with the progress the step record shows, is final even when the harness labels the notification possibly interim (the agent left background work running): run the `then` command at once instead of ending the turn to wait for another notification. Answer a return with no marker under such a note the same way, with `--marker none`. Running `record` is always safe: it refuses an agent that has not ended (`agent-running`) or a gate run still inside its bound (`gate-running`) and leaves the request pending. After `agent-running`, wait for the agent's notification; after `gate-running`, run the same `record` again at once, since no notification comes for a gate run. `next` answers `gate-running` too while the checkpoint's runs are inside their bound: run the same `next` again at once.
- Relay to `record` the request id, the agent id and the marker you saw.
- Never edit the rendered prompt.
- Never read the rendered prompt.
- Never compose an implementer prompt.
- Never commit.
- Never copy a return's `Follow-ups:` line into the follow-up record: the driver copies it when it records the return.
- Never edit an `Attempts:` line.
- Never stop a running `record`, nor a running `next` once every step is done (TaskStop on its shell included): `record` owns the gate's detached test runs and that `next` the checkpoint's, so stopping either kills its runs: a stopped `record` leaves the next `record` reading the attempt as a mismatch (observed 2026-11-01), and a stopped `next` leaves the checkpoint's runs to start again. Run each in the foreground with the 600000 ms timeout, which moves it to the background by itself on a timeout, and answer the stop guard by saying the call is in flight.
- Never wait on a record with `while pgrep -f "<command>"; do sleep 5; done`: `pgrep -f` matches the waiting shell's own command line, so the loop never ends (observed 2026-10-29). Wait on the PID (`kill -0 <pid>`), bracket one character of the pattern (`pgrep -f "[s]tep_loop.py record"`), or use a monitor with an until-loop, and stop every wait loop once its record returns.
- Keep one request in flight: spawn the next only after `record` has returned it.

## Procedure

1. From the pipeline's worktree root run `step_loop.py next $ARGUMENTS`. In the Praxion checkout run `python3 scripts/step_loop.py next $ARGUMENTS` instead. After this call run only the commands the driver prints: `then` and `stop.resume`. When the pipeline's worktree branched from a branch the default branch has not absorbed, give `--base-ref <the pipeline's Base commit>` on this first call only: every command the driver prints repeats the location options you gave, so running each as printed keeps the base. The driver reads declared files against the merge-base with the default branch, so the parent branch's commits make unstarted steps read as in flight. The loop's base is the last commit before its first step, which is the Base commit only while nothing was committed after it: when the orchestrator committed the design or a test amendment since, give the commit before the first step, or steps whose declared files those commits touched read as already started. Record that choice in the checkpoint digest.
2. Act on the exit code and `outcome`:

   | Exit | `outcome` | Do |
   |---|---|---|
   | 0 | `spawn` | Call the Agent tool with `request.agent_call` exactly as printed. When the completion notification arrives, run `then` with `<agentId>` and the marker filled in, and act on that envelope the same way. |
   | 0 | `complete` | Leave the loop and go to the pre-verification checkpoint. The driver has already run, whole and green, every pocket a step's gate deferred. |
   | 2 | `needs-human` | A `stop.cause` of `checkpoint-due` means every step is done and pockets wait for the checkpoint: run `stop.resume` at once; that `next` runs the checkpoint. A `stop.cause` of `checkpoint-red` means a pocket that steps deferred failed its whole run: show the user the stop, the steps it names and `stop.handoff`, and stop; once the remedy is committed, run `stop.resume`. A `stop.cause` of `not-driven` means the plan assigns that step outside the loop: run it the normal way; before committing its files, run their derived scope (`resolve_test_scope.py --changed <its files> \| sh -e`), since no loop gate runs on a step the loop does not drive; in its results block count each red test a later step's `Read-only:` field lists as `pending=`, not `fail=`, or the driver reads the step as red and stops `not-driven` on it again; tick its progress line, tell the user in one line, then run `stop.resume`. For any other cause show the user the stop and `stop.handoff`, and stop; the hand recoveries for the common stops are in [stop recoveries](references/stop-recoveries.md). |
   | 3 | `budget-exhausted` | The allowance is used (see the [spawn budget](../software-planning/references/coordination-details.md#spawn-budget)): show the user the stop as a re-tier signal, and stop. Never skip the verifier. If the user keeps the plan, the orchestrator runs the remaining steps outside the loop: spawn the agent, run each derived scope by hand and unbounded, commit by pathspec, note it in each step block and in the checkpoint digest. Moving a step out frees no budget for the steps that stay in (observed 2026-10-31). Amend a plan block only at a stop, since `record` issues the next request in the same call; before a run starts, put the id-citation pre-check in every driven step's `Done when`, because one refused commit costs an attempt. |
   | 4 | `error` | Fix your call as `error.message` says. Never edit pipeline files to get past it. |
   | 1 | `error` | Report it to the user and do not retry. |

   A step with a `Check:` runs its check and the pockets its change reaches by name; a pocket the test scope widens to its whole suite is left for the checkpoint (a `Deferred:` line in its block), which the driver runs before `complete`. When a stop or `budget-exhausted` carries `stop.waiting`, those pockets have not run whole since the steps it names: run each pocket's whole suite before the verifier.
3. The marker is the terminal marker on the last line of the agent's final message, lowercase and without brackets: `complete`, `blocked`, `conflict` or `partial`, or `none` when the message carries no marker.
4. If the Agent call fails before any agent starts, run the `then` command with `--not-started "<the error>"` in place of `--agent-id` and `--marker`. That record takes the request back and issues none: it prints the outcome `withdrawn` (exit 0), whose `then` is the `next` call that continues the loop. Between the two no request is out, so that is the moment to amend a plan block; left as it is, the plan gets the same attempt issued again.
5. Run every `record` and `next` with the Bash timeout at 600000 ms: a `next` once every step is done runs the checkpoint and waits for its runs as long as a `record` waits for a gate's. If one is cut off anyway, run the same command again: it resumes where it stopped.
6. If the session that made the Agent call ended before the agent returned (a restart), the agent can no longer end and `record` refuses it as running. Run the `then` command with the agent id the observation log or the transcript store gives, `--marker none`, and `--session-exited`: the driver takes the transcript back as it stands and gates or stops on what it shows.
