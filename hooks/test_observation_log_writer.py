"""The writer records exactly what the registry says, and `standard` mode
classifies tool-call rows.

The writer-truth tests drive `writer.record_tool_call` across every `Mode`
with a distinct row shape and assert the writer's *actual* output (a row
written or not) agrees with `registry.records(event_class, mode)` for the
class that row shape classifies as. A writer whose output disagrees with the
registry -- the defect class `record_gate_fire` demonstrates today by
ignoring the kill switch entirely -- must fail this test.

The classification tests assert `record_tool_call`'s classify-and-decide is a
pure function of (row, mode, marker_present): file-changing and
first-of-subagent tool calls, and Skill calls, are written in `standard`; a
later non-file-changing call from an already-seen subagent is not.
`full` writes every non-blocklisted call regardless of classification. Any
failure to create the first-call marker must still leave the row written --
at-least-once, never zero.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from hooks._observation_log import registry, writer
from hooks._observation_log.modes import Mode


def _write_and_read(
    tmp_path: Path, mode: Mode, row: dict, *, is_subagent: bool = False
) -> list[dict]:
    ai_state_dir = tmp_path / mode.value / ".ai-state"
    ai_state_dir.mkdir(parents=True, exist_ok=True)
    writer.record_tool_call(
        ai_state_dir, row, is_subagent=is_subagent, env={"PRAXION_OBSERVATION_LOG": mode.value}
    )
    obs_path = ai_state_dir / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]


def test_a_file_changing_tool_call_is_written_in_exactly_the_modes_the_registry_allows(
    tmp_path: Path,
) -> None:
    row = {"tool_name": "Write", "file_paths": ["src/thing.py"]}

    for mode in Mode:
        expected = registry.records(registry.EventClass.TOOL_FILE_CHANGE, mode)

        rows = _write_and_read(tmp_path, mode, row)

        assert bool(rows) == expected, (
            f"mode={mode.value}: writer output disagrees with registry.records() "
            f"for TOOL_FILE_CHANGE (wrote={bool(rows)}, registry says={expected})"
        )


def test_canary_a_writer_that_ignores_the_registry_is_caught(tmp_path: Path, monkeypatch) -> None:
    """Gate-liveness canary: force `registry.records` to deny every class,
    then assert a row still cannot be produced -- if the writer under test
    consulted a cached or hardcoded table instead of calling the registry
    live (the `record_gate_fire` defect class this test generalizes), the
    row would still appear and this assertion would catch it.
    """
    monkeypatch.setattr(registry, "records", lambda event_class, mode: False)

    rows = _write_and_read(tmp_path, Mode.FULL, {"tool_name": "Write", "file_paths": ["x.py"]})

    assert rows == [], (
        "with registry.records() forced to deny everything, any row written "
        "proves the writer disagreed with the registry instead of consulting it"
    )


# -- standard-mode row classification -----------------------------------------------


def test_standard_mode_writes_file_changing_and_first_of_subagent_and_skill_but_not_a_later_other_call(
    tmp_path: Path,
) -> None:
    ai_state_dir = tmp_path / "standard-classify" / ".ai-state"
    ai_state_dir.mkdir(parents=True)
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value}

    # First tool call of a subagent, not file-changing: written (TOOL_FIRST_OF_SUBAGENT).
    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "sub-1"},
        is_subagent=True,
        env=env,
    )
    # A later non-file-changing call from the SAME subagent: not written (TOOL_OTHER).
    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "sub-1"},
        is_subagent=True,
        env=env,
    )
    # A file-changing call from the main agent: always written (TOOL_FILE_CHANGE).
    writer.record_tool_call(
        ai_state_dir, {"tool_name": "Edit", "file_paths": ["x.py"]}, is_subagent=False, env=env
    )
    # A Skill call: always written (SKILL_ACTIVATION), regardless of subagent status.
    writer.record_tool_call(
        ai_state_dir, {"tool_name": "Skill", "file_paths": []}, is_subagent=False, env=env
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]

    assert [r["tool_name"] for r in rows] == ["Read", "Edit", "Skill"], (
        "the second, non-file-changing call from an already-seen subagent must not "
        "be recorded in standard mode"
    )


def test_full_mode_writes_every_non_blocklisted_tool_call_regardless_of_classification(
    tmp_path: Path,
) -> None:
    ai_state_dir = tmp_path / "full-classify" / ".ai-state"
    ai_state_dir.mkdir(parents=True)
    env = {"PRAXION_OBSERVATION_LOG": Mode.FULL.value}

    for _ in range(3):
        writer.record_tool_call(
            ai_state_dir,
            {"tool_name": "Read", "file_paths": [], "agent_id": "sub-1"},
            is_subagent=True,
            env=env,
        )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]

    assert len(rows) == 3, "full mode must write every tool call, not just each subagent's first"


def test_unwritable_marker_directory_still_writes_the_first_call_row(
    tmp_path: Path, monkeypatch
) -> None:
    """Append-then-mark ordering means any OSError on the
    marker path must still leave the row written -- at-least-once, never
    absent, even when the marker cannot be created at all.
    """
    ai_state_dir = tmp_path / "unwritable-marker" / ".ai-state"
    ai_state_dir.mkdir(parents=True)
    unwritable_tmp = tmp_path / "no-write-tmp"
    unwritable_tmp.mkdir()
    unwritable_tmp.chmod(0o500)  # read+execute only: marker creation must fail with OSError
    monkeypatch.setenv("TMPDIR", str(unwritable_tmp))

    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "agent-race"},
        is_subagent=True,
        env={"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value},
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]

    assert len(rows) == 1, "an unwritable marker directory must never cost the row itself"


# -- Rotation (moved verbatim from hooks/test_hook_utils.py with the writer) ----


def test_rotate_triggers_at_threshold(tmp_path, monkeypatch):
    """When the active file exceeds the size threshold, append_observation
    renames it to <obs_path>.1 and the new row lands in a fresh active file."""
    obs_path = tmp_path / "observations.jsonl"
    obs_path.write_text('{"existing":"row"}\n', encoding="utf-8")

    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 1)
    writer.append_observation(obs_path, {"event": "new"})

    rotated = Path(str(obs_path) + ".1")
    assert rotated.exists(), "original obs file must be renamed to .1 after threshold breach"
    active_lines = obs_path.read_text(encoding="utf-8").splitlines()
    assert len(active_lines) == 1, "active file must hold exactly the new row after rotation"
    assert "new" in active_lines[0], "new row must appear in the fresh active file"


def test_rotate_below_threshold_no_rotate(tmp_path):
    """A single append that keeps the file below the default (large) threshold
    must not create a .1 rotation file."""
    obs_path = tmp_path / "observations.jsonl"

    writer.append_observation(obs_path, {"event": "tiny"})

    rotated = Path(str(obs_path) + ".1")
    assert not rotated.exists(), "no .1 rotation file must exist when below the threshold"


def test_rotate_swallows_oserror(tmp_path, monkeypatch):
    """When os.replace raises OSError during rotation, append_observation must
    not propagate the exception and must still write the observation."""
    obs_path = tmp_path / "observations.jsonl"
    obs_path.write_text('{"existing":"row"}\n', encoding="utf-8")
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 1)

    def _fail_replace(*args, **kwargs):
        raise OSError("forced rename failure")

    monkeypatch.setattr(os, "replace", _fail_replace)

    writer.append_observation(obs_path, {"event": "swallowed"})

    content = obs_path.read_text(encoding="utf-8")
    assert "swallowed" in content, "observation must be written even when os.replace fails"


def test_append_observation_uses_fcntl_lock(tmp_path):
    """append_observation must use the observations.lock file so that concurrent
    callers are safely serialized; the observation must also be written."""
    obs_path = tmp_path / "observations.jsonl"

    writer.append_observation(obs_path, {"event": "lock_check", "value": 42})

    lock_path = obs_path.parent / "observations.lock"
    assert lock_path.exists(), "lock file must exist after append_observation"
    content = obs_path.read_text(encoding="utf-8")
    assert "lock_check" in content, "observation must be written to the active file"


def test_canary_rotate_at_threshold_zero(tmp_path, monkeypatch):
    """Gate-liveness canary: with OBSERVATIONS_MAX_BYTES=0 every existing file
    satisfies the rotation condition (size >= 0). After append_observation the
    original file must be at <obs_path>.1.

    This canary must go RED if rotation is ever silently removed."""
    obs_path = tmp_path / "observations.jsonl"
    obs_path.touch()

    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 0)
    writer.append_observation(obs_path, {"event": "canary"})

    rotated = Path(str(obs_path) + ".1")
    assert rotated.exists(), (
        "rotation canary FAILED: <obs_path>.1 must exist when threshold is 0 "
        "— rotation is either absent or misconditioned"
    )
