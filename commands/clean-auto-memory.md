---
description: List orphan Claude Code auto-memory directories for worktrees and prompt for cleanup
argument-hint: [--dry-run]
allowed-tools: [Bash(ls:*), Bash(du:*), Bash(rm:*), Bash(git:*), Bash(basename:*), Read, AskUserQuestion]
disable-model-invocation: true
---

Enumerate orphan Claude Code auto-memory directories under `~/.claude/projects/` whose corresponding git worktree has been removed, and help the user delete them. **Opt-in only** — the command never deletes without explicit confirmation, and never touches auto-memory directories that do not match the `-worktrees-*` pattern.

## Scope Boundary (read first)

Claude Code stores per-cwd auto-memory in `~/.claude/projects/<slug>/`. When a git worktree is created, its auto-memory slug contains `-worktrees-<name>` as a substring (e.g., `-Users-fperez-dev-myrepo--claude-worktrees-feat-x`). When the worktree is removed, that directory is orphaned.

This command **only** enumerates and deletes directories whose name contains `-worktrees-`. The main repo's auto-memory (no `-worktrees-` substring) is never listed and never deleted, regardless of user input.

## Arguments

- `$ARGUMENTS` — pass `--dry-run` to list orphans without asking for confirmation or deleting anything.

## Process

### 1. Probe git worktree state

Run `git worktree list --porcelain`. If the command fails (not inside a git repo, or git unavailable), print a warning and exit without deleting anything:

> `Not inside a git worktree or git unavailable. Refusing to enumerate or delete auto-memory directories. No action taken.`

On success, extract the live worktree names — for each line starting with `worktree `, take the path and use `basename` to get the trailing path component. This is the live-worktree set.

### 2. Derive the repo-scope prefix

Compute `$(git rev-parse --show-toplevel | sed 's|/|-|g')` to get the current repo's auto-memory slug prefix. This value scopes enumeration to the current repo's auto-memory directories only — other projects' worktree auto-memory is out of scope for this invocation.

### 3. Enumerate candidate directories

List `~/.claude/projects/` and select directories where **both** conditions hold:

- The directory name starts with the repo-scope prefix from step 2 (current repo only).
- The directory name contains the substring `-worktrees-` (worktree auto-memory pattern, not main-repo auto-memory).

For each candidate, extract the worktree name by splitting on the **last** occurrence of `-worktrees-` and taking the suffix.

### 4. Compute orphan set

An orphan is a candidate whose extracted worktree name is **not** in the live-worktree set from step 1.

### 5. Display and confirm

If the orphan set is empty, print:

> `No orphan worktree auto-memory directories found. Nothing to clean.`

and exit.

Otherwise, for each orphan print path and size via `du -sh`, then print a summary line:

> `Found <N> orphan auto-memory directories (<total-size>).`

If `$ARGUMENTS` contains `--dry-run`, stop here. Do not prompt. Do not delete.

Otherwise, ask the user: `Delete all <N> orphan directories listed above? [y/N]`. Use `AskUserQuestion` for the prompt; accept a `y` / `yes` (case-insensitive) as confirmation, anything else as abort. On abort, print `Aborted. No directories removed.` and exit.

### 6. Pattern-guarded deletion

For each confirmed orphan path:

- Re-check the path contains `-worktrees-` — if it does not, skip it and print `Refusing to remove <path>: does not match -worktrees- pattern`.
- Re-check the path is under `~/.claude/projects/` — if it is not, skip it and print `Refusing to remove <path>: outside ~/.claude/projects/`.
- Run `rm -rf <path>`.

The two guards above are defensive — the enumeration in step 3 already scopes correctly, but the guards make the deletion step self-contained. **Never** invoke `rm -rf` on a path that fails either guard.

### 7. Report

Print `Removed <M> of <N> orphan directories.` where `M` is the count of successful deletions and `N` is the count presented to the user. If `M < N`, list the skipped paths with the reason.

## Safety Invariants

- The command does nothing destructive without user confirmation (steps 5, 6).
- The command never enumerates or deletes directories outside `~/.claude/projects/`.
- The command never enumerates or deletes directories whose name lacks the `-worktrees-` substring.
- The command never enumerates or deletes directories from other repos (repo-scope filter in step 3).
- If `git worktree list` fails, the command exits without any deletions.
- `--dry-run` is a pure inspection mode; the filesystem is never modified.
