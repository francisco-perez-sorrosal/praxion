---
id: dec-draft-53d813ee
title: Spawns count toward the Task slug their prompt states, joined on agent id from the recorded Agent result; unknown spawns pend
status: proposed
category: behavioral
date: 2026-10-01
summary: "The Agent tool's PostToolUse result (agentId + prompt) is recorded in standard and full modes with spawned_agent_id/spawned_agent_type/task_slug; new agent_start rows carry slug_attribution; spawn_count.py attributes each agent to its prompt's first Task slug (else the checkout), keeps rows written before the change on their project, falls back to the agent's own transcript, and holds the verdict for spawns it cannot attribute"
tags: [spawn-budget, observability, observations-jsonl, wal, pipeline, td-288]
made_by: agent
agent_type: systems-architect
branch: worktree-wal-slug-attribution
pipeline_tier: standard
affected_files:
  - hooks/_observation_log/registry.py
  - hooks/_observation_log/writer.py
  - hooks/_hook_utils.py
  - hooks/remind_task_brief.py
  - hooks/capture_observations.py
  - hooks/capture_session.py
  - scripts/spawn_count.py
  - skills/software-planning/references/coordination-details.md
affected_reqs: [REQ-04, REQ-05, REQ-06, REQ-07, REQ-08, REQ-09]
supersedes_in_part: [dec-394]
---

## Context

`dec-394` clause 2 counts `agent_start` rows whose `project` equals the slug. `project` is the checkout's directory name, so a pipeline split that keeps working in its parent's worktree is invisible (`slug-unseen`) and keeps charging the parent: remove-chub went 25 to 28 while remove-chub-land read unseen (td-288). The orchestrator puts `Task slug: <slug>` in every spawn prompt.

Verified on Claude Code 2.1.285 against the hooks reference and a live payload capture:
- `SubagentStart` carries `agent_id` and `agent_type` but no prompt and no `tool_use_id`.
- The `Agent` tool's `PostToolUse` carries `tool_input.prompt` and `tool_response.agentId`. That `agentId` equals the `SubagentStart` `agent_id`, both for a foreground (`completed`) and a background (`async_launched`) spawn.
- A `SendMessage` resume fires another `SubagentStart` with the same `agent_id`.
- Two like spawns launched together cannot be told apart by event order (acceptance BA-03).

In `standard` mode (`dec-401`) the main session's `Agent` result was not recorded.

## Decision

**Recording.**
- A spawn-tool (`Agent`, `Task`) `PostToolUse` whose `tool_response.agentId` is a non-empty string writes its `tool_use` row under a new recording class, `TOOL_AGENT_SPAWN`. The class is recorded in `full` and `standard`, because `spawn_count.py` declares it at `min_mode: standard`: this applies `dec-401`'s own rule. The row carries three additive fields:
  - `spawned_agent_id`;
  - `spawned_agent_type`;
  - `task_slug`, the first `Task slug:` value in the prompt, or `null` when none is stated.
- Every new `agent_start` row carries `slug_attribution: "spawn-prompt"`.
- `project` keeps meaning "the checkout" on every row.
- The prompt pattern moves from `remind_task_brief.py` into `hooks/_hook_utils.py` as `stated_task_slug`, its single definition.

**Counting** (`spawn_count.py`). Every agent id witnessed by a first `agent_start` or a spawn-result row is one spawn, and later starts are resumes. Its owner is decided by the first rule that matches:
1. A first `agent_start` without `slug_attribution` (a row written before this change): that row's `project`. History counts exactly as before.
2. A spawn-result row: its `task_slug`, or its `project` when the slug is `null`.
3. The agent's own subagent transcript, read at the I/O edge (including Workflow-run agents): the slug its first message states, or the start row's `project`.
4. Otherwise unattributed.

The rest of the count follows from ownership:
- A slug's tally is the agents it owns.
- Unattributed agents are pending for every slug at once. `within` needs `charged + unsized resumes + unattributed ≤ budget`.
- A slug is seen when some row's `project` names it or some agent's owner is it; otherwise it is withheld as `slug-unseen`.
- The JSON envelope adds an `unattributed` list only when it is non-empty, so a log of rows written before the change reports byte-identically.

**Activation:** no. The order-based pairing alternative is ruled out by BA-03, and the undocumented `.meta.json` `toolUseId` is ruled out as a primary path. That leaves one documented join key, so there is no honest uncertainty between viable designs.

## Considered Options

### Option 1 — pair `PreToolUse` prompts with the next `SubagentStart` by order
- **Pros:** attribution known at start time.
- **Cons:** guesses under concurrency (BA-03), and the harness documents no ordering. Rejected.

### Option 2 — join through the undocumented `subagents/agent-<id>.meta.json` `toolUseId`
- **Pros:** the join is available at `SubagentStart`.
- **Cons:** an undocumented internal. It still needs the prompt recorded by `tool_use_id`, so it adds a second row type. Rejected as the primary path.

### Option 3 — record the `Agent` result and join on agent id at read time (chosen)
- **Pros:** the evidence is documented and verified live. The join is order-independent, rows written before the change keep their count, and unknown spawns fail safe.
- **Cons:** one more recorded row per spawn in `standard`, and attribution is a read-time computation.

### Option 4 — document that a split needs its own worktree
- **Pros:** no code.
- **Cons:** leaves the miscount in place. The user explicitly asked for the fix instead.

## Consequences

- **Positive:**
  - A split continuing in its parent's worktree is charged to its own slug.
  - Lost `SubagentStart` deliveries no longer undercount, because the result row witnesses the spawn.
  - Resumes follow their agent, whatever the resume message says.
  - The orchestrator sees unattributable spawns by name.
- **Negative:**
  - `standard` now records the main session's `Agent` results.
  - The transcript fallback reads an undocumented first-line format, as resume sizing already does. When that format can't be read, the spawn degrades to pending.
  - A spawn that is never attributable pessimises verdicts in its log near the budget.
  - A lost start followed by a resume under-reports that resume.
- **Revisit when** real pipeline tallies show a non-empty `unattributed` list more than occasionally. Then stamp the slug onto `agent_start` at write time when the result row already exists, or add a stop-time read of the agent's own transcript.

## Prior Decision

Narrows `dec-394` clause 2 only, on what a spawn is attributed to. "`agent_start` rows whose `project` is the slug" becomes "agents whose owner is the slug", with ownership derived as above and rows written before the change still owned by their `project`. The rest of clause 2 survives unchanged:
- the first start is a spawn and a later start is a resume;
- heavy resumes are charged at the 250k threshold;
- an unseen slug is withheld (exit 2) and never reported as zero.

`dec-394`'s other clauses (the artifact floor, the calibration reminder) and `dec-412`'s budget figures are untouched.
