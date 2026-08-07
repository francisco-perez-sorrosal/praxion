"""Tests for worktree_guard.py -- PreToolUse boundary enforcement.

Two layers, both load-bearing:

* **Process-boundary tests** (`_run_hook`) drive the hook exactly as Claude Code
  does and assert the *exit code*. That is not a stylistic choice: PreToolUse
  treats only exit 2 as "block this tool call" and silently discards every other
  non-zero as an error the model never sees (see `hooks/commit_gate.sh` for the
  incident that established the convention). A guard whose verdict is right and
  whose exit code is wrong is indistinguishable from no guard, and only a real
  process can prove the code that leaves it.
* **In-process tests** drive the helpers and `main()` directly. They reach the
  branch-level failure modes a subprocess cannot force -- git timing out, a
  target path whose ancestors do not exist, a symlinked path that normalizes
  back into the session tree -- and they are what makes those branches visible
  to coverage at all.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "worktree_guard.py"


def _load_guard_module():
    """Load worktree_guard.py by path (hooks/ is not a package)."""
    spec = importlib.util.spec_from_file_location("worktree_guard_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _load_guard_module()


@pytest.fixture
def main_repo(tmp_path: Path) -> Path:
    """A real git repo serving as the 'main' worktree."""
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


@pytest.fixture
def linked_worktree(main_repo: Path, tmp_path: Path) -> Path:
    """A linked worktree created from the main repo."""
    wt = tmp_path / "linked"
    subprocess.run(
        [
            "git",
            "-C",
            str(main_repo),
            "worktree",
            "add",
            "-q",
            str(wt),
            "-b",
            "feature",
        ],
        check=True,
    )
    return wt


def _run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess with a JSON payload on stdin."""
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


class TestGuardPassThrough:
    """Cases where the guard must NOT block."""

    def test_ignores_non_guarded_tool(self, linked_worktree: Path) -> None:
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 0
        assert result.stderr == ""

    def test_ignores_relative_path(self, linked_worktree: Path) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "subdir/file.md"},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 0

    def test_allows_write_inside_session_worktree(self, linked_worktree: Path) -> None:
        target = linked_worktree / "new.md"
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 0

    def test_allows_write_outside_any_git_tree(self, linked_worktree: Path, tmp_path: Path) -> None:
        non_git = tmp_path / "outside" / "config.json"
        non_git.parent.mkdir()
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(non_git)},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 0

    def test_skips_when_session_is_main_worktree(self, main_repo: Path) -> None:
        # Writing anywhere is fine when we are not in a linked worktree.
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(main_repo / "any.md")},
            "cwd": str(main_repo),
        }
        result = _run_hook(payload, main_repo)
        assert result.returncode == 0

    def test_disable_flag_bypasses_guard(
        self, linked_worktree: Path, main_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(guard.DISABLE_FLAG, "1")
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(main_repo / "leak.md")},
            "cwd": str(linked_worktree),
        }
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=str(linked_worktree),
            env={**{"PATH": ""}, guard.DISABLE_FLAG: "1"},
            timeout=10,
        )
        # Even with a hostile cross-boundary target, the disable flag short-circuits.
        assert result.returncode == 0


class TestGuardBlocks:
    """Cases where the guard MUST block."""

    def test_blocks_write_to_sibling_main_repo(
        self, linked_worktree: Path, main_repo: Path
    ) -> None:
        leak = main_repo / "rules" / "leak.md"
        leak.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(leak)},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr
        assert "cross-worktree" in result.stderr

    def test_blocks_edit_tool_same_semantics(self, linked_worktree: Path, main_repo: Path) -> None:
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(main_repo / "README.md")},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 2

    def test_blocks_write_to_new_path_under_main_repo(
        self, linked_worktree: Path, main_repo: Path
    ) -> None:
        # File does not yet exist; guard must walk parents to probe git tree.
        new_file = main_repo / "fresh" / "nested" / "new.md"
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(new_file)},
            "cwd": str(linked_worktree),
        }
        result = _run_hook(payload, linked_worktree)
        assert result.returncode == 2


