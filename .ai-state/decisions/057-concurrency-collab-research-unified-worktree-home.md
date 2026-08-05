---
id: dec-057
title: Unified Worktree Home on `.claude/worktrees/`
status: accepted
category: architectural
date: 2026-04-19
summary: '`/create-worktree` and `/merge-worktree` migrate from `.trees/<name>/` to `.claude/worktrees/<name>/`, matching `EnterWorktree` built-in behavior; `.gitignore` adds the new path; `.trees/` retained through a two-release deprecation window.'
tags:
  - concurrency
  - worktree
  - commands
  - migration
made_by: agent
agent_type: systems-architect
pipeline_tier: full
affected_files:
  - "commands/create-worktree.md"
  - "commands/merge-worktree.md"
  - ".gitignore"
  - "scripts/migrate_worktree_home.sh"
  - "README.md"
  - "README_DEV.md"
---

## Context

Praxion has two worktree locations: `.trees/<name>/` created by `/create-worktree` (predates EnterWorktree adoption), and `.claude/worktrees/<slug>/` created by `EnterWorktree` (Claude Code v2.1.32+, Nov 2025). Neither is wrong; both are real git worktrees. The split is accidental drift, not a deliberate separation, and causes operational confusion: `/merge-worktree` only handles `.trees/`, so a pipeline worktree merged via `/merge-worktree <slug>` fails to locate the directory.

User decision is explicit: "Unify on `.claude/worktrees/`. Migrate `/create-worktree` and `/merge-worktree` to produce and consume this path." Transitional support for `.trees/` is expected with a deprecation window.

Additional finding from codebase inspection: `.claude/worktrees/` is NOT currently in `.gitignore` (only `.trees/` is). This must land alongside the command retargeting or the first use of the retargeted `/create-worktree` accidentally commits worktree contents.

## Decision

The unified worktree home is `.claude/worktrees/`. All three primitives write to this path:

- `EnterWorktree` (Claude Code built-in, already correct).
- `/create-worktree <name>` (retargeted).
- `/merge-worktree <name>` (retargeted, with `.trees/` fallback during deprecation).

Specific changes:

1. `commands/create-worktree.md` -- change creation path to `.claude/worktrees/$ARGUMENTS`. Add a pre-step: if `.trees/$ARGUMENTS` exists, warn the user (deprecation notice) and proceed to the new path.
2. `commands/merge-worktree.md` -- change primary path to `.claude/worktrees/$ARGUMENTS`. Fallback: if not found, check `.trees/$ARGUMENTS` and print deprecation notice.
3. `.gitignore` -- add `.claude/worktrees/` after the existing `.trees/` line. Keep `.trees/` ignored through the deprecation window.
4. `scripts/migrate_worktree_home.sh` (new) -- one-shot helper that lists existing `.trees/<name>/` directories and emits copy-paste-ready `git worktree move .trees/<name> .claude/worktrees/<name>` commands. No automatic move; user verifies each worktree.
5. README and README_DEV -- short migration note.

`/create-worktree` is NOT retired. It remains the user-initiated convenience layer (scratch worktrees without an agent pipeline); `EnterWorktree` remains the agent-initiated primitive. Unifying the path is sufficient.

Deprecation timeline:

- Release N (this pipeline): `.claude/worktrees/` is the default; `.trees/` triggers warnings.
- Release N+1: `/create-worktree` hard-errors on `.trees/`; `/merge-worktree` removes fallback.
- Release N+2: `.gitignore` removes `.trees/`.

## Considered Options

### 1. Retarget `/create-worktree` (chosen)

Path unification without retiring the command. Preserves muscle memory for users who rely on `/create-worktree` for scratch worktrees.

### 2. Retire `/create-worktree`; everyone uses `EnterWorktree`

One command, one path, simplest long-term. Rejected by user decision -- disruption to existing workflows outweighs the simplicity gain at this stage.

### 3. Keep `.trees/` as the primary home; retarget `EnterWorktree`

Rejected: `EnterWorktree` is a Claude Code built-in whose target we do not control; fighting the upstream default is a losing maintenance battle.

### 4. Support both paths indefinitely (no deprecation)

Rejected: creates permanent split-home confusion; reconciliation scripts and documentation must handle two cases forever.

## Consequences

**Positive:**

- Single worktree home across all three concurrency modes and all creation primitives.
- `/merge-worktree` now locates pipeline worktrees (fixes the split-home bug).
- `.gitignore` gap closed -- prevents accidental commit of worktree contents.
- User migration is bounded (2 releases) and user-verified (no automatic `git worktree move`).

**Negative:**

- Two-release deprecation window adds transitional code (warnings + fallback) that must be removed later.
- Users must update muscle memory.
- Existing `.trees/<name>/` worktrees persist on disk until user migrates them.

**Risks:**

- User skips migration helper and finds their `.trees/<name>/` worktree orphaned after `.gitignore` removes `.trees/`. Mitigation: README note + release N+1 hard-error on `.trees/` surfaces the problem before release N+2.
- `.gitignore` change accidentally stops ignoring `.trees/`. Mitigation: the two entries are additive; one line is added without touching the other.
