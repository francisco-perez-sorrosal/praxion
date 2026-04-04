---
description: Merge a worktree branch back into current branch
argument-hint: [branch-name]
allowed-tools: [Bash(git:*), Bash(python*), Read, Grep]
---

Merge the $ARGUMENTS worktree from `.trees/$ARGUMENTS` into the current branch.

## Steps

1. Change into the `.trees/$ARGUMENTS` directory
2. Examine and understand in depth the changes that were made in the last commit
3. Change back to the root directory
4. Merge in the worktree
5. Check for merge conflicts using `git status`, `git diff --name-only --diff-filter=U`, or `git ls-files -u`
6. Run `.ai-state/` reconciliation: `python scripts/reconcile_ai_state.py` — this resolves memory.json and observations.jsonl conflicts semantically, renumbers duplicate ADR sequence numbers, and regenerates DECISIONS_INDEX.md
7. Resolve any remaining conflicts based on your knowledge of the changes and continue the merging process
