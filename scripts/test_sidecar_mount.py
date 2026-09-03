"""Behavioral tests for `_sidecar_mount.py` -- DS-10 (state mount lifecycle)
and DS-11 (state branch convergence).

`_sidecar_mount.py` does not exist yet (concurrent BDD/TDD with its
implementation) -- this is the RED skeleton, confirmed to fail on
`ModuleNotFoundError` before the module lands. Every fixture below drives
*real* `git worktree` / `git merge` / `git branch` commands under
`tmp_path`; nothing about git is mocked, because the whole premise this
module exists to prove (`ARCH_WT_RULING.md` sec. 4, sec. 13) rests on
verified git behaviour -- a mocked git subprocess would prove nothing about
it.

`_state_repo.py` is a sibling dependency for the *production* mount-discovery
path, but nothing under test here calls the resolver, so no
`pytest.importorskip("_state_repo")` guard is needed in this file.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py`.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import _sidecar_mount
import pytest

_IDENTITY = ("-c", "user.email=test@example.com", "-c", "user.name=Test")

_SKELETON_SUBDIRS = (
    "decisions/drafts",
    "specs",
    "sentinel_reports",
    "skill_genesis_reports",
    "metrics_reports",
    "idea_ledgers",
    "eval_ledger",
)


class _NullLock:
    """No-op lock, injected via `converge(..., lock=...)`.

    `_sidecar_commit.py` owns the real per-mount commit lock and is not
    written yet. Per the paired assignment's brief, `converge()`'s `lock=`
    keyword is assumed to default to the real lock; every test here passes
    this no-op explicitly, so the suite never depends on the commit-lock
    module landing first and never exercises real lock contention (that
    belongs to that module's own test suite).
    """

    def __enter__(self) -> _NullLock:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


# --- git plumbing ----------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _configure_identity(repo: Path) -> None:
    """Pin an identity in the repo itself, not just per-commit.

    `git merge --no-ff` and `git merge --squash` create commits without going
    through `_commit_all`, so a fixture relying on the machine's *global* git
    identity passes here and fails on a machine (or CI runner) that has none.
    """
    _git_ok(repo, "config", "user.email", "test@example.com")
    _git_ok(repo, "config", "user.name", "Test")


def _commit_all(repo: Path, message: str) -> None:
    _git_ok(repo, "add", "-A")
    _git_ok(repo, *_IDENTITY, "commit", "-q", "-m", message)


def _worktree_git_dir(checkout: Path) -> Path:
    """Resolve a worktree's real git-dir from its `.git` pointer file."""
    result = _git_ok(checkout, "rev-parse", "--git-dir")
    git_dir = Path(result.stdout.strip())
    return git_dir if git_dir.is_absolute() else (checkout / git_dir).resolve()


# --- fixture builders --------------------------------------------------------


def _init_plain_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git_ok(repo_root, "init", "-q", "-b", "main")
    _configure_identity(repo_root)
    (repo_root / "f.txt").write_text("x\n")
    _commit_all(repo_root, "seed")


def _init_sidecar(sidecar_root: Path, *, subdirs: Sequence[str] = _SKELETON_SUBDIRS) -> None:
    """A sidecar repo: seeded skeleton, committed on `main`, then detached.

    Mirrors `praxion-sidecar init`'s own sequence (`ARCH_WT_RULING.md` sec.
    5): `main` must stay free for the project's own mount to check out.
    """
    sidecar_root.mkdir(parents=True, exist_ok=True)
    _git_ok(sidecar_root, "init", "-q", "-b", "main")
    _configure_identity(sidecar_root)
    (sidecar_root / ".ai-state").mkdir()
    (sidecar_root / ".ai-state" / "DESIGN.md").write_text("seed\n")
    _sidecar_mount.seed_skeleton(sidecar_root, subdirs)
    _commit_all(sidecar_root, "seed sidecar state")
    _git_ok(sidecar_root, "checkout", "-q", "--detach")


def _init_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    _git_ok(project_root, "init", "-q", "-b", "main")
    _configure_identity(project_root)
    _exclude_nested_worktrees(project_root)
    (project_root / "app.py").write_text("code\n")
    _commit_all(project_root, "init")


def _exclude_nested_worktrees(project_root: Path) -> None:
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


def _mount_main(sidecar_root: Path, project_root: Path) -> Path:
    """Mount the sidecar's `main` branch at `<project_root>/.praxion`."""
    _sidecar_mount.create_mount(sidecar_root, project_root, "main", project_branch="main")
    return project_root / _sidecar_mount.MOUNT_DIRNAME


def _add_project_worktree(
    project_root: Path, dir_name: str, branch: str, base: str = "main"
) -> Path:
    checkout = project_root / "wts" / dir_name
    _git_ok(project_root, "worktree", "add", "-q", str(checkout), "-b", branch, base)
    # The feature branch must genuinely diverge on the PROJECT side. Without a
    # commit of its own it is trivially an ancestor of `main`, every
    # eligibility assertion below passes or fails vacuously, and `merge
    # --squash` has nothing to squash.
    (checkout / f"{dir_name}.py").write_text(f"{dir_name} feature\n")
    _commit_all(checkout, f"{dir_name} feature work")
    return checkout


def _mount_worktree(
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
class _DivergedFixture:
    sidecar_root: Path
    project_root: Path
    main_mount: Path
    wt_checkout: Path
    wt_mount: Path
    project_branch: str
    sidecar_branch: str


def _build_diverged_fixture(tmp_path: Path, *, name: str = "x") -> _DivergedFixture:
    """Sidecar + main mount + one project worktree with a real, unmerged
    state commit on its own sidecar branch -- the baseline every DS-11
    eligibility test starts from.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    main_mount = _mount_main(sidecar_root, project_root)

    project_branch = f"feat/{name}"
    sidecar_branch = f"wt/{name}"
    wt_checkout = _add_project_worktree(project_root, name, project_branch)
    wt_mount = _mount_worktree(
        sidecar_root, wt_checkout, sidecar_branch, base_branch="main", project_branch=project_branch
    )
    (wt_mount / ".ai-state" / "DESIGN.md").write_text(f"{name}-change\n")
    _commit_all(wt_mount, f"{name} state")

    return _DivergedFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        wt_checkout=wt_checkout,
        wt_mount=wt_mount,
        project_branch=project_branch,
        sidecar_branch=sidecar_branch,
    )


@dataclasses.dataclass(frozen=True)
class _MixedFixture:
    sidecar_root: Path
    project_root: Path
    main_mount: Path
    eligible: _DivergedFixture
    ineligible: _DivergedFixture


def _build_mixed_fixture(tmp_path: Path) -> _MixedFixture:
    """One branch already merged on the project side (eligible for
    convergence) alongside one that never merges (ineligible forever) -- the
    shared starting point for the fixed-point and channel-survival tests.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    main_mount = _mount_main(sidecar_root, project_root)

    eligible_branch = "wt/e"
    eligible_project_branch = "feat/e"
    eligible_checkout = _add_project_worktree(project_root, "e", eligible_project_branch)
    eligible_mount = _mount_worktree(
        sidecar_root,
        eligible_checkout,
        eligible_branch,
        base_branch="main",
        project_branch=eligible_project_branch,
    )
    (eligible_mount / ".ai-state" / "DESIGN.md").write_text("e-change\n")
    _commit_all(eligible_mount, "e state")
    _git_ok(project_root, "merge", "-q", "--no-ff", "--no-edit", eligible_project_branch)

    ineligible_branch = "wt/i"
    ineligible_project_branch = "feat/i"
    ineligible_checkout = _add_project_worktree(project_root, "i", ineligible_project_branch)
    ineligible_mount = _mount_worktree(
        sidecar_root,
        ineligible_checkout,
        ineligible_branch,
        base_branch="main",
        project_branch=ineligible_project_branch,
    )
    (ineligible_mount / ".ai-state" / "DESIGN.md").write_text("i-change\n")
    _commit_all(ineligible_mount, "i state")
    # feat/i never merges into the project's main -- stays live and
    # unresolved, so eligibility runs the full ancestor-then-squashed-branch
    # check on every converge call (the fixed-point object-write exemption).

    return _MixedFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        eligible=_DivergedFixture(
            sidecar_root=sidecar_root,
            project_root=project_root,
            main_mount=main_mount,
            wt_checkout=eligible_checkout,
            wt_mount=eligible_mount,
            project_branch=eligible_project_branch,
            sidecar_branch=eligible_branch,
        ),
        ineligible=_DivergedFixture(
            sidecar_root=sidecar_root,
            project_root=project_root,
            main_mount=main_mount,
            wt_checkout=ineligible_checkout,
            wt_mount=ineligible_mount,
            project_branch=ineligible_project_branch,
            sidecar_branch=ineligible_branch,
        ),
    )


def _sidecar_snapshot(sidecar_root: Path, mounts: Sequence[Path]) -> tuple[object, ...]:
    """A comparable snapshot of everything a fixed-point converge run must
    leave untouched: refs, the worktree list, and each mount's tree/HEAD.

    Deliberately excludes the *project* repository's object database -- the
    named, scoped exemption (`ARCH_WT_RULING.md` sec. 13.4): the
    squashed-branch test writes an unreachable loose object there on every
    run against an ineligible branch, by design.
    """
    refs = _git_ok(sidecar_root, "for-each-ref").stdout
    worktree_list = _git_ok(sidecar_root, "worktree", "list", "--porcelain").stdout
    mount_states = tuple(
        (
            _git_ok(mount, "status", "--porcelain").stdout,
            _git_ok(mount, "rev-parse", "HEAD").stdout.strip(),
        )
        for mount in mounts
    )
    return (refs, worktree_list, mount_states)


# --- StateMountState (DS-10) -------------------------------------------------


def test_absent_mount_slot_classifies_as_absent(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.Absent)


def test_real_sidecar_worktree_classifies_as_sidecar_worktree(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.SidecarWorktree)
    assert result.branch == "main"
    assert result.sidecar_common_dir == (sidecar_root / ".git").resolve()


def test_foreign_real_directory_at_mount_slot_classifies_as_foreign_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _init_project(project_root)
    (project_root / _sidecar_mount.MOUNT_DIRNAME).mkdir()

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.ForeignDir)


