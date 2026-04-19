"""Tests for worktree_guard.py -- PreToolUse boundary enforcement."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "worktree_guard.py"


def _load_guard_module():
    """Load worktree_guard.py by path (hooks/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "worktree_guard_under_test", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
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
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"], check=True
    )
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

    def test_allows_write_outside_any_git_tree(
        self, linked_worktree: Path, tmp_path: Path
    ) -> None:
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

    def test_blocks_edit_tool_same_semantics(
        self, linked_worktree: Path, main_repo: Path
    ) -> None:
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
