"""Tests for ObservationStore JSONL append-only store."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from memory_mcp.observations import ObservationStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def obs_file(tmp_path: Path) -> Path:
    """Return a path for a new observations JSONL file (not yet created)."""
    return tmp_path / "observations.jsonl"


@pytest.fixture
def store(obs_file: Path) -> ObservationStore:
    """Return an ObservationStore backed by a fresh path."""
    return ObservationStore(obs_file)


def _make_observation(
    *,
    timestamp: str = "2026-01-15T10:00:00Z",
    session_id: str = "session-1",
    agent_type: str = "main",
    agent_id: str = "agent-1",
    project: str = "test-project",
    event_type: str = "tool_use",
    tool_name: str | None = "Write",
    file_paths: list[str] | None = None,
    outcome: str | None = "success",
    classification: str | None = "implementation",
    metadata: dict | None = None,
) -> dict:
    """Build a minimal observation dict with sensible defaults."""
    return {
        "timestamp": timestamp,
        "session_id": session_id,
        "agent_type": agent_type,
        "agent_id": agent_id,
        "project": project,
        "event_type": event_type,
        "tool_name": tool_name,
        "file_paths": file_paths or [],
        "outcome": outcome,
        "classification": classification,
        "metadata": metadata or {},
    }


# -- Append -------------------------------------------------------------------


class TestAppend:
    def test_creates_file_on_first_append(self, obs_file: Path, store: ObservationStore):
        assert not obs_file.exists()
        store.append(_make_observation())
        assert obs_file.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        deep_path = tmp_path / "a" / "b" / "observations.jsonl"
        deep_store = ObservationStore(deep_path)
        deep_store.append(_make_observation())
        assert deep_path.exists()

    def test_single_observation_is_valid_jsonl(self, obs_file: Path, store: ObservationStore):
        obs = _make_observation(tool_name="Edit")
        store.append(obs)

        lines = obs_file.read_text().strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["tool_name"] == "Edit"
        assert parsed["session_id"] == "session-1"

    def test_multiple_appends_produce_separate_lines(self, obs_file: Path, store: ObservationStore):
        for i in range(5):
            store.append(_make_observation(timestamp=f"2026-01-15T10:0{i}:00Z"))

        lines = obs_file.read_text().strip().splitlines()
        assert len(lines) == 5

        # Each line is independently parseable
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed

    def test_append_uses_compact_json(self, obs_file: Path, store: ObservationStore):
        store.append(_make_observation())
        line = obs_file.read_text().strip()
        # Compact separators means no spaces after : or ,
        assert ": " not in line
        assert ", " not in line


# -- Query (no filters) -------------------------------------------------------


class TestQueryAll:
    def test_returns_all_observations(self, store: ObservationStore):
        for i in range(3):
            store.append(_make_observation(timestamp=f"2026-01-15T10:0{i}:00Z"))

        results = store.query(limit=100)
        assert len(results) == 3

    def test_empty_file_returns_empty_list(self, store: ObservationStore):
        results = store.query()
        assert results == []

    def test_nonexistent_file_returns_empty_list(self, tmp_path: Path):
        store = ObservationStore(tmp_path / "does-not-exist.jsonl")
        assert store.query() == []


# -- Query filters ------------------------------------------------------------


class TestQueryFilters:
    def test_since_filter(self, store: ObservationStore):
        store.append(_make_observation(timestamp="2026-01-10T00:00:00Z"))
        store.append(_make_observation(timestamp="2026-01-15T00:00:00Z"))
        store.append(_make_observation(timestamp="2026-01-20T00:00:00Z"))

        results = store.query(since="2026-01-14T00:00:00Z")
        assert len(results) == 2
        assert results[0]["timestamp"] == "2026-01-15T00:00:00Z"

    def test_until_filter(self, store: ObservationStore):
        store.append(_make_observation(timestamp="2026-01-10T00:00:00Z"))
        store.append(_make_observation(timestamp="2026-01-15T00:00:00Z"))
        store.append(_make_observation(timestamp="2026-01-20T00:00:00Z"))

        results = store.query(until="2026-01-15T00:00:00Z")
        assert len(results) == 2
        assert results[-1]["timestamp"] == "2026-01-15T00:00:00Z"

    def test_session_id_filter(self, store: ObservationStore):
        store.append(_make_observation(session_id="sess-a"))
        store.append(_make_observation(session_id="sess-b"))
        store.append(_make_observation(session_id="sess-a"))

        results = store.query(session_id="sess-a")
        assert len(results) == 2
        assert all(r["session_id"] == "sess-a" for r in results)

    def test_tool_filter(self, store: ObservationStore):
        store.append(_make_observation(tool_name="Write"))
        store.append(_make_observation(tool_name="Edit"))
        store.append(_make_observation(tool_name="Write"))

        results = store.query(tool_filter="Write")
        assert len(results) == 2
        assert all(r["tool_name"] == "Write" for r in results)

    def test_classification_filter(self, store: ObservationStore):
        store.append(_make_observation(classification="test"))
        store.append(_make_observation(classification="implementation"))
        store.append(_make_observation(classification="test"))

        results = store.query(classification="test")
        assert len(results) == 2
        assert all(r["classification"] == "test" for r in results)

    def test_event_type_filter(self, store: ObservationStore):
        store.append(_make_observation(event_type="tool_use"))
        store.append(_make_observation(event_type="session_start"))

        results = store.query(event_type="session_start")
        assert len(results) == 1
        assert results[0]["event_type"] == "session_start"

    def test_combined_filters(self, store: ObservationStore):
        store.append(
            _make_observation(
                session_id="sess-a", tool_name="Write", classification="implementation"
            )
        )
        store.append(
            _make_observation(session_id="sess-a", tool_name="Edit", classification="test")
        )
        store.append(
            _make_observation(
                session_id="sess-b", tool_name="Write", classification="implementation"
            )
        )

        results = store.query(session_id="sess-a", classification="implementation")
        assert len(results) == 1
        assert results[0]["tool_name"] == "Write"


# -- Query limit --------------------------------------------------------------


class TestQueryLimit:
    def test_limit_caps_results(self, store: ObservationStore):
        for i in range(10):
            store.append(_make_observation(timestamp=f"2026-01-15T10:{i:02d}:00Z"))

        results = store.query(limit=3)
        assert len(results) == 3

    def test_limit_returns_most_recent(self, store: ObservationStore):
        for i in range(10):
            store.append(_make_observation(timestamp=f"2026-01-15T10:{i:02d}:00Z"))

        results = store.query(limit=2)
        assert results[0]["timestamp"] == "2026-01-15T10:08:00Z"
        assert results[1]["timestamp"] == "2026-01-15T10:09:00Z"


# -- Malformed lines ----------------------------------------------------------


class TestMalformedLines:
    def test_skips_malformed_json(self, obs_file: Path, store: ObservationStore):
        # Write valid, then malformed, then valid
        store.append(_make_observation(tool_name="Write"))

        with obs_file.open("a") as f:
            f.write("this is not json\n")
            f.write("{incomplete json\n")

        store.append(_make_observation(tool_name="Edit"))

        results = store.query()
        assert len(results) == 2
        assert results[0]["tool_name"] == "Write"
        assert results[1]["tool_name"] == "Edit"

    def test_skips_empty_lines(self, obs_file: Path, store: ObservationStore):
        store.append(_make_observation())

        with obs_file.open("a") as f:
            f.write("\n\n\n")

        store.append(_make_observation())

        results = store.query()
        assert len(results) == 2


# -- Session observations -----------------------------------------------------


class TestSessionObservations:
    def test_returns_all_for_session(self, store: ObservationStore):
        for _i in range(5):
            store.append(_make_observation(session_id="target-session"))
        store.append(_make_observation(session_id="other-session"))

        results = store.session_observations("target-session")
        assert len(results) == 5
        assert all(r["session_id"] == "target-session" for r in results)


# -- Rotation -----------------------------------------------------------------


class TestRotation:
    def test_no_rotation_when_small(self, store: ObservationStore):
        store.append(_make_observation())
        result = store.rotate_if_needed(max_bytes=1024 * 1024)
        assert result is None

    def test_no_rotation_when_file_missing(self, store: ObservationStore):
        result = store.rotate_if_needed()
        assert result is None

    def test_rotates_when_exceeding_threshold(self, obs_file: Path, store: ObservationStore):
        # Write enough data to exceed a small threshold
        for i in range(100):
            store.append(_make_observation(timestamp=f"2026-01-15T{i // 60:02d}:{i % 60:02d}:00Z"))

        small_threshold = 100  # bytes — will definitely be exceeded
        rotated = store.rotate_if_needed(max_bytes=small_threshold)

        assert rotated is not None
        assert rotated.startswith("observations.")
        assert rotated.endswith(".jsonl")
        # Original file should no longer exist
        assert not obs_file.exists()

    def test_rotated_file_preserves_data(self, obs_file: Path, store: ObservationStore):
        for i in range(10):
            store.append(_make_observation(timestamp=f"2026-01-15T10:{i:02d}:00Z"))

        rotated = store.rotate_if_needed(max_bytes=100)
        assert rotated is not None

        # Read the rotated file directly
        rotated_path = obs_file.parent / rotated
        assert rotated_path.exists()

        lines = rotated_path.read_text().strip().splitlines()
        assert len(lines) == 10

    def test_avoids_overwriting_same_day_rotation(self, obs_file: Path, store: ObservationStore):
        # First rotation
        for _ in range(10):
            store.append(_make_observation())
        first_rotated = store.rotate_if_needed(max_bytes=100)

        # Second rotation (write more data)
        for _ in range(10):
            store.append(_make_observation())
        second_rotated = store.rotate_if_needed(max_bytes=100)

        assert first_rotated is not None
        assert second_rotated is not None
        assert first_rotated != second_rotated


# -- Count and file_size -------------------------------------------------------


class TestCountAndSize:
    def test_count_matches_appended(self, store: ObservationStore):
        assert store.count() == 0
        for _ in range(7):
            store.append(_make_observation())
        assert store.count() == 7

    def test_file_size_zero_when_missing(self, store: ObservationStore):
        assert store.file_size() == 0

    def test_file_size_grows_with_appends(self, store: ObservationStore):
        store.append(_make_observation())
        size_after_one = store.file_size()
        assert size_after_one > 0

        store.append(_make_observation())
        assert store.file_size() > size_after_one


# -- Concurrent appends -------------------------------------------------------


class TestConcurrentAppends:
    def test_concurrent_appends_no_corruption(self, obs_file: Path, store: ObservationStore):
        """Multiple threads appending simultaneously should not corrupt the file."""
        num_threads = 8
        appends_per_thread = 25
        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(appends_per_thread):
                    store.append(
                        _make_observation(
                            session_id=f"thread-{thread_id}",
                            timestamp=f"2026-01-15T10:{thread_id:02d}:{i:02d}Z",
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Threads raised errors: {errors}"

        # All lines should be valid JSON
        expected_total = num_threads * appends_per_thread
        results = store.query(limit=expected_total + 1)
        assert len(results) == expected_total

        # Each line should be independently parseable
        lines = obs_file.read_text().strip().splitlines()
        assert len(lines) == expected_total
        for line in lines:
            json.loads(line)  # Should not raise


# -- Count sessions -----------------------------------------------------------


class TestCountSessions:
    """Tests for ObservationStore.count_sessions() — AC 1.4.d.

    Contract (from SYSTEMS_PLAN §Interfaces / count_sessions):
      - Reads the observations.jsonl path configured on the store.
      - Returns 0 when the file is missing or empty.
      - Counts distinct session_id values across ALL records (not only
        session_start events). Every observation carries session_id via
        capture hooks.
      - Records without a session_id field are skipped.
      - Malformed JSONL lines are skipped; valid records still counted.
      - Blank / whitespace-only lines are skipped.
    """

    def test_count_sessions_missing_file(self, tmp_path: Path):
        """Returns 0 when the underlying file has never been created."""
        store = ObservationStore(tmp_path / "never-created.jsonl")
        assert store.count_sessions() == 0

    def test_count_sessions_empty_file(self, obs_file: Path, store: ObservationStore):
        """Returns 0 when the file exists but has no content."""
        obs_file.touch()
        assert obs_file.exists()
        assert obs_file.stat().st_size == 0
        assert store.count_sessions() == 0

    def test_count_sessions_three_distinct(self, store: ObservationStore):
        """Ten records across three distinct session_ids → returns 3."""
        session_ids = ["sess-a", "sess-b", "sess-c"]
        # 10 records distributed across 3 sessions (4+3+3)
        distribution = ["sess-a"] * 4 + ["sess-b"] * 3 + ["sess-c"] * 3
        for i, sid in enumerate(distribution):
            store.append(
                _make_observation(
                    session_id=sid,
                    timestamp=f"2026-01-15T10:{i:02d}:00Z",
                )
            )

        assert store.count_sessions() == len(set(session_ids))

    def test_count_sessions_duplicates_collapsed(self, store: ObservationStore):
        """Twenty records sharing 2 session_ids collapse to count of 2."""
        for i in range(20):
            store.append(
                _make_observation(
                    session_id="sess-x" if i % 2 == 0 else "sess-y",
                    timestamp=f"2026-01-15T11:{i:02d}:00Z",
                )
            )

        assert store.count_sessions() == 2

    def test_count_sessions_skips_missing_id(self, obs_file: Path, store: ObservationStore):
        """Records without a session_id field do not contribute to the count."""
        # Two valid records with session_ids
        store.append(_make_observation(session_id="sess-present"))
        store.append(_make_observation(session_id="sess-also-present"))

        # Direct writes of records missing session_id (bypassing append's schema)
        with obs_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": "2026-01-15T12:00:00Z", "event_type": "x"}) + "\n")
            f.write(json.dumps({"timestamp": "2026-01-15T12:01:00Z", "session_id": None}) + "\n")
            f.write(json.dumps({"timestamp": "2026-01-15T12:02:00Z", "session_id": ""}) + "\n")

        # Only the two valid session_ids should be counted
        assert store.count_sessions() == 2

    def test_count_sessions_skips_malformed(self, obs_file: Path, store: ObservationStore):
        """Malformed JSONL lines are skipped; valid records still counted."""
        store.append(_make_observation(session_id="sess-valid-1"))

        # Inject unparseable lines between valid records
        with obs_file.open("a", encoding="utf-8") as f:
            f.write("this is not json\n")
            f.write("{incomplete json\n")
            f.write("}not-json-either\n")

        store.append(_make_observation(session_id="sess-valid-2"))
        store.append(_make_observation(session_id="sess-valid-1"))  # duplicate

        # Two distinct valid session_ids survive despite malformed noise
        assert store.count_sessions() == 2

    def test_count_sessions_whitespace_tolerated(self, obs_file: Path, store: ObservationStore):
        """Blank lines and whitespace-only lines are skipped."""
        store.append(_make_observation(session_id="sess-alpha"))

        with obs_file.open("a", encoding="utf-8") as f:
            f.write("\n")
            f.write("   \n")
            f.write("\t\n")
            f.write("\n\n")

        store.append(_make_observation(session_id="sess-beta"))

        assert store.count_sessions() == 2
