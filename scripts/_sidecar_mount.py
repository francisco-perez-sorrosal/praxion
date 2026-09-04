"""State-mount lifecycle and state-branch convergence for sidecar placement.

Three layers, in the order a reader meets them:

1. **The mount.** Every project checkout -- the main checkout and each linked
   worktree, uniformly -- carries a real directory at ``<checkout>/.praxion-state``
   that is a ``git worktree`` of the sidecar repository on a branch of its own,
   which is what keeps every path Praxion writes resolving *inside* the
   checkout the session runs in. ``classify_mount`` names whatever sits in that
   slot; ``create_mount`` and ``prune_mount`` are its only two writers.

2. **The branch.** Each mount holds one sidecar branch. ``classify_branch``
   answers a different question about a different slot: did the *project* work
   this branch's state belongs to land on the project's current HEAD? It is a
   pure function of the current tips -- never cached, never persisted, because
   a live worktree keeps committing state after its first convergence and any
   latched answer would be wrong for every long pipeline.

3. **Convergence.** ``converge`` merges the state branches whose project work
   provably landed, deletes the ones already contained in the target branch
   whose mount is gone, and leaves everything else as it found it. Re-running
   it at the fixed point does nothing -- which is what lets three independent
   channels call it without coordinating with each other.

Git plumbing -- ref resolution, ancestry, pointer-file and worktree-list
parsing, the squash-merge patch probe -- lives in ``_sidecar_git``, which knows
nothing of either classification. Every git invocation names its repository
explicitly; nothing here reads the process working directory.
"""

from __future__ import annotations

import dataclasses
import os
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Union

import _sidecar_git as gitp
from _git_runner import GitUnavailableError, git_output, run_git
from _sidecar_commit import mount_lock

# The mount directory name is a code constant, not configuration: four readers
# in two languages would otherwise have to learn a string nobody will change.
MOUNT_DIRNAME = ".praxion-state"

# Sidecar branches for linked project worktrees all live under this prefix; the
# main checkout's branch (`main`) is deliberately outside it, so a convergence
# scan can never nominate its own merge target as one of its sources.
STATE_BRANCH_PREFIX = "wt/"

# Machine-local, per-branch, removed with the branch by git's own branch-delete
# config cleanup. It never enters the project repository or the manifest.
PROJECT_BRANCH_CONFIG_SUFFIX = "praxion-project-branch"

STATE_DIRNAME = ".ai-state"

# A `git worktree` materialises only *tracked* content and git tracks no empty
# directory, so a fresh mount is silently missing every state subdirectory that
# happens to be empty unless the sidecar seeds a real file into each one.
SKELETON_SUBDIRS: tuple[str, ...] = (
    "decisions/drafts",
    "specs",
    "sentinel_reports",
    "skill_genesis_reports",
    "metrics_reports",
    "idea_ledgers",
    "eval_ledger",
)

_GITKEEP = ".gitkeep"

# git's own wording when `worktree add` is refused because the branch is held
# by another worktree; the captured group is that worktree's path.
_BRANCH_HELD_ELSEWHERE = re.compile(r"is already used by worktree at '([^']+)'")


class SidecarMountError(Exception):
    """A mount operation could not be carried out.

    The three subclasses are named ``...Refused`` rather than ``...Error``
    because each is a *refusal to act on a state this module recognises*,
    not a failure mid-operation -- the distinction their callers switch on.
    """


