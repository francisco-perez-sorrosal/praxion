---
id: dec-476
draft_id: dec-draft-7a68ab13
title: Spawn rows carry the spawning session's kind and checkout; headless slug-less spawns are left out
status: accepted
category: behavioral
date: 2026-10-27
summary: The spawn-result row records session_kind (from the harness entrypoint, closed map) and checkout; the tally leaves a headless session's slug-less spawn out of every slug and lists it, and charges an interactive slug-less spawn only to the pipeline's own checkout.
tags: [spawn-budget, observation-log, attribution, hooks]
made_by: agent
agent_type: systems-architect
branch: worktree-gate-repairs
pipeline_tier: standard
affected_files:
  - hooks/capture_observations.py
  - hooks/_hook_utils.py
  - scripts/spawn_count.py
affected_reqs: [REQ-04, REQ-05, REQ-06]
supersedes_in_part: dec-413
---

## Context

`spawn_count.py` charged a slug every slug-less spawn recorded in a checkout named after it (dec-413 rule 2's null-slug fallback to `project`). Headless measurement sessions run inside a pipeline's worktree (startup probes, spikes, channel probes) spawn agents with no `Task slug:` line, so lean-spawn-pilot read 86 charged against a true count near 26 (td-433); on 2026-10-26 it read 123, 57 of them from one-spawn headless sessions. Leaving such spawns unattributed is no fix: an unattributed spawn is pending for every slug, so every later pipeline would read `indeterminate`. The hook process inherits `CLAUDE_CODE_ENTRYPOINT` (`cli` in an interactive session; headless transcripts record `sdk-cli`) and `CLAUDE_PROJECT_DIR`.

## Decision

1. The Agent `PostToolUse` hook writes two additive keys on the spawn-result row: `session_kind`, from a closed map of the entrypoint (`cli`, `claude-vscode`, `claude-desktop` to `interactive`; `sdk-cli`, `sdk-py`, `sdk-ts` to `headless`; anything else omitted), and `checkout`, the resolved project directory. One reader in `hooks/_hook_utils.py`.
2. Owner rule 2 becomes: a stated slug owns the agent from any checkout and session kind (unchanged); a slug-less spawn of a `headless` session is left out of every slug, never pending, and listed under a conditional `left_out` key with its reason; a slug-less spawn of an interactive or unknown session is charged to the slug only from the pipeline's own checkout: the checkout the tally runs from when it is named after the slug, else (tally run elsewhere) every checkout named after it. A row without `checkout` falls back to `project` as today.
3. Rules 1, 3 and 4, the pending pool and the verdict are unchanged; a log with neither key reports byte-identically.

**Activation:** no -- the read-time transcript alternative contradicts the requirement that rows without evidence read as today.

## Considered Options

### Record kind and checkout at spawn time (chosen)
- Pro: evidence where the decision is made; old logs unchanged; no extra reads.
- Con: history is not corrected (past probe spawns stay charged).

### Read the spawning session's transcript entrypoint at tally time
- Pro: corrects history while transcripts exist.
- Con: changes the tally of rows that carry no evidence, contrary to the old-log requirement; one transcript read per session.

### Exclude by agent-type pattern
- Con: probe sessions spawn ordinary `praxion:*` agents; brittle.

## Consequences

- Positive: a pipeline's tally is its own spawns; what was left out stays visible.
- Negative: a headless orchestrator that forgets to state its slug is left out (listed, not silent); two optional keys on every spawn-result row.

## Prior Decision

dec-413 rule 2 charged a null-slug spawn to the row's `project`. This decision narrows that clause only: by session kind (headless spawns are left out) and by checkout identity (a same-named other checkout is not the pipeline's own). Its recording class, stated-slug ownership, rules 1, 3 and 4, and the pending pool stand.
