---
id: dec-433
draft_id: dec-draft-4629985f
title: A synchronous PreToolUse hook reminds a capped subagent at 60 and 80 percent of its declared maxTurns, counting distinct requests in its own transcript
status: accepted
category: architectural
date: 2026-10-05
summary: New hooks/remind_turn_budget.py registered under PreToolUse with matcher "" emits one additionalContext line per agent and threshold, reading the cap from the agent definition by agent_type and the turn count from the agent's own transcript through the shared hooks/_agent_transcript.py; silent for the main session, uncapped agents and every error.
tags: [hook, pretooluse, turn-budget, maxturns, implementer, additionalcontext, fail-open]
made_by: agent
agent_type: systems-architect
branch: worktree-step-loop-driver
pipeline_tier: full
affected_files:
  - hooks/remind_turn_budget.py
  - hooks/_agent_transcript.py
  - hooks/hooks.json
affected_reqs: [REQ-32, REQ-33]
dissent: []
---

## Context

Implementers cap out at their declared `maxTurns` (100) with nothing on disk to gate. The harness gives no per-spawn turn cap and no mid-run signal. The researcher verified against the raw hooks reference, and with a live probe on 2.1.289, that a PreToolUse hook firing inside a subagent:

- receives `agent_id` and `agent_type` (`praxion:<name>`);
- carries the parent's `transcript_path`, from which the agent's own transcript derives as `<dirname>/<session_id>/subagents/agent-<agent_id>.jsonl`;
- has `hookSpecificOutput.additionalContext` delivered to the subagent;
- does not receive `maxTurns` in the payload.

## Decision

Add `hooks/remind_turn_budget.py`, registered in `hooks/hooks.json` under `PreToolUse` with matcher `""`, synchronous, timeout 5, and the same `2>/dev/null` discipline as its siblings. It is modelled on `hooks/remind_task_brief.py`: `additionalContext` only, exit 0 on every path, kill switch `PRAXION_DISABLE_TURN_BUDGET_REMINDER`.

- No `agent_id` → exit at once (main session).
- The cap is read from the agent definition: `praxion:<name>` → the plugin's `agents/<name>.md`; a bare name → the project's or the user's `.claude/agents/<name>.md`. No declared cap → silent.
- Turns are the distinct `requestId`s in the agent's own transcript, counted through the shared `hooks/_agent_transcript.py`, the same counter the driver records.
- Thresholds are 60 and 80 percent (`used*100 >= cap*t`). Only the highest crossed threshold is emitted, and the lower one is consumed with it.
- Once per agent and threshold is enforced by an `O_CREAT|O_EXCL` marker file under `<tempdir>/praxion-turn-budget/<session_id>/`.
- The texts follow PC-6 and are held as constants. A test pins the 80 percent implementer sentence to the agent definition's clause.

## Considered Options

### Option 1 — PreToolUse reminder from the transcript (chosen)
- **Pros:** fires while the agent can still stop committable; a confirmed payload; one counter shared with the driver.
- **Cons:** a process start on every tool call in every session; transcript writes may lag by a request.

### Option 2 — SubagentStop block hook forcing a committable stop
- **Cons:** it keeps the same agent running on its remaining turns, which is not the fresh-attempt model; the 8-continuation cap applies.

### Option 3 — Static `<finish>` ordering only
- **Pros:** zero runtime cost.
- **Cons:** no trigger at the moment it pays off. It stays as the fallback.

## Consequences

**Positive:** the 80 percent rule in the implementer definition gets a trigger instead of relying on the agent's own count.

**Negative:** this is the first synchronous hook on every tool call. Latency is bounded by FC-05 (0.2 s main path) and FC-06 (0.3 s subagent path). A POSIX `sh` pre-filter that skips Python when the payload names no `agent_id` is the held-back optimisation. A resumed agent's count is cumulative while the harness may reset its cap; the driver never resumes, so this is accepted.

## Disconfirmation

- **Falsifier:** driven implementers that crossed 80 percent still return with no `Result:` line and no committable tree at the same rate as before (from the ledger's `turns` and stop reasons over the next three pipelines), or FC-05/FC-06 readings exceed their bounds.
- **Steelmanned runner-up:** no hook at all. The rendered prompt's `<finish>` block already orders the work so that a cap leaves a committable state, and the driver's `turn-cap` stop reason feeds the next attempt's prompt. That costs nothing per tool call in every session across every managed project, which a per-call hook cannot claim.
- **Reversal trigger:** if FC-05 or FC-06 fails on the measuring machine, or the cap-out rate does not move with the reminder live, retire the hook in favour of the static ordering (or ship the `sh` pre-filter first, if latency is the only failure).
