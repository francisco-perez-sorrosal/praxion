"""Behavioral tests for `_sidecar_mount.py` -- the state mount lifecycle.

Every fixture (see `_sidecar_testkit.py`) drives *real* `git worktree` /
`git merge` / `git branch` commands under `tmp_path`; nothing about git is
mocked, because the whole premise this module exists to prove rests on
verified git behaviour -- a mocked git subprocess would prove nothing about
it. The branch slot and convergence are covered by
`test_sidecar_convergence.py`, split along the same seam as the modules.

`_state_repo.py` is a sibling dependency for the *production* mount-discovery
path, but nothing under test here calls the resolver, so no
`pytest.importorskip("_state_repo")` guard is needed in this file.

Import strategy: plain sibling import (`scripts/` has no `__init__.py`, so
pytest's prepend import mode puts it on `sys.path[0]`), matching
`scripts/test_state_repo.py`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import _sidecar_mount
import pytest
from _sidecar_testkit import (
    SKELETON_SUBDIRS,
    build_diverged_fixture,
    git,
    git_ok,
    init_plain_repo,
    init_project,
    init_sidecar,
    mount_main,
)

# --- StateMountState -------------------------------------------------


def test_absent_mount_slot_classifies_as_absent(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    init_project(project_root)

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.Absent)


def test_real_sidecar_worktree_classifies_as_sidecar_worktree(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.SidecarWorktree)
    assert result.branch == "main"
    assert result.sidecar_common_dir == (sidecar_root / ".git").resolve()


def test_foreign_real_directory_at_mount_slot_classifies_as_foreign_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    init_project(project_root)
    (project_root / _sidecar_mount.MOUNT_DIRNAME).mkdir()

    result = _sidecar_mount.classify_mount(project_root)

    assert isinstance(result, _sidecar_mount.ForeignDir)


def test_worktree_of_a_different_repository_classifies_as_foreign_repo(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    other_repo = tmp_path / "unrelated-repo"
    init_project(project_root)
    init_plain_repo(other_repo)

    git_ok(
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
    worktree of *it* sitting at `<project>/.praxion-state` is structurally
    indistinguishable from ours. Passing the real sidecar's common directory
    is what separates them -- and omitting it must keep today's behaviour.
    """
    sidecar_root = tmp_path / "sidecar"
    other_sidecar = tmp_path / "other-sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_sidecar(other_sidecar)
    init_project(project_root)
    git_ok(
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
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)

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
    init_sidecar(sidecar_root)
    init_project(project_a)
    init_project(project_b)
    mount_main(sidecar_root, project_a)

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
    init_sidecar(sidecar_root)
    init_project(project_a)
    init_project(project_b)
    mount_main(sidecar_root, project_a)

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
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount = mount_main(sidecar_root, project_root)
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
    init_sidecar(sidecar_root)
    init_project(project_a)
    init_project(project_b)
    live = mount_main(sidecar_root, project_a)
    git_ok(sidecar_root, "branch", "wt/b", "main")

    _sidecar_mount.create_mount(sidecar_root, project_b, "wt/b", project_branch="main")

    assert str(live) in git_ok(sidecar_root, "worktree", "list").stdout


def test_repair_mount_repoints_the_sidecar_record_at_the_moved_checkout(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)
    moved = tmp_path / "project-moved"
    shutil.move(str(project_root), str(moved))
    assert _sidecar_mount.backlink_is_stale(moved)

    _sidecar_mount.repair_mount(sidecar_root, moved)

    assert not _sidecar_mount.backlink_is_stale(moved)


def test_backlink_is_not_stale_for_a_checkout_that_never_moved(tmp_path: Path) -> None:
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    init_sidecar(sidecar_root)
    init_project(project_root)
    mount_main(sidecar_root, project_root)

    assert not _sidecar_mount.backlink_is_stale(project_root)


def test_create_mount_records_project_branch_mapping_in_sidecar_config_only(tmp_path: Path) -> None:
    fixture = build_diverged_fixture(tmp_path, name="map")

    sidecar_value = git_ok(
        fixture.sidecar_root,
        "config",
        "--get",
        f"branch.{fixture.sidecar_branch}.praxion-project-branch",
    ).stdout.strip()
    project_lookup = git(
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
    init_sidecar(sidecar_root)  # seeds SKELETON_SUBDIRS before the initial commit
    init_project(project_root)

    mount = mount_main(sidecar_root, project_root)

    for subdir in SKELETON_SUBDIRS:
        gitkeep = mount / ".ai-state" / subdir / ".gitkeep"
        assert gitkeep.exists(), f"missing seeded {subdir}"


# --- prune_mount ----------------------------------------------------------------


def test_prune_mount_succeeds_for_a_gone_checkout_even_when_its_mount_was_dirty(
    tmp_path: Path,
) -> None:
    """A removed project worktree takes its nested mount's working tree with
    it -- there is nothing left for `prune_mount` to protect by the time it
    runs, so it neither raises nor needs to inspect the mount's own git
    status. The branch's committed history is untouched: `prune_mount` never
    deletes a branch, only a worktree registration.
    """
    fixture = build_diverged_fixture(tmp_path, name="gone")
    (fixture.wt_mount / ".ai-state" / "DESIGN.md").write_text("uncommitted\n")
    committed_tip = git_ok(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).stdout

    shutil.rmtree(fixture.wt_checkout)

    _sidecar_mount.prune_mount(fixture.sidecar_root, fixture.wt_checkout)

    assert git_ok(fixture.sidecar_root, "rev-parse", fixture.sidecar_branch).stdout == committed_tip
