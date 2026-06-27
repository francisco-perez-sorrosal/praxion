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


# -- Rotation-behavior tests --------------------------------------------------
# These tests target append_observation / _rotate_if_needed / OBSERVATIONS_MAX_BYTES
# which are added to _hook_utils.py by the paired implementer step.
# They are intentionally RED until that step lands (AttributeError on missing symbols).


def test_rotate_triggers_at_threshold(tmp_path, monkeypatch):
    """When the active file exceeds the size threshold, append_observation
    renames it to <obs_path>.1 and the new row lands in a fresh active file."""
    hu = _import_hook_utils()
    obs_path = tmp_path / "observations.jsonl"
    # Pre-populate so file size exceeds the to-be-set threshold of 1 byte.
    obs_path.write_text('{"existing":"row"}\n', encoding="utf-8")

    monkeypatch.setattr(hu, "OBSERVATIONS_MAX_BYTES", 1)
    hu.append_observation(obs_path, {"event": "new"})

    rotated = Path(str(obs_path) + ".1")
    assert rotated.exists(), "original obs file must be renamed to .1 after threshold breach"
    active_lines = obs_path.read_text(encoding="utf-8").splitlines()
    assert len(active_lines) == 1, "active file must hold exactly the new row after rotation"
    assert "new" in active_lines[0], "new row must appear in the fresh active file"


def test_rotate_below_threshold_no_rotate(tmp_path, monkeypatch):
    """A single append that keeps the file below the default (large) threshold
    must not create a .1 rotation file."""
    hu = _import_hook_utils()
    obs_path = tmp_path / "observations.jsonl"

    # Default OBSERVATIONS_MAX_BYTES is 10 MiB; one tiny row is far below it.
    hu.append_observation(obs_path, {"event": "tiny"})

    rotated = Path(str(obs_path) + ".1")
    assert not rotated.exists(), "no .1 rotation file must exist when below the threshold"


def test_rotate_swallows_oserror(tmp_path, monkeypatch):
    """When os.replace raises OSError during rotation, append_observation must
    not propagate the exception and must still write the observation."""
    hu = _import_hook_utils()
    obs_path = tmp_path / "observations.jsonl"
    obs_path.write_text('{"existing":"row"}\n', encoding="utf-8")

    monkeypatch.setattr(hu, "OBSERVATIONS_MAX_BYTES", 1)

    def _fail_replace(*args, **kwargs):
        raise OSError("forced rename failure")

    monkeypatch.setattr(os, "replace", _fail_replace)

    # Must not raise despite the forced OSError.
    hu.append_observation(obs_path, {"event": "swallowed"})

    content = obs_path.read_text(encoding="utf-8")
    assert "swallowed" in content, "observation must be written even when os.replace fails"


def test_append_observation_uses_fcntl_lock(tmp_path):
    """append_observation must use the observations.lock file so that concurrent
    callers are safely serialized; the observation must also be written."""
    hu = _import_hook_utils()
    obs_path = tmp_path / "observations.jsonl"
    observation = {"event": "lock_check", "value": 42}

    hu.append_observation(obs_path, observation)

    lock_path = obs_path.parent / "observations.lock"
    assert lock_path.exists(), "lock file must exist after append_observation"
    content = obs_path.read_text(encoding="utf-8")
    assert "lock_check" in content, "observation must be written to the active file"


def test_canary_rotate_at_threshold_zero(tmp_path, monkeypatch):
    """Gate-liveness canary: with OBSERVATIONS_MAX_BYTES=0 every existing file
    satisfies the rotation condition (size >= 0). After append_observation the
    original file must be at <obs_path>.1.

    This canary must go RED if rotation is ever silently removed."""
    hu = _import_hook_utils()
    obs_path = tmp_path / "observations.jsonl"
    # A zero-byte file: stat().st_size == 0 >= 0 == threshold → rotation fires.
    obs_path.touch()

    monkeypatch.setattr(hu, "OBSERVATIONS_MAX_BYTES", 0)
    hu.append_observation(obs_path, {"event": "canary"})

    rotated = Path(str(obs_path) + ".1")
    assert rotated.exists(), (
        "rotation canary FAILED: <obs_path>.1 must exist when threshold is 0 "
        "— rotation is either absent or misconditioned"
    )
