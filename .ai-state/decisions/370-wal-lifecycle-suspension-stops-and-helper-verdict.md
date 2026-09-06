---
id: dec-370
title: The WAL closes subagent lifecycles the harness never reports, and names unannounced helpers
status: accepted
category: behavioral
date: 2026-09-05
summary: capture_session.py appends transcript-sourced agent_stop rows for turn-limit suspensions and orchestrator stops (stop_source transcript-notification), and splits unobserved-start into unobserved-start (delivery loss after work) and unobserved-agent (unannounced harness helper), so P03 measures real lifecycle loss instead of two harness behaviours the hooks cannot influence
tags: [observability, observations-jsonl, hooks, agent-lifecycle, sentinel-p03, truncation, additive-schema]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/capture_session.py
  - hooks/test_capture_session.py
  - agents/sentinel.md
affected_reqs: []
dissent: "The turn-limit notification is harness prose with no published contract; parsing it couples a durable ledger to wording that can change silently, and a harness-side SubagentStop-on-suspension would make the whole mechanism unnecessary."
---

## Context

Sentinel P03 (2026-09-04) reported six `agent_start` rows that emitted `tool_use` and never received an `agent_stop`, tripled from the prior run and spread one per session, and asked for an investigation of Stop-hook delivery. The transcripts settled the cause: two of the six were verifiably background subagents that "stopped at their N-turn limit (partial result; SendMessage to continue)". The harness suspends such an agent, tells the *main* agent through a task-notification in the session transcript, and fires no `SubagentStop`. The other four fit the same shape (their sessions kept running for hours after the agent's last tool use). A second unreported terminal shape exists for `TaskStop` ("was stopped by Claude"). Normal completions do fire `SubagentStop` (verified on a background sentinel run the same day).

S-14 raised the mirror image: 3,031 stops against 257 starts. Of the 2,812 stops the WAL could not pair, 2,770 carried `agent_type: unknown` and had *no row of any kind* for their id, one roughly every 30 s during a session. Those are the harness's own internal helper agents, announced by a stop and nothing else. Only 14 unpaired stops had prior work, the actual start-delivery loss the existing `unobserved-start` verdict was written for. The one verdict lumped both.

Neither behaviour is a defect in this fleet's hooks, yet both surface as findings every audit, and the completion handshake (dec-248) has no telemetry for the suspension case at all, the "Layer B" gap the truncation-recovery design left open.

## Decision

1. **Transcript-sourced stops.** On the main-agent `Stop` hook, `capture_session.py` reads a bounded tail of the session transcript, finds task-notification blocks whose summary matches the turn-limit or stopped-by-orchestrator shape, and for every task id that has an `agent_start` and no `agent_stop` in the WAL tail appends an `agent_stop` row with `start_correlation: paired`, `outcome: turn-limit | stopped`, and a new additive field `stop_source: transcript-notification`. Hook-delivered stops carry `stop_source: hook`. The append is idempotent across turns and degrades silently when the transcript is absent, unreadable, or worded differently.
2. **Split the correlation verdict.** `unobserved-agent` is a stop whose id has no prior row of any kind (an unannounced helper). `unobserved-start` narrows to ids with prior `tool_use` rows and no start (delivery loss). `paired` and `not-applicable` are unchanged.
3. **History baseline for P03.** The sentinel counts transcript-sourced stops as paired, reports `unobserved-agent` and `unobserved-start` as two separate INFO counts, and treats an unpaired start dated before 2026-09-05 as pre-baseline INFO named by id. Only a post-baseline unpaired start that did work is a WARN.

## Considered Options

### Re-specify P03 only (documentation)
Cheapest, but the WAL stays wrong: every consumer that reads it (`reconcile_pipeline_state.py`, the dashboard, future audits) still sees a worked agent with no end, and the suspension signal dec-248 wanted never exists.

### Backfill stops at session end
A `SessionEnd`-time sweep could close every start still open in that session. It would pair the rows but say nothing about *why*, and it arrives only when the session dies, hours after the fact; background agents also legitimately outlive turns, so a per-turn variant is unsafe.

### Transcript-sourced stops at the main Stop hook (chosen)
The transcript is the only place the harness records a suspension, and the main agent's `Stop` fires shortly after every notification is delivered. The row carries the cause. Cost is one bounded tail read per turn and a dependency on harness wording, mitigated by a pure, separately tested parser and silent degradation.

### Upstream harness change
The right long-term answer (a `SubagentStop` with a suspension reason), outside this repository's control. If it ships, the transcript scan becomes a no-op because the hook-delivered stop arrives first.

## Consequences

- P03 stops manufacturing findings from two harness behaviours the fleet cannot change, and gains a real signal: `outcome: turn-limit` rows are a per-agent-type suspension rate the completion handshake and the routing table can act on.
- The WAL schema grows by one field (`stop_source`) and one vocabulary value (`unobserved-agent`); both additive. Readers keyed on `unobserved-start` see a smaller, more honest count.
- A resumed agent (`SendMessage` after suspension) that later completes carries two stops: `turn-limit` then `hook`. That is its true lifecycle; readers pair on set membership and are unaffected.
- The six historical unpaired starts stay unpaired; the baseline names them rather than rewriting history.
- Harness wording drift silently returns to today's behaviour. The parser's fixture test is the tripwire, and the sentinel's post-baseline WARN is the backstop.
