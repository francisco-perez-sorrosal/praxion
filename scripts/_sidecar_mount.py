"""State-mount lifecycle for sidecar placement.

Every project checkout -- the main checkout and each linked worktree,
uniformly -- carries a real directory at ``<checkout>/.praxion-state`` that is
a ``git worktree`` of the sidecar repository on a branch of its own, which is
what keeps every path Praxion writes resolving *inside* the checkout the
session runs in. ``classify_mount`` names whatever sits in that slot;
``create_mount`` and ``prune_mount`` are its only two writers; ``repair_mount``
re-points the sidecar's own record after a checkout moves; ``seed_skeleton``
gives a fresh sidecar the tracked placeholders a worktree needs before it can
materialise every state subdirectory.

What happens *between* mounts -- classifying a mounted branch against the
project's tips and converging the eligible ones -- lives in
``_sidecar_convergence``, which imports this module and never the reverse:
dec-368's cohesion split, applied once more at the seam between the mount
slot and the branch slot. Git plumbing -- ref resolution, ancestry,
pointer-file and worktree-list parsing -- lives in ``_sidecar_git``, which
knows nothing of either. Every git invocation names its repository
explicitly; nothing here reads the process working directory.
"""

from __future__ import annotations

import dataclasses
import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Union

import _sidecar_git as gitp
from _git_runner import run_git

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


def describe_mount_state(state: StateMountState) -> str:
    if isinstance(state, ForeignDir):
        return state.reason
    if isinstance(state, ForeignRepo):
        return f"it is a worktree of {state.git_common_dir}"
    if isinstance(state, SidecarWorktree):
        return f"it is already mounted on {state.branch}"
    return "it is absent"


def sidecar_common_dir(sidecar_root: Path) -> Path:
    """The sidecar's git common directory, in the form a mount's ``.git`` pointer yields."""
    return (Path(sidecar_root) / ".git").resolve()


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
    state = classify_mount(checkout, expected_common_dir=sidecar_common_dir(sidecar_root))
    if not isinstance(state, Absent):
        raise MountCreationRefused(
            reason=f"{Path(checkout) / MOUNT_DIRNAME} cannot be created: {describe_mount_state(state)}"
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

    Does not gate on the mount's own dirtiness: both production callers have
    already made that check moot by the time they get here -- ``publish``
    verifies every mount is clean before it ever starts tearing one down, and
    the orphan sweep only reaches a mount whose checkout is already gone, at
    which point any uncommitted content in it went with the checkout, not
    with this call. Uncommitted mount state is protected upstream instead:
    the Stop-hook autocommit and the pre-promotion mount commit bound how
    much work a live checkout can carry uncommitted, and ``doctor`` reports
    the mount's dirtiness for as long as the checkout is still there to read
    it. The sidecar branch itself is untouched here -- dropping it is a
    separate, deliberate step (``drop_branch``) -- so its committed history
    survives a prune regardless. A locked worktree is reported, never
    forced: ``--force`` would override the lock whichever tool placed it
    (Claude Code locks worktrees it creates).
    """
    state = classify_mount(checkout, expected_common_dir=sidecar_common_dir(sidecar_root))
    if isinstance(state, Absent):
        return
    mount = Path(checkout) / MOUNT_DIRNAME
    if not isinstance(state, SidecarWorktree):
        raise MountRemovalRefused(f"{mount} is not a state mount: {describe_mount_state(state)}")

    removal = run_git(sidecar_root, "worktree", "remove", str(mount))
    if removal.returncode != 0:
        raise MountRemovalRefused(
            removal.stderr.strip() or f"git worktree remove exited {removal.returncode}"
        )
    gitp.run_or_raise(sidecar_root, MountRemovalRefused, "worktree", "prune")
