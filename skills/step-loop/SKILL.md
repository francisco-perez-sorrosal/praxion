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
- Call `record` when the agent's completion notification arrives. A return that carries a terminal marker, together with the progress the step record shows, is final even when the harness labels the notification possibly interim (the agent left background work running): run the `then` command at once instead of ending the turn to wait for another notification. Answer a return with no marker under such a note the same way, with `--marker none`. Running `record` is always safe: it refuses an agent that has not ended (`agent-running`) or a gate run still inside its bound (`gate-running`) and leaves the request pending. After `agent-running`, wait for the agent's notification; after `gate-running`, run the same `record` again at once, since no notification comes for a gate run.
- Relay to `record` the request id, the agent id and the marker you saw.
- Never edit the rendered prompt.
- Never read the rendered prompt.
- Never compose an implementer prompt.
- Never commit.
- Never edit an `Attempts:` line.
- Never stop a running `record` (TaskStop on its shell included): it owns the gate's detached test runs, so stopping it kills them and the next `record` reads the attempt as a mismatch (observed 2026-11-01). Run it in the foreground with the 600000 ms timeout, which moves it to the background by itself on a timeout, and answer the stop guard by saying the record is in flight.
- Never wait on a record with `while pgrep -f "<command>"; do sleep 5; done`: `pgrep -f` matches the waiting shell's own command line, so the loop never ends (observed 2026-10-29). Wait on the PID (`kill -0 <pid>`), bracket one character of the pattern (`pgrep -f "[s]tep_loop.py record"`), or use a monitor with an until-loop, and stop every wait loop once its record returns.
- Keep one request in flight: spawn the next only after `record` has returned it.

## Procedure

1. From the pipeline's worktree root run `step_loop.py next $ARGUMENTS`. In the Praxion checkout run `python3 scripts/step_loop.py next $ARGUMENTS` instead. After this call run only the commands the driver prints: `then` and `stop.resume`. When the pipeline's worktree branched from a branch the default branch has not absorbed, add `--base-ref <the pipeline's Base commit>` to every `next`, `record` and `status` call (the printed `then` omits it): the driver reads declared files against the merge-base with the default branch, so the parent branch's commits make unstarted steps read as in flight. Record that choice in the checkpoint digest.
2. Act on the exit code and `outcome`:

   | Exit | `outcome` | Do |
   |---|---|---|
   | 0 | `spawn` | Call the Agent tool with `request.agent_call` exactly as printed. When the completion notification arrives, run `then` with `<agentId>` and the marker filled in, and act on that envelope the same way. |
   | 0 | `complete` | Leave the loop and go to the pre-verification checkpoint. |
   | 2 | `needs-human` | A `stop.cause` of `not-driven` means the plan assigns that step outside the loop: run it the normal way, tick its progress line, tell the user in one line, then run `stop.resume`. For any other cause show the user the stop and `stop.handoff`, and stop; the hand recoveries for the common stops are in [stop recoveries](references/stop-recoveries.md). |
   | 3 | `budget-exhausted` | The allowance is used (see the [spawn budget](../software-planning/references/coordination-details.md#spawn-budget)): show the user the stop as a re-tier signal, and stop. Never skip the verifier. If the user keeps the plan, the orchestrator runs the remaining steps outside the loop: spawn the agent, run each derived scope by hand and unbounded, commit by pathspec, note it in each step block and in the checkpoint digest. Moving a step out frees no budget for the steps that stay in (observed 2026-10-31). Amend a plan block only at a stop, since `record` issues the next request in the same call; before a run starts, put the id-citation pre-check in every driven step's `Done when`, because one refused commit costs an attempt. |
   | 4 | `error` | Fix your call as `error.message` says. Never edit pipeline files to get past it. |
   | 1 | `error` | Report it to the user and do not retry. |

3. The marker is the terminal marker on the last line of the agent's final message, lowercase and without brackets: `complete`, `blocked`, `conflict` or `partial`, or `none` when the message carries no marker.
4. If the Agent call fails before any agent starts, run the `then` command with `--not-started "<the error>"` in place of `--agent-id` and `--marker`.
5. Run every `record` with the Bash timeout at 600000 ms. If one is cut off anyway, run the same command again: it resumes where it stopped.
6. If the session that made the Agent call ended before the agent returned (a restart), the agent can no longer end and `record` refuses it as running. Run the `then` command with the agent id the observation log or the transcript store gives, `--marker none`, and `--session-exited`: the driver takes the transcript back as it stands and gates or stops on what it shows.
