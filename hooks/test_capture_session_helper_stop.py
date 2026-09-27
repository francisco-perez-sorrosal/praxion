"""Harness helper stops become slim `helper_stop` rows.

Four quadrants over (prior WAL row for the agent Y/N) x (agent's own
transcript exists Y/N): only "no prior row AND no own transcript" writes the
slim `helper_stop` row with its exact five-key shape; every other quadrant
writes the full `agent_stop` row unchanged -- the conservative fallback, so a
real agent is never mistaken for a helper.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from hooks._observation_log.registry import EventClass

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "capture_session.py"


def _load_module():
    if str(HOOKS_DIR) not in sys.path:
        sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location("capture_session", HOOK_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".ai-state").mkdir()
    return tmp_path


def _stop_payload(project: Path, agent_id: str, session_id: str) -> dict:
    transcript = project / "transcript.jsonl"
    transcript.write_text("", encoding="utf-8")
    return {
        "hook_event_name": "SubagentStop",
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": "",
        "transcript_path": str(transcript),
        "cwd": str(project),
    }


def _own_transcript_path(project: Path, session_id: str, agent_id: str) -> Path:
    """Mirrors capture_session.py's `_subagent_own_transcript_path`: a
    sibling of the parent transcript, under `<session_id>/subagents/`."""
    path = project / session_id / "subagents" / f"agent-{agent_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_prior_start_row(project: Path, session_id: str, agent_id: str) -> None:
    obs_path = project / ".ai-state" / "observations.jsonl"
    row = {
        "timestamp": "2026-09-01T00:00:00+00:00",
        "session_id": session_id,
        "agent_type": "praxion:implementer",
        "agent_id": agent_id,
        "project": "repo",
        "event_type": "agent_start",
    }
    obs_path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _run_stop(module, payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRAXION_DISABLE_OBSERVABILITY", raising=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    module.main()


def _read_wal(project: Path) -> list[dict]:
    obs_path = project / ".ai-state" / "observations.jsonl"
    if not obs_path.exists():
        return []
    return [json.loads(line) for line in obs_path.read_text(encoding="utf-8").splitlines() if line]


def test_no_prior_row_and_no_own_transcript_writes_a_slim_helper_stop_row(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    session_id, agent_id = "sess-1", "agent-orphan"
    payload = _stop_payload(project, agent_id, session_id)
    # Deliberately: no prior WAL row, no own-transcript file created.

    _run_stop(module, payload, monkeypatch)

    rows = _read_wal(project)
    assert len(rows) == 1
    assert rows[0]["event_type"] == EventClass.HELPER_STOP.value
    assert set(rows[0]) == {
        "timestamp",
        "session_id",
        "agent_id",
        "project",
        "event_type",
        "log_mode",
    }


def test_no_prior_row_but_own_transcript_exists_writes_agent_stop_unchanged(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    session_id, agent_id = "sess-2", "agent-real"
    payload = _stop_payload(project, agent_id, session_id)
    _own_transcript_path(project, session_id, agent_id).write_text("", encoding="utf-8")
    # Deliberately: no prior WAL row, but the agent's own transcript exists.

    _run_stop(module, payload, monkeypatch)

    rows = _read_wal(project)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "agent_stop"


def test_prior_row_exists_and_no_own_transcript_writes_agent_stop_unchanged(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    session_id, agent_id = "sess-3", "agent-known"
    _write_prior_start_row(project, session_id, agent_id)
    payload = _stop_payload(project, agent_id, session_id)
    # Deliberately: a prior agent_start row exists, no own-transcript file.

    _run_stop(module, payload, monkeypatch)

    rows = _read_wal(project)
    assert rows[-1]["event_type"] == "agent_stop"


def test_prior_row_and_own_transcript_both_exist_writes_agent_stop_unchanged(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_module()
    session_id, agent_id = "sess-4", "agent-both"
    _write_prior_start_row(project, session_id, agent_id)
    _own_transcript_path(project, session_id, agent_id).write_text("", encoding="utf-8")
    payload = _stop_payload(project, agent_id, session_id)

    _run_stop(module, payload, monkeypatch)

    rows = _read_wal(project)
    assert rows[-1]["event_type"] == "agent_stop"
