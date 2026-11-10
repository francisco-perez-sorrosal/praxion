---
id: dec-497
draft_id: dec-draft-24425744
title: The coordination protocol stays resident in the managed main session; its pipeline-only half is not deferred to a trigger
status: accepted
category: behavioral
date: 2026-11-10
summary: "The startup-context diet's item 4 main-session half (defer the coordination protocol's pipeline-only text until a Standard or Full pipeline runs) is closed by decision. The pipeline-only group is about 1,496 tokens (bytes/3.6 estimate; 2,055 by tokenizer), but no trigger fires before the text is first needed. A first-spawn deny is late in 5 of 13 pipeline sessions and circular for the rows that prescribe spawns, and it would fire anyway in 14 of 15 Praxion sessions. The managed main session keeps the protocol resident (dec-490); the spawn half landed as the audience split (dec-495)."
tags: [startup-context-diet, rule-delivery, coordination-protocol, session-start, token-budget, closure]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: spike
affected_files:
  - rules/swe/swe-agent-coordination-protocol.md
  - rules/_audience.yaml
  - hooks/_rule_delivery.py
affected_reqs: []
---

## Context

Finish-line item 4 was to take the coordination protocol's orchestrator-only parts out of resident delivery, in sub-moves. The spawn half landed as the audience split (dec-495, v0.60.0): inheriting spawns no longer receive the `orchestrator-only` spans, a shed of 14,068 characters of this rule. The main-session half asked whether the text the main session needs only once a Standard or Full pipeline runs could reach it on a trigger instead of at SessionStart. Process Calibration and the Conversation Checkpoints stay resident by the plan.

A timeboxed $0 Spike (`cp-main-session-spike`, decision in its `LEARNINGS.md`) did three things:

- It classified every line of the rule body into spans: *always needed* (A) or *needed only once a pipeline runs* (P), each flagged by whether dec-495 already keeps it out of spawns.
- It sized P.
- It tested candidate triggers against this machine's transcripts (30 days for Praxion; 60 days across managed projects).

The findings:

- **Size of P.** P is Pipeline Isolation, the "architecture approved / plan ready / resuming" and doc-engineer bullets of Proactive Agent Usage, the Coordination Pipeline lead-in, and its rows from "Do not skip stages" to "Intra-step pair-review", less the any-tier rows (Context-engineer scope, Sentinel, Skill-genesis).
  - 5,384 bytes, about **1,496 tokens** by `measure_token_budget.py`'s offline estimate (`bytes / 3.6`).
  - **2,055** by tokenizer: the fallback undercounts this table-heavy file by about 25%.
  - That is about 10% of the 19,918-token always-loaded reading and 3.4% of the 60,954-token managed main-session startup.
- **The only pre-choice channel is a deny.** Path scope, Write/Edit gates and non-blocking hooks all arrive after the call they would govern (the 2026-11-06 channel spike and dec-496).
- **A deny on the first spawn is too late in 5 of 13 Praxion pipeline sessions.**
  - Three created the pipeline worktree and wrote its `TASK_BRIEF.md` before the first spawn. That is Pipeline Isolation's moment.
  - Two resumed a pipeline and did 74 and 90 tool calls of pipeline work before any spawn.
- **The trigger is circular.** In one resumed session the first spawn was the verifier light-review that a P row prescribes: the text the trigger would deliver is what causes the spawn that fires it.
- **The saving lands in few sessions.** 14 of 15 Praxion interactive sessions spawned, as did 16 of 21 pooled across managed projects (crvntx 1 of 4). The expected saving is about 140 tokens per Praxion session and about 410 pooled. That is before a refusal of about 250 tokens in every spawning session, plus one more after each compaction that precedes a spawn (12 in one session).

## Decision

Close item 4's main-session half by decision. The managed main session keeps the whole coordination protocol resident at SessionStart, as dec-490 delivers it. No deny-once, path scope, skill-load or prompt trigger is built for its pipeline-only text. The move-eval kits and governed checks (td-579) are not built for this move.

## Considered Options

### A. Deny-once at the first `Agent`/`Workflow` call (main session only, re-armed at compaction)

- Pro: the Agent tool is a single structured choke point, with no command parsing, unlike item 3's Bash gap. The deny reason arrives before the spawn.
- Con: it is late for Pipeline Isolation in 3 of 13 pipeline sessions, and late or circular in resumed pipelines (2 of 13), where the P rows prescribe the spawns.
  - It fires in 93% of Praxion sessions anyway, so the realised saving is about 140 to 410 tokens per session before refusal costs.
  - It needs per-session state that compaction must reset.
  - A refusal inside a step-loop relay spends the loop's iteration budget.
  - It has no Codex or Cursor export.

### B. A with Pipeline Isolation and the resume/plan-ready bullets kept resident

- Pro: it removes the set-up lateness, and P shrinks to about 1,600 tokens (tokenizer).
- Con: the rework-loop, pre-refactor and pair-review rows stay circular in resumed sessions. It keeps every cost of A for an even smaller expected saving.

### C. Triggers on worktree creation, skill load, `.ai-work/**` path scope or `UserPromptSubmit`

- Con: each fires after the need or carries no deterministic pipeline signal.
  - Resumed pipelines create no worktree.
  - `EnterWorktree` is refused in pinned sessions, and Bash text matching is brittle.
  - The choice to invoke the step loop is itself P text.
  - Pipeline docs are first touched through Bash, and worktree paths sit outside a root `.ai-work/**` glob.
  - The tier is the model's own choice at intake.

### D. Keep the protocol resident for the main session; the audience split serves spawns (chosen, with dec-495)

- Pro: no timing risk and no meaning lost. No new hook, state or refusal, and the exports are unchanged.
- Con: it forgoes about 1,496 tokens (estimate), or 2,055 by tokenizer, per managed main session.

## Consequences

- Positive: every managed main session has the full pipeline protocol before its first pipeline action, including resumed pipelines and orchestrator-only work, as today. The F1 floor (dec-490) and the Codex and Cursor exports are untouched.
- Negative: the main session keeps paying for the pipeline-only text, a recorded forgoing of about 2,055 tokenizer tokens.
- Item 4 is closed for the finish line: its spawn half was measured (dec-495) and its main half is closed by this record. The finish line moves on to items 6 to 8.

## Reversal trigger

Revisit if any of these happens:

- The harness gains a channel that places context before a tool call runs, or a deterministic "pipeline started" event that precedes the first pipeline write.
- A managed-project sample beyond Praxion shows most interactive sessions never spawn, with pipelines starting through a spawn rather than a worktree or a resume.
- A td-579 kit is built for another reason, making a moment-of-need split measurable.
