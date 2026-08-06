"""Canary tests for hooks/commit_gate.sh — PreToolUse shell fast-path for git commits.

Cites: rules/swe/gate-liveness.md — every CODE gate ships a sibling canary proving
it fails on a known-bad input. The gate's job is to intercept `git commit` commands
and forward them to a Python hook; non-commit commands must be silently ignored.
These tests prove the gate:
  - blocks the fast-path for git commit commands (they reach Python)
  - allows the fast-path for non-commit commands (silent exit 0)
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


def _write_exiting_spy(tmp_path: Path, code: int) -> Path:
    """Write a Python stub that exits with `code` after draining stdin."""
    spy = tmp_path / f"exit_{code}_hook.py"
    spy.write_text(f"import sys\nsys.stdin.read()\nsys.exit({code})\n", encoding="utf-8")
    return spy


def _run_gate(
    payload: dict,
    *,
    hook: Path | None = None,
    env: dict[str, str] | None = None,
    blocking: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Invoke commit_gate.sh with a JSON payload on stdin."""
    real_hook = str(hook) if hook else str(HOOKS_DIR / "check_id_citation_discipline.py")
    merged_env = dict(os.environ)
    merged_env.update(env or {})
    argv = [str(GATE_SCRIPT)] + (["--blocking"] if blocking else []) + [real_hook]
    return subprocess.run(
        argv,
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
    assert os.access(GATE_SCRIPT, os.X_OK), f"{GATE_SCRIPT} is not executable (chmod +x required)"


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
        f"non-commit command {command!r} must not reach Python; stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# PreToolUse exit-code translation (--blocking)
# ---------------------------------------------------------------------------


def test_blocking_translates_findings_exit_into_pretooluse_block(tmp_path: Path) -> None:
    """A gate reporting findings (1) must reach Claude Code as a block (2).

    PreToolUse treats *only* exit 2 as "block this tool call"; every other
    non-zero is a non-blocking error the model never sees. Praxion's check_*
    scripts use the POSIX-natural 1-on-findings, so without this translation a
    gate detects a violation perfectly and has its verdict discarded --
    check_id_citation_discipline.py did exactly that while the rule it enforces
    called it "the primary enforcement layer".
    """
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 1),
        blocking=True,
    )
    assert result.returncode == 2


def test_without_blocking_a_findings_exit_passes_through(tmp_path: Path) -> None:
    """Reminders must not block, so the translation is opt-in per invocation.

    remind_adr.py and remind_calibration.py are wrapped by the same gate and
    exit 0 normally -- but a Python traceback also exits 1, the same code a gate
    uses for findings. A blanket translation would turn any crashing reminder
    into a commit blocker.
    """
    result = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 1),
    )
    assert result.returncode == 1


def test_blocking_leaves_clean_and_error_codes_unchanged(tmp_path: Path) -> None:
    """Only the findings code is translated; 0 and 2 pass through untouched."""
    clean = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 0),
        blocking=True,
    )
    script_error = _run_gate(
        _make_bash_payload("git commit -m 'x'"),
        hook=_write_exiting_spy(tmp_path, 2),
        blocking=True,
    )
    assert clean.returncode == 0
    assert script_error.returncode == 2


def test_id_citation_gate_is_wired_as_blocking() -> None:
    """The mechanism is useless unwired -- pin the declaration, not just the code.

    This is the half a unit test cannot reach: commit_gate.sh can translate
    correctly forever while hooks.json invokes it without the flag.
    """
    raw = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))
    # Events nest under a top-level "hooks" key; reading the top level directly
    # yields an empty list and a vacuously passing test.
    hooks_json = raw["hooks"]
    commands = [
        h["command"]
        for group in hooks_json.get("PreToolUse", [])
        for h in group.get("hooks", [])
        if "command" in h
    ]
    id_citation = [c for c in commands if "check_id_citation_discipline.py" in c]
    assert id_citation, "the id-citation gate is not wired into PreToolUse at all"
    for command in id_citation:
        assert "--blocking" in command, f"gate invoked without --blocking: {command}"
