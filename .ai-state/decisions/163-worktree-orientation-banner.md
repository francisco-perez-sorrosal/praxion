---
id: dec-163
title: Worktree-orientation banner via a SessionStart hook
status: accepted
category: implementation
date: 2026-05-12
summary: Inject the worktree-context banner with a dedicated SessionStart hook (inject_worktree_banner.py) rather than a committed .claude/worktrees/CLAUDE.md or a worktree-local note file.
tags: [worktree, hooks, context-engineering, roadmap-p5]
made_by: user
branch: main
pipeline_tier: lightweight
affected_files:
  - hooks/inject_worktree_banner.py
  - hooks/hooks.json
  - rules/swe/swe-agent-coordination-protocol.md
  - skills/software-planning/references/coordination-details.md
  - commands/merge-worktree.md
---

## Context

Roadmap item P5 ("Minimal worktree-context banner") addresses a recurring failure: an agent operating inside `.claude/worktrees/<name>/` loses track of which checkout it is in and writes into the parent (`main`) tree. Praxion already has the *enforcement* half — `worktree_guard.py`, a `PreToolUse(Write|Edit|NotebookEdit)` hook that blocks cross-worktree writes — but no *proactive* half that orients the agent before it forms the bad intent. P5 offered three mechanisms: (a) a committed `.claude/worktrees/CLAUDE.md` loaded as an ancestor, (b) a `SessionStart` hook that detects worktree context and injects the banner via `additionalContext`, (c) a worktree-local note file written by `/create-worktree` / `EnterWorktree` and re-read after compaction.

## Decision

Use mechanism **(b)**: a dedicated `SessionStart` hook, `hooks/inject_worktree_banner.py`. When the session's cwd is inside a *linked* git worktree (detected by comparing `git rev-parse --git-dir` against `--git-common-dir`), it emits an `additionalContext` banner naming the worktree root, the canonical (main) checkout, the `.ai-work/` (gitignored, worktree-local) vs `.ai-state/` (committed, reconciled at `/merge-worktree`) distinction, and a `pwd` reminder. It is fail-open (any error → exit 0, no output), silent in the main worktree, and honors a `PRAXION_DISABLE_WORKTREE_BANNER=1` opt-out mirroring the existing `PRAXION_DISABLE_*` convention. Git-probing logic is intentionally duplicated (not extracted into a shared module) because there are only two worktree hooks; a third would be the trigger to extract `hooks/_worktree_utils`.

## Considered Options

### (a) Committed `.claude/worktrees/CLAUDE.md` + `.gitignore` exception

- **Pro:** simplest; no new executable code; uses native ancestor-`CLAUDE.md` loading.
- **Con:** only loads when the worktree directory is literally nested under `.claude/worktrees/` in the *main* repo's tree (true by Praxion convention, but fragile); the file is a checkout of `main`'s own tree, so editing it diverges per-worktree and creates merge noise; cannot name the *specific* worktree path dynamically.

### (b) `SessionStart` hook — **chosen**

- **Pro:** composes with Praxion's existing `SessionStart` hook chain (`inject_memory`, `auto_complete_install`, `measure_context_surface`); symmetric with `worktree_guard.py` (banner = heads-up, guard = backstop) and can reuse the same git-detection idiom; computes the worktree/main paths dynamically; ships via `install.sh` like every other hook; no `.gitignore` change.
- **Con:** `SessionStart` does not re-fire when `EnterWorktree` is called mid-session, and `SubagentStart` `additionalContext` is silently ignored by Claude Code — so subagents spawned after an `EnterWorktree` are *not* covered by the banner (they remain covered by `worktree_guard.py`'s hard block).

### (c) Worktree-local note via `/create-worktree` / `EnterWorktree`

- **Pro:** survives compaction if agents re-read it like `PIPELINE_STATE.md`.
- **Con:** most moving parts (touches two creation flows + adds a file to the re-read-after-compaction set); does not fire for orchestrator-created pipeline worktrees unless the `EnterWorktree` path is also wired; partially duplicates what `precompact_state.py` already does for pipeline docs.

## Consequences

**Positive.** Closes the "lost agent writes to parent" hole for the most common case (a session opened inside a worktree) with native, low-maintenance machinery; the banner is self-announcing (injects itself only when relevant) so it costs zero always-loaded budget; the three cross-references (`swe-agent-coordination-protocol.md`, `coordination-details.md#pipeline-worktree-lifecycle`, `commands/merge-worktree.md`) make the banner+guard pair discoverable from the coordination docs.

**Negative / follow-up.** Subagents spawned after a mid-session `EnterWorktree` do not receive the banner — only the `worktree_guard.py` block protects them. The obvious follow-up is to carry an abbreviated worktree note via `inject_subagent_context.py` (the existing `PreToolUse(Agent)` `updatedInput` hook); deferred to keep P5 surgical. Also: two worktree hooks now carry near-identical `git rev-parse` probing — acceptable at two copies, but a third worktree hook should trigger extraction of `hooks/_worktree_utils`.
