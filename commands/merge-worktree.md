---
description: Merge a worktree branch back into current branch
argument-hint: [branch-name]
allowed-tools: [Bash(git:*), Bash(python*), Bash(test:*), Read, Grep]
---

Merge the $ARGUMENTS worktree into the current branch. Primary worktree home is `.claude/worktrees/$ARGUMENTS`; `.trees/$ARGUMENTS` is supported as a transitional fallback during the deprecation window.

## Steps

1. Locate the worktree:
   - If `.claude/worktrees/$ARGUMENTS` exists, use it as `WORKTREE_PATH`.
   - Else if `.trees/$ARGUMENTS` exists, set `WORKTREE_PATH=.trees/$ARGUMENTS` and emit a deprecation notice: `.trees/ worktree home is deprecated. Move to .claude/worktrees/ by running scripts/migrate_worktree_home.sh (Step 9 output).` Continue with the merge.
   - Else stop and tell the user the worktree cannot be found under either path.
2. Change into `$WORKTREE_PATH` and examine in depth the changes that were made in the last commit (and, if useful, the full branch history via `git log <default-branch>..HEAD`).
3. Change back to the root directory.
4. Squash-merge safety check (AC-15). If the user explicitly requested squash-merge (e.g. `git merge --squash`), run this preflight:
   - Determine the merge base: `BASE=$(git merge-base HEAD "$BRANCH")` where `$BRANCH` is the worktree's branch.
   - Check whether the branch touched `.ai-state/`: `git diff --name-only "$BASE..$BRANCH" -- .ai-state/ | head -n 1`.
   - If any path is returned, refuse the merge and print: `Squash-merge erases .ai-state/ history. Use regular merge (no --squash) or rebase + merge. See rules/swe/vcs/pr-conventions.md for details.` Stop without merging.
   - If no `.ai-state/` paths are touched, squash-merge is permitted.
5. Merge in the worktree. Default: `git merge --ff-only "$BRANCH"` to preserve a linear history. If `--ff-only` refuses because the branch has diverged from the target, stop and tell the user to rebase the branch on the target first (`git rebase <default-branch>` from inside the worktree) and re-run the merge. Do not silently fall back to a non-fast-forward merge commit. The user's explicit `--squash` or rebase choice (when it passed the check in Step 4) is honored.
6. Check for merge conflicts using `git status`, `git diff --name-only --diff-filter=U`, or `git ls-files -u`.
7. Run `.ai-state/` reconciliation: `python scripts/reconcile_ai_state.py` — this resolves memory.json and observations.jsonl conflicts semantically, renumbers duplicate ADR sequence numbers, and regenerates `DECISIONS_INDEX.md`.
8. Promote any draft ADRs introduced by the merged branch: `python3 scripts/finalize_adrs.py --merged` (command-layer invocation complementing the post-merge git hook — idempotent; no-op when the hook already ran).
9. Resolve any remaining conflicts based on your knowledge of the changes and continue the merging process.
