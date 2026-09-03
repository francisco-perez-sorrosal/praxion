"""`merge-back`'s two forms, and the one thing that separates them.

Both forms merge sidecar state branches into the branch this checkout has
mounted, through the *same* primitive (``_sidecar_mount.merge_back``). They
differ in exactly one argument -- whether a conflict may be left in the tree:

    merge-back --from wt/x   an operator asked for this branch, and is present
                             to resolve it, so markers may stay
    merge-back --auto        nobody is present (SessionStart, the finalize
                             chain), so a conflict aborts and the mount is
                             returned clean

That single divergence is why this module exists as one file rather than two:
the policy is one boolean, and splitting the forms across modules would let
them drift into two merge implementations with two sets of edge cases.

Everything here reports through ``Report`` -- lines plus an exit code -- and
never prints. The caller decides which stream a report belongs on, which keeps
the ``--quiet`` rule (informational output is suppressible, a problem is not)
in one place instead of scattered through the verb bodies.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import _sidecar_commit as commits
import _sidecar_git as gitp
import _sidecar_mount as mounts
import _sidecar_render as render
from _sidecar_cli import EXIT_ACTIONABLE, EXIT_OK, EnvironmentProblem, refusal

RECONCILER_SCRIPT = "reconcile_ai_state.py"

# The reconciler renumbers ADR drafts and regenerates an index; on the largest
# state trees that is still seconds, so a minute is only ever reached by a hang.
RECONCILER_TIMEOUT_SECONDS = 60.0

DRY_RUN_TRAILER = "Dry run: nothing was modified."
FIXED_POINT_LINE = "Nothing to converge."

_SKIP_PHRASES = {
    mounts.IneligibilityReason.PROJECT_BRANCH_NOT_MERGED: "project branch not merged",
    mounts.IneligibilityReason.PROJECT_BRANCH_DELETED: "project branch deleted",
    mounts.IneligibilityReason.MAPPING_MISSING: "no project branch recorded for it",
    mounts.IneligibilityReason.MAPPING_UNRESOLVABLE: "its project branch cannot be resolved",
}


@dataclasses.dataclass(frozen=True)
class Report:
    """What to tell the operator, and what to exit with."""

    lines: tuple[str, ...]
    exit_code: int = EXIT_OK


# --- the reconciler seam ----------------------------------------------------


def reconcile_state_mount(mount: Path, _branch: str) -> None:
    """Reconcile ``mount`` after a merge landed, and fold the result into it.

    The `post_merge_hook` seam ``converge`` documents, bound to the real
    script -- and the same seam the explicit verb uses, so both forms of
    merge-back reconcile identically rather than through two code paths.

    Whatever the reconciler produces (renumbered ADRs, a regenerated index)
    exists *only* because of this merge, so it is amended into the merge commit
    rather than committed after it. A follow-up commit would leave the merge
    commit describing a tree that was never correct on disk, and would replace
    the merge with a single-parent commit at the tip -- erasing, from every
    later reader, the fact that a convergence happened at all.

    A reconciler failure is reported and stepped over rather than raised: the
    merge itself already succeeded, and turning a reconciliation problem into a
    merge-back failure would leave the operator with a landed merge and an
    error that says nothing about it.
    """
    _run_reconciler(mount)
    _fold_reconciliation_into_head(mount)


def _fold_reconciliation_into_head(mount: Path) -> None:
    """Amend whatever the reconciler left in the tree into the merge commit.

    Always called with the mount's commit lock already held -- by the explicit
    verb directly, and by ``converge`` around the whole run.
    """
    paths = commits.residue_paths(mount)
    if not paths:
        return
    gitp.run_or_raise(mount, EnvironmentProblem, "add", "--", *paths)
    gitp.run_or_raise(
        mount,
        EnvironmentProblem,
        *gitp.identity_args(mount),
        "commit",
        "-q",
        "--amend",
        "--no-edit",
    )


def _run_reconciler(mount: Path) -> None:
    script = Path(__file__).resolve().parent / RECONCILER_SCRIPT
    if not script.is_file():
        print(
            f"warning: {script} is missing — state was merged but not reconciled.", file=sys.stderr
        )
        return
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(script), "--target-mount", str(mount)],
            capture_output=True,
            text=True,
            timeout=RECONCILER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"warning: state reconciliation could not run ({error}).", file=sys.stderr)
        return
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        print(
            f"warning: state reconciliation failed in {render.abbreviate_home(mount)}.",
            file=sys.stderr,
        )
        for line in detail[-3:]:
            print(f"  {line}", file=sys.stderr)


# --- merge-back --from ------------------------------------------------------


def merge_back_from(sidecar: Path, checkout: Path, branch: str, *, dry_run: bool) -> Report:
    """Merge one named branch into this checkout's mounted state branch.

    Conflict markers are *allowed* to survive: the operator named this branch
    and is standing here to resolve it. The result is exit `1` -- actionable,
    not a refusal -- because the outcome is exactly what was asked for.
    """
    target = _require_target(sidecar, checkout)
    _require_branch(sidecar, branch)
    if dry_run:
        return Report((f"Would merge {branch} into {target.branch}.", DRY_RUN_TRAILER))

    _require_clean_mount(target.mount, branch)
    with commits.mount_lock(target.mount):
        result = mounts.merge_back(sidecar, checkout, branch, allow_conflict_markers=True)
        if result.outcome is mounts.MergeOutcome.FAILED:
            raise EnvironmentProblem(
                f"Merging {branch} into {target.branch} failed before git merged anything.\n"
                f"{result.detail}\n"
                f"Nothing was merged and the mount is unchanged; fix the cause and re-run."
            )
        if result.outcome is mounts.MergeOutcome.CONFLICTED:
            return Report(_conflict_lines(target.mount, branch), EXIT_ACTIONABLE)
        reconcile_state_mount(target.mount, branch)
    return Report((f"Merged {branch} into {target.branch}.",))


def _conflict_lines(mount: Path, branch: str) -> tuple[str, ...]:
    return (
        f"Conflict merging {branch} — the mount is left mid-merge for you to resolve.",
        "Praxion left the markers in place because you named this branch explicitly.",
        f"Resolve them, then:  git -C {mount} commit",
        f"Or abandon the merge:  git -C {mount} merge --abort",
    )


# --- merge-back --auto ------------------------------------------------------


def merge_back_auto(sidecar: Path, checkout: Path, project_root: Path, *, dry_run: bool) -> Report:
    """Converge every eligible state branch; never leave a mount mid-merge.

    The convergence engine's CLI face. A conflict here aborts (no operator is
    present on the channels that call this) and the run exits `1` naming the
    branch and the explicit command that *can* resolve it.
    """
    _require_target(sidecar, checkout)
    result = mounts.converge(
        sidecar,
        checkout,
        project_root,
        dry_run=dry_run,
        post_merge_hook=None if dry_run else reconcile_state_mount,
    )
    lines = _convergence_lines(result, dry_run=dry_run)
    if not lines:
        return Report((FIXED_POINT_LINE,))
    if dry_run:
        lines = (*lines, DRY_RUN_TRAILER)
    return Report(lines, EXIT_ACTIONABLE if (result.aborted or result.failed) else EXIT_OK)


def _convergence_lines(result: mounts.ConvergeResult, *, dry_run: bool) -> tuple[str, ...]:
    """One line per branch the run acted on, or declined to act on.

    A branch that is merged *and* still mounted is the steady state of every
    live worktree, so it earns no line -- otherwise the fixed point would be a
    wall of text saying nothing happened.
    """
    prefix = "would " if dry_run else ""
    lines = [f"{prefix}converged {branch}" for branch in result.merged]
    lines += [
        f"{prefix}dropped {branch}: merged, and its mount is gone" for branch in result.deleted
    ]
    lines += [
        f"aborted {branch}: conflict — run praxion-sidecar merge-back --from {branch}"
        for branch in result.aborted
    ]
    # Deliberately *not* phrased as a conflict, and deliberately not offering
    # `merge-back --from`: git never merged anything, so the operator's next
    # move is to fix what git reported, not to resolve markers that do not
    # exist. The branch stays eligible and `doctor`'s state-branch row keeps
    # showing it until a later run succeeds.
    lines += [f"failed {branch}: {reason}" for branch, reason in sorted(result.failed.items())]
    lines += [
        f"skipped {branch}: {_skip_phrase(result.states.get(branch))}"
        for branch in result.skipped
        if not isinstance(result.states.get(branch), mounts.MergedLive)
    ]
    return tuple(lines)


def _skip_phrase(state: object) -> str:
    if isinstance(state, mounts.UnmergedIneligible):
        return _SKIP_PHRASES.get(state.reason, str(state.reason))
    if isinstance(state, mounts.MergedOrphan):
        return "merged, but its branch could not be deleted"
    return "not eligible to converge"


# --- merge-back --from ... --drop ------------------------------------------


def drop_state_branch(sidecar: Path, branch: str, *, dry_run: bool) -> Report:
    """Delete ``branch`` outright, merged or not -- the two-step escape hatch.

    The mount precondition is checked *first*, before any confirmation is
    sought: git refuses to delete a branch a worktree holds, and discovering
    that after the operator confirmed a destructive action is the worst
    possible moment to discover it.
    """
    _require_droppable(sidecar, branch)
    if dry_run:
        return Report((f"Would delete {branch} from the sidecar.", DRY_RUN_TRAILER))
    mounts.drop_branch(sidecar, branch)
    return Report((f"Deleted {branch}. Any state only it carried is gone.",))


def _require_droppable(sidecar: Path, branch: str) -> None:
    if gitp.branch_is_checked_out(sidecar, branch):
        raise refusal(
            f"Refusing to drop {branch}: a state mount still has it checked out.",
            "Deleting a branch a worktree holds would strand that mount — remove the mount first.",
            "Remove the project worktree, then:  praxion-sidecar link --prune",
        )
    _require_branch(sidecar, branch)


# --- shared preconditions ---------------------------------------------------


def _require_branch(sidecar: Path, branch: str) -> None:
    if not gitp.branch_exists(sidecar, branch):
        raise refusal(
            f"Refusing to act on {branch}: no such branch in this sidecar.",
            "State branches are named wt/<worktree>; the one you named was "
            "deleted, or never existed.",
            "List them:  praxion-sidecar doctor",
        )


@dataclasses.dataclass(frozen=True)
class _Target:
    """Where a merge lands: the mount directory, and the branch it holds."""

    mount: Path
    branch: str


def _require_target(sidecar: Path, checkout: Path) -> _Target:
    """The mount to merge into, classified once and carried as a pair.

    Both facts come from one classification because they are one fact: a slot
    that is a state mount always has a branch, and asking twice would let the
    two answers disagree between the calls.
    """
    state = mounts.classify_mount(checkout, expected_common_dir=(sidecar / ".git").resolve())
    if not isinstance(state, mounts.SidecarWorktree):
        raise refusal(
            "Refusing to merge back: this checkout has no state mount to merge into.",
            f"{checkout / mounts.MOUNT_DIRNAME} is not a worktree of this project's sidecar.",
            "Recreate it:  praxion-sidecar link",
        )
    return _Target(mount=checkout / mounts.MOUNT_DIRNAME, branch=state.branch)


def _require_clean_mount(mount: Path, branch: str) -> None:
    """A merge into a dirty or mid-merge mount would mix unrelated work in."""
    if gitp.merge_in_progress(mount):
        raise refusal(
            f"Refusing to merge {branch}: the state mount is already mid-merge.",
            f"{mount} carries an unresolved merge; a second one would bury it.",
            f"Finish it:  git -C {mount} commit   or abandon it:  git -C {mount} merge --abort",
        )
    status = gitp.porcelain_status(mount)
    if status is None or status.strip():
        raise refusal(
            f"Refusing to merge {branch}: the state mount has uncommitted changes.",
            f"{mount} would carry them into the merge, and a conflict would mix "
            "them with the resolution.",
            "Commit them first:  praxion-sidecar commit",
        )
