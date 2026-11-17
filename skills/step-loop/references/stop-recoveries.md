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

## Revising a step block

A step block is the unit the driver tracks its attempts and its verified record by: editing the block (not only `Files:`) opens a new series for that step. That is how a blocked or exhausted step is cleared: with no request out, edit the step's own block, then run `next`.

Never edit the block of a step the loop has already verified. Its verified record belongs to the old block, so the next `next` issues the step again (observed 2026-11-12).

## Putting a step ahead of the next

A plan block is amended while no request is out. To run a step before the one `next` would issue, take that request back first: `record --request <id> --not-started "<reason>"` prints `withdrawn` and issues nothing. Insert or revise the block, then run the `next` its `then` names; it issues exactly one request, for the step the plan now puts first.

- A `next` made after the plan changed while a request is out stops with `request-outstanding`, naming the request. Take it back with `--not-started` if no agent started on it, else record its return; then run `next` again.
- A request whose step's block was revised after its series' records is refused by a return's `record`: put the block back as it was, record the return, then re-apply the revision.
- Declared limit: a block revised while its series' first request is out is not seen, and `next` issues the stale request again. Withdraw that request before revising the block.
- The blocks of later steps can be amended freely while an earlier request is out.

## An attempts line that disagrees with its request

`attempts-disagree` means an `Attempts:` line in `WIP.md` names a request whose attempt (`-a<n>-`) is not the line's own `count=`; a hand edit or a stale line does that. Neither `next` nor `record` acts on it. Correct the line so the count is the request's attempt (or remove its `request=` when no agent ran it), then run `next`.

## A plan field the driver cannot read

`unreadable-plan-field` means a driven step's `Iterations:` or `Change type:` value does not read; the evidence names the field, the value as written and the line to correct. Fix that line in `IMPLEMENTATION_PLAN.md` (a whole number of at least 1, or one of the listed change types; the plan-level `Change type:` line sits outside every step block), then run `next`. A step's own `Iterations:` line is part of its block, so correcting it opens a fresh series for the step.

## A warning that a file was left uncommitted

A file the step's agent changed outside the step's `Files:` is left uncommitted, and the driver warns `undeclared-edit`; the warning names the file, not the remedy. The relay never commits, so the orchestrator does it at a step boundary: read `git status` after each `record`, and commit what is left by name at the next stop, or before the step that follows depends on it.

The warning `outer-loop-edit` is different: an outer-loop test file is never committed by the driver, and a change to one goes through a Spec Question and an answered `Resolved in:`, not through a hand commit (see [`coordination-details.md § Spec-Question Routing`](../../software-planning/references/coordination-details.md#spec-question-routing)).
