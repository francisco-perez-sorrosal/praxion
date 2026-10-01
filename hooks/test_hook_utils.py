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


# -- stated_task_slug: the one reading of a prompt's `Task slug:` marker ------


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Task slug: `auth-flow`", "auth-flow"),
        ("Task slug: auth-flow\n", "auth-flow"),
        ("Task slug:auth-flow", "auth-flow"),
        ("Task  slug:\n  auth-flow", "auth-flow"),
        ("blah\n\nTask slug: auth-flow\nmore", "auth-flow"),
        ("Task slug: auth_flow-2.", "auth_flow-2"),
        ("Task slug: v1.2-fix", "v1"),
    ],
    ids=[
        "backticks",
        "bare",
        "no-space",
        "wrapped-marker",
        "middle-line",
        "alphabet",
        "dot-ends-slug",
    ],
)
def test_stated_task_slug_reads_the_slug_the_marker_names(text, slug):
    assert _import_hook_utils().stated_task_slug(text) == slug


@pytest.mark.parametrize("trailer", [".", ",", ";", ":", ")", "?", "!", "\n", "`."])
def test_stated_task_slug_ends_at_the_first_character_outside_the_alphabet(trailer):
    """Silent failure pinned: a sentence-final period read into the slug pointed
    the brief reminder at `.ai-work/auth-flow./TASK_BRIEF.md`."""
    text = f"Task slug: auth-flow{trailer} Design it."
    assert _import_hook_utils().stated_task_slug(text) == "auth-flow"


def test_stated_task_slug_reads_the_first_marker_when_a_prompt_states_two():
    text = "Task slug: first-slug\n\nlater, Task slug: second-slug."
    assert _import_hook_utils().stated_task_slug(text) == "first-slug"


@pytest.mark.parametrize("text", ["", "no marker here", "Task slug: -auth", "Task slug: "])
def test_stated_task_slug_is_none_without_a_slug(text):
    assert _import_hook_utils().stated_task_slug(text) is None


@pytest.mark.parametrize(
    "not_text",
    [None, 7, 1.5, ["Task slug: x"], {"prompt": "Task slug: x"}, b"Task slug: x"],
    ids=["none", "int", "float", "list", "object", "bytes"],
)
def test_stated_task_slug_is_none_for_input_that_is_not_text(not_text):
    assert _import_hook_utils().stated_task_slug(not_text) is None


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
    ["send_event.py", "capture_session.py", "capture_observations.py"],
)
def test_observability_hook_exits_silently_when_disabled(script):
    """With PRAXION_DISABLE_OBSERVABILITY set, each observability hook must
    exit 0 and emit no output."""
    result = _run_hook(script, _MINIMAL_PAYLOAD, {"PRAXION_DISABLE_OBSERVABILITY": "1"})
    assert result.returncode == 0, f"{script} exited {result.returncode}: {result.stderr}"
    assert result.stdout == "", f"{script} emitted stdout when disabled: {result.stdout!r}"


# -- record_gate_fire() --------------------------------------------------------
# The shared helper every commit-gate script calls to record its own
# pass/warn/block verdict. `append_observation`, `_rotate_if_needed`, and
# `OBSERVATIONS_MAX_BYTES` moved to `hooks/_observation_log/writer.py` --
# their rotation-behavior tests moved with them, to
# `hooks/test_observation_log_writer.py`. What remains here is
# `record_gate_fire`'s own contract: it is a thin forwarding wrapper now, so
# these tests cover the forwarding, the no-`.ai-state/` no-op, and that a
# failure anywhere downstream still cannot reach a gate's exit path. Per-gate
# call-site wiring is covered by each gate's own test file.


def test_record_gate_fire_appends_row_with_expected_fields(tmp_path, monkeypatch):
    hu = _import_hook_utils()
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ai-state").mkdir()

    hu.record_gate_fire("check_token_ratchet", "block", "listing over ceiling", session_id="s1")

    obs_path = tmp_path / ".ai-state" / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["event_type"] == "gate_fire"
    # Both keys carry the same value: `hook` (what the gate-fire rollup groups by)
    # and `tool_name` (the field every other observation event carries).
    assert row["hook"] == "check_token_ratchet"
    assert row["tool_name"] == "check_token_ratchet"
    assert row["outcome"] == "block"
    assert row["reason"] == "listing over ceiling"
    assert row["session_id"] == "s1"
    assert "timestamp" in row


def test_record_gate_fire_noop_when_no_ai_state_dir(tmp_path, monkeypatch):
    """No `.ai-state/` at cwd (e.g. a non-managed project) -> silent no-op."""
    hu = _import_hook_utils()
    monkeypatch.chdir(tmp_path)

    hu.record_gate_fire("check_code_quality", "pass")

    assert not (tmp_path / ".ai-state").exists()


def _import_writer():
    """Import the observation-log writer with `hooks/` on sys.path -- the
    same sibling-style import `_hook_utils.record_gate_fire` uses internally,
    so monkeypatching this module object affects that call too."""
    sys.path.insert(0, str(HOOKS_DIR))
    from _observation_log import writer

    return writer


def test_record_gate_fire_swallows_append_observation_exception(tmp_path, monkeypatch):
    """A defect in the writer's append itself must never reach the gate."""
    hu = _import_hook_utils()
    writer = _import_writer()
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ai-state").mkdir()

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writer, "append_observation", _raise)

    # Must not raise.
    hu.record_gate_fire("check_code_quality", "pass")


def test_record_gate_fire_writes_nothing_when_mode_is_off(tmp_path, monkeypatch):
    """The fixed bug: a gate's row must not leak when recording is off.

    Previously `record_gate_fire` had no mode check of its own at all --
    every row it built landed regardless of the kill switch. It now gates
    through the same `writer.record()` every other writer uses.
    """
    hu = _import_hook_utils()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAXION_OBSERVATION_LOG", "off")
    (tmp_path / ".ai-state").mkdir()

    hu.record_gate_fire("check_token_ratchet", "block", "listing over ceiling")

    assert not (tmp_path / ".ai-state" / "observations.jsonl").exists()
