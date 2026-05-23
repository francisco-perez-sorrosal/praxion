"""Canary tests for hooks/commit_gate.sh — PreToolUse shell fast-path for git commits.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. The gate's job is to intercept `git commit` commands
and forward them to a Python hook; non-commit commands must be silently ignored.
These tests prove the gate:
  - blocks the fast-path for git commit commands (they reach Python)
  - allows the fast-path for non-commit commands (silent exit 0)
  - respects the PRAXION_DISABLE_MEMORY_MCP kill-switch
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
GATE_SCRIPT = HOOKS_DIR / "commit_gate.sh"

DELEGATION_MARKER = "COMMIT_GATE_DELEGATED"


def _write_delegation_spy(tmp_path: Path) -> Path:
    """Write a Python stub that prints a marker when invoked by the gate."""
    spy = tmp_path / "spy_hook.py"
    spy.write_text(
        f"import sys\nsys.stdin.read()\nprint({DELEGATION_MARKER!r})\n",
        encoding="utf-8",
    )
    return spy


def _run_gate(
    payload: dict,
    *,
    hook: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke commit_gate.sh with a JSON payload on stdin."""
    real_hook = (
        str(hook) if hook else str(HOOKS_DIR / "check_id_citation_discipline.py")
    )
    # Pop the disable var for a clean baseline FIRST (Praxion's own env sets it),
    # then apply the test's env LAST so a test that explicitly sets
    # PRAXION_DISABLE_MEMORY_MCP=1 still takes effect.
    merged_env = dict(os.environ)
    merged_env.pop("PRAXION_DISABLE_MEMORY_MCP", None)
    merged_env.update(env or {})
    return subprocess.run(
        [str(GATE_SCRIPT), real_hook],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=merged_env,
        check=False,
    )


def _make_bash_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------------------
# Script integrity
# ---------------------------------------------------------------------------


def test_gate_script_is_executable() -> None:
    """The shell gate must be executable or the hook silently no-ops."""
    assert GATE_SCRIPT.exists(), f"missing {GATE_SCRIPT}"
    assert os.access(GATE_SCRIPT, os.X_OK), (
        f"{GATE_SCRIPT} is not executable (chmod +x required)"
    )


# ---------------------------------------------------------------------------
# Canary: git commit commands reach Python (fast-path does NOT fire)
# ---------------------------------------------------------------------------


def test_blocks_fast_path_for_git_commit_command(tmp_path: Path) -> None:
    """Canary: a `git commit` command is forwarded to Python, not silently dropped.

    The gate exists to run the Python hook on every commit attempt. If the
    fast-path fires for a `git commit` command, violations would be silently
    missed. This test proves the gate bites by asserting the spy hook is reached.
    """
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload("git commit -m 'add feature'"), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        "commit_gate.sh must delegate a `git commit` command to Python "
        f"(fast-path must NOT silence it); stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}"
    )


def test_blocks_fast_path_for_git_commit_no_edit(tmp_path: Path) -> None:
    """Canary: `git commit --no-edit` is also forwarded to Python."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload("git commit --no-edit"), hook=spy_hook)
    assert result.returncode == 0
    assert DELEGATION_MARKER in result.stdout, (
        "commit_gate.sh must delegate `git commit --no-edit` to Python"
    )


# ---------------------------------------------------------------------------
# Happy paths: non-commit commands are silently ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git push origin main",
        "ls -la",
        "python script.py",
    ],
    ids=["git-status", "git-push", "ls", "python"],
)
def test_non_commit_command_exits_fast(command: str, tmp_path: Path) -> None:
    """Non-commit commands exit 0 with empty stdout — Python never runs."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(_make_bash_payload(command), hook=spy_hook)
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}"
    assert DELEGATION_MARKER not in result.stdout, (
        f"non-commit command {command!r} must not reach Python; "
        f"stdout={result.stdout!r}"
    )


def test_kill_switch_skips_gate_entirely(tmp_path: Path) -> None:
    """PRAXION_DISABLE_MEMORY_MCP=1 causes the gate to exit 0 without forwarding."""
    spy_hook = _write_delegation_spy(tmp_path)
    result = _run_gate(
        _make_bash_payload("git commit -m 'test'"),
        hook=spy_hook,
        env={"PRAXION_DISABLE_MEMORY_MCP": "1"},
    )
    assert result.returncode == 0
    assert DELEGATION_MARKER not in result.stdout, (
        "PRAXION_DISABLE_MEMORY_MCP=1 must suppress forwarding to Python"
    )
