"""The rewrite hook is installed, repaired and checked wherever the finalize hooks are.

The onboarding hook reconciler does to `post-rewrite` exactly what it does to
`post-merge`, in every mode and repository shape; the pin upgrade gives a project
onboarded by an earlier release the slot, repairs it, reports it in check mode and
records it; every surface names the same set of hooks; the hook-mirror check is
quiet with four finalize hooks installed; and the dispatcher, invoked under a name
it does not serve, names the four it does.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.acceptance.drivers.hook_installation import (
    DISPATCHER,
    EARLIER_FINALIZE_HOOKS,
    PROJECT_HOOKS,
    foreign_hook_body,
    git_in,
    hooks_dir_in_use,
    installed_hook_names,
    link_target,
    live_hook,
    managed_project,
    mirror_check,
    plain_repository,
    reconcile,
    recorded_hooks,
    run_dispatcher_as,
    slot_shape,
    snapshot,
    upgrade_pins,
    write_hook,
)
from tests.acceptance.drivers.hooks import FINALIZE_HOOKS

COMPARED = ("post-merge", "post-rewrite")
FOREIGN_DIR = ".husky/_"


# -- Repository shapes the reconciler handles, prepared alike for both compared slots ------


def _empty_slots(repo: Path, sandbox: Path) -> None:
    """Nothing in either slot, `core.hooksPath` unset."""


def _foreign_hooks_in_the_slots(repo: Path, sandbox: Path) -> None:
    for name in COMPARED:
        write_hook(repo / ".git" / "hooks" / name, foreign_hook_body(name))


def _foreign_hooks_path(repo: Path, sandbox: Path) -> None:
    for name in COMPARED:
        write_hook(repo / FOREIGN_DIR / name, foreign_hook_body(name))
    git_in(repo, sandbox, "config", "core.hooksPath", FOREIGN_DIR)


def _praxion_wrapper_path_missing_both_wrappers(repo: Path, sandbox: Path) -> None:
    _foreign_hooks_path(repo, sandbox)
    reconcile(repo, sandbox, "install")
    for name in COMPARED:
        (hooks_dir_in_use(repo, sandbox) / name).unlink(missing_ok=True)


def _unresolvable_hooks_path(repo: Path, sandbox: Path) -> None:
    (repo / "not-a-dir.txt").write_text("a file, not a directory\n", encoding="utf-8")
    git_in(repo, sandbox, "config", "core.hooksPath", "not-a-dir.txt")


def _wrapper_surviving_an_unset_hooks_path(repo: Path, sandbox: Path) -> None:
    _foreign_hooks_path(repo, sandbox)
    reconcile(repo, sandbox, "install")
    git_in(repo, sandbox, "config", "--unset", "core.hooksPath")


def _both_slots_installed_as_symlinks(repo: Path, sandbox: Path) -> None:
    for name in COMPARED:
        (repo / ".git" / "hooks" / name).symlink_to(DISPATCHER)


def _installed_over_foreign_hooks(repo: Path, sandbox: Path) -> None:
    _foreign_hooks_in_the_slots(repo, sandbox)
    reconcile(repo, sandbox, "install")


Shape = Callable[[Path, Path], None]
MODE_AND_SHAPE: dict[str, tuple[str, Shape]] = {
    "install, empty slot": ("install", _empty_slots),
    "install, foreign hook in the slot": ("install", _foreign_hooks_in_the_slots),
    "install, core.hooksPath naming a foreign directory": ("install", _foreign_hooks_path),
    "install, core.hooksPath naming Praxion's wrapper directory": (
        "install",
        _praxion_wrapper_path_missing_both_wrappers,
    ),
    "install, unresolvable core.hooksPath": ("install", _unresolvable_hooks_path),
    "heal, wrapper left behind by an unset core.hooksPath": (
        "heal",
        _wrapper_surviving_an_unset_hooks_path,
    ),
    "heal, empty slot": ("heal", _empty_slots),
    "uninstall, installed in an empty slot": ("uninstall", _both_slots_installed_as_symlinks),
    "uninstall, installed over a foreign hook": ("uninstall", _installed_over_foreign_hooks),
}


@pytest.mark.parametrize("case", list(MODE_AND_SHAPE))
def test_the_reconciler_treats_the_rewrite_slot_exactly_as_the_merge_slot(
    tmp_path: Path, case: str
) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)
    mode, prepare = MODE_AND_SHAPE[case]
    prepare(repo, sandbox)

    reconcile(repo, sandbox, mode)

    hooks_dir = hooks_dir_in_use(repo, sandbox)
    assert slot_shape(hooks_dir, "post-rewrite") == slot_shape(hooks_dir, "post-merge")


def test_the_reconciler_reports_the_rewrite_slot_wherever_it_reports_the_merge_slot(
    tmp_path: Path,
) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)
    reconcile(repo, sandbox, "install")

    status = reconcile(repo, sandbox, "status", "--json")

    assert status.stdout.count("post-merge") > 0, status.stdout
    assert status.stdout.count("post-rewrite") == status.stdout.count("post-merge"), status.stdout


@pytest.mark.parametrize("missing", COMPARED)
def test_the_reconciler_status_flags_a_missing_rewrite_slot_as_it_flags_a_missing_merge_slot(
    tmp_path: Path, missing: str
) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)
    reconcile(repo, sandbox, "install")
    (repo / ".git" / "hooks" / missing).unlink(missing_ok=True)

    status = reconcile(repo, sandbox, "status")

    assert status.returncode == 1, status.stdout + status.stderr


def test_a_foreign_rewrite_hook_still_runs_after_the_reconciler_chains_it(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)
    marker = tmp_path / "foreign-ran.txt"
    write_hook(repo / ".git" / "hooks" / "post-rewrite", f"#!/bin/sh\necho ran >> '{marker}'\n")
    reconcile(repo, sandbox, "install")
    git_in(
        repo,
        sandbox,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t.invalid",
        "commit",
        "-q",
        "--allow-empty",
        "--no-verify",
        "-m",
        "one",
    )

    git_in(
        repo,
        sandbox,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t.invalid",
        "commit",
        "-q",
        "--amend",
        "--allow-empty",
        "--no-verify",
        "-m",
        "one again",
    )

    assert marker.exists(), "the preserved foreign post-rewrite hook did not run"
    assert slot_shape(repo / ".git" / "hooks", "post-rewrite")[0] != "absent"
    assert (repo / ".git" / "hooks" / "post-rewrite.pre-praxion").exists(), (
        "the foreign post-rewrite hook was not preserved and chained"
    )


# -- The pin upgrade --------------------------------------------------------------------------


def _absent(repo: Path, live: Path) -> None:
    """The slot an earlier release never filled."""


def _dangling(repo: Path, live: Path) -> None:
    gone = repo / "cache" / "praxion" / "0.7.0" / "scripts" / "git-finalize-hook.sh"
    (repo / ".git" / "hooks" / "post-rewrite").symlink_to(gone)


def _pinned_to_an_earlier_live_version(repo: Path, live: Path) -> None:
    earlier = repo.parent / "plugins" / "cache" / "bit-agora" / "praxion" / "0.8.5" / "scripts"
    write_hook(earlier / "git-finalize-hook.sh", "#!/usr/bin/env bash\n")
    (repo / ".git" / "hooks" / "post-rewrite").symlink_to(earlier / "git-finalize-hook.sh")


def _foreign(repo: Path, live: Path) -> None:
    write_hook(repo / ".git" / "hooks" / "post-rewrite", foreign_hook_body("post-rewrite"))


REWRITE_SLOT_STATES = {
    "absent": _absent,
    "dangling": _dangling,
    "pinned to an earlier plugin version": _pinned_to_an_earlier_live_version,
    "held by a foreign hook": _foreign,
}


@pytest.mark.parametrize("state", list(REWRITE_SLOT_STATES))
def test_the_pin_upgrade_links_the_rewrite_slot_to_the_live_plugin(
    tmp_path: Path, state: str
) -> None:
    repo, live = managed_project(tmp_path)
    REWRITE_SLOT_STATES[state](repo, live)

    upgraded = upgrade_pins(repo, live)

    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    assert {name: link_target(repo, name) for name in FINALIZE_HOOKS} == {
        name: live_hook(live) for name in FINALIZE_HOOKS
    }


def test_the_pin_upgrade_backs_up_a_foreign_rewrite_hook(tmp_path: Path) -> None:
    repo, live = managed_project(tmp_path)
    _foreign(repo, live)

    upgrade_pins(repo, live)

    backups = [
        entry.read_text(encoding="utf-8")
        for entry in (repo / ".git" / "hooks").iterdir()
        if entry.name.startswith("post-rewrite.") and entry.is_file()
    ]
    assert backups == [foreign_hook_body("post-rewrite")]


def test_the_pin_upgrade_repairs_legacy_single_trigger_hooks_into_all_four_finalize_hooks(
    tmp_path: Path,
) -> None:
    repo, live = managed_project(tmp_path)
    legacy = repo / "cache" / "praxion" / "0.5.0" / "scripts" / "git-post-merge-hook.sh"
    for name in EARLIER_FINALIZE_HOOKS:
        slot = repo / ".git" / "hooks" / name
        slot.unlink()
        slot.symlink_to(legacy)

    upgrade_pins(repo, live)

    assert {name: link_target(repo, name) for name in FINALIZE_HOOKS} == {
        name: live_hook(live) for name in FINALIZE_HOOKS
    }


def test_the_pin_upgrade_check_mode_reports_a_missing_rewrite_slot_and_changes_nothing(
    tmp_path: Path,
) -> None:
    repo, live = managed_project(tmp_path)
    upgrade_pins(repo, live)
    (repo / ".git" / "hooks" / "post-rewrite").unlink(missing_ok=True)
    before = snapshot(repo)

    checked = upgrade_pins(repo, live, "--check")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert "post-rewrite" in checked.stdout + checked.stderr
    assert snapshot(repo) == before


def test_the_pin_upgrade_leaves_a_self_hosted_praxion_link_alone(tmp_path: Path) -> None:
    repo, live = managed_project(tmp_path)
    self_hosted = tmp_path / "dev" / "praxion" / "scripts" / "git-finalize-hook.sh"
    write_hook(self_hosted, "#!/usr/bin/env bash\n")
    for name in FINALIZE_HOOKS:
        slot = repo / ".git" / "hooks" / name
        slot.unlink(missing_ok=True)
        slot.symlink_to(self_hosted)

    upgrade_pins(repo, live)

    assert {name: link_target(repo, name) for name in FINALIZE_HOOKS} == {
        name: str(self_hosted) for name in FINALIZE_HOOKS
    }


def test_the_pin_upgrade_records_the_rewrite_hook_among_the_installed_hooks(
    tmp_path: Path,
) -> None:
    repo, live = managed_project(tmp_path)

    upgrade_pins(repo, live)

    assert sorted(recorded_hooks(repo)) == sorted(PROJECT_HOOKS)


def test_a_second_pin_upgrade_leaves_the_upgraded_project_rewrite_slot_included_unchanged(
    tmp_path: Path,
) -> None:
    repo, live = managed_project(tmp_path)
    upgrade_pins(repo, live)
    after_first = snapshot(repo)

    second = upgrade_pins(repo, live)

    assert link_target(repo, "post-rewrite") == live_hook(live)
    assert second.returncode == 0, second.stdout + second.stderr
    assert snapshot(repo) == after_first
    assert upgrade_pins(repo, live, "--check").returncode == 0


# -- Every surface names the same hooks -----------------------------------------------------


def test_the_reconciler_installs_pre_commit_and_the_four_finalize_hooks(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)

    reconcile(repo, sandbox, "install")

    assert installed_hook_names(repo / ".git" / "hooks") == set(PROJECT_HOOKS)


# -- The mirror check and the dispatcher ----------------------------------------------------


def test_the_hook_mirror_check_reports_nothing_with_the_four_finalize_hooks_installed(
    tmp_path: Path,
) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)
    (repo / "scripts").mkdir()
    shutil.copy2(DISPATCHER, repo / "scripts" / DISPATCHER.name)
    for name in FINALIZE_HOOKS:
        (repo / ".git" / "hooks" / name).symlink_to(repo / "scripts" / DISPATCHER.name)

    checked = mirror_check(repo, sandbox)

    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_the_dispatcher_invoked_under_an_unserved_name_lists_the_four_finalize_hooks(
    tmp_path: Path,
) -> None:
    sandbox = tmp_path / "sandbox"
    repo = plain_repository(tmp_path / "repo", sandbox)

    ran = run_dispatcher_as("pre-push", repo, sandbox)

    said = ran.stdout + ran.stderr
    assert {name for name in FINALIZE_HOOKS if name in said} == set(FINALIZE_HOOKS), said
