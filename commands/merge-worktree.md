---
description: Merge a worktree branch back into current branch
argument-hint: "[branch-name]"
allowed-tools: [Bash(git:*), Bash(python*), Bash(test:*), Bash(praxion-sidecar:*), Read, Grep]
disable-model-invocation: true
---

Merge the $ARGUMENTS worktree into the current branch. Primary worktree home is `.claude/worktrees/$ARGUMENTS`; `.trees/$ARGUMENTS` is supported as a transitional fallback during the deprecation window.

> This command is the `.ai-state/` reconciliation point for a pipeline worktree — Steps 7–8 below are the contract (the SessionStart banner that used to announce it was retired together with the duplicate worktree guard, since native worktree isolation needs neither).

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
4.5. State convergence (preferred, not required). Resolve the worktree's `.ai-state/` placement: `python3 scripts/_state_repo.py --print "$WORKTREE_PATH"`. If the output includes `placement=sidecar`, the project's `.ai-state/` lives in a state-mount sidecar rather than inside the project repo — run `praxion-sidecar merge-back --from wt/$ARGUMENTS` from the root directory, against the target checkout's own mount. This is the explicit merge-back form: it **may leave conflict markers** in the mount rather than aborting, which is correct here because an operator is present to resolve them (the CLI prints both the resolve and the abort commands). Doing this now, before Step 5's project-branch merge, promotes any draft ADRs or other `.ai-state/` writes made inside the worktree in this same run, giving the earliest possible visibility. If the output is `placement=in-repo` (or any other value), skip this step — there is no separate mount to converge. Proceed to Step 5 regardless of this step's outcome (converged, nothing to converge, or conflict markers left for later resolution): this step is a **convenience, not a correctness requirement**. State written inside a sidecar-placed worktree also converges automatically, from the project's own post-merge finalize chain and from the next session's start-up self-heal, so skipping this step, letting it time out, or merging with a different tool entirely never strands worktree state permanently. Anything still unconverged is surfaced by `praxion-sidecar doctor`'s `state-unmerged` and `state-eligible` rows, each printed with its exact fix command.
5. Merge in the worktree. Default: `git merge --ff-only "$BRANCH"` to preserve a linear history. If `--ff-only` refuses because the branch has diverged from the target, stop and tell the user to rebase the branch on the target first (`git rebase <default-branch>` from inside the worktree) and re-run the merge. Do not silently fall back to a non-fast-forward merge commit. The user's explicit `--squash` or rebase choice (when it passed the check in Step 4) is honored.
6. Check for merge conflicts using `git status`, `git diff --name-only --diff-filter=U`, or `git ls-files -u`.
7. Run `.ai-state/` reconciliation: `python scripts/reconcile_ai_state.py` — this renumbers duplicate ADR sequence numbers and regenerates `DECISIONS_INDEX.md`. It acts only on paths git reports as conflicted, and git ignores the observation log, so it carries none of the worktree's log rows; Step 9.5 does.
8. Promote any draft ADRs introduced by the merged branch: `python3 scripts/finalize_adrs.py --merged` (command-layer invocation complementing the post-merge git hook — idempotent; no-op when the hook already ran).
9. Resolve any remaining conflicts based on your knowledge of the changes and continue the merging process.
   Then commit everything the merge left dirty under `.ai-state/` — reconciliation and finalize outputs, the observations-summary tail, the calibration row — as **one** `chore(state)` commit, staged by name. A finalize or ledger migration that surfaces after that commit rides the next state commit rather than getting one of its own.
9.5. Merge the worktree's observation log into this checkout's log. A worktree's log is deleted with the worktree and git does not carry it, so this is the only point where the spawns, stops and costs it recorded are kept. From the root directory run `python3 scripts/merge_worktree_log.py --worktree "$WORKTREE_PATH"` and report what it prints: rows copied, rows already held (skipped), and malformed lines left behind. Safe to repeat. The exit code decides Step 10:
    - `0` — merged, nothing to merge (the worktree never recorded), or recording is off. Proceed to Step 10.
    - `1` — the log could not be merged whole (a segment unreadable or missing, or this checkout's own log unreadable or unwritable). Every row that could be copied was. Show the printed `reason:`, do **not** remove the worktree in Step 10, and tell the user the rows still in the worktree will be lost with it. Offer to re-run once the cause is fixed. Remove the worktree anyway only if the user explicitly chooses to discard those rows.
    - `2` — input error (not a worktree of this repository, or not inside a repository). Show the message and treat it as exit `1`.
    A merge made without this command (a plain `git merge`, a pull) does the same for every worktree this checkout contains, from the post-merge hook.
10. Teardown, once the merge is clean and Step 9.5 allows it (optional — leave the worktree in place if the user wants to keep working in it). Claude Code locks a worktree it opened for the session, and that lock outlives the session, so `git worktree remove "$WORKTREE_PATH"` alone refuses on a still-locked worktree. Check first with `git worktree list --porcelain | grep -A2 "$WORKTREE_PATH"` (a locked entry carries a `locked` line); if locked, run `git worktree unlock "$WORKTREE_PATH"` — `unlock` itself errors on an already-unlocked worktree, so only run it when the check confirms a lock. Then `git worktree remove "$WORKTREE_PATH"`. Under sidecar placement (the same `--print` check from Step 4.5), also run `praxion-sidecar link --prune` afterward — it drops the now-orphaned mount entry the removed worktree left behind in the sidecar; skip it under `placement=in-repo`, where there is no mount to prune.
