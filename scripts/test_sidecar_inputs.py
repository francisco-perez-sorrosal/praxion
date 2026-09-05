"""Behavioral tests for `_sidecar_inputs.py::gather()` -- the CLI wiring
layer that reads the world once into `_sidecar_checks.CheckInputs` (+ a
`Facts` record for `status`).

Every fixture drives the real `praxion-sidecar` CLI (`init`, `link`) as a
subprocess against a real `tmp_path` git project and a real sidecar repo,
matching `scripts/test_praxion_sidecar.py`'s own black-box style -- nothing
about git is mocked, because `gather()` exists to turn "what is on disk"
into "what the registry judges", and a mocked git subprocess would prove
nothing about that translation. `_sidecar_testkit.py`'s `worktree_git_dir`
is the one helper imported directly rather than re-derived.

Three groups, matching `gather()`'s own branches:

1. A healthy `SidecarOwned` placement, freshly `init`-ed -- one assertion
   per `CheckInputs`/`Facts` field, on its *value*.
2. Field-level detectors -- one observable flipped at a time (a dirty
   mount, a second linked worktree, a stale manifest root, an orphaned
   mount, a dead lock record, a mid-merge mount).
3. Non-sidecar placements -- `InRepo` (hooks-only inputs) and the three
   *reported, never raised* unresolved variants (`Dangling`, `Foreign`,
   `NotYetLinked`).
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
from pathlib import Path

import _sidecar_checks
import _sidecar_commit
import _sidecar_inputs
import _sidecar_manifest
import _sidecar_mount
import _state_repo
import install_git_hooks
import pytest
from _sidecar_cli import Context
from _sidecar_testkit import worktree_git_dir

_CLI = Path(__file__).resolve().parent / "praxion-sidecar"
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_ORIGIN_URL = "https://github.com/acme/billing"
_ORIGIN_ID = "github.com--acme--billing"


# --- git plumbing ------------------------------------------------------------


def _git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _init_project_repo(root: Path, *, origin: str | None = _ORIGIN_URL) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git_ok(root, "init", "-q", "-b", "main")
    _git_ok(root, "config", "user.email", "test@example.com")
    _git_ok(root, "config", "user.name", "Test")
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    _git_ok(root, "add", "README.md")
    _git_ok(root, "commit", "-q", "-m", "seed")
    if origin is not None:
        _git_ok(root, "remote", "add", "origin", origin)


def _add_worktree(project: Path, name: str, *, branch: str) -> Path:
    checkout = project / ".claude" / "worktrees" / name
    checkout.parent.mkdir(parents=True, exist_ok=True)
    _git_ok(project, "worktree", "add", str(checkout), "-b", branch)
    return checkout


# --- CLI invocation ------------------------------------------------------------


def run_cli(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CLI), *args], cwd=str(cwd), env=env, capture_output=True, text=True
    )


def _init_ok(project: Path, env: dict[str, str]) -> None:
    result = run_cli(["init"], project, env)
    assert result.returncode == 0, result.stderr


def _link_ok(checkout: Path, env: dict[str, str]) -> None:
    result = run_cli(["link"], checkout, env)
    assert result.returncode == 0, result.stderr


def _gather(
    checkout: Path, sidecar_root: Path
) -> tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts]:
    return _sidecar_inputs.gather(Context(checkout=checkout.resolve(), sidecar_root=sidecar_root))


# --- fixtures ------------------------------------------------------------


@pytest.fixture
def sidecar_root(tmp_path: Path) -> Path:
    return tmp_path / "sidecars"


@pytest.fixture
def cli_env(sidecar_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PRAXION_SIDECAR_ROOT"] = str(sidecar_root)
    env["NO_COLOR"] = "1"
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        env[var] = "Test"
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        env[var] = "test@example.com"
    return env


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "billing"
    _init_project_repo(root)
    return root


@pytest.fixture
def healthy(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts]:
    """A freshly `init`-ed sidecar -- every group-1 test reads off this."""
    _init_ok(project, cli_env)
    return _gather(project, sidecar_root)


# --- group 1: a healthy SidecarOwned placement ------------------------------


def test_gather_reports_sidecar_owned_placement_with_the_mounted_branch(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert isinstance(inputs.placement, _state_repo.SidecarOwned)
    assert inputs.placement.branch == "main"


def test_gather_reports_the_exclude_block_as_current_after_init(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.exclude_block is _sidecar_checks.ExcludeBlockState.CURRENT


def test_gather_reports_every_default_shadow_slot_as_linked(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert set(inputs.shadow_slots) == {
        ".ai-state",
        "CLAUDE.md",
        "CLAUDE.local.md",
        ".claude/settings.local.json",
    }
    assert all(
        state is _sidecar_checks.ShadowState.LINKED for state in inputs.shadow_slots.values()
    )


def test_gather_reports_the_default_share_slot_as_shared(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.shared_slots == {"docs/architecture.md": _sidecar_checks.SharedState.SHARED}


def test_gather_reports_no_untouched_paths_when_claude_md_is_absent(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.untouched_paths == {}


def test_gather_reports_hooks_status_as_empty_before_hooks_are_installed(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.hooks_status == {}


def test_gather_reports_hooks_status_matching_a_freshly_installed_hook_chain(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    install_git_hooks.install_or_heal(project, "install", _PLUGIN_ROOT)

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.hooks_status == install_git_hooks.build_status(project, _PLUGIN_ROOT)
    assert inputs.hooks_status["slots"]


def test_gather_reports_the_mount_as_a_sidecar_worktree_on_the_resolved_common_dir(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts], sidecar_root: Path
) -> None:
    inputs, _facts = healthy
    assert isinstance(inputs.mount, _sidecar_mount.SidecarWorktree)
    assert inputs.mount.branch == "main"
    assert inputs.mount.sidecar_common_dir == (sidecar_root / _ORIGIN_ID / ".git").resolve()


def test_gather_reports_no_branches_when_no_worktree_is_linked(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.branches == {}


def test_gather_reports_no_orphaned_mounts_and_no_mid_merge_mount_when_healthy(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.orphaned_mounts == ()
    assert inputs.mount_mid_merge is False


def test_gather_reports_the_sidecar_repo_as_clean_with_no_unpushed_commits(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.sidecar_repo == _sidecar_checks.SidecarRepoState(
        is_git_repo=True, dirty_files=0, unpushed_commits=0
    )


def test_gather_reports_no_remote_when_none_is_configured(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.remote is None


def test_gather_reports_guards_roots_as_not_stale_for_the_main_checkout(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.guards_roots_stale is False


def test_gather_reports_the_lock_as_idle_when_uncontended(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.lock_state == _sidecar_commit.Idle()


def test_gather_reports_no_unresolved_placement_for_a_healthy_sidecar(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    inputs, _facts = healthy
    assert inputs.unresolved_placement is None


def test_gather_facts_carry_the_checkouts_origin_sidecar_and_manifest(
    healthy: tuple[_sidecar_checks.CheckInputs, _sidecar_inputs.Facts],
) -> None:
    _inputs, facts = healthy
    assert facts.origin == _ORIGIN_URL
    assert facts.checkout.kind == "main"
    assert facts.sidecar is not None
    assert facts.sidecar.branch == "main"
    assert facts.sidecar.dirty_files == 0
    assert facts.sidecar.unpushed_commits == 0
    assert facts.manifest is not None
    assert facts.manifest.project.id == _ORIGIN_ID


# --- group 2: field-level detectors -----------------------------------------


def test_gather_reports_a_dirty_mount_in_sidecar_repo_dirty_files(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    (project / ".ai-state" / "scratch.md").write_text("draft\n", encoding="utf-8")

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.sidecar_repo is not None
    assert inputs.sidecar_repo.dirty_files == 1


def test_gather_lists_a_linked_worktrees_branch_among_branches(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    worktree = _add_worktree(project, "wt1", branch="feat")
    _link_ok(worktree, cli_env)

    inputs, _facts = _gather(project, sidecar_root)

    assert set(inputs.branches) == {"wt/wt1"}


def test_gather_flags_guards_roots_stale_when_the_checkout_is_absent_from_manifest_roots(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    manifest_file = _sidecar_manifest.manifest_path(sidecar_root / _ORIGIN_ID / ".git")
    manifest = _sidecar_manifest.load_manifest(manifest_file)
    stale = dataclasses.replace(
        manifest,
        project=dataclasses.replace(manifest.project, roots=[Path("/nonexistent/elsewhere")]),
    )
    _sidecar_manifest.write_manifest(manifest_file, stale)

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.guards_roots_stale is True


def test_gather_reports_orphaned_mounts_for_a_removed_worktree_checkout(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    worktree = _add_worktree(project, "wt1", branch="feat")
    _link_ok(worktree, cli_env)
    shutil.rmtree(worktree)

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.orphaned_mounts == ("wt1",)


def test_gather_reports_the_lock_as_stale_when_a_dead_holders_record_remains(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    mount = project / _sidecar_mount.MOUNT_DIRNAME
    lock_path = _sidecar_commit.lock_path_for(mount)
    lock_path.write_text("999999\n2024-01-01T00:00:00Z\n", encoding="utf-8")

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.lock_state == _sidecar_commit.StaleLock(
        holder_pid=999999, since="2024-01-01T00:00:00Z"
    )


def test_gather_reports_mount_mid_merge_when_a_merge_head_is_present(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    mount = project / _sidecar_mount.MOUNT_DIRNAME
    (worktree_git_dir(mount) / "MERGE_HEAD").write_text("deadbeef\n", encoding="utf-8")

    inputs, _facts = _gather(project, sidecar_root)

    assert inputs.mount_mid_merge is True


# --- group 3: non-sidecar placements ----------------------------------------


def test_gather_reports_in_repo_placement_as_hooks_only_inputs(
    project: Path, sidecar_root: Path
) -> None:
    inputs, facts = _gather(project, sidecar_root)

    assert isinstance(inputs.placement, _state_repo.InRepo)
    assert inputs.exclude_block is None
    assert inputs.sidecar_repo is None
    assert inputs.unresolved_placement is None
    assert inputs.hooks_status == {}
    assert facts.sidecar is None
    assert facts.manifest is None


def test_gather_reports_a_dangling_shadow_through_unresolved_placement(
    project: Path, sidecar_root: Path
) -> None:
    (project / ".ai-state").symlink_to(project / "nonexistent-mount")

    inputs, _facts = _gather(project, sidecar_root)

    assert isinstance(inputs.placement, _state_repo.Dangling)
    assert inputs.unresolved_placement is not None
    assert inputs.unresolved_placement.reason is _sidecar_checks.UnresolvedReason.DANGLING
    assert _sidecar_checks.evaluate_checks(inputs)


def test_gather_reports_a_foreign_shadow_through_unresolved_placement(
    project: Path, sidecar_root: Path
) -> None:
    fake_mount = project / "fake-mount"
    (fake_mount / ".ai-state").mkdir(parents=True)
    (project / ".ai-state").symlink_to(fake_mount / ".ai-state")

    inputs, _facts = _gather(project, sidecar_root)

    assert isinstance(inputs.placement, _state_repo.Foreign)
    assert inputs.unresolved_placement is not None
    assert inputs.unresolved_placement.reason is _sidecar_checks.UnresolvedReason.FOREIGN
    assert _sidecar_checks.evaluate_checks(inputs)


def test_gather_reports_a_not_yet_linked_worktree_through_unresolved_placement(
    project: Path, cli_env: dict[str, str], sidecar_root: Path
) -> None:
    _init_ok(project, cli_env)
    worktree = _add_worktree(project, "wt1", branch="feat")

    inputs, _facts = _gather(worktree, sidecar_root)

    assert isinstance(inputs.placement, _state_repo.NotYetLinked)
    assert inputs.unresolved_placement is not None
    assert inputs.unresolved_placement.reason is _sidecar_checks.UnresolvedReason.UNLINKED
    assert _sidecar_checks.evaluate_checks(inputs)
