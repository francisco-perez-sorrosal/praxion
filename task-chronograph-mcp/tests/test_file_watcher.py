"""Tests for file_watcher: parse_progress_line, helpers, and watch_progress_file."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from task_chronograph_mcp.events import EventStore, EventType
from task_chronograph_mcp.file_watcher import (
    _parse_labels_and_summary,
    _parse_timestamp,
    parse_progress_line,
    watch_progress_file,
)

# ---------------------------------------------------------------------------
# parse_progress_line
# ---------------------------------------------------------------------------


class TestParseProgressLine:
    def test_valid_line_without_labels(self):
        line = "[2025-01-15T14:30:00] [researcher] Phase 2/5: analysis -- Analyzing auth libraries"
        event = parse_progress_line(line)
        assert event is not None
        assert event.event_type == EventType.PHASE_TRANSITION
        assert event.agent_type == "researcher"
        assert event.phase == 2
        assert event.total_phases == 5
        assert event.phase_name == "analysis"
        assert event.message == "Analyzing auth libraries"
        assert event.labels == {}

    def test_valid_line_with_labels(self):
        line = (
            "[2025-01-15T14:30:00] [researcher] Phase 2/5: analysis"
            " -- Analyzing auth #observability #feature=auth"
        )
        event = parse_progress_line(line)
        assert event is not None
        assert event.labels == {"observability": "", "feature": "auth"}
        assert event.message == "Analyzing auth"

    def test_valid_line_with_only_key_value_labels(self):
        line = (
            "[2025-01-15T14:30:00] [architect] Phase 1/7: assess"
            " -- Starting assessment #scope=narrow #priority=high"
        )
        event = parse_progress_line(line)
        assert event is not None
        assert event.labels == {"scope": "narrow", "priority": "high"}
        assert event.message == "Starting assessment"

    def test_malformed_line_returns_none(self):
        assert parse_progress_line("This is not a progress line") is None

    def test_empty_string_returns_none(self):
        assert parse_progress_line("") is None

    def test_partial_format_returns_none(self):
        assert parse_progress_line("[2025-01-15T14:30:00] [researcher]") is None

    def test_whitespace_only_returns_none(self):
        assert parse_progress_line("   ") is None

    def test_leading_whitespace_is_stripped(self):
        line = (
            "  [2025-01-15T14:30:00] [researcher] Phase 2/5: analysis -- Analyzing auth libraries"
        )
        event = parse_progress_line(line)
        assert event is not None
        assert event.agent_type == "researcher"


# ---------------------------------------------------------------------------
# _parse_labels_and_summary
# ---------------------------------------------------------------------------


class TestParseLabelsAndSummary:
    def test_mixed_text_and_labels(self):
        labels, summary = _parse_labels_and_summary("Some text here #tag1 #key=value")
        assert labels == {"tag1": "", "key": "value"}
        assert summary == "Some text here"

    def test_no_labels_returns_pure_summary(self):
        labels, summary = _parse_labels_and_summary("Just plain summary text")
        assert labels == {}
        assert summary == "Just plain summary text"

    def test_only_labels(self):
        labels, summary = _parse_labels_and_summary("#tag1 #tag2 #key=val")
        assert labels == {"tag1": "", "tag2": "", "key": "val"}
        assert summary == ""

    def test_empty_string(self):
        labels, summary = _parse_labels_and_summary("")
        assert labels == {}
        assert summary == ""

    def test_labels_interleaved_with_text(self):
        """Labels can appear anywhere in the string -- all #tokens are extracted."""
        labels, summary = _parse_labels_and_summary("Before #mid middle #end")
        assert labels == {"mid": "", "end": ""}
        assert summary == "Before middle"


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_valid_iso_timestamp(self):
        ts = _parse_timestamp("2025-01-15T14:30:00")
        assert isinstance(ts, datetime)
        assert ts.year == 2025
        assert ts.month == 1
        assert ts.hour == 14

    def test_valid_iso_with_timezone(self):
        ts = _parse_timestamp("2025-01-15T14:30:00+00:00")
        assert isinstance(ts, datetime)

    def test_invalid_timestamp_falls_back_to_now(self):
        before = datetime.now(UTC)
        ts = _parse_timestamp("not-a-timestamp")
        after = datetime.now(UTC)
        assert before <= ts <= after

    def test_empty_string_falls_back_to_now(self):
        before = datetime.now(UTC)
        ts = _parse_timestamp("")
        after = datetime.now(UTC)
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# watch_progress_file
# ---------------------------------------------------------------------------

# A filesystem event reaches the watcher after a platform-dependent delay, and a write made
# before the watcher is armed raises no event at all, so the test rewrites the same content
# until the store shows it, within a bound, instead of sleeping fixed times.
SEEN_DEADLINE_SECONDS = 15.0
REWRITE_EVERY_SECONDS = 1.0
POLL_SECONDS = 0.05


async def _write_until_seen(path, content: str, store: EventStore) -> None:
    # Yield once first: the watcher seeds its line counts from the file as it starts, and a
    # seed taken after the write would count the line as already seen.
    await asyncio.sleep(POLL_SECONDS)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SEEN_DEADLINE_SECONDS
    next_write = loop.time()
    while store.get_pipeline_summary()["event_count"] == 0 and loop.time() < deadline:
        if loop.time() >= next_write:
            path.write_text(content)
            next_write = loop.time() + REWRITE_EVERY_SECONDS
        await asyncio.sleep(POLL_SECONDS)


class TestWatchProgressFile:
    async def test_new_lines_added_to_store(self, tmp_path):
        """Writing new progress lines to PROGRESS.md adds events to the store."""
        store = EventStore()
        store.set_loop(asyncio.get_running_loop())

        progress_file = tmp_path / "PROGRESS.md"
        progress_file.write_text("")

        watcher_task = asyncio.create_task(watch_progress_file(tmp_path, store))

        await _write_until_seen(
            progress_file,
            "[2025-01-15T14:30:00] [researcher] Phase 2/5: analysis -- Analyzing auth\n",
            store,
        )

        watcher_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher_task

        summary = store.get_pipeline_summary()
        assert summary["event_count"] >= 1
        events = summary["recent_events"]
        phase_events = [e for e in events if e["event_type"] == "phase_transition"]
        assert len(phase_events) == 1
        assert phase_events[0]["agent_type"] == "researcher"
        assert phase_events[0]["phase"] == 2