class MountCreationRefused(SidecarMountError):  # noqa: N818 - see SidecarMountError
    """The mount slot could not be claimed.

    ``git_exit_code`` is git's own exit code when git refused (128 for the
    branch-already-checked-out case, which is the invariant git enforces for
    us), and ``None`` when this module refused before running git.
    """

    def __init__(self, reason: str, git_exit_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.git_exit_code = git_exit_code


class MountBranchInUse(MountCreationRefused):  # noqa: N818 - see SidecarMountError
    """The sidecar branch this mount needs is checked out by another mount.

    A distinct type rather than a message variant because the operator's next
    move is different in kind: nothing occupies *this* checkout's slot, so the
    generic "move it aside" advice is not merely unhelpful but wrong.
    """

    def __init__(self, branch: str, holder: str) -> None:
        super().__init__(
            reason=(
                f"another checkout of this project already holds the sidecar branch "
                f"{branch!r} at {holder}; a second clone on the same machine is not "
                f"supported yet"
            ),
            git_exit_code=128,
        )
        self.branch = branch
        self.holder = holder


class MountRemovalRefused(SidecarMountError):  # noqa: N818 - see SidecarMountError
    """The mount holds state that removing it would discard or strand."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BranchDropRefused(SidecarMountError):  # noqa: N818 - see SidecarMountError
    """A branch cannot be dropped while one of its preconditions is unmet."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- the mount slot ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Absent:
    """No mount slot occupant -- the only state a mount may be created into."""


@dataclasses.dataclass(frozen=True)
class SidecarWorktree:
    """A worktree of the sidecar repository, checked out on ``branch``."""

    branch: str
    sidecar_common_dir: Path


@dataclasses.dataclass(frozen=True)
class ForeignDir:
    """Something occupies the slot that is not a usable state mount.

    ``reason`` carries the specifics, including the one case that *is* a git
    worktree but still cannot serve as a mount: a detached HEAD, which has no
    branch to commit state onto.
    """

    reason: str


@dataclasses.dataclass(frozen=True)
class ForeignRepo:
    """A checkout of some other repository sits in the slot."""

    git_common_dir: Path


# `Union`, not `X | Y`: a runtime alias in that form needs 3.10, and this module
# is imported by git hooks in consumer projects whose interpreter Praxion does
# not choose (`scripts/**` targets 3.9+ -- see the per-file-ignores note in
# `pyproject.toml`). The same constraint keeps the two enums below off `StrEnum`.
StateMountState = Union[Absent, SidecarWorktree, ForeignDir, ForeignRepo]  # noqa: UP007


def classify_mount(checkout: Path, *, expected_common_dir: Path | None = None) -> StateMountState:
    """Name whatever occupies ``<checkout>/.praxion-state``.

    Pure filesystem reads -- no subprocess -- because this runs on the
    SessionStart and ``post-checkout`` paths for every checkout, and because
    the sidecar's common directory is derivable from the ``.git`` pointer file
    alone.

    ``expected_common_dir`` is the identity check, passed by every caller
    holding a sidecar root (the reconciler that creates and repairs mounts
    included): a worktree of any *other* repository is then ``ForeignRepo``
    even when it carries a state tree of its own -- which is what makes
    ``SidecarWorktree``'s claim enforced here rather than asserted in a
    docstring. Omitted, the mounted tree's own content answers it.
    """
    mount = Path(checkout) / MOUNT_DIRNAME
    if mount.is_symlink():
        return ForeignDir(reason=f"{MOUNT_DIRNAME} is a symlink, not a real directory")
    if not mount.exists():
        return Absent()
    if not mount.is_dir():
        return ForeignDir(reason=f"{MOUNT_DIRNAME} is a file, not a directory")

    git_path = mount / ".git"
    if git_path.is_dir():
        return ForeignRepo(git_common_dir=git_path.resolve())
    if not git_path.is_file():
        return ForeignDir(reason=f"{MOUNT_DIRNAME} is a real directory with no git repository")

    worktree_git_dir = gitp.read_gitdir_pointer(git_path)
    if worktree_git_dir is None:
        return ForeignDir(reason=f"{MOUNT_DIRNAME}/.git carries no readable gitdir pointer")
    common_dir = gitp.common_dir_of_worktree(worktree_git_dir)
    if common_dir is None:
        return ForeignRepo(git_common_dir=worktree_git_dir)
    if expected_common_dir is not None:
        if common_dir != Path(expected_common_dir):
            return ForeignRepo(git_common_dir=common_dir)
    elif not (mount / STATE_DIRNAME).is_dir():
        # Without an expected common dir the only available discriminator is
        # the mounted tree's content: a worktree carrying no state tree is
        # somebody else's checkout that happens to sit at our path. Identity
        # against a *recorded* sidecar (origin / roots) belongs to the
        # placement resolver either way.
        return ForeignRepo(git_common_dir=common_dir)

    branch = gitp.head_branch(worktree_git_dir)
    if branch is None:
        return ForeignDir(reason=f"{MOUNT_DIRNAME} is on a detached HEAD, not on a state branch")
    return SidecarWorktree(branch=branch, sidecar_common_dir=common_dir)


def resolve_target_mount(path_str: str) -> Path:
    """Validate a ``--target-mount`` CLI argument and return the mount path.

    Shared by ``reconcile_ai_state.py`` and ``check_squash_safety.py`` --
    both diagnose a state mount at merge-back and both refuse anything that
    is not itself ``<checkout>/.praxion-state`` for some checkout currently on a
    state branch. A shadow symlink (``<project>/.ai-state``) or an arbitrary
    directory both fail this even when they resolve into a real mount's
    content, because the caller (``merge_back``'s post-merge seam) always
    names the mount itself, never a path that merely reaches through it.
    """
    mount = Path(path_str)
    if mount.name != MOUNT_DIRNAME:
        raise ValueError(
            f"--target-mount must name a state mount ({MOUNT_DIRNAME} directory); got {mount}"
        )
    state = classify_mount(mount.parent, expected_common_dir=None)
    if not isinstance(state, SidecarWorktree):
        raise ValueError(f"{mount} is not a state mount: {state!r}")
    return mount


def _describe(state: StateMountState) -> str:
    if isinstance(state, ForeignDir):
        return state.reason
    if isinstance(state, ForeignRepo):
        return f"it is a worktree of {state.git_common_dir}"
    if isinstance(state, SidecarWorktree):
        return f"it is already mounted on {state.branch}"
    return "it is absent"


# --- creating, seeding and removing a mount ---------------------------------


def seed_skeleton(repo_root: Path, subdirs: Sequence[str] | None = None) -> None:
    """Ensure a tracked placeholder exists in every expected state subdirectory.

    Called on the sidecar *before* its initial commit; idempotent, so the
    reconciler may call it again when a new subdirectory is added.
    """
    selected = SKELETON_SUBDIRS if subdirs is None else tuple(subdirs)
    root = Path(repo_root)
    relative_paths = []
    for subdir in selected:
        keep = root / STATE_DIRNAME / subdir / _GITKEEP
        keep.parent.mkdir(parents=True, exist_ok=True)
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
        relative_paths.append(str(keep.relative_to(root)))
    if relative_paths:
        gitp.run_or_raise(root, SidecarMountError, "add", "--", *relative_paths)


def create_mount(
    sidecar_root: Path,
    checkout: Path,
    branch: str,
    *,
    project_branch: str,
    base_branch: str | None = None,
) -> None:
    """Materialise the sidecar at ``<checkout>/.praxion-state`` on ``branch``.

    ``base_branch`` creates ``branch`` from it; omit it to check out a branch
    that already exists. Git refuses a branch already checked out elsewhere
    (exit 128); that refusal is surfaced rather than swallowed, because one
    branch per mount is an invariant git enforces so none of ours has to.
    """
    state = classify_mount(checkout, expected_common_dir=_sidecar_common_dir(sidecar_root))
    if not isinstance(state, Absent):
        raise MountCreationRefused(
            reason=f"{Path(checkout) / MOUNT_DIRNAME} cannot be created: {_describe(state)}"
        )

    # The slot is `Absent`, so any administrative entry the sidecar still holds
    # for it -- or for any other checkout -- describes a directory that is gone:
    # a `git clean -ffdx` in the project, or a sidecar copied from another
    # machine whose worktree records came with it. `worktree prune` drops
    # exactly those entries and never a live one, so it cannot cost anything
    # here, while without it git refuses the add below outright.
    run_git(sidecar_root, "worktree", "prune")

    mount = Path(checkout) / MOUNT_DIRNAME
    add_args = ["worktree", "add", "-q"]
    if base_branch is None:
        add_args += [str(mount), branch]
    else:
        add_args += ["-b", branch, str(mount), base_branch]

    result = run_git(sidecar_root, *add_args)
    if result.returncode != 0:
        held_at = _BRANCH_HELD_ELSEWHERE.search(result.stderr)
        if held_at is not None:
            raise MountBranchInUse(branch, held_at.group(1))
        raise MountCreationRefused(
            reason=result.stderr.strip() or f"git worktree add exited {result.returncode}",
            git_exit_code=result.returncode,
        )
    gitp.set_branch_config(
        sidecar_root, branch, PROJECT_BRANCH_CONFIG_SUFFIX, project_branch, error=SidecarMountError
    )


def backlink_is_stale(checkout: Path) -> bool:
    """Whether the sidecar's record of where this mount lives has gone stale.

    Moving a project directory leaves the mount's own forward pointer correct
    -- it is absolute and the sidecar did not move -- so the checkout keeps
    working while every sidecar-side operation (``worktree list``, pruning,
    merge-back bookkeeping) still believes the mount is at the old path.

    Compared through ``realpath`` on both sides: the recorded path is whatever
    string git was handed at ``worktree add`` time, so an unresolved symlink in
    a temp-directory prefix would otherwise read as a move and provoke a repair
    on every single ``link``.
    """
    mount = Path(checkout) / MOUNT_DIRNAME
    worktree_git_dir = gitp.read_gitdir_pointer(mount / ".git")
    if worktree_git_dir is None:
        return False
    recorded = gitp.recorded_worktree_path(worktree_git_dir)
    if recorded is None:
        return False
    return os.path.realpath(recorded) != os.path.realpath(mount / ".git")


def repair_mount(sidecar_root: Path, checkout: Path) -> None:
    """Point the sidecar's own record back at where the mount actually is.

    ``git worktree repair`` rewrites that one reverse pointer and touches
    nothing else; it is idempotent, so a caller that repairs a healthy mount
    merely wastes a subprocess.
    """
    mount = Path(checkout) / MOUNT_DIRNAME
    gitp.run_or_raise(sidecar_root, SidecarMountError, "worktree", "repair", str(mount))


def prune_mount(sidecar_root: Path, checkout: Path) -> None:
    """Remove ``<checkout>/.praxion-state`` from the sidecar's worktree list.

    Refuses on the two git-mechanical states in which removal would discard
    work: a dirty tree, or a mount left mid-merge. Branch-level eligibility is
    a separate question, deliberately not consulted -- dropping an unmerged
    branch is a two-step path that *starts* by removing its mount. A locked
    worktree is reported, never forced: ``--force`` would override the lock
    whichever tool placed it (Claude Code locks worktrees it creates).
    """
    state = classify_mount(checkout, expected_common_dir=_sidecar_common_dir(sidecar_root))
    if isinstance(state, Absent):
        return
    mount = Path(checkout) / MOUNT_DIRNAME
    if not isinstance(state, SidecarWorktree):
        raise MountRemovalRefused(f"{mount} is not a state mount: {_describe(state)}")

    if gitp.merge_in_progress(mount):
        raise MountRemovalRefused(f"{mount} is mid-merge; resolve or abort the merge first")
    status = gitp.porcelain_status(mount)
    if status is None:
        raise MountRemovalRefused(f"{mount} status could not be read")
    if status.strip():
        raise MountRemovalRefused(f"{mount} has uncommitted changes; commit or discard them first")

    removal = run_git(sidecar_root, "worktree", "remove", str(mount))
    if removal.returncode != 0:
        raise MountRemovalRefused(
            removal.stderr.strip() or f"git worktree remove exited {removal.returncode}"
        )
    gitp.run_or_raise(sidecar_root, MountRemovalRefused, "worktree", "prune")


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
    state = classify_mount(checkout, expected_common_dir=_sidecar_common_dir(sidecar_root))
    mount = Path(checkout) / MOUNT_DIRNAME
    if not isinstance(state, SidecarWorktree):
        raise SidecarMountError(f"{mount} is not a state mount: {_describe(state)}")
    return mount


def _sidecar_common_dir(sidecar_root: Path) -> Path:
    # Resolved, because that is the form the mount's `.git` pointer yields.
    return (Path(sidecar_root) / ".git").resolve()


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

    base_branch = _mounted_branch(checkout, _sidecar_common_dir(sidecar_root))
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
    mount_state = classify_mount(checkout, expected_common_dir=_sidecar_common_dir(sidecar_root))
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
