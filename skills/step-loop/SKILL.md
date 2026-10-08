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
- Call `record` only after the agent's completion notification arrives.
- Relay to `record` the request id, the agent id and the marker you saw.
- Never edit the rendered prompt.
- Never read the rendered prompt.
- Never compose an implementer prompt.
- Never commit.
- Never edit an `Attempts:` line.
- Keep one request in flight: spawn the next only after `record` has returned it.

## Procedure

1. From the pipeline's worktree root run `step_loop.py next $ARGUMENTS`. In the Praxion checkout run `python3 scripts/step_loop.py next $ARGUMENTS` instead. After this call run only the commands the driver prints: `then` and `stop.resume`.
2. Act on the exit code and `outcome`:

   | Exit | `outcome` | Do |
   |---|---|---|
   | 0 | `spawn` | Call the Agent tool with `request.agent_call` exactly as printed. When the completion notification arrives, run `then` with `<agentId>` and the marker filled in, and act on that envelope the same way. |
   | 0 | `complete` | Leave the loop and go to the pre-verification checkpoint. |
   | 2 | `needs-human` | A `stop.cause` of `not-driven` means the plan assigns that step outside the loop: run it the normal way, tick its progress line, tell the user in one line, then run `stop.resume`. For any other cause show the user the stop and `stop.handoff`, and stop. |
   | 3 | `budget-exhausted` | The allowance is used (see the [spawn budget](../software-planning/references/coordination-details.md#spawn-budget)): show the user the stop as a re-tier signal, and stop. Never skip the verifier. |
   | 4 | `error` | Fix your call as `error.message` says. Never edit pipeline files to get past it. |
   | 1 | `error` | Report it to the user and do not retry. |

3. The marker is the terminal marker on the last line of the agent's final message, lowercase and without brackets: `complete`, `blocked`, `conflict` or `partial`, or `none` when the message carries no marker.
4. If the Agent call fails before any agent starts, run the `then` command with `--not-started "<the error>"` in place of `--agent-id` and `--marker`.
5. Run every `record` with the Bash timeout at 600000 ms. If one is cut off anyway, run the same command again: it resumes where it stopped.
