"""Shared git-backed fixtures for the sidecar test suites.

Every builder here drives *real* ``git worktree`` / ``git merge`` / ``git
branch`` commands under a ``tmp_path``; nothing about git is mocked, because
the premise the sidecar modules exist to prove rests on verified git
behaviour -- a mocked git subprocess would prove nothing about it. Used by
``test_sidecar_mount.py`` (the mount slot) and ``test_sidecar_convergence.py``
(the branch slot and convergence), which split along the same seam as the
modules they cover; the other sidecar suites keep the smaller builders they
already carry.

Not a test module: no ``test_`` prefix, so pytest never collects it, and
plain sibling import (``scripts/`` has no ``__init__.py``, so pytest's prepend
import mode puts it on ``sys.path[0]``) is what the two test files use.
"""

from __future__ import annotations

import dataclasses
import subprocess
from collections.abc import Sequence
from pathlib import Path

import _sidecar_mount

IDENTITY = ("-c", "user.email=test@example.com", "-c", "user.name=Test")

SKELETON_SUBDIRS = (
    "decisions/drafts",
    "specs",
    "sentinel_reports",
    "skill_genesis_reports",
    "metrics_reports",
    "idea_ledgers",
    "eval_ledger",
)


class NullLock:
    """No-op lock, injected via `converge(..., lock=...)`.

    `_sidecar_commit.py` owns the real per-mount commit lock; the convergence
    suite passes this no-op explicitly so it never exercises real lock
    contention, which belongs to that module's own test suite.
    """

    def __enter__(self) -> NullLock:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


# --- git plumbing ----------------------------------------------------------


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def configure_identity(repo: Path) -> None:
    """Pin an identity in the repo itself, not just per-commit.

    `git merge --no-ff` and `git merge --squash` create commits without going
    through `commit_all`, so a fixture relying on the machine's *global* git
    identity passes here and fails on a machine (or CI runner) that has none.
    """
    git_ok(repo, "config", "user.email", "test@example.com")
    git_ok(repo, "config", "user.name", "Test")


def commit_all(repo: Path, message: str) -> None:
    git_ok(repo, "add", "-A")
    git_ok(repo, *IDENTITY, "commit", "-q", "-m", message)


def worktree_git_dir(checkout: Path) -> Path:
    """Resolve a worktree's real git-dir from its `.git` pointer file."""
    result = git_ok(checkout, "rev-parse", "--git-dir")
    git_dir = Path(result.stdout.strip())
    return git_dir if git_dir.is_absolute() else (checkout / git_dir).resolve()


# --- fixture builders --------------------------------------------------------


def init_plain_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    git_ok(repo_root, "init", "-q", "-b", "main")
    configure_identity(repo_root)
    (repo_root / "f.txt").write_text("x\n")
    commit_all(repo_root, "seed")


def init_sidecar(sidecar_root: Path, *, subdirs: Sequence[str] = SKELETON_SUBDIRS) -> None:
    """A sidecar repo: seeded skeleton, committed on `main`, then detached.

    Mirrors `praxion-sidecar init`'s own sequence (`ARCH_WT_RULING.md` sec.
    5): `main` must stay free for the project's own mount to check out.
    """
    sidecar_root.mkdir(parents=True, exist_ok=True)
    git_ok(sidecar_root, "init", "-q", "-b", "main")
    configure_identity(sidecar_root)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("seed\n")
    _sidecar_mount.seed_skeleton(sidecar_root, subdirs)
    commit_all(sidecar_root, "seed sidecar state")
    git_ok(sidecar_root, "checkout", "-q", "--detach")


def init_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    git_ok(project_root, "init", "-q", "-b", "main")
    configure_identity(project_root)
    exclude_nested_worktrees(project_root)
    (project_root / "app.py").write_text("code\n")
    commit_all(project_root, "init")


def exclude_nested_worktrees(project_root: Path) -> None:
    """Exclude the mount and the linked-worktree directory, as `link` does.

    Without it `git add -A` records a *gitlink* for every nested worktree, so
    a project-side commit carries entries the feature branch's tree lacks and
    the squashed-tree probe compares two trees that were never meant to
    differ. Reproducing the exclude block is what makes the fixture behave
    like a managed project rather than an unconfigured one.
    """
    exclude = project_root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text(f"/{_sidecar_mount.MOUNT_DIRNAME}/\n/wts/\n")


def mount_main(sidecar_root: Path, project_root: Path) -> Path:
    """Mount the sidecar's `main` branch at `<project_root>/.praxion-state`."""
    _sidecar_mount.create_mount(sidecar_root, project_root, "main", project_branch="main")
    return project_root / _sidecar_mount.MOUNT_DIRNAME


def add_project_worktree(
    project_root: Path, dir_name: str, branch: str, base: str = "main"
) -> Path:
    checkout = project_root / "wts" / dir_name
    git_ok(project_root, "worktree", "add", "-q", str(checkout), "-b", branch, base)
    # The feature branch must genuinely diverge on the PROJECT side. Without a
    # commit of its own it is trivially an ancestor of `main`, every
    # eligibility assertion below passes or fails vacuously, and `merge
    # --squash` has nothing to squash.
    (checkout / f"{dir_name}.py").write_text(f"{dir_name} feature\n")
    commit_all(checkout, f"{dir_name} feature work")
    return checkout


