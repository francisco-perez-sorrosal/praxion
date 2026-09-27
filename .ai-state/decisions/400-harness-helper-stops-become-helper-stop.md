---
id: dec-400
draft_id: dec-draft-2b4320a6
title: Harness helper stops are written as their own slim helper_stop event, not as agent_stop rows
status: accepted
category: behavioral
date: 2026-09-27
summary: "A SubagentStop with no prior log row and no own transcript is written as a slim helper_stop row (no agent_type, no usage, no transcript scan) in every recording mode; the log reader presents legacy agent_stop rows self-reporting unobserved-agent with no usage as helper_stop; P03's envelope and the unobserved-agent vocabulary are unchanged; narrows dec-370's representation of the helper class"
tags: [observability, observations-jsonl, hooks, agent-lifecycle, sentinel-p03, td-212, additive-schema]
made_by: agent
agent_type: systems-architect
branch: worktree-wal-modes-core
pipeline_tier: standard
affected_files:
  - hooks/capture_session.py
  - hooks/_observation_log/reader.py
  - hooks/_observation_log/registry.py
  - scripts/check_agent_lifecycle_pairing.py
  - scripts/workflow_run_cost.py
  - scripts/project_metrics/collectors/cost_collector_read.py
affected_reqs: [REQ-11, REQ-12, REQ-13, REQ-14]
supersedes_in_part: [dec-370]
---

## Context

dec-370 named the harness's unannounced internal helper agents as a correlation verdict on `agent_stop` rows (`start_correlation: unobserved-agent`), so sentinel P03 could count them apart from real lifecycle loss. td-212 then measured their cost:
- **Volume:** since 2026-09-18, 159 of 184 `agent_stop` rows in the main checkout are helpers.
- **Miscounting:** consumers that counted `agent_stop` rows counted helpers as agents. A published attribution figure read "51 of 524" where the truth was 23 of 25 real agents.
- **Pollution:** helpers populate an `unknown` agent-type bucket.
- **Wasted work:** because a helper has no transcript of its own, `capture_session` falls back to streaming the whole parent transcript looking for its lines. That is about 53 ms per helper on a 5.8 MB transcript, and it grows with the session.

The re-probe established that no real data exists for a helper. There is no start row, no prior row of any kind, and no transcript anywhere under the harness's project directories.

The intake proposed collapsing helpers into a per-session count on the `session_stop` row. Measurement argues against that:
- **No I/O saved:** a collapse still needs one filesystem write per helper (a counter or marker instead of a log append).
- **New state:** it adds cross-invocation mutable state inside async, concurrent, fail-open hooks.
- **Structural race:** 59 of the last 159 helpers arrived immediately *after* a `session_stop`, so each session's final helpers would never be counted.
- **P03 and cost tooling:** P03's per-id substrate would become a count, and `workflow_run_cost.py`'s helper section would go blind.

## Decision

1. **Writer.** On SubagentStop, `capture_session` computes the existing verdict unchanged. When the verdict is `unobserved-agent`, the payload carries `transcript_path` and `session_id`, and the agent has no transcript of its own (neither the sibling `agent-<id>.jsonl` nor a Workflow-run copy), it writes a `helper_stop` row with exactly `timestamp`, `session_id`, `agent_id`, `project`, `event_type` and `log_mode`, and scans no transcript. In every other case, including when the check cannot run or the own transcript exists, it writes today's `agent_stop` row unchanged, verdict and usage included.
2. **Every recording mode.** `helper_stop` is recorded in `full` and `standard`. It is not a mode question.
3. **Reader upcast.** The log reader presents a legacy `agent_stop` row as `helper_stop`, cut to the five `helper_stop` keys other than `log_mode` (which a legacy row never carries, so the upcast row reads as `full`), when all four hold: the row has no `log_mode` key, so it was written before this change; its `start_correlation` is `unobserved-agent`; its `usage_source` is neither `subagent-transcript` nor `parent-transcript`; and none of its token fields (`tokens_in`, `tokens_out`, `cache_read`, `cache_create`) is set. Every row the writer now appends carries `log_mode`, so an `agent_stop` the writer deliberately kept is never relabelled.

   The rule is deliberately conservative, so it covers only part of the legacy helper population. In main's log on 2026-09-27 (23,818 rows, 4,073 `agent_stop`), it upcasts 288 rows, and none of their `agent_id`s appears in any other row, so it has no false positives. About 3,710 legacy helper stops exist, and two shapes stay `agent_stop`:
   - **274 parent-contaminated helpers** (2026-09-08 to 2026-09-14). They self-report `unobserved-agent` and carry token counts but no `usage_source` key: the stop path of that period summed the parent transcript's usage onto the helper's row, and 270 of them carry the parent's model. The token clause keeps them because, with no source label, their counts cannot be told from real usage.
   - **3,145 pre-split helpers** (2026-08-07 to 2026-09-06), stamped `unobserved-start` with `agent_type: unknown` and no usage, whose `agent_id` appears in no other row. They were written before dec-370's `unobserved-agent` verdict reached the hooks.

   All 3,419 sit in the `.1` archive, outside every active-only reader and the reconciler's 7-day window, and they leave the log at the next rotation. Until then, readers of `.1`, such as the cost collector, still see them as `agent_stop`.
