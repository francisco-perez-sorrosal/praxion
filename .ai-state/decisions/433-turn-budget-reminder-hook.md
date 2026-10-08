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

## Status note (user, 2026-10-07)

Accepted as the design decision, not yet in force. The user ruled on 2026-10-07 that this record stands as the decision the follow-up pipeline implements, and that it is not in force until the component ships within its bounds; a finalized record cannot return to `proposed`, so the status stays `accepted` and this note carries the condition. The finalize at merge promoted the record with the pipeline's other drafts, but the component it decides (`hooks/remind_turn_budget.py`, its registration and its live probe) moved to the follow-up pipeline with the split, so no reading of its latency or of its effect on cap-outs exists yet. The follow-up pipeline's hook step builds it against this record as written, its probe step measures the two latency bounds the spec carries for it (0.2 s on a main-session payload, 0.3 s on a subagent payload whose transcript holds 100 requests), and that pipeline's orchestrator records the readings here and re-affirms the decision when both bounds hold, or applies the reversal trigger above (retire in favour of the static finish ordering, or ship the `sh` pre-filter first when latency is the only failure). Until then the rendered prompt's `<finish>` block and the driver's `turn-cap` stop reason are the only guard against a cap-out.

## Status note (orchestrator, 2026-10-08) — in force

Re-affirmed with measurements by the `step-loop-dogfood` pipeline (Claude Code 2.1.293). The hook
`hooks/remind_turn_budget.py` is built as this record decides and registered in `hooks/hooks.json`
(one synchronous PreToolUse group, matcher `""`, timeout 5). Readings on the measuring machine, the
command as registered through `sh -c`, the median of three consecutive runs: a main-session payload
0.15 s (bound 0.2 s; the hook printed nothing), a subagent payload for `praxion:implementer` whose
transcript holds 100 distinct requests cut from a real implementer transcript 0.16 s (bound 0.3 s;
the 80 percent line emitted). A live probe from a scratch repository — a nested headless session
loading the worktree's plugin and spawning a throwaway agent capped at 10 turns — left
`[turn-budget] 6 of 10 turns used` and `[turn-budget] 8 of 10 turns used` in the subagent's
transcript and nothing in the main session's. Both bounds hold and the lines reach the agent, so the
reversal trigger does not fire and this decision is in force from the pipeline's merge; the earlier
status note of 2026-10-07 is superseded by this one. Its falsifier (the implementer cap-out rate
over the three-pipeline window) is judged by the calibration rows that follow.
