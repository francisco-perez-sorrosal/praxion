"""Tests for query_memory_write_evidence.py -- characterization baseline.

No test file existed for this reader before this one (flagged in
LEARNINGS.md: an orphan for the test-topology's coverage invariant -- neither
a registered group nor a prior test exists). `iter_rows` pins the current
JSONL-parsing surface (malformed lines skipped, no rotation-archive handling
at all -- the script reads exactly the path it is given) before it migrates
onto `reader.read_segment(path)` in a later step. `query()` pins the
spawn/write tally and keep/drop decision over a small fixture WAL.

Run: ``pytest scripts/test_query_memory_write_evidence.py``
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

qmwe = importlib.import_module("query_memory_write_evidence")


def _write_wal(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# iter_rows -- the JSONL reader
# --------------------------------------------------------------------------- #


def test_iter_rows_skips_malformed_lines_not_raised(tmp_path: Path) -> None:
    wal_path = tmp_path / "observations.jsonl"
    well_formed = {"agent_type": "praxion:implementer", "event_type": "agent_start"}
    wal_path.write_text(
        "not-json{{{\n\n" + json.dumps(well_formed) + "\n" + '{"agent_type": "praxion:i',
        encoding="utf-8",
    )

    rows = list(qmwe.iter_rows(wal_path))

    assert rows == [well_formed]


def test_iter_rows_reads_exactly_the_given_path_no_rotation_archive(tmp_path: Path) -> None:
    """Characterization: this reader has no notion of a `.1` rotation
    archive at all -- it streams the one path it is handed, verbatim."""
    archive_path = tmp_path / "observations.jsonl.1"
    active_path = tmp_path / "observations.jsonl"
    archive_row = {"agent_type": "praxion:researcher", "event_type": "agent_start"}
    active_row = {"agent_type": "praxion:implementer", "event_type": "agent_start"}
    _write_wal(archive_path, [archive_row])
    _write_wal(active_path, [active_row])

    rows = list(qmwe.iter_rows(active_path))

    assert rows == [active_row]


# --------------------------------------------------------------------------- #
# query -- spawn/write tally and keep/drop decision
# --------------------------------------------------------------------------- #


def test_query_counts_spawns_and_marker_writes_per_agent_type(tmp_path: Path) -> None:
    wal_path = _write_wal(
        tmp_path / "observations.jsonl",
        [
            {"agent_type": "praxion:implementer", "event_type": "agent_start"},
            {
                "agent_type": "praxion:implementer",
                "event_type": "tool_use",
                "tool_name": "Write",
                "file_paths": ["/home/x/.claude/agent-memory/notes.md"],
            },
            {
                "agent_type": "praxion:implementer",
                "event_type": "tool_use",
                "tool_name": "Edit",
                "file_paths": ["/home/x/.claude/projects/p/memory/MEMORY.md"],
            },
            # A non-praxion agent_type must never contribute to the result.
            {"agent_type": "other:agent", "event_type": "agent_start"},
        ],
    )

    result = qmwe.query(wal_path)

    assert result == {
        "praxion:implementer": {
            "spawns": 1,
            "writes_agent_memory": 1,
            "writes_slash_memory": 1,
            "decision": "keep",
        }
    }


def test_query_drops_only_when_spawns_meet_the_floor_with_zero_writes(tmp_path: Path) -> None:
    rows = [
        {"agent_type": "praxion:sentinel", "event_type": "agent_start"}
        for _ in range(qmwe.KEEP_MIN_SPAWNS)
    ]
    wal_path = _write_wal(tmp_path / "observations.jsonl", rows)

    result = qmwe.query(wal_path)

    assert result["praxion:sentinel"]["decision"] == "drop"


def test_query_keeps_when_spawn_count_is_below_the_floor_even_with_no_writes(
    tmp_path: Path,
) -> None:
    rows = [
        {"agent_type": "praxion:sentinel", "event_type": "agent_start"}
        for _ in range(qmwe.KEEP_MIN_SPAWNS - 1)
    ]
    wal_path = _write_wal(tmp_path / "observations.jsonl", rows)

    result = qmwe.query(wal_path)

    assert result["praxion:sentinel"]["decision"] == "keep"


def test_query_over_an_empty_wal_returns_no_agents(tmp_path: Path) -> None:
    wal_path = _write_wal(tmp_path / "observations.jsonl", [])

    assert qmwe.query(wal_path) == {}


# --------------------------------------------------------------------------- #
# An unreadable log is a named failure, never an empty tally (td-276)
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod-000 file")
def test_main_exits_1_naming_an_unreadable_wal(tmp_path: Path, monkeypatch, capsys) -> None:
    wal_path = _write_wal(
        tmp_path / "observations.jsonl",
        [{"agent_type": "praxion:implementer", "event_type": "agent_start"}],
    )
    wal_path.chmod(0o000)
    monkeypatch.setattr(sys, "argv", ["query_memory_write_evidence", "--wal", str(wal_path)])
    try:
        code = qmwe.main()
    finally:
        wal_path.chmod(0o644)

    assert code == 1
    assert "unreadable" in capsys.readouterr().out