4. **Consumers.**
   - P03 pairs on `helper_stop` rows and classifies unmatched ones exactly as it classified a stop self-reporting `unobserved-agent`, so its JSON envelope keys and counts are unchanged.
   - `workflow_run_cost.py` lists `helper_stop` rows in its `unobserved` section as before.
   - The cost collector's `agent_stop` census stops counting new helper stops and the legacy ones the upcast recognizes. This is a deliberate correction: those helpers were already classified `unparsed` and never entered a total. The two residual shapes in Decision 3 stay in the census, quarantined (`pre-attribution` for the 274 token-bearing rows, `unparsed` for the rest), until they rotate out, so no token total is inflated.

## Considered Options

### Split into a `helper_stop` event type (chosen)

- **Pros:** exact counts; no new state; no race. A reader counting `agent_stop` counts agents by construction. The per-helper transcript stream is skipped. It is stricter than today's verdict: a real agent whose rows scrolled out of the tail but whose transcript exists keeps an `agent_stop` with its usage.
- **Cons:** helper rows stay in the log (slim, ~200 bytes, ~20/day since 2026-09-18). It adds one event type every consumer of stop rows must know about, which the reader's upcast and the registry make explicit.

### Collapse into a per-session count on `session_stop`

- **Pros:** no helper rows in the log.
- **Cons:** one out-of-log write per helper anyway; new concurrent state; systematic undercount of post-`Stop` helpers; P03's substrate changes from ids to a count; `workflow_run_cost`'s helper section disappears.

### Keep them as `agent_stop` + `unobserved-agent`, slimmed

- **Pros:** zero consumer change.
- **Cons:** leaves the counting trap in place for every future reader, human or agent, that counts `agent_stop` rows.

## Consequences

**Positive**
- `agent_stop` means "an agent stopped".
- td-212's consumer harms end at the source.
- Helper stops cost a slim append instead of a parent-transcript stream.
- P03 needs no instruction change.

**Negative**
- The cost collector's reported `total_agent_stop_rows` and quarantine counts drop retroactively, via the upcast, by the legacy helper stops it recognizes (288 in main's log on 2026-09-27). Anyone comparing a metrics report across the change sees a step.
- The helper test depends on the harness keeping helper transcripts absent and the sibling path stable. If that changes, the conservative fallback writes today's `agent_stop`, degrading to current behaviour rather than losing data.

## Prior Decision

**Narrowed:** dec-370 clause 2 defined the harness-helper class as a `start_correlation` value (`unobserved-agent`) on `agent_stop` rows. This record moves the class to its own event type, `helper_stop`, and tightens its test with the own-transcript check.

**Surviving unchanged:**
- clause 1 (transcript-sourced `agent_stop` rows for turn-limit and orchestrator-stopped suspensions, `stop_source`);
- the rest of clause 2 (the `unobserved-start` narrowing and the verdict vocabulary, including `unobserved-agent`, which remains the name P03 reports the class under and the marker the reader upcasts from);
- clause 3 (P03's baseline and INFO/WARN split).