def test_worktree_of_a_different_repository_classifies_as_foreign_repo(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    other_repo = tmp_path / "unrelated-repo"
    _init_project(project_root)
    _init_plain_repo(other_repo)

    _git_ok(
        other_repo,
        "worktree",
        "add",
        "-q",
        str(project_root / _sidecar_mount.MOUNT_DIRNAME),
        "-b",
        "borrowed",
        "main",
    )

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.ForeignRepo)
    assert result.git_common_dir == (other_repo / ".git").resolve()


def test_another_managed_repos_worktree_is_foreign_once_the_sidecar_root_is_known(
    tmp_path: Path,
) -> None:
    """Content alone cannot prove identity; the expected common dir can.

    A second Praxion-managed repository carries its own `.ai-state/`, so a
    worktree of *it* sitting at `<project>/.praxion` is structurally
    indistinguishable from ours. Passing the real sidecar's common directory
    is what separates them -- and omitting it must keep today's behaviour.
    """
    sidecar_root = tmp_path / "sidecar"
    other_sidecar = tmp_path / "other-sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_sidecar(other_sidecar)
    _init_project(project_root)
    _git_ok(
        other_sidecar,
        "worktree",
        "add",
        "-q",
        str(project_root / _sidecar_mount.MOUNT_DIRNAME),
        "main",
    )

    without_identity = _sidecar_mount.classify_mount(project_root)
    with_identity = _sidecar_mount.classify_mount(
        project_root, expected_common_dir=(sidecar_root / ".git").resolve()
    )

    assert isinstance(without_identity, _sidecar_mount.SidecarWorktree)
    assert isinstance(with_identity, _sidecar_mount.ForeignRepo)
    assert with_identity.git_common_dir == (other_sidecar / ".git").resolve()


