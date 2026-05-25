---
description: Create a new git worktree in .claude/worktrees/
argument-hint: [branch-name]
allowed-tools: [Bash(git:*), Bash(ln:*), Bash(ls:*), Bash(test:*), Bash(cursor:*)]
disable-model-invocation: true
---

Create a new worktree named .claude/worktrees/$ARGUMENTS.

> **Migration note.** `/create-worktree` now targets `.claude/worktrees/` (unified with Claude Code's built-in `EnterWorktree`). Legacy `.trees/` paths are supported in `/merge-worktree` for a deprecation window; create your new worktrees under the new path.

## Steps

0. If `.trees/$ARGUMENTS` already exists on disk, emit a one-line deprecation notice — e.g. `Legacy .trees/$ARGUMENTS worktree found. Use scripts/migrate_worktree_home.sh to migrate. Proceeding with new path.` — then proceed.
1. Check if `.claude/worktrees/$ARGUMENTS` already exists. If it does, stop and tell the user the worktree already exists.
2. Create a new git worktree under `.claude/worktrees/` with the name `$ARGUMENTS`.
3. Symlink the `.venv` folder into the worktree directory.
4. Launch the user's editor in that directory (try `cursor` first; if unavailable, try `code`; if neither is found, print the worktree path for the user to open manually).
