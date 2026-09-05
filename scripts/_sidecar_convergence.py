"""State-branch classification and convergence for sidecar placement.

Two layers, in the order a reader meets them:

1. **The branch.** Each state mount (``_sidecar_mount``) holds one sidecar
   branch. ``classify_branch`` asks a question about the branch, not the
   mount: did the *project* work this branch's state belongs to land on the
   project's current HEAD? It is a pure function of the current tips -- never
   cached, never persisted, because a live worktree keeps committing state
   after its first convergence and any latched answer would be wrong for
   every long pipeline.

2. **Convergence.** ``converge`` merges the state branches whose project work
   provably landed, deletes the ones already contained in the target branch
   whose mount is gone, and leaves everything else as it found it. Re-running
   it at the fixed point does nothing -- which is what lets three independent
   channels call it without coordinating with each other. ``merge_back`` is
   the single-branch step ``converge`` and the operator verb share;
   ``drop_branch`` is the one deliberate path that discards unmerged state.

Mount naming and lifecycle live in ``_sidecar_mount``; git plumbing --
ancestry, the squash-merge patch probe, merge and abort -- in
``_sidecar_git``. Both are imported here and neither imports back. Every git
invocation names its repository explicitly; nothing here reads the process
working directory.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Union

import _sidecar_git as gitp
from _git_runner import GitUnavailableError, git_output, run_git
from _sidecar_commit import mount_lock
from _sidecar_mount import (
    MOUNT_DIRNAME,
    PROJECT_BRANCH_CONFIG_SUFFIX,
    STATE_BRANCH_PREFIX,
    SidecarMountError,
    SidecarWorktree,
    classify_mount,
    describe_mount_state,
    sidecar_common_dir,
)


class BranchDropRefused(SidecarMountError):  # noqa: N818 - see SidecarMountError
    """A branch cannot be dropped while one of its preconditions is unmet."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- merging one branch back ------------------------------------------------


