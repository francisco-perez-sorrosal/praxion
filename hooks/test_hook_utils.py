"""Tests for hooks/_hook_utils.py — shared hook utilities.

Covers:
  - is_disabled(): per-project opt-out flag parsing.
  - End-to-end integration: each observability hook returns exit 0 without
    producing output when PRAXION_DISABLE_OBSERVABILITY is set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _clear_praxion_env(monkeypatch):
    """Each test starts with the observability opt-out flag unset."""
    monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)


def _import_hook_utils():
    """Reload `_hook_utils` so tests pick up current env state."""
    sys.path.insert(0, str(HOOKS_DIR))
    import importlib

    import _hook_utils

    return importlib.reload(_hook_utils)


def test_is_disabled_false_when_unset(monkeypatch):
    hu = _import_hook_utils()
    assert hu.is_disabled("PRAXION_DISABLE_OBSERVABILITY") is False


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "Yes", "  yes  "])
def test_is_disabled_true_for_truthy_values(monkeypatch, truthy):
    monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", truthy)
    hu = _import_hook_utils()
    assert hu.is_disabled("PRAXION_DISABLE_OBSERVABILITY") is True


@pytest.mark.parametrize("falsy", ["", "0", "false", "no", "off", "disabled"])
def test_is_disabled_false_for_falsy_values(monkeypatch, falsy):
    monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", falsy)
    hu = _import_hook_utils()
    assert hu.is_disabled("PRAXION_DISABLE_OBSERVABILITY") is False


def test_observability_flag_name():
    hu = _import_hook_utils()
    assert hu.DISABLE_OBSERVABILITY == "PRAXION_DISABLE_OBSERVABILITY"
    assert hu.DISABLE_OBSERVABILITY.startswith("PRAXION_DISABLE_")


# -- Integration: observability hooks short-circuit when disabled -------------


def _run_hook(script_name: str, payload: dict, env_extra: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script_name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


_MINIMAL_PAYLOAD = {
    "cwd": "/tmp",
    "hook_event_name": "SessionStart",
    "session_id": "test-session",
    "transcript_path": "/dev/null",
    "tool_name": "Bash",
    "tool_input": {"command": "echo hi"},
    "tool_response": {},
}


@pytest.mark.parametrize(
    "script",
    ["send_event.py", "capture_session.py", "capture_memory.py"],
)
def test_observability_hook_exits_silently_when_disabled(script):
    """With PRAXION_DISABLE_OBSERVABILITY set, each observability hook must
    exit 0 and emit no output."""
    result = _run_hook(script, _MINIMAL_PAYLOAD, {"PRAXION_DISABLE_OBSERVABILITY": "1"})
    assert result.returncode == 0, f"{script} exited {result.returncode}: {result.stderr}"
    assert result.stdout == "", f"{script} emitted stdout when disabled: {result.stdout!r}"