def mount_worktree(
    sidecar_root: Path,
    checkout: Path,
    sidecar_branch: str,
    *,
    base_branch: str,
    project_branch: str,
) -> Path:
    _sidecar_mount.create_mount(
        sidecar_root,
        checkout,
        sidecar_branch,
        project_branch=project_branch,
        base_branch=base_branch,
    )
    return checkout / _sidecar_mount.MOUNT_DIRNAME


@dataclasses.dataclass(frozen=True)
class DivergedFixture:
    sidecar_root: Path
    project_root: Path
    main_mount: Path
    wt_checkout: Path
    wt_mount: Path
    project_branch: str
    sidecar_branch: str


def build_diverged_fixture(tmp_path: Path, *, name: str = "x") -> DivergedFixture:
    """Sidecar + main mount + one project worktree with a real, unmerged
    state commit on its own sidecar branch -- the baseline every
    eligibility test starts from.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    main_mount = mount_main(sidecar_root, project_root)

    project_branch = f"feat/{name}"
    sidecar_branch = f"wt/{name}"
    wt_checkout = add_project_worktree(project_root, name, project_branch)
    wt_mount = mount_worktree(
        sidecar_root, wt_checkout, sidecar_branch, base_branch="main", project_branch=project_branch
    )
    (wt_mount / ".ai-state" / "DESIGN.md").write_text(f"{name}-change\n")
    commit_all(wt_mount, f"{name} state")

    return DivergedFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        wt_checkout=wt_checkout,
        wt_mount=wt_mount,
        project_branch=project_branch,
        sidecar_branch=sidecar_branch,
    )


@dataclasses.dataclass(frozen=True)
class MixedFixture:
    sidecar_root: Path
    project_root: Path
    main_mount: Path
    eligible: DivergedFixture
    ineligible: DivergedFixture


def build_mixed_fixture(tmp_path: Path) -> MixedFixture:
    """One branch already merged on the project side (eligible for
    convergence) alongside one that never merges (ineligible forever) -- the
    shared starting point for the fixed-point and channel-survival tests.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    main_mount = mount_main(sidecar_root, project_root)

    eligible_branch = "wt/e"
    eligible_project_branch = "feat/e"
    eligible_checkout = add_project_worktree(project_root, "e", eligible_project_branch)
    eligible_mount = mount_worktree(
        sidecar_root,
        eligible_checkout,
        eligible_branch,
        base_branch="main",
        project_branch=eligible_project_branch,
    )
    (eligible_mount / ".ai-state" / "DESIGN.md").write_text("e-change\n")
    commit_all(eligible_mount, "e state")
    git_ok(project_root, "merge", "-q", "--no-ff", "--no-edit", eligible_project_branch)

    ineligible_branch = "wt/i"
    ineligible_project_branch = "feat/i"
    ineligible_checkout = add_project_worktree(project_root, "i", ineligible_project_branch)
    ineligible_mount = mount_worktree(
        sidecar_root,
        ineligible_checkout,
        ineligible_branch,
        base_branch="main",
        project_branch=ineligible_project_branch,
    )
    (ineligible_mount / ".ai-state" / "DESIGN.md").write_text("i-change\n")
    commit_all(ineligible_mount, "i state")
    # feat/i never merges into the project's main -- stays live and
    # unresolved, so eligibility runs the full ancestor-then-squashed-branch
    # check on every converge call (the fixed-point object-write exemption).

    return MixedFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        eligible=DivergedFixture(
            sidecar_root=sidecar_root,
            project_root=project_root,
            main_mount=main_mount,
            wt_checkout=eligible_checkout,
            wt_mount=eligible_mount,
            project_branch=eligible_project_branch,
            sidecar_branch=eligible_branch,
        ),
        ineligible=DivergedFixture(
            sidecar_root=sidecar_root,
            project_root=project_root,
            main_mount=main_mount,
            wt_checkout=ineligible_checkout,
            wt_mount=ineligible_mount,
            project_branch=ineligible_project_branch,
            sidecar_branch=ineligible_branch,
        ),
    )


def sidecar_snapshot(
    sidecar_root: Path, mounts: Sequence[Path], project_root: Path
) -> tuple[object, ...]:
    """A comparable snapshot of everything a fixed-point converge run must
    leave untouched: the sidecar's refs and worktree list, each mount's
    tree/HEAD, and the *project* repository's object count.

    The project's object store is in the snapshot on purpose. The squash
    probe that runs for every still-unmerged branch used to write one
    unreachable commit object into it per run -- invisible to `git status`,
    reclaimed by gc, but a write into the one repository the whole feature
    exists to keep untouched. Counting objects is what proves it no longer
    does.
    """
    refs = git_ok(sidecar_root, "for-each-ref").stdout
    worktree_list = git_ok(sidecar_root, "worktree", "list", "--porcelain").stdout
    mount_states = tuple(
        (
            git_ok(mount, "status", "--porcelain").stdout,
            git_ok(mount, "rev-parse", "HEAD").stdout.strip(),
        )
        for mount in mounts
    )
    project_objects = git_ok(project_root, "count-objects", "-v").stdout
    return (refs, worktree_list, mount_states, project_objects)
