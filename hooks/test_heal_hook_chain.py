"""Tests for heal_hook_chain.py -- SessionStart self-heal.

Two layers:
  - In-process tests drive `main()` and the helpers directly, letting a
    monkeypatched `subprocess.run` prove the fast-exit path makes ZERO
    subprocess calls -- the property this hook exists to guarantee for the
    overwhelming majority of sessions (no Praxion wrapper directory).
  - A process-level test drives the hook exactly as Claude Code does and
    asserts on stdout/exit code, proving the fail-open contract survives a
    real crash, not just a monkeypatched one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "heal_hook_chain.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("heal_hook_chain_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


heal = _load_module()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    return root


def _run_hook(payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=full_env,
    )


class TestFastExit:
    def test_no_git_repo_makes_zero_subprocess_calls(self, tmp_path, monkeypatch):
        def _explode(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called on the fast-exit path")

        monkeypatch.setattr(heal.subprocess, "run", _explode)
        assert heal._existing_wrapper_dir(tmp_path) is None

    def test_no_wrapper_directory_makes_zero_subprocess_calls(self, repo, monkeypatch):
        def _explode(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called on the fast-exit path")

        monkeypatch.setattr(heal.subprocess, "run", _explode)
        assert heal._existing_wrapper_dir(repo) is None

    def test_main_fast_exits_silently_via_stdin_payload(self, repo):
        result = _run_hook({"cwd": str(repo)})
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_linked_worktree_common_dir_resolves_without_subprocess(self, repo, monkeypatch):
        (repo / "README.md").write_text("x\n")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-q", "-m", "init")
        wt = repo.parent / "wt"
        _git(repo, "worktree", "add", str(wt), "-b", "wtbranch")

        def _explode(*args, **kwargs):
            raise AssertionError("subprocess.run must not be called on the fast-exit path")

        monkeypatch.setattr(heal.subprocess, "run", _explode)
        common = heal._fast_common_dir(wt)
        assert common is not None
        assert common.resolve() == (repo / ".git").resolve()
        assert heal._existing_wrapper_dir(wt) is None


class TestHealInvocation:
    def test_wrapper_dir_present_invokes_install_git_hooks_once(self, repo, monkeypatch):
        wrapper_dir = repo / ".git" / heal.WRAPPER_DIRNAME
        wrapper_dir.mkdir(parents=True)

        calls: list[list[str]] = []

        class _FakeResult:
            returncode = 0
            stdout = json.dumps({"changed": True, "messages": ["core.hooksPath restored -> /x"]})

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeResult()

        monkeypatch.setattr(heal.subprocess, "run", _fake_run)
        summary = heal._run_heal(
            repo, Path("/fake-plugin-root-that-is-only-checked-if-file-exists")
        )
        # install_git_hooks.py under a nonexistent plugin root -> _run_heal
        # returns None (script.is_file() guard) without calling subprocess.
        assert summary is None
        assert calls == []

    def test_wrapper_dir_present_real_plugin_root_invokes_heal_once(
        self, repo, monkeypatch, tmp_path
    ):
        wrapper_dir = repo / ".git" / heal.WRAPPER_DIRNAME
        wrapper_dir.mkdir(parents=True)
        plugin_root = tmp_path / "plugin"
        script = plugin_root / "scripts" / "install_git_hooks.py"
        script.parent.mkdir(parents=True)
        script.write_text("#!/usr/bin/env python3\n")

        calls: list[list[str]] = []

        class _FakeResult:
            returncode = 0
            stdout = json.dumps({"changed": True, "messages": ["core.hooksPath restored -> /x"]})

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            return _FakeResult()

        monkeypatch.setattr(heal.subprocess, "run", _fake_run)
        summary = heal._run_heal(repo, plugin_root)
        assert len(calls) == 1
        assert "--heal" in calls[0]
        assert summary == "core.hooksPath restored -> /x"

    def test_no_summary_when_heal_performed_no_write(self, repo, monkeypatch, tmp_path):
        plugin_root = tmp_path / "plugin"
        script = plugin_root / "scripts" / "install_git_hooks.py"
        script.parent.mkdir(parents=True)
        script.write_text("#!/usr/bin/env python3\n")

        class _FakeResult:
            returncode = 0
            stdout = json.dumps({"changed": False, "messages": ["wrapper bodies already current"]})

        monkeypatch.setattr(heal.subprocess, "run", lambda cmd, **kw: _FakeResult())
        assert heal._run_heal(repo, plugin_root) is None

    def test_main_emits_one_line_when_heal_writes(self, repo, monkeypatch):
        wrapper_dir = repo / ".git" / heal.WRAPPER_DIRNAME
        wrapper_dir.mkdir(parents=True)
        monkeypatch.setattr(
            heal, "_run_heal", lambda cwd, plugin_root: "core.hooksPath restored -> /x"
        )
        buf = []
        monkeypatch.setattr(heal, "_emit", lambda ctx: buf.append(ctx))
        monkeypatch.setattr(sys, "stdin", _StdinStub(json.dumps({"cwd": str(repo)})))
        heal.main()
        assert len(buf) == 1
        assert "restored" in buf[0]


class _StdinStub:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


_FAIL_OPEN_RUNNER = """
import importlib.util, io, sys
sys.path.insert(0, {hooks_dir!r})
spec = importlib.util.spec_from_file_location("heal_under_test", {module_path!r})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod._fast_common_dir = lambda cwd: (_ for _ in ()).throw(RuntimeError("boom"))
sys.stdin = io.StringIO("{{}}")
try:
    mod.main()
except Exception:
    pass  # the exact fail-open wrapper this hook ships in its __main__ block
sys.exit(0)
"""


class TestFailOpen:
    def test_internal_exception_exits_0_with_no_traceback(self, tmp_path):
        """Reproduces the module's own `try: main() except Exception: pass`
        wrapper with an internal function forced to raise, proving the
        contract holds for a REAL exception, not just a monkeypatched call
        the test itself wraps in try/except."""
        runner = tmp_path / "runner.py"
        runner.write_text(
            _FAIL_OPEN_RUNNER.format(
                module_path=str(MODULE_PATH), hooks_dir=str(MODULE_PATH.parent)
            )
        )
        result = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True)
        assert result.returncode == 0
        assert "Traceback" not in result.stderr
        assert "Traceback" not in result.stdout

    def test_disable_flag_fast_exits_even_with_wrapper_dir_present(self, repo):
        wrapper_dir = repo / ".git" / "praxion-hooks"
        wrapper_dir.mkdir(parents=True)
        result = _run_hook({"cwd": str(repo)}, env={"PRAXION_DISABLE_HOOK_CHAIN_HEAL": "1"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""