def test_the_real_sidecars_mount_still_classifies_as_sidecar_worktree_with_identity(
    tmp_path: Path,
) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)

    result = _sidecar_mount.classify_mount(
        project_root, expected_common_dir=(sidecar_root / ".git").resolve()
    )

    assert isinstance(result, _sidecar_mount.SidecarWorktree)
    assert result.branch == "main"


def test_the_module_imports_on_the_consumer_hook_interpreter_floor(tmp_path: Path) -> None:
    """`scripts/` is imported by git hooks under a consumer project's own
    interpreter, which Praxion does not choose -- `pyproject.toml` pins that
    floor at 3.9. Ruff cannot see the violation (`target-version = "py311"`
    makes `StrEnum` and `X | Y` the *preferred* spelling), so the floor needs
    its own canary. Skipped, never silently passed, when no 3.9 is installed.
    """
    interpreter = shutil.which("python3.9")
    if interpreter is None:
        pytest.skip("no python3.9 on PATH to check the consumer-hook floor against")

    module_dir = Path(_sidecar_mount.__file__).parent
    result = subprocess.run(
        [
            interpreter,
            "-c",
            f"import sys; sys.path.insert(0, {str(module_dir)!r}); import _sidecar_mount",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


# --- create_mount -------------------------------------------------------------


def test_create_mount_refuses_a_branch_already_checked_out_elsewhere(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    _init_sidecar(sidecar_root)
    _init_project(project_a)
    _init_project(project_b)
    _mount_main(sidecar_root, project_a)

    with pytest.raises(_sidecar_mount.MountCreationRefused) as excinfo:
        _sidecar_mount.create_mount(sidecar_root, project_b, "main", project_branch="main")

    assert excinfo.value.git_exit_code == 128


def test_create_mount_names_the_holder_when_the_branch_is_mounted_elsewhere(
    tmp_path: Path,
) -> None:
    """Nothing occupies the second checkout's own slot, so a refusal that only
    quotes git's wording sends the operator hunting for a file that is not
    there. The message has to name the collision and where it lives."""
    sidecar_root = tmp_path / "sidecar"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    _init_sidecar(sidecar_root)
    _init_project(project_a)
    _init_project(project_b)
    _mount_main(sidecar_root, project_a)

    with pytest.raises(_sidecar_mount.MountBranchInUse) as excinfo:
        _sidecar_mount.create_mount(sidecar_root, project_b, "main", project_branch="main")

    assert excinfo.value.branch == "main"
    assert Path(excinfo.value.holder) == project_a / _sidecar_mount.MOUNT_DIRNAME
    assert "second clone on the same machine is not supported yet" in str(excinfo.value)


def test_create_mount_clears_a_stale_worktree_record_before_claiming_the_slot(
    tmp_path: Path,
) -> None:
    """A mount directory removed outside git's knowledge leaves a record git
    then refuses to add over -- the `git clean -ffdx` case, and the case of a
    sidecar copied from another machine with its worktree records in tow."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    mount = _mount_main(sidecar_root, project_root)
    shutil.rmtree(mount)

    _sidecar_mount.create_mount(sidecar_root, project_root, "main", project_branch="main")

    assert (mount / ".ai-state" / "DESIGN.md").read_text(encoding="utf-8") == "seed\n"


def test_create_mount_leaves_a_live_worktree_record_of_another_checkout_alone(
    tmp_path: Path,
) -> None:
    """The inverse guard on the pruning above: clearing stale records must
    never reach a mount whose directory is still standing."""
    sidecar_root = tmp_path / "sidecar"
    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    _init_sidecar(sidecar_root)
    _init_project(project_a)
    _init_project(project_b)
    live = _mount_main(sidecar_root, project_a)
    _git_ok(sidecar_root, "branch", "wt/b", "main")

    _sidecar_mount.create_mount(sidecar_root, project_b, "wt/b", project_branch="main")

    assert str(live) in _git_ok(sidecar_root, "worktree", "list").stdout


def test_repair_mount_repoints_the_sidecar_record_at_the_moved_checkout(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)
    moved = tmp_path / "project-moved"
    shutil.move(str(project_root), str(moved))
    assert _sidecar_mount.backlink_is_stale(moved)

    _sidecar_mount.repair_mount(sidecar_root, moved)

    assert not _sidecar_mount.backlink_is_stale(moved)


def test_backlink_is_not_stale_for_a_checkout_that_never_moved(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)

    assert not _sidecar_mount.backlink_is_stale(project_root)


def test_create_mount_records_project_branch_mapping_in_sidecar_config_only(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="map")

    sidecar_value = _git_ok(
        fixture.sidecar_root,
        "config",
        "--get",
        f"branch.{fixture.sidecar_branch}.praxion-project-branch",
    ).stdout.strip()
    project_lookup = _git(
        fixture.project_root,
        "config",
        "--get",
        f"branch.{fixture.sidecar_branch}.praxion-project-branch",
    )

    assert sidecar_value == fixture.project_branch
    assert project_lookup.returncode != 0


# --- Skeleton seeding -----------------------------------------------------------


def test_fresh_mount_contains_every_expected_ai_state_subdirectory(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)  # seeds _SKELETON_SUBDIRS before the initial commit
    _init_project(project_root)

    mount = _mount_main(sidecar_root, project_root)

    for subdir in _SKELETON_SUBDIRS:
        gitkeep = mount / ".ai-state" / subdir / ".gitkeep"
        assert gitkeep.exists(), f"missing seeded {subdir}"


# --- merge_back -----------------------------------------------------------------


def test_merge_back_makes_a_worktree_edit_visible_in_the_target_checkout(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="mb")

    result = _sidecar_mount.merge_back(
        fixture.sidecar_root,
        fixture.project_root,
        fixture.sidecar_branch,
        allow_conflict_markers=False,
    )

    assert result.conflicted is False
    assert (fixture.main_mount / ".ai-state" / "DESIGN.md").read_text() == "mb-change\n"


# --- prune_mount ----------------------------------------------------------------


def test_prune_mount_refuses_a_dirty_mount(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="dirty")
    (fixture.wt_mount / ".ai-state" / "DESIGN.md").write_text("uncommitted\n")

    with pytest.raises(_sidecar_mount.MountRemovalRefused):
        _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)


def test_prune_mount_refuses_a_mount_left_mid_merge(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="mid")
    git_dir = _worktree_git_dir(fixture.wt_mount)
    head = _git_ok(fixture.sidecar_root, "rev-parse", "main").stdout
    (git_dir / "MERGE_HEAD").write_text(head)

    with pytest.raises(_sidecar_mount.MountRemovalRefused):
        _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)


# --- StateBranchState / classify_branch (DS-11) ------------------------------


def test_state_branch_state_variants_are_frozen_against_mutation() -> None:
    result = _sidecar_mount.UnmergedIneligible(reason="ProjectBranchNotMerged")

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.reason = "MappingMissing"  # type: ignore[misc]


def test_classify_branch_reports_not_merged_before_any_project_merge(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="pending")

    result = _sidecar_mount.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_mount.UnmergedIneligible(reason="ProjectBranchNotMerged")


def test_classify_branch_detects_a_regular_merge_as_ancestor_evidence(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="anc")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)

    result = _sidecar_mount.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_mount.UnmergedEligible(evidence="Ancestor")


def test_classify_branch_detects_a_github_style_squash_merge_the_ancestor_test_misses(
    tmp_path: Path,
) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="sq")

    # A GitHub squash-merge: the feature branch's tree lands in one new
    # commit on main with no ancestry link back to the branch -- exactly the
    # shape the plain ancestor test cannot see.
    _git_ok(fixture.project_root, "merge", "-q", "--squash", fixture.project_branch)
    _commit_all(fixture.project_root, f"squash-merge {fixture.project_branch}")

    ancestor_only = _git(
        fixture.project_root, "merge-base", "--is-ancestor", fixture.project_branch, "HEAD"
    )
    assert ancestor_only.returncode != 0, (
        "fixture invariant: the ancestor test alone must fail here"
    )

    result = _sidecar_mount.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_mount.UnmergedEligible(evidence="SquashedTree")


def test_classify_branch_never_raises_on_an_unresolvable_recorded_ref(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)
    _git_ok(sidecar_root, "branch", "wt/gone", "main")
    _git_ok(sidecar_root, "config", "branch.wt/gone.praxion-project-branch", "feat/never-existed")

    result = _sidecar_mount.classify_branch(sidecar_root, project_root, "wt/gone", project_root)

    assert result == _sidecar_mount.UnmergedIneligible(reason="MappingUnresolvable")


def test_classify_branch_reports_missing_mapping_without_raising(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    _init_sidecar(sidecar_root)
    _init_project(project_root)
    _mount_main(sidecar_root, project_root)
    _git_ok(sidecar_root, "branch", "wt/unmapped", "main")  # predates the mapping scheme

    result = _sidecar_mount.classify_branch(sidecar_root, project_root, "wt/unmapped", project_root)

    assert result == _sidecar_mount.UnmergedIneligible(reason="MappingMissing")


def test_classify_branch_reflects_current_tips_not_a_cached_state(tmp_path: Path) -> None:
    """No persisted state: once a branch's sidecar commits move past what
    was converged, the next call re-classifies from the current tips -- it
    does not stay latched at the old result.
    """
    fixture = _build_diverged_fixture(tmp_path, name="live")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    merged_once = _sidecar_mount.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )
    assert isinstance(merged_once, _sidecar_mount.MergedLive)

    # The worktree is still live and keeps writing state after convergence.
    (fixture.wt_mount / ".ai-state" / "DESIGN.md").write_text("live-more\n")
    _commit_all(fixture.wt_mount, "more state after convergence")

    result = _sidecar_mount.classify_branch(
        fixture.sidecar_root, fixture.project_root, fixture.sidecar_branch, fixture.project_root
    )

    assert result == _sidecar_mount.UnmergedEligible(evidence="Ancestor")


# --- converge() ------------------------------------------------------------------


def test_converge_aborts_a_genuine_conflict_and_leaves_the_mount_clean(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="conflict")
    # Independent, conflicting edit on the MAIN sidecar branch itself.
    (fixture.main_mount / ".ai-state" / "DESIGN.md").write_text("main-change\n")
    _commit_all(fixture.main_mount, "main state, diverging")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)

    result = _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )

    assert fixture.sidecar_branch in result.aborted
    git_dir = _worktree_git_dir(fixture.main_mount)
    assert not (git_dir / "MERGE_HEAD").exists()
    assert _git_ok(fixture.main_mount, "status", "--porcelain").stdout == ""
    assert _git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode == 0


def test_converge_is_a_zero_write_no_op_at_the_fixed_point(tmp_path: Path) -> None:
    fixture = _build_mixed_fixture(tmp_path)
    mounts = (fixture.main_mount, fixture.eligible.wt_mount, fixture.ineligible.wt_mount)

    first = _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    assert fixture.eligible.sidecar_branch in first.merged

    snapshot_after_first = _sidecar_snapshot(fixture.sidecar_root, mounts)
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    snapshot_after_second = _sidecar_snapshot(fixture.sidecar_root, mounts)
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    snapshot_after_third = _sidecar_snapshot(fixture.sidecar_root, mounts)

    assert snapshot_after_second == snapshot_after_first
    assert snapshot_after_third == snapshot_after_second


def test_ineligible_branch_survives_converge_across_three_different_checkouts(
    tmp_path: Path,
) -> None:
    fixture = _build_mixed_fixture(tmp_path)
    before_commit = _git_ok(
        fixture.sidecar_root, "rev-parse", fixture.ineligible.sidecar_branch
    ).stdout.strip()

    # Channel 1: the project post-merge finalize chain, running in the main checkout.
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    # Channel 2: the SessionStart heal, running inside a linked worktree's own
    # checkout -- a different `checkout` argument, same sidecar repo.
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.eligible.wt_checkout, fixture.project_root, lock=_NullLock()
    )
    # Channel 3: the main checkout again (mirrors the explicit /merge-worktree
    # channel resolving to the same call shape once nothing new is eligible).
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )

    after_commit = _git_ok(
        fixture.sidecar_root, "rev-parse", fixture.ineligible.sidecar_branch
    ).stdout.strip()
    mapping = _git_ok(
        fixture.sidecar_root,
        "config",
        "--get",
        f"branch.{fixture.ineligible.sidecar_branch}.praxion-project-branch",
    ).stdout.strip()

    assert after_commit == before_commit
    assert mapping == fixture.ineligible.project_branch


def test_converge_dry_run_reports_the_plan_and_mutates_nothing(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="dry")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    snapshot_before = _sidecar_snapshot(
        fixture.sidecar_root, (fixture.main_mount, fixture.wt_mount)
    )

    result = _sidecar_mount.converge(
        fixture.sidecar_root,
        fixture.project_root,
        fixture.project_root,
        dry_run=True,
        lock=_NullLock(),
    )

    assert fixture.sidecar_branch in result.merged
    snapshot_after = _sidecar_snapshot(fixture.sidecar_root, (fixture.main_mount, fixture.wt_mount))
    assert snapshot_after == snapshot_before


def test_converge_automatically_deletes_a_merged_orphan_branch(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="orphan")
    _git_ok(fixture.project_root, "merge", "-q", "--no-ff", "--no-edit", fixture.project_branch)
    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )
    # The mount is removed first, then the project worktree -- the lifecycle
    # order that turns MergedLive into MergedOrphan.
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)
    _git_ok(fixture.project_root, "worktree", "remove", "--force", str(fixture.wt_checkout))

    _sidecar_mount.converge(
        fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
    )

    assert _git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode != 0


def test_converge_never_auto_drops_an_unmerged_ineligible_branch(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="keep")
    _sidecar_mount.prune_mount(
        fixture.sidecar_root, fixture.wt_checkout
    )  # unblocks drop_branch, not converge

    for _ in range(3):
        _sidecar_mount.converge(
            fixture.sidecar_root, fixture.project_root, fixture.project_root, lock=_NullLock()
        )

    assert _git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode == 0


# --- can_drop_branch / drop_branch ------------------------------------------------


def test_can_drop_branch_is_refused_while_its_mount_still_exists(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="hold")

    precondition = _sidecar_mount.can_drop_branch(fixture.sidecar_root, fixture.sidecar_branch)

    assert precondition.ready is False


def test_can_drop_branch_is_accepted_once_the_mount_is_pruned(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="free")
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)

    precondition = _sidecar_mount.can_drop_branch(fixture.sidecar_root, fixture.sidecar_branch)

    assert precondition.ready is True


def test_drop_branch_is_the_only_path_that_removes_an_unmerged_branch(tmp_path: Path) -> None:
    fixture = _build_diverged_fixture(tmp_path, name="drop")
    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)

    _sidecar_mount.drop_branch(fixture.sidecar_root, fixture.sidecar_branch)

    assert _git(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).returncode != 0