class TestGuardFailsOpen:
    """Internal errors must never wedge the user's work."""

    def test_malformed_payload_exits_zero(self, linked_worktree: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="not-json",
            capture_output=True,
            text=True,
            cwd=str(linked_worktree),
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_payload_exits_zero(self, linked_worktree: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            input="{}",
            capture_output=True,
            text=True,
            cwd=str(linked_worktree),
            timeout=10,
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# In-process helpers
# ---------------------------------------------------------------------------


def _drive_main(payload: object, monkeypatch: pytest.MonkeyPatch, raw: str | None = None) -> None:
    """Run guard.main() in-process with the payload on stdin."""
    monkeypatch.delenv(guard.DISABLE_FLAG, raising=False)
    stdin = raw if raw is not None else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    guard.main()


class TestDisableFlag:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "  yes  "])
    def test_truthy_values_disable_the_guard(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(guard.DISABLE_FLAG, value)
        assert guard._is_disabled() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
    def test_falsy_values_leave_the_guard_active(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(guard.DISABLE_FLAG, value)
        assert guard._is_disabled() is False

    def test_unset_flag_leaves_the_guard_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(guard.DISABLE_FLAG, raising=False)
        assert guard._is_disabled() is False


class TestGitInvocation:
    """`_git` is the guard's only source of truth; every failure mode returns None."""

    def test_returns_stripped_stdout_on_success(self, main_repo: Path) -> None:
        assert guard._git(main_repo, "rev-parse", "--show-toplevel") == str(
            main_repo.resolve()
        ) or guard._git(main_repo, "rev-parse", "--show-toplevel").endswith(main_repo.name)

    def test_returns_none_on_non_zero_exit(self, tmp_path: Path) -> None:
        outside = tmp_path / "not-a-repo"
        outside.mkdir()
        assert guard._git(outside, "rev-parse", "--show-toplevel") is None

    def test_returns_none_when_stdout_is_empty(self, main_repo: Path) -> None:
        assert guard._git(main_repo, "rev-parse", "--quiet", "--verify", "HEAD^{tree}") is not None
        assert guard._git(main_repo, "config", "--get", "praxion.nonexistent.key") is None

    def test_returns_none_when_git_times_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=guard.SUBPROCESS_TIMEOUT_SECONDS)

        monkeypatch.setattr(guard.subprocess, "run", _timeout)
        assert guard._git(Path("/tmp"), "rev-parse") is None

    def test_returns_none_when_git_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _missing(*_args, **_kwargs):
            raise OSError("git not found")

        monkeypatch.setattr(guard.subprocess, "run", _missing)
        assert guard._git(Path("/tmp"), "rev-parse") is None


class TestSessionWorktreeResolution:
    def test_linked_worktree_resolves_to_its_root(self, linked_worktree: Path) -> None:
        assert guard._resolve_session_worktree(linked_worktree) == linked_worktree.resolve()

    def test_main_worktree_resolves_to_none(self, main_repo: Path) -> None:
        assert guard._resolve_session_worktree(main_repo) is None

    def test_non_git_cwd_resolves_to_none(self, tmp_path: Path) -> None:
        assert guard._resolve_session_worktree(tmp_path) is None

    def test_unresolvable_toplevel_resolves_to_none(
        self, linked_worktree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """git answering the dir probes but not `--show-toplevel` must not
        produce a half-built session root."""
        real_git = guard._git

        def _no_toplevel(cwd: Path, *args: str):
            if args[:2] == ("rev-parse", "--show-toplevel"):
                return None
            return real_git(cwd, *args)

        monkeypatch.setattr(guard, "_git", _no_toplevel)
        assert guard._resolve_session_worktree(linked_worktree) is None


class TestPathContainment:
    def test_path_under_root_is_within(self, tmp_path: Path) -> None:
        assert guard._is_within(tmp_path / "a" / "b.md", tmp_path.resolve()) is True

    def test_root_itself_is_within(self, tmp_path: Path) -> None:
        assert guard._is_within(tmp_path, tmp_path.resolve()) is True

    def test_sibling_path_is_not_within(self, tmp_path: Path) -> None:
        sibling = tmp_path.parent / f"{tmp_path.name}-other"
        assert guard._is_within(sibling / "x.md", tmp_path.resolve()) is False


class TestNearestExistingAncestor:
    def test_finds_the_first_existing_parent(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "file.md"
        assert guard._nearest_existing_ancestor(deep) == tmp_path

    def test_existing_parent_is_returned_directly(self, tmp_path: Path) -> None:
        assert guard._nearest_existing_ancestor(tmp_path / "file.md") == tmp_path

    def test_filesystem_root_has_no_ancestor_above_it(self) -> None:
        assert guard._nearest_existing_ancestor(Path("/")) is None


class TestTargetGitRoot:
    def test_directory_target_probes_itself(self, main_repo: Path) -> None:
        assert guard._target_git_root(main_repo) == main_repo.resolve()

    def test_nonexistent_target_probes_its_nearest_ancestor(self, main_repo: Path) -> None:
        assert guard._target_git_root(main_repo / "no" / "such" / "f.md") == main_repo.resolve()

    def test_target_outside_any_repo_returns_none(self, tmp_path: Path) -> None:
        outside = tmp_path / "plain"
        outside.mkdir()
        assert guard._target_git_root(outside / "f.md") is None

    def test_target_with_no_existing_ancestor_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guard, "_nearest_existing_ancestor", lambda _p: None)
        assert guard._target_git_root(Path("/nonexistent/deep/f.md")) is None


class TestBlockVerdict:
    def test_block_exits_with_the_only_code_pretooluse_treats_as_blocking(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exit 2, not 1. PreToolUse discards every other non-zero code, so a
        correct verdict on the wrong code is a verdict nobody receives."""
        with pytest.raises(SystemExit) as excinfo:
            guard._block("/other/repo/f.md", tmp_path / "session", tmp_path / "other")
        assert excinfo.value.code == 2

        stderr = capsys.readouterr().err
        assert "BLOCKED" in stderr
        assert "/other/repo/f.md" in stderr
        assert guard.DISABLE_FLAG in stderr, "the block message must name its own escape hatch"


class TestMainInProcess:
    def test_disable_flag_short_circuits_before_reading_stdin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(guard.DISABLE_FLAG, "1")

        def _explode():
            raise AssertionError("stdin must not be read when the guard is disabled")

        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        monkeypatch.setattr(sys.stdin, "read", _explode)
        guard.main()  # returns without touching stdin

    def test_malformed_json_returns_without_blocking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _drive_main(None, monkeypatch, raw="{not json")

    @pytest.mark.parametrize("tool_name", ["Bash", "Read", "Grep", ""])
    def test_unguarded_tools_return_immediately(
        self, tool_name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _drive_main({"tool_name": tool_name, "tool_input": {"file_path": "/x"}}, monkeypatch)

    @pytest.mark.parametrize("file_path", ["", "relative/path.md"])
    def test_missing_or_relative_target_returns_immediately(
        self, file_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _drive_main({"tool_name": "Write", "tool_input": {"file_path": file_path}}, monkeypatch)

    def test_absent_cwd_falls_back_to_the_process_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No `cwd` in the payload must not crash — os.getcwd() is the fallback."""
        monkeypatch.chdir(tmp_path)
        _drive_main(
            {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "f.md")}},
            monkeypatch,
        )
        assert os.getcwd() == str(tmp_path.resolve())

    def test_main_worktree_session_never_blocks(
        self, main_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _drive_main(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(main_repo / "anything.md")},
                "cwd": str(main_repo),
            },
            monkeypatch,
        )

    def test_target_inside_the_session_worktree_never_blocks(
        self, linked_worktree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _drive_main(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(linked_worktree / "new.md")},
                "cwd": str(linked_worktree),
            },
            monkeypatch,
        )

    def test_target_outside_every_git_tree_never_blocks(
        self, linked_worktree: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = tmp_path / "config"
        outside.mkdir()
        _drive_main(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(outside / "settings.json")},
                "cwd": str(linked_worktree),
            },
            monkeypatch,
        )

    def test_target_normalizing_back_into_the_session_root_never_blocks(
        self, linked_worktree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Symlink / path-normalization edge: containment says "outside" but the
        target's git tree is the session's own, so the write is legitimate."""
        monkeypatch.setattr(guard, "_is_within", lambda _c, _r: False)
        _drive_main(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(linked_worktree / "inside.md")},
                "cwd": str(linked_worktree),
            },
            monkeypatch,
        )

    @pytest.mark.parametrize("tool_name", ["Write", "Edit", "NotebookEdit"])
    def test_cross_tree_write_blocks_for_every_guarded_tool(
        self,
        tool_name: str,
        linked_worktree: Path,
        main_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(SystemExit) as excinfo:
            _drive_main(
                {
                    "tool_name": tool_name,
                    "tool_input": {"file_path": str(main_repo / "leak.md")},
                    "cwd": str(linked_worktree),
                },
                monkeypatch,
            )
        assert excinfo.value.code == 2

    def test_cross_tree_write_to_a_third_worktree_blocks(
        self,
        linked_worktree: Path,
        main_repo: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The sibling-worktree direction, not just the main-repo one."""
        other = tmp_path / "second"
        subprocess.run(
            ["git", "-C", str(main_repo), "worktree", "add", "-q", str(other), "-b", "second"],
            check=True,
        )
        with pytest.raises(SystemExit) as excinfo:
            _drive_main(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(other / "README.md")},
                    "cwd": str(linked_worktree),
                },
                monkeypatch,
            )
        assert excinfo.value.code == 2