class MergeOutcome(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """The three things a merge-back attempt can do -- never two of them."""

    MERGED = "merged"
    CONFLICTED = "conflicted"
    FAILED = "failed"


@dataclasses.dataclass(frozen=True)
class MergeBackResult:
    branch: str
    outcome: MergeOutcome
    # git's own first stderr line, carried only for FAILED: the operator needs
    # the actual reason, and no other outcome has one to give.
    detail: str = ""

    @property
    def conflicted(self) -> bool:
        return self.outcome is MergeOutcome.CONFLICTED


def merge_back(
    sidecar_root: Path,
    target_checkout: Path,
    from_branch: str,
    *,
    allow_conflict_markers: bool,
) -> MergeBackResult:
    """Merge ``from_branch`` into the branch mounted at ``target_checkout``.

    ``allow_conflict_markers`` is the whole automatic/explicit divergence: an
    automatic run aborts and leaves the mount clean, while the operator-driven
    verb may leave markers for manual resolution. The merge runs *in the
    mount*, so the sidecar's own merge drivers apply by construction.

    A non-zero git exit is *not* evidence of a conflict. Git can also fail
    before merging anything -- a broken environment, a locked index, an
    unreadable object store -- and reporting that as a conflict sends the
    operator to `merge-back --from`, which fails the same way for the same
    reason. The two are told apart by the only artifact a real conflict leaves:
    ``MERGE_HEAD``, checked before any abort can remove it.
    """
    mount = _require_state_mount(sidecar_root, target_checkout)
    try:
        result = gitp.merge_branch(mount, from_branch)
    except GitUnavailableError as error:
        return MergeBackResult(from_branch, MergeOutcome.FAILED, str(error))
    if result.returncode == 0:
        return MergeBackResult(from_branch, MergeOutcome.MERGED)
    if not gitp.merge_in_progress(mount):
        return MergeBackResult(from_branch, MergeOutcome.FAILED, _first_line(result.stderr))
    if not allow_conflict_markers:
        gitp.abort_merge(mount)
    return MergeBackResult(from_branch, MergeOutcome.CONFLICTED)


def _first_line(stderr: str) -> str:
    """git's own diagnosis, first line only -- the rest is usually advice."""
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return "git exited non-zero without a message"


def _require_state_mount(sidecar_root: Path, checkout: Path) -> Path:
    state = classify_mount(checkout, expected_common_dir=sidecar_common_dir(sidecar_root))
    mount = Path(checkout) / MOUNT_DIRNAME
    if not isinstance(state, SidecarWorktree):
        raise SidecarMountError(f"{mount} is not a state mount: {describe_mount_state(state)}")
    return mount


# --- the branch slot --------------------------------------------------------


class IneligibilityReason(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """Why a branch carries no positive evidence that its project work landed."""

    PROJECT_BRANCH_NOT_MERGED = "ProjectBranchNotMerged"
    PROJECT_BRANCH_DELETED = "ProjectBranchDeleted"
    MAPPING_MISSING = "MappingMissing"
    MAPPING_UNRESOLVABLE = "MappingUnresolvable"


class MergeEvidence(str, Enum):  # noqa: UP042 -- `StrEnum` needs 3.11
    """How the project work behind a branch was shown to have landed."""

    ANCESTOR = "Ancestor"
    SQUASHED_TREE = "SquashedTree"


@dataclasses.dataclass(frozen=True)
class UnmergedIneligible:
    """Not contained in the target branch, and no evidence it may be merged."""

    reason: IneligibilityReason | str


@dataclasses.dataclass(frozen=True)
class UnmergedEligible:
    """Not contained in the target branch; its project work provably landed."""

    evidence: MergeEvidence | str


@dataclasses.dataclass(frozen=True)
class MergedLive:
    """Already contained in the target branch; its mount is still in use."""


@dataclasses.dataclass(frozen=True)
class MergedOrphan:
    """Already contained in the target branch; nothing holds it any more."""


StateBranchState = Union[  # noqa: UP007 -- see the `StateMountState` note
    UnmergedIneligible, UnmergedEligible, MergedLive, MergedOrphan
]


def classify_branch(
    sidecar_root: Path,
    checkout: Path,
    branch_name: str,
    project_root: Path,
) -> StateBranchState:
    """Classify one sidecar branch against the current tips. Never raises.

    ``checkout`` is the project checkout whose mounted branch is the merge
    target and whose HEAD the project-side evidence is measured against;
    ``project_root`` anchors the project's shared ref and object namespace.
    Totality is structural -- every git call below goes through a helper
    answering ``None``/``False`` instead of raising -- and the outer guard is
    the last line of defence on the hook path, where an exception is the one
    failure convergence must not introduce.
    """
    try:
        return _classify_branch(sidecar_root, checkout, branch_name, project_root)
    except (GitUnavailableError, OSError):
        return UnmergedIneligible(reason=IneligibilityReason.MAPPING_UNRESOLVABLE)


def _classify_branch(
    sidecar_root: Path,
    checkout: Path,
    branch_name: str,
    project_root: Path,
) -> StateBranchState:
    # The mapping is resolved first on purpose: a branch nobody can trace back
    # to project work is never a deletion candidate, however contained it is.
    project_branch = gitp.get_branch_config(sidecar_root, branch_name, PROJECT_BRANCH_CONFIG_SUFFIX)
    if not project_branch:
        return UnmergedIneligible(reason=IneligibilityReason.MAPPING_MISSING)
    resolved = gitp.resolve_branch_ref(project_root, project_branch)
    if resolved is None:
        return UnmergedIneligible(reason=IneligibilityReason.MAPPING_UNRESOLVABLE)

    base_branch = _mounted_branch(checkout, sidecar_common_dir(sidecar_root))
    if base_branch is not None and gitp.is_ancestor(sidecar_root, branch_name, base_branch):
        if gitp.branch_is_checked_out(sidecar_root, branch_name):
            return MergedLive()
        return MergedOrphan()

    head = git_output(checkout, "rev-parse", "HEAD")
    evidence = None if head is None else _merge_evidence(project_root, head, resolved)
    if evidence is not None:
        return UnmergedEligible(evidence=evidence)
    if not gitp.branch_exists(project_root, project_branch):
        return UnmergedIneligible(reason=IneligibilityReason.PROJECT_BRANCH_DELETED)
    return UnmergedIneligible(reason=IneligibilityReason.PROJECT_BRANCH_NOT_MERGED)


def _merge_evidence(project_root: Path, head: str, project_branch_ref: str) -> MergeEvidence | None:
    """Positive evidence that ``project_branch_ref`` landed on ``head``, else ``None``.

    The ancestor test runs first because it is a cheap graph walk covering
    merge commits, fast-forwards and rebase merges -- keeping the common case
    (nothing to do) to one walk per branch, which is what makes convergence
    affordable on the SessionStart path. Only when it fails does the more
    expensive squash-merge probe run (see ``_sidecar_git``, which documents the
    unreachable object it writes into the project's store).
    """
    if gitp.is_ancestor(project_root, project_branch_ref, head):
        return MergeEvidence.ANCESTOR

    if gitp.patch_already_applied(project_root, head, project_branch_ref):
        return MergeEvidence.SQUASHED_TREE
    return None


def _mounted_branch(checkout: Path, expected_common_dir: Path) -> str | None:
    state = classify_mount(checkout, expected_common_dir=expected_common_dir)
    return state.branch if isinstance(state, SidecarWorktree) else None


# --- convergence ------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ConvergeResult:
    """What a convergence run did, or would do under ``dry_run``."""

    merged: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    aborted: tuple[str, ...] = ()
    # branch -> git's own reason. Distinct from `aborted`: nothing was merged
    # and nothing conflicted, so the branch is still exactly as eligible as it
    # was and the next run will retry it once the cause is gone.
    failed: Mapping[str, str] = dataclasses.field(default_factory=lambda: MappingProxyType({}))
    # Carried so the callers that report convergence (a finalize-chain log
    # line, the session banner) can name each skip's reason without paying for
    # a second classification pass over the same branches.
    states: Mapping[str, StateBranchState] = dataclasses.field(
        default_factory=lambda: MappingProxyType({})
    )


def _default_lock(target_mount: Path) -> AbstractContextManager[object]:
    """The per-mount commit lock convergence holds for a whole run.

    Named rather than inlined so there is one place that binds the real lock
    and so the single-lock rule stays visible: convergence takes the *target*
    mount's lock, never a source mount's, which makes a lock-ordering cycle
    unrepresentable rather than merely unlikely. The lock itself lives in the
    commit module because every other holder (finalize commit, Stop-hook
    commit) is a commit.
    """
    return mount_lock(target_mount)


@dataclasses.dataclass(frozen=True)
class _ConvergencePlan:
    """What a run would do, computed before anything is touched."""

    states: Mapping[str, StateBranchState]
    eligible: tuple[str, ...]
    orphaned: tuple[str, ...]
    skipped: tuple[str, ...]


def converge(
    sidecar_root: Path,
    checkout: Path,
    project_root: Path,
    *,
    dry_run: bool = False,
    lock: AbstractContextManager[object] | None = None,
    post_merge_hook: Callable[[Path, str], None] | None = None,
) -> ConvergeResult:
    """Bring every eligible state branch into the branch mounted at ``checkout``.

    Plan first, then act -- so ``dry_run`` reports the plan the real run would
    execute rather than a second derivation of it. Conflicts abort (no operator
    is present on these channels), and a fixed-point run takes no lock and
    writes nothing at all. ``post_merge_hook`` is the seam for the state
    reconciler, invoked with the target mount and the branch just merged.
    """
    mount_state = classify_mount(checkout, expected_common_dir=sidecar_common_dir(sidecar_root))
    if not isinstance(mount_state, SidecarWorktree):
        return ConvergeResult()

    plan = _plan_convergence(sidecar_root, checkout, project_root)
    if dry_run or not (plan.eligible or plan.orphaned):
        return ConvergeResult(
            merged=plan.eligible,
            deleted=plan.orphaned,
            skipped=plan.skipped,
            states=plan.states,
        )

    mount = Path(checkout) / MOUNT_DIRNAME
    with _default_lock(mount) if lock is None else lock:
        merged, aborted, failed = _merge_eligible(
            sidecar_root, checkout, mount, plan.eligible, post_merge_hook
        )
        orphaned = plan.orphaned + _newly_orphaned(sidecar_root, checkout, project_root, merged)
        deleted, refused = _delete_orphans(sidecar_root, mount, orphaned, mount_state.branch)
    return ConvergeResult(
        merged=merged,
        deleted=deleted,
        skipped=plan.skipped + refused,
        aborted=aborted,
        failed=failed,
        states=plan.states,
    )


def _plan_convergence(sidecar_root: Path, checkout: Path, project_root: Path) -> _ConvergencePlan:
    states = {
        branch: classify_branch(sidecar_root, checkout, branch, project_root)
        for branch in gitp.branches_with_prefix(sidecar_root, STATE_BRANCH_PREFIX)
    }
    eligible = tuple(b for b, s in states.items() if isinstance(s, UnmergedEligible))
    orphaned = tuple(b for b, s in states.items() if isinstance(s, MergedOrphan))
    return _ConvergencePlan(
        states=MappingProxyType(states),
        eligible=eligible,
        orphaned=orphaned,
        skipped=tuple(b for b in states if b not in eligible and b not in orphaned),
    )


def _newly_orphaned(
    sidecar_root: Path, checkout: Path, project_root: Path, merged: tuple[str, ...]
) -> tuple[str, ...]:
    """Branches this run's own merges just turned into deletion candidates.

    The plan is computed before anything is touched, so a branch merged here
    was ``UnmergedEligible`` at plan time and cannot appear in the plan's
    orphan set -- yet the moment its state lands in the target branch and no
    mount holds it, it is exactly what ``_delete_orphans`` exists to remove.
    Re-classifying *only* the branches this run merged is what lets one call
    reach the fixed point, rather than leaving a branch that a second,
    identical call would delete.
    """
    return tuple(
        branch
        for branch in merged
        if isinstance(classify_branch(sidecar_root, checkout, branch, project_root), MergedOrphan)
    )


def _merge_eligible(
    sidecar_root: Path,
    checkout: Path,
    mount: Path,
    branches: tuple[str, ...],
    post_merge_hook: Callable[[Path, str], None] | None,
) -> tuple[tuple[str, ...], tuple[str, ...], Mapping[str, str]]:
    """Merge each branch into the mount; return ``(merged, aborted, failed)``.

    ``failed`` maps a branch to git's own reason, and is kept apart from
    ``aborted`` because the two need opposite advice: an aborted branch wants
    an operator to resolve a conflict, a failed one wants the environment
    fixed before any merge is attempted at all.
    """
    merged: list[str] = []
    aborted: list[str] = []
    failed: dict[str, str] = {}
    for branch in branches:
        result = merge_back(sidecar_root, checkout, branch, allow_conflict_markers=False)
        if result.outcome is MergeOutcome.FAILED:
            failed[branch] = result.detail
            continue
        if result.outcome is MergeOutcome.CONFLICTED:
            aborted.append(branch)
            continue
        merged.append(branch)
        if post_merge_hook is not None:
            post_merge_hook(mount, branch)
    return tuple(merged), tuple(aborted), MappingProxyType(failed)


def _delete_orphans(
    sidecar_root: Path, mount: Path, branches: tuple[str, ...], base_branch: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Delete each orphan; return ``(deleted, refused)``."""
    deleted: list[str] = []
    refused: list[str] = []
    for branch in branches:
        dropped = _delete_contained_branch(sidecar_root, mount, branch, base_branch)
        (deleted if dropped else refused).append(branch)
    if deleted:
        run_git(sidecar_root, "worktree", "prune")
    return tuple(deleted), tuple(refused)


def _delete_contained_branch(
    sidecar_root: Path, mount: Path, branch: str, base_branch: str
) -> bool:
    """Delete ``branch`` only while it is still contained in ``base_branch``.

    Two independent guards: the ancestry is re-checked here rather than
    trusted from classification time, and the delete runs *in the mount* --
    whose HEAD is the base branch -- with ``-d`` rather than ``-D``, so git's
    own "not fully merged" refusal checks the same property again. Run from the
    sidecar root, ``-d`` would measure containment against the sidecar's own
    (normally detached) HEAD and refuse every deletion.
    """
    if not gitp.is_ancestor(sidecar_root, branch, base_branch):
        return False
    return gitp.delete_branch_if_merged(mount, branch)


# --- dropping an unmerged branch (explicit, two-step) -----------------------


@dataclasses.dataclass(frozen=True)
class DropPrecondition:
    ready: bool
    reason: str = ""


def can_drop_branch(sidecar_root: Path, branch: str) -> DropPrecondition:
    """Report whether ``branch`` could be dropped right now.

    Callers check this *before* prompting for confirmation: git refuses to
    delete a branch a worktree holds, and surfacing that after the operator
    confirmed a destructive action is the worst possible moment.
    """
    if gitp.branch_is_checked_out(sidecar_root, branch):
        return DropPrecondition(
            ready=False,
            reason=f"{branch} is checked out in a state mount; remove that mount first",
        )
    if not gitp.branch_exists(sidecar_root, branch):
        return DropPrecondition(ready=False, reason=f"{branch} does not exist")
    return DropPrecondition(ready=True)


def drop_branch(sidecar_root: Path, branch: str) -> None:
    """Delete ``branch`` whether or not it was merged.

    The only path here that can discard unmerged state, reached through the
    explicit verb and never from convergence.
    """
    precondition = can_drop_branch(sidecar_root, branch)
    if not precondition.ready:
        raise BranchDropRefused(precondition.reason)
    gitp.run_or_raise(sidecar_root, BranchDropRefused, "branch", "-D", branch)
