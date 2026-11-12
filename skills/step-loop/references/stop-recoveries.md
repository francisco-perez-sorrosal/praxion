# Stop Recoveries

Hand recoveries for the stops and refusals of the step-loop driver that its printed `Next:` line does not spell out. Back to [SKILL.md](../SKILL.md). Each is the orchestrator's work, done between a stop and the next `next`; the relay never improvises one.

## A Check that cannot pass before the commit

A step whose Check reads the committed tree (a plugin copy built from `git archive HEAD`, for example) cannot go green for a change that only the commit makes true, such as a file-mode change: the driver gates before it commits, so the step is red at its own gate however correct it is (observed 2026-11-06).

- Plan such a step as `Assignee: orchestrator` from the start.
- When it comes back `[BLOCKED]` for this reason, record the return, commit the change by pathspec, and run the Check yourself.
- Then set the block to `Assignee: orchestrator` and `Files: none` with a note naming the commit, and append a `Result: pass=N fail=0 skip=0` section to `TEST_RESULTS.md`. The reconciler reads the last `Result:` line, so a step with a Check that is not driven stays pending without it.

## A commit that is refused

The driver's commit goes through the repository's hooks. When the commit gate (`hooks/commit_gate.sh`) rejects a Bash call whose text holds `git` and `commit`, nothing in that call runs, and the refusal carries the checker's findings and the way out.

- Before committing a step, run the checker on its files yourself: `check_id_citation_discipline.py --files <the staged paths>`. Mark a fixture literal that mirrors a real step header with the checker's ignore marker.
- Put the fix and the `git add` in one Bash call that holds no `git ... commit` text, and the commit in the next.
- Never call `record` until `git log -1` shows the step's commit. A refused driver commit records a mismatch and spends an attempt.
- A refused commit leaves the step's files staged, so any later call whose text holds `git` and `commit`, a heredoc included, is blocked too until the findings are fixed.

## A driver commit refused by a consistency hook

The driver commits the step's declared `Files` by literal pathspec. A hook that reads two files against each other (generator and generated, canonical and copies, registry and carriers) fails when only one of them is staged: pre-commit stashes the rest, and the driver records a mismatch with "the gate passed, but the repository's hooks refused the step-loop driver's commit" (observed 2026-10-13). The rules-manifest drift hook and the decision-reciprocity hook can refuse a driver commit the same way; the reciprocity hook can also trip on an untracked draft.

- Commit the whole consistent set yourself by pathspec, with a message that names the step, then let the next attempt find nothing left to commit. Better, declare the generator and its outputs in the step's `Files` before the loop starts.
- On a step marked `review: force`, a hand commit made before `record` leaves a record with no commit, and `next` stops with `loop-state-defect` because no commit holds the reviewed work. Declare the outputs in `Files` there, or run the light review outside the loop and amend the step block with the verdict and `**Review**: off`. The driver reads `review: force` only from a `**Review**:` field line, never from the heading.
- A `[CONFLICT]` return whose Check passes is still committed for its declared files, so HEAD can hold half a change. After adding the paths to `Files:`, trust `next` over `status`, and commit the consistent remainder yourself before the re-issued implementer confirms it.

## A commit-disturbed-tree stop

The driver stops `commit-disturbed-tree` when its commit met files outside its paths, or did not finish, and writes `TREE_SNAPSHOT_<request>.patch` beside the task documents. The loop stays stopped until a person deletes that file. A glob in `Files:` (`dir/*`) matches nothing in the driver's literal pathspecs and is the usual cause; name each path, or a directory by its bare path with no trailing slash (observed 2026-10-11).

1. Restore the reverted work from the snapshot, one path at a time: `git apply --include=<path> TREE_SNAPSHOT_<request>.patch`. Skip any file a hook rewrites on its own.
2. Amend the step's `Files:` to the concrete paths. That opens a new series, and the next request is `s<N>-p2-a1-...`.
3. Delete the snapshot, then run `next`.

## A reopened step

A step the loop does not drive, with `Files:` set and no Check, is judged by its changed files and the latest test status, which is not scoped to the step. A later red test makes it read `WIP=[COMPLETE] but tests red`, and `next` hands it back as not driven (observed 2026-10-17). This is a workaround until the reconciler scopes the judgement.

Once such a step is committed and verified, set its plan `**Files**:` to `none (orchestrator note: committed in <sha>, files ..., Done-when confirmed by ...)`. A not-driven step with no files and no Check, ticked in `WIP.md`, reads as done outside whatever later steps record. The same fix fits a step whose files all belong to an earlier step.

## A stop handoff that crashes

On a stop the driver composes `HANDOFF.md` in the task directory. A hand-written `HANDOFF.md` that lacks the required sections or the boundary header makes the composer refuse to overwrite it, and `record` exits 1 after it has already recorded the return. This is a workaround for that crash, not a design.

- Move the hand-written file aside (rename it, outside the task directory if the name matters) and run `next`: the stop is then written normally.
- Do not retry the `record`; the return is already recorded.
