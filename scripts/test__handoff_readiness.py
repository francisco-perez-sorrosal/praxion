"""Tests for `_handoff_readiness.py`'s WAL reader -- characterization baseline.

`session_wal_rows(repo_root)` is the one reader in this module that touches
the observations WAL (the pure `readiness()` decision function and the git
adapters `dirty_paths`/`parse_porcelain_z` are already exercised through
`scripts/test_compose_handoff.py`'s re-export of `_handoff_readiness`). No
test file existed for this module before this one -- `session_wal_rows` pins
the current read surface (malformed lines skipped, only the active segment
read, a missing WAL degrades to no rows) before it migrates onto
`reader.read_rows(archives=False)` in a later step.

Run: ``pytest scripts/test__handoff_readiness.py``
"""

from __future__ import annotations

import json
from pathlib import Path

import _handoff_readiness as readiness_mod

OBS_REL = Path(".ai-state") / "observations.jsonl"


def _write_wal(repo_root: Path, text: str) -> Path:
    obs_path = repo_root / OBS_REL
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    obs_path.write_text(text, encoding="utf-8")
    return obs_path


def test_returns_rows_for_the_newest_session_bearing_row(tmp_path: Path) -> None:
    _write_wal(
        tmp_path,
        json.dumps({"session_id": "s1", "event_type": "agent_start", "agent_id": "a1"})
        + "\n"
        + json.dumps({"session_id": "s2", "event_type": "agent_start", "agent_id": "a2"})
        + "\n",
    )

    rows = readiness_mod.session_wal_rows(tmp_path)

    assert [r["session_id"] for r in rows] == ["s2"]


def test_malformed_and_non_object_lines_are_skipped_not_raised(tmp_path: Path) -> None:
    well_formed = {"session_id": "s1", "event_type": "agent_start", "agent_id": "a1"}
    _write_wal(
        tmp_path,
        "not-json{{{\n"
        + json.dumps(["not", "an", "object"])
        + "\n"
        + json.dumps(well_formed)
        + "\n"
        + '{"session_id": "s1", "event_type": "agent_st',  # torn tail line
    )

    rows = readiness_mod.session_wal_rows(tmp_path)

    assert rows == [well_formed]


def test_reads_only_the_active_segment_not_the_rotation_archive(tmp_path: Path) -> None:
    archive_path = tmp_path / ".ai-state" / "observations.jsonl.1"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(
        json.dumps({"session_id": "archived", "event_type": "agent_start", "agent_id": "a0"})
        + "\n",
        encoding="utf-8",
    )
    _write_wal(
        tmp_path,
        json.dumps({"session_id": "active", "event_type": "agent_start", "agent_id": "a1"}) + "\n",
    )

    rows = readiness_mod.session_wal_rows(tmp_path)

    assert [r["session_id"] for r in rows] == ["active"]


def test_missing_wal_returns_no_rows(tmp_path: Path) -> None:
    assert readiness_mod.session_wal_rows(tmp_path) == []


def test_rows_with_no_session_id_at_all_return_no_rows(tmp_path: Path) -> None:
    """No row identifies a session -- `readiness()` reads this as
    `wal-unreadable`, so the reader must not fabricate a session from rows
    that carry none."""
    _write_wal(
        tmp_path,
        json.dumps({"event_type": "agent_start", "agent_id": "a1"}) + "\n",
    )

    assert readiness_mod.session_wal_rows(tmp_path) == []
