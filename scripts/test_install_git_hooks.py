"""Tests for install_git_hooks.py -- observe-then-compose git hook chaining.

Covers, in order:
  - Hook-chain state classification (`observe_hooks_path`, `classify_hook_slot`):
    all `HooksPathState` and `HookSlotState` variants against real `tmp_path`
    git repos.
  - Wrapper exit-code policy and re-entrancy guard: the rendered wrapper
    invoked directly (subprocess) against a fake delegate script, proving the
    per-hook-class policy from the shell up -- a stub team hook that exits
    non-zero must abort a pre-commit chain and must NOT abort a post-* chain
    (the canary this milestone's RISKY steps exist to prove).
  - The five(+one)-branch `install_or_heal` action table, idempotency
    (second run performs zero writes), and the non-ping-pong invariant.
  - `--status` / `--uninstall` / exit-code contract via the real CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_git_hooks as hooks  # noqa: E402

_CLI = Path(__file__).resolve().parent / "install_git_hooks.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def _git_unchecked(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _write_and_chmod(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_CLI), *args], capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    (root / "README.md").write_text("x\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")
    return root


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "plugin"
    (root / "scripts" / "assets").mkdir(parents=True)
    _write_and_chmod(
        root / "scripts" / hooks.FINALIZE_DISPATCHER,
        '#!/usr/bin/env bash\necho "dispatch:$(basename "$0")" >&2\nexit 0\n',
    )
    _write_and_chmod(
        root / "scripts" / "assets" / "praxion-precommit-hook.sh.tmpl",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    return root


# ---- Hook-chain state classification ----------------------------------------


class TestObserveHooksPath:
    def test_unset_returns_unset(self, repo):
        assert isinstance(hooks.observe_hooks_path(repo), hooks.Unset)

    def test_unset_when_slot_occupied_is_still_unset(self, repo):
        _write_and_chmod(repo / ".git" / "hooks" / "pre-commit", "#!/bin/sh\nexit 0\n")
        assert isinstance(hooks.observe_hooks_path(repo), hooks.Unset)

    def test_foreign_directory(self, repo):
        d = repo / ".husky" / "_"
        d.mkdir(parents=True)
        _git(repo, "config", "core.hooksPath", ".husky/_")
        state = hooks.observe_hooks_path(repo)
        assert isinstance(state, hooks.Foreign)
        assert state.dir_raw == ".husky/_"
        assert state.dir_abs == d.resolve()

    def test_wrapper_directory_returns_praxion_wrapper_with_delegate(self, repo):
        wrapper_dir = hooks.wrapper_dir_path(repo)
        wrapper_dir.mkdir(parents=True)
        hooks.write_recorded_delegate(wrapper_dir, ".husky/_")
        _git(repo, "config", "core.hooksPath", str(wrapper_dir))
        state = hooks.observe_hooks_path(repo)
        assert isinstance(state, hooks.PraxionWrapper)
        assert state.delegate.raw == ".husky/_"

    def test_unresolvable_when_value_is_a_file_not_a_directory(self, repo):
        garbage = repo / "not-a-dir.txt"
        garbage.write_text("x")
        _git(repo, "config", "core.hooksPath", "not-a-dir.txt")
        state = hooks.observe_hooks_path(repo)
        assert isinstance(state, hooks.Unresolvable)
        assert state.reason == "not-a-directory"

    def test_unresolvable_when_value_does_not_exist(self, repo):
        _git(repo, "config", "core.hooksPath", "does/not/exist")
        state = hooks.observe_hooks_path(repo)
        assert isinstance(state, hooks.Unresolvable)


class TestClassifyHookSlot:
    def test_absent(self, repo):
        assert isinstance(
            hooks.classify_hook_slot(repo / ".git" / "hooks", "pre-commit"), hooks.Absent
        )

    def test_praxion_symlink_to_finalize_dispatcher(self, repo, plugin_root):
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "post-merge").symlink_to(plugin_root / "scripts" / hooks.FINALIZE_DISPATCHER)
        assert isinstance(hooks.classify_hook_slot(hooks_dir, "post-merge"), hooks.PraxionSymlink)

    def test_praxion_inline_precommit_is_symlink_variant(self, repo):
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "pre-commit").write_text(hooks.PRECOMMIT_TEMPLATE_PATH.read_text())
        assert isinstance(hooks.classify_hook_slot(hooks_dir, "pre-commit"), hooks.PraxionSymlink)

    def test_wrapper_file_marker(self, repo):
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "pre-commit").write_text(
            f"#!/usr/bin/env bash\n{hooks.WRAPPER_MARKER}\nexit 0\n"
        )
        assert isinstance(
            hooks.classify_hook_slot(hooks_dir, "pre-commit"), hooks.PraxionWrapperFile
        )

    def test_foreign_occupied_regular_file(self, repo):
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "pre-commit").write_text("#!/bin/sh\necho hi\n")
        assert isinstance(hooks.classify_hook_slot(hooks_dir, "pre-commit"), hooks.ForeignOccupied)

    def test_dangling_symlink_is_foreign_occupied(self, repo):
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "pre-commit").symlink_to(hooks_dir / "does-not-exist")
        assert isinstance(hooks.classify_hook_slot(hooks_dir, "pre-commit"), hooks.ForeignOccupied)


# ---- Wrapper exit-code policy + re-entrancy -------------------------------------


class TestWrapperExitPolicy:
    def test_pre_commit_delegate_success_runs_praxion_step(self, repo, plugin_root):
        delegate_dir = repo / ".husky" / "_"
        delegate_dir.mkdir(parents=True)
        delegate_marker = repo / "delegate_ran"
        _write_and_chmod(
            delegate_dir / "pre-commit", f'#!/usr/bin/env bash\ntouch "{delegate_marker}"\nexit 0\n'
        )
        praxion_marker = repo / "praxion_ran"
        _write_and_chmod(
            plugin_root / "scripts" / "assets" / "praxion-precommit-hook.sh.tmpl",
            f'#!/usr/bin/env bash\ntouch "{praxion_marker}"\nexit 0\n',
        )
        wrapper = repo / "wrapper-pre-commit"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="pre-commit",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        result = subprocess.run([str(wrapper)], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0
        assert delegate_marker.exists()
        assert praxion_marker.exists()

    def test_pre_commit_delegate_failure_aborts_and_skips_praxion_step(self, repo, plugin_root):
        """The RISKY canary: a stub team pre-commit hook exiting non-zero must
        abort the chain with that exit code, and Praxion's own gate must NOT
        run -- a wrapper that swallows this status defeats the team's gate."""
        delegate_dir = repo / ".husky" / "_"
        delegate_dir.mkdir(parents=True)
        _write_and_chmod(delegate_dir / "pre-commit", "#!/usr/bin/env bash\nexit 7\n")
        praxion_marker = repo / "praxion_ran"
        _write_and_chmod(
            plugin_root / "scripts" / "assets" / "praxion-precommit-hook.sh.tmpl",
            f'#!/usr/bin/env bash\ntouch "{praxion_marker}"\nexit 0\n',
        )
        wrapper = repo / "wrapper-pre-commit"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="pre-commit",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        result = subprocess.run([str(wrapper)], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 7
        assert not praxion_marker.exists()

    def test_post_merge_delegate_failure_reports_and_continues(self, repo, plugin_root):
        delegate_dir = repo / ".husky" / "_"
        delegate_dir.mkdir(parents=True)
        _write_and_chmod(delegate_dir / "post-merge", "#!/usr/bin/env bash\nexit 7\n")
        finalize_marker = repo / "finalize_ran"
        _write_and_chmod(
            plugin_root / "scripts" / hooks.FINALIZE_DISPATCHER,
            f'#!/usr/bin/env bash\ntouch "{finalize_marker}"\nexit 0\n',
        )
        wrapper = repo / "post-merge"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="post-merge",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        result = subprocess.run([str(wrapper)], cwd=repo, capture_output=True, text=True)
        assert result.returncode == 0
        assert "delegate exited 7" in result.stderr
        assert finalize_marker.exists()

    def test_post_merge_dispatches_with_correct_basename(self, repo, plugin_root):
        """`git-finalize-hook.sh` dispatches on `basename "$0"` -- the wrapper
        must preserve that identity through to the sourced dispatcher."""
        delegate_dir = repo / ".husky" / "_"
        delegate_dir.mkdir(parents=True)
        _write_and_chmod(delegate_dir / "post-merge", "#!/usr/bin/env bash\nexit 0\n")
        wrapper = repo / "post-merge"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="post-merge",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        result = subprocess.run([str(wrapper)], cwd=repo, capture_output=True, text=True)
        assert "dispatch:post-merge" in result.stderr

    def test_reentrancy_guard_refuses_delegate_at_depth(self, repo, plugin_root):
        delegate_dir = repo / ".husky" / "_"
        delegate_dir.mkdir(parents=True)
        delegate_marker = repo / "delegate_ran"
        _write_and_chmod(
            delegate_dir / "pre-commit", f'#!/usr/bin/env bash\ntouch "{delegate_marker}"\nexit 0\n'
        )
        wrapper = repo / "wrapper-pre-commit"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="pre-commit",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        env = {**os.environ, "PRAXION_HOOK_CHAIN_DEPTH": "1"}
        result = subprocess.run([str(wrapper)], cwd=repo, capture_output=True, text=True, env=env)
        assert "refusing to exec delegate" in result.stderr
        assert not delegate_marker.exists()

    def test_relative_delegate_resolves_against_second_worktree_root(self, repo, plugin_root):
        """A linked worktree runs its OWN copy of the delegate, not
        the main checkout's, even though the delegate path is recorded raw
        and relative."""
        (repo / ".husky" / "_").mkdir(parents=True)
        _write_and_chmod(repo / ".husky" / "_" / "pre-commit", "#!/usr/bin/env bash\nexit 3\n")

        wt = repo.parent / "wt2"
        _git(repo, "worktree", "add", str(wt), "-b", "wt2")
        (wt / ".husky" / "_").mkdir(parents=True)
        wt_marker = wt / "delegate_ran"
        _write_and_chmod(
            wt / ".husky" / "_" / "pre-commit",
            f'#!/usr/bin/env bash\ntouch "{wt_marker}"\nexit 0\n',
        )

        wrapper = wt / "wrapper-pre-commit"
        _write_and_chmod(
            wrapper,
            hooks.render_wrapper(
                hook_name="pre-commit",
                delegate_raw=".husky/_",
                delegate_mode="dir",
                plugin_root=plugin_root,
            ),
        )
        result = subprocess.run([str(wrapper)], cwd=wt, capture_output=True, text=True)
        assert result.returncode == 0
        assert wt_marker.exists()


# ---- Five(+one)-branch action table + idempotency + non-ping-pong --------------


class TestInstallOrHeal:
    def test_unset_absent_installs_plain_slots_byte_identical_to_template(self, repo, plugin_root):
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.changed
        hooks_dir = repo / ".git" / "hooks"
        assert (hooks_dir / "pre-commit").read_text() == hooks.PRECOMMIT_TEMPLATE_PATH.read_text()
        assert os.access(hooks_dir / "pre-commit", os.X_OK)
        for name in hooks.FINALIZE_HOOK_NAMES:
            assert (hooks_dir / name).is_symlink()
            assert os.readlink(hooks_dir / name) == str(
                plugin_root / "scripts" / hooks.FINALIZE_DISPATCHER
            )

    def test_unset_absent_second_run_reports_no_change(self, repo, plugin_root):
        hooks.install_or_heal(repo, "install", plugin_root)
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert not result.changed

    def test_drifted_precommit_content_is_topped_up_in_place(self, repo, plugin_root):
        """A Praxion-installed pre-commit hook whose body predates the
        current shipped template is rewritten byte-for-byte on the next
        install/upgrade run -- the content-aware top-up mechanism the
        onboarding skill's bespoke predicate table previously carried,
        now subsumed by the installer's own idempotent write."""
        hooks_dir = repo / ".git" / "hooks"
        stale_body = hooks.PRECOMMIT_TEMPLATE_PATH.read_text(encoding="utf-8").replace(
            "id-citation-discipline.py", "id-citation-discipline-OLD.py"
        )
        _write_and_chmod(hooks_dir / "pre-commit", stale_body)
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.changed
        assert (hooks_dir / "pre-commit").read_text() == hooks.PRECOMMIT_TEMPLATE_PATH.read_text()

    def test_unset_foreign_occupied_preserves_backup_and_installs_wrapper(self, repo, plugin_root):
        hooks_dir = repo / ".git" / "hooks"
        _write_and_chmod(hooks_dir / "pre-commit", "#!/usr/bin/env bash\necho custom\nexit 0\n")
        original = (hooks_dir / "pre-commit").read_text()
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.changed
        assert (hooks_dir / "pre-commit.pre-praxion").read_text() == original
        assert hooks._has_marker(hooks_dir / "pre-commit", hooks.WRAPPER_MARKER)

    def test_unset_foreign_occupied_never_overwrites_existing_backup(self, repo, plugin_root):
        hooks_dir = repo / ".git" / "hooks"
        _write_and_chmod(
            hooks_dir / "pre-commit.pre-praxion", "#!/usr/bin/env bash\necho original\n"
        )
        _write_and_chmod(hooks_dir / "pre-commit", "#!/usr/bin/env bash\necho newer\nexit 0\n")
        hooks.install_or_heal(repo, "install", plugin_root)
        assert "original" in (hooks_dir / "pre-commit.pre-praxion").read_text()

    def test_foreign_hookspath_creates_wrapper_dir_and_repoints(self, repo, plugin_root):
        (repo / ".husky" / "_").mkdir(parents=True)
        _git(repo, "config", "core.hooksPath", ".husky/_")
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.changed
        wrapper_dir = hooks.wrapper_dir_path(repo)
        assert wrapper_dir.is_dir()
        for name in hooks.ALL_HOOK_NAMES:
            assert (wrapper_dir / name).is_file()
        current = _git(repo, "config", "--get", "core.hooksPath").stdout.strip()
        assert current == str(wrapper_dir)
        recorded = hooks.read_recorded_delegate(wrapper_dir)
        assert recorded is not None
        assert recorded.raw == ".husky/_"

    def test_praxion_wrapper_second_run_performs_zero_writes(self, repo, plugin_root):
        (repo / ".husky" / "_").mkdir(parents=True)
        _git(repo, "config", "core.hooksPath", ".husky/_")
        hooks.install_or_heal(repo, "install", plugin_root)
        wrapper_dir = hooks.wrapper_dir_path(repo)
        mtimes_before = {p.name: p.stat().st_mtime_ns for p in wrapper_dir.glob("*")}
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert not result.changed
        mtimes_after = {p.name: p.stat().st_mtime_ns for p in wrapper_dir.glob("*")}
        assert mtimes_before == mtimes_after

    def test_non_ping_pong_refuses_manufactured_self_delegation_on_heal(self, repo, plugin_root):
        """A manufactured self-delegating wrapper dir: the recorded delegate
        resolves to the wrapper directory itself. Heal must refuse and leave
        core.hooksPath untouched (still Unset)."""
        wrapper_dir = hooks.wrapper_dir_path(repo)
        wrapper_dir.mkdir(parents=True)
        hooks.write_recorded_delegate(wrapper_dir, str(wrapper_dir))
        result = hooks.install_or_heal(repo, "heal", plugin_root)
        assert result.refused
        assert "non-ping-pong" in result.reason
        current = _git_unchecked(repo, "config", "--get", "core.hooksPath")
        assert current.returncode != 0

    def test_config_resolving_to_wrapper_dir_via_symlink_is_never_adopted_as_foreign(
        self, repo, plugin_root
    ):
        """A `core.hooksPath` that resolves (through a symlink) to the exact
        wrapper directory is classified `PraxionWrapper` by observation
        itself -- it never reaches the `Foreign` adoption branch at all, so
        the self-delegation hazard is caught one layer earlier than the
        explicit non-ping-pong check. Still refuses (no recorded delegate
        yet), never silently succeeds."""
        wrapper_dir = hooks.wrapper_dir_path(repo)
        wrapper_dir.mkdir(parents=True)
        loop = repo / "loop-to-wrapper"
        loop.symlink_to(wrapper_dir)
        _git(repo, "config", "core.hooksPath", str(loop))
        assert isinstance(hooks.observe_hooks_path(repo), hooks.PraxionWrapper)
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.refused

    def test_heal_repoints_when_hookspath_unset_but_wrapper_survives(self, repo, plugin_root):
        (repo / ".husky" / "_").mkdir(parents=True)
        _git(repo, "config", "core.hooksPath", ".husky/_")
        hooks.install_or_heal(repo, "install", plugin_root)
        wrapper_dir = hooks.wrapper_dir_path(repo)
        _git(repo, "config", "--unset", "core.hooksPath")

        result = hooks.install_or_heal(repo, "heal", plugin_root)
        assert result.changed
        current = _git(repo, "config", "--get", "core.hooksPath").stdout.strip()
        assert current == str(wrapper_dir)

    def test_heal_never_onboards_a_fresh_unset_absent_slot(self, repo, plugin_root):
        result = hooks.install_or_heal(repo, "heal", plugin_root)
        assert not result.changed
        assert not (repo / ".git" / "hooks" / "pre-commit").exists()

    def test_heal_is_noop_when_hookspath_unset_and_no_wrapper_dir(self, repo, plugin_root):
        result = hooks.install_or_heal(repo, "heal", plugin_root)
        assert not result.changed
        assert not result.refused

    def test_unresolvable_refuses_and_changes_nothing(self, repo, plugin_root):
        garbage = repo / "not-a-dir.txt"
        garbage.write_text("x")
        _git(repo, "config", "core.hooksPath", "not-a-dir.txt")
        result = hooks.install_or_heal(repo, "install", plugin_root)
        assert result.refused
        assert not result.changed
        assert not (repo / ".git" / "hooks" / "pre-commit").exists()

    def test_wrapper_dir_resolves_via_git_common_dir_in_linked_worktree(self, repo, plugin_root):
        wt = repo.parent / "wt-common"
        _git(repo, "worktree", "add", str(wt), "-b", "wt-common-branch")
        assert hooks.wrapper_dir_path(wt) == hooks.wrapper_dir_path(repo)
        # And it does NOT live under the linked worktree's own .git file.
        wt_git = _git(wt, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip()
        assert not str(hooks.wrapper_dir_path(wt)).startswith(wt_git)


# ---- --status / --uninstall / exit-code contract --------------------------------


class TestCLI:
    def test_usage_error_no_mode_flag(self, repo):
        result = _run_cli("--repo-root", str(repo))
        assert result.returncode == 2

    def test_usage_error_two_mode_flags(self, repo):
        result = _run_cli("--install", "--heal", "--repo-root", str(repo))
        assert result.returncode == 2

    def test_environment_error_not_a_git_repo(self, tmp_path):
        result = _run_cli("--status", "--repo-root", str(tmp_path))
        assert result.returncode == 4

    def test_status_ok_when_all_slots_can_fire(self, repo, plugin_root):
        hooks.install_or_heal(repo, "install", plugin_root)
        result = _run_cli("--status", "--repo-root", str(repo), "--plugin-root", str(plugin_root))
        assert result.returncode == 0

    def test_status_and_install_from_linked_worktree_resolve_common_hooks_dir(
        self, repo, plugin_root
    ):
        """Canary: `--install`/`--status` from a linked worktree (whose
        `.git` is a file, not a directory) must resolve the plain-slot hooks
        directory through the git COMMON dir -- before the fix, `--install`
        crashed `NotADirectoryError` and `--status` reported every slot
        absent because both read `repo_root / ".git" / "hooks"` literally."""
        wt = repo.parent / "wt-if16"
        _git(repo, "worktree", "add", str(wt), "-b", "wt-if16-branch")

        install_result = _run_cli(
            "--install", "--repo-root", str(wt), "--plugin-root", str(plugin_root)
        )
        assert install_result.returncode == 0, install_result.stderr

        status_result = _run_cli(
            "--status",
            "--repo-root",
            str(wt),
            "--plugin-root",
            str(plugin_root),
            "--json",
        )
        assert status_result.returncode == 0, status_result.stdout
        payload = json.loads(status_result.stdout)
        assert not payload["cannot_fire"], payload
        assert all(slot["praxion_can_fire"] for slot in payload["slots"])
        # And the slots landed in the COMMON dir's hooks/, not the worktree's own .git file.
        common_dir = hooks.git_common_dir(wt)
        assert (common_dir / "hooks" / "pre-commit").is_file()

    def test_status_actionable_when_a_slot_cannot_fire(self, repo, plugin_root):
        result = _run_cli("--status", "--repo-root", str(repo), "--plugin-root", str(plugin_root))
        assert result.returncode == 1

    def test_status_json_names_unresolvable_slots(self, repo, plugin_root):
        garbage = repo / "x.txt"
        garbage.write_text("x")
        _git(repo, "config", "core.hooksPath", "x.txt")
        result = _run_cli(
            "--status", "--repo-root", str(repo), "--plugin-root", str(plugin_root), "--json"
        )
        assert result.returncode == 1
        payload = json.loads(result.stdout)
        assert payload["cannot_fire"]

    def test_install_refused_returns_exit_3(self, repo, plugin_root):
        garbage = repo / "x.txt"
        garbage.write_text("x")
        _git(repo, "config", "core.hooksPath", "x.txt")
        result = _run_cli("--install", "--repo-root", str(repo), "--plugin-root", str(plugin_root))
        assert result.returncode == 3

    def test_install_ok_returns_exit_0(self, repo, plugin_root):
        result = _run_cli("--install", "--repo-root", str(repo), "--plugin-root", str(plugin_root))
        assert result.returncode == 0

    def test_uninstall_restores_pre_praxion_hookspath(self, repo, plugin_root):
        (repo / ".husky" / "_").mkdir(parents=True)
        _git(repo, "config", "core.hooksPath", ".husky/_")
        hooks.install_or_heal(repo, "install", plugin_root)

        result = hooks.uninstall(repo)
        assert result.changed
        current = _git(repo, "config", "--get", "core.hooksPath").stdout.strip()
        assert current == ".husky/_"
        assert not hooks.wrapper_dir_path(repo).exists()

    def test_uninstall_restores_backup_for_wrapper_file(self, repo, plugin_root):
        hooks_dir = repo / ".git" / "hooks"
        _write_and_chmod(hooks_dir / "pre-commit", "#!/usr/bin/env bash\necho custom\nexit 0\n")
        original = (hooks_dir / "pre-commit").read_text()
        hooks.install_or_heal(repo, "install", plugin_root)

        hooks.uninstall(repo)
        assert (hooks_dir / "pre-commit").read_text() == original
        assert not (hooks_dir / "pre-commit.pre-praxion").exists()

    def test_uninstall_removes_fresh_install_with_no_backup(self, repo, plugin_root):
        hooks.install_or_heal(repo, "install", plugin_root)
        result = hooks.uninstall(repo)
        assert result.changed
        assert not (repo / ".git" / "hooks" / "pre-commit").exists()
