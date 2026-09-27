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
import subprocess
import sys
from pathlib import Path

from hooks._observation_log import registry, writer
from hooks._observation_log.modes import Mode

REPO_ROOT = Path(__file__).resolve().parent.parent


def _marker_tmp(tmp_path: Path) -> Path:
    """A per-test temp dir for first-call markers -- never the real host
    ``/tmp``, which the writer falls back to only when ``env`` carries no
    ``TMPDIR``/``TEMP``/``TMP`` key at all.
    """
    marker_dir = tmp_path / "marker-tmp"
    marker_dir.mkdir(exist_ok=True)
    return marker_dir


def _write_and_read(
    tmp_path: Path, mode: Mode, row: dict, *, is_subagent: bool = False
) -> list[dict]:
    ai_state_dir = tmp_path / mode.value / ".ai-state"
    ai_state_dir.mkdir(parents=True, exist_ok=True)
    writer.record_tool_call(
        ai_state_dir,
        row,
        is_subagent=is_subagent,
        env={"PRAXION_OBSERVATION_LOG": mode.value, "TMPDIR": str(_marker_tmp(tmp_path))},
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
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(_marker_tmp(tmp_path))}

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
    env = {"PRAXION_OBSERVATION_LOG": Mode.FULL.value, "TMPDIR": str(_marker_tmp(tmp_path))}

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


def test_unwritable_marker_directory_still_writes_the_first_call_row(tmp_path: Path) -> None:
    """Append-then-mark ordering means any OSError on the
    marker path must still leave the row written -- at-least-once, never
    absent, even when the marker cannot be created at all.
    """
    ai_state_dir = tmp_path / "unwritable-marker" / ".ai-state"
    ai_state_dir.mkdir(parents=True)
    unwritable_tmp = tmp_path / "no-write-tmp"
    unwritable_tmp.mkdir()
    unwritable_tmp.chmod(0o500)  # read+execute only: marker creation must fail with OSError

    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "agent-race"},
        is_subagent=True,
        env={"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(unwritable_tmp)},
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]

    assert len(rows) == 1, "an unwritable marker directory must never cost the row itself"


def test_a_pre_existing_marker_for_a_different_log_does_not_suppress_this_logs_first_call(
    tmp_path: Path,
) -> None:
    """The marker key includes the log directory's identity (device+inode),
    not just the agent_id -- a marker already created for one project's log
    must never suppress a same-named agent's first-call row in a different
    project's log.
    """
    marker_tmp = _marker_tmp(tmp_path)
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(marker_tmp)}

    other_ai_state_dir = tmp_path / "other-project" / ".ai-state"
    other_ai_state_dir.mkdir(parents=True)
    writer.record_tool_call(
        other_ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "shared-agent-id"},
        is_subagent=True,
        env=env,
    )
    assert len(list(marker_tmp.iterdir())) == 1, (
        "fixture assumption: the first call left exactly one marker behind"
    )

    this_ai_state_dir = tmp_path / "this-project" / ".ai-state"
    this_ai_state_dir.mkdir(parents=True)
    writer.record_tool_call(
        this_ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "shared-agent-id"},
        is_subagent=True,
        env=env,
    )

    obs_path = this_ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1, (
        "a marker created for a different log's identity must not suppress "
        "this log's own first-call row"
    )


def test_a_losing_first_call_marker_race_does_not_raise_or_lose_the_row(
    tmp_path: Path, monkeypatch
) -> None:
    """Two of a subagent's "first" calls racing to create the marker: the
    loser's O_CREAT|O_EXCL raises FileExistsError, which must be swallowed
    -- the row it guards was already appended before the marker create was
    even attempted.
    """
    ai_state_dir = tmp_path / "race" / ".ai-state"
    ai_state_dir.mkdir(parents=True)
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(_marker_tmp(tmp_path))}

    real_open = os.open

    def _racing_open(path, flags, *args, **kwargs):
        if flags & os.O_EXCL:
            raise FileExistsError("simulated concurrent winner")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", _racing_open)

    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "racer"},
        is_subagent=True,
        env=env,
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1, "a losing marker-create race must never cost the row itself"


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


# -- log_mode / log_mode_source stamping ----------------------------------------


