---
id: dec-496
draft_id: dec-draft-c16be513
title: The intermediate-documents rule stays resident in the managed main session; its point-of-use move is closed, not pursued
status: accepted
category: behavioral
date: 2026-11-10
summary: "The startup-context diet's item 3 (deliver the intermediate-documents rule to the main session at the point of use, by a path scope on .ai-work/** and .ai-state/** plus a write-time gate) is closed by decision: orchestrators reach those paths through Bash first, so every channel after session start reaches the rule late or never. The managed main session keeps the rule resident by SessionStart delivery (dec-490); the spawn half landed as the audience split (dec-495)."
tags: [startup-context-diet, rule-delivery, intermediate-documents, path-scope, session-start, token-budget, closure]
made_by: agent
agent_type: orchestrator
branch: main
pipeline_tier: spike
affected_files:
  - rules/swe/agent-intermediate-documents.md
  - rules/_manifest.yaml
  - hooks/_rule_delivery.py
affected_reqs: []
---

## Context

The startup-context diet's finish line closes each roadmap item either by landing it with a measured before and after or by a recorded decision not to pursue it. Item 3 was the intermediate-documents move: once project gating (dec-490) made `rules/swe/agent-intermediate-documents.md` managed-only and hook-delivered, the remaining step was to stop sending it to every managed session and spawn and deliver it at the point of use instead. The plan was a native path scope on `.ai-work/**` and `.ai-state/**` plus a write-time gate for the first write's path choice, on the decision-record gate's pattern (dec-481).

The move had two halves. The spawn half landed as the audience split (dec-495, v0.60.0). Inheriting spawns no longer receive the rule's orchestrator-only text, which is 1,098 characters of this rule and 15,166 characters across both core units. This record decides the main-session half.

The evidence is the 2026-11-06 channel spike (`aid-channel-spike`, $0), recorded in the diet's `LEARNINGS.md`. It used this project's last-30-day main-session transcripts, 57 tool-using sessions:

- 14 sessions named `.ai-work/` or `.ai-state/` in a Bash command. Every one of them did so before any Read, Write or Edit of those paths.
- Of those 14, 2 never touched the paths with Read, Write or Edit at all. 9 touched them natively only later, after gaps of 1 to 250 tool calls (median 141). One session wrote in its very first tool call.
- A native path scope fires only on Read, Write or Edit, or on a single-file `cat` or `head`. A `mkdir`, a redirect, a heredoc, `cp`, `mv` and `tee` do not count (memory doc, fetched 2026-11-05).
- A non-blocking PreToolUse `additionalContext` is placed beside the tool result, after the command ran (hooks doc wording plus Praxion's own transcript order). Only a deny puts text in front of the call it governs.

A precision on the evidence: the detector counted sessions whose Bash commands *named* the paths, which is a first touch. A looser detector found 11 sessions whose first write was a Bash write. The conclusion holds under either reading.

## Decision

Close item 3's main-session half by decision. The managed main session keeps the intermediate-documents rule resident, delivered at SessionStart as dec-490 set it (`install: hook-deliver`, gated by `scope_of(cwd)`). No path scope, no Write/Edit gate and no Bash deny-once gate is added for this rule.

## Considered Options

### A. Path scope plus resident projection plus Write/Edit gate (the planned move, the dec-480/dec-481 pattern)

- Pro: about 1,582 tokens saved per managed main session that never touches the paths, and about 1,225 on average over the sample.
- Con: it reaches the orchestrator after the location choice in every session that matters. 9 of 14 got the rule late (median 141 calls) and 2 of 14 never. The rule's core is *where* a document goes, so text that arrives after the first write has already missed its moment. On Windows, user-scope `paths:` never fire (dec-480).

### B. A plus a Bash deny-once hook

- Pro: it is the only channel after session start that precedes the choice. It closes the Bash gap for 14 of 14 sessions whenever the command names the path.
- Con: a refusal the user sees in every touching session, at about 250 tokens per retry (an estimate). It needs per-session delivered-state, which compaction leaves stale. It misses paths built from variables or reached by `cd`. It is Claude Code only, with no Codex or Cursor export. Net saving is about 1,105 tokens per main session on average, against a gate with timing risk.

### C. Keep the rule resident for the main session and split it for spawns (chosen, with dec-495)

- Pro: no timing risk and no meaning lost. The main session gets the full rule before its first action. The spawn half already recovers the orchestrator-only text on every inheriting spawn (about 320 a month here).
- Con: it forgoes about 1,169 tokens of whole-rule delivery per managed main session (bytes/3.6 estimate for the whole unit, `count_spawn_shed.py`). That is about 6% of the 19,918-token always-loaded reading.

### D. A moment-of-need split of the rule itself

A resident core of about 500 tokens (intro, `.ai-work/`, slug convention), with the rest (ledger, lifecycle, cleanup, parallel execution, about 1,150 tokens) behind path scope or a gate. The spike noted this variant but did not rank it. It inherits A's and B's timing faults for the deferred half. The ledger and parallel-execution text is first needed at the first ledger write or the first concurrent spawn, both of which also start in Bash or the Agent tool. Not pursued. It is the first option to revisit if the reversal trigger below fires.

## Consequences

- Positive: the rule reaches the orchestrator before the location choice in 100% of managed main sessions, as it does today. No new hook, state or refusal. Codex and Cursor exports are unchanged, and with hooks absent the F1 floor stands as accepted in dec-490.
- Negative: the main session keeps paying for the whole rule. This is a recorded forgoing, not a hidden cost: about 1,169 tokens per managed main session.
- Item 3 is closed for the finish line: the spawn half was measured (dec-495) and the main half is closed by this record.

## Reversal trigger

Revisit if any of these happens:

- The harness gains a channel that places text before a Bash command runs: a pre-execution `additionalContext`, or path-scoped rules that fire on Bash writes.
- A fresh transcript sample shows orchestrators reaching `.ai-work/` and `.ai-state/` through Read, Write or Edit first.
- The move eval gains a kit and governed checks for this rule (td-579) that could show option D's adherence parity.