def test_every_recorded_row_carries_the_resolved_log_mode(tmp_path: Path) -> None:
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()

    written = writer.record(
        ai_state_dir,
        registry.EventClass.AGENT_START,
        {"event_type": "agent_start", "agent_id": "a1"},
        env={"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value},
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]
    assert written is True
    assert rows[0]["log_mode"] == "standard"


def test_only_session_start_carries_log_mode_source(tmp_path: Path) -> None:
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value}

    writer.record(
        ai_state_dir, registry.EventClass.SESSION_START, {"event_type": "session_start"}, env=env
    )
    writer.record(
        ai_state_dir, registry.EventClass.AGENT_START, {"event_type": "agent_start"}, env=env
    )

    obs_path = ai_state_dir / "observations.jsonl"
    rows = [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]
    session_start, agent_start = rows
    assert session_start["log_mode_source"] == "setting"
    assert "log_mode_source" not in agent_start


def test_record_never_mutates_the_callers_row(tmp_path: Path) -> None:
    """`record` must stamp a copy -- the caller's own dict is untouched, so a
    caller that reuses or logs the row afterward never sees a value it never
    put there."""
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    row = {"event_type": "agent_start"}

    writer.record(
        ai_state_dir,
        registry.EventClass.AGENT_START,
        row,
        env={"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value},
    )

    assert row == {"event_type": "agent_start"}, "the caller's row dict must not be mutated"


# -- hot-path import constraint --------------------------------------------------

_BANNED_HOT_PATH_MODULES = ("dataclasses", "typing", "inspect", "tempfile", "subprocess", "urllib")


def test_the_tool_call_writer_path_never_imports_the_banned_hot_path_modules(
    tmp_path: Path,
) -> None:
    """`capture_observations.py`'s per-tool-call path -- import through a
    full `record_tool_call` drive, including the marker-classification
    branch -- must never pull in any of these modules into a fresh
    interpreter's `sys.modules`. The log directory exists, so the drive
    reaches the marker digest and the append rather than failing at the
    directory stat.
    """
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from hooks._observation_log import writer\n"
        "writer.record_tool_call(\n"
        "    Path(sys.argv[1]),\n"
        "    {'tool_name': 'Read', 'file_paths': [], 'agent_id': 'x'},\n"
        "    is_subagent=True,\n"
        "    env={'PRAXION_OBSERVATION_LOG': 'standard', 'TMPDIR': sys.argv[2]},\n"
        ")\n"
        f"banned = {_BANNED_HOT_PATH_MODULES!r}\n"
        "hit = sorted(m for m in sys.modules if m.split('.')[0] in banned)\n"
        "print(','.join(hit))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(ai_state_dir), str(_marker_tmp(tmp_path))],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"tool-call writer path imported banned hot-path modules: {result.stdout.strip()}"
    )
    assert (ai_state_dir / "observations.jsonl").exists(), (
        "the drive must reach the append, or the import check covered nothing"
    )


# -- first-call marker: which rows consume it, and when --------------------------


def test_a_subagent_whose_first_call_is_a_skill_still_gets_a_tool_use_row(
    tmp_path: Path,
) -> None:
    """A Skill row is not `tool_use`, so it must not consume the first-call
    marker: the subagent's next non-file call is still its first tool call,
    and the lifecycle check needs that row to tell a running agent from one
    that died on arrival."""
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(_marker_tmp(tmp_path))}
    skill = {"tool_name": "Skill", "file_paths": [], "agent_id": "sub-s"}
    read = {"tool_name": "Read", "file_paths": ["a.py"], "agent_id": "sub-s"}

    writer.record_tool_call(ai_state_dir, skill, is_subagent=True, env=env)
    writer.record_tool_call(ai_state_dir, read, is_subagent=True, env=env)

    rows = _read_rows(ai_state_dir)
    assert [r["tool_name"] for r in rows] == ["Skill", "Read"]


def test_the_marker_is_never_set_when_the_row_it_marks_was_not_written(
    tmp_path: Path, monkeypatch
) -> None:
    """Append-then-mark: a failed append must leave no marker behind, or the
    subagent's next call would be dropped as a later call with no first-call
    row ever written."""
    ai_state_dir = tmp_path / ".ai-state"
    ai_state_dir.mkdir()
    marker_tmp = _marker_tmp(tmp_path)
    env = {"PRAXION_OBSERVATION_LOG": Mode.STANDARD.value, "TMPDIR": str(marker_tmp)}

    def _failing_append(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(writer, "append_observation", _failing_append)
    writer.record_tool_call(
        ai_state_dir,
        {"tool_name": "Read", "file_paths": [], "agent_id": "sub-a"},
        is_subagent=True,
        env=env,
    )

    assert list(marker_tmp.iterdir()) == [], "a marker was set for a row that was never written"


def _read_rows(ai_state_dir: Path) -> list[dict]:
    obs_path = ai_state_dir / "observations.jsonl"
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]
