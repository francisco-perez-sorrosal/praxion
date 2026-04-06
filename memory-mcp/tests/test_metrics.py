"""Tests for memory_mcp.metrics module."""

from __future__ import annotations

import json

import pytest

from memory_mcp.metrics import (
    _compute_observation_metrics,
    _compute_store_metrics,
    _fmt_duration,
    _stats,
    compute_metrics,
)
from memory_mcp.observations import ObservationStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def sample_memories():
    """Sample memories dict matching memory.json structure."""
    return {
        "learnings": {
            "gotcha-one": {
                "value": "Some gotcha",
                "summary": "A gotcha about X",
                "created_at": "2026-03-01T10:00:00Z",
                "updated_at": "2026-03-15T10:00:00Z",
                "valid_at": "2026-03-01T10:00:00Z",
                "invalid_at": None,
                "tags": ["gotcha", "hooks", "observability"],
                "confidence": 0.8,
                "importance": 7,
                "source": {"type": "session", "agent_type": "researcher"},
                "access_count": 5,
                "last_accessed": "2026-04-01T10:00:00Z",
                "status": "active",
                "links": [{"target": "learnings.gotcha-two", "relation": "related-to"}],
                "type": "gotcha",
                "created_by": None,
            },
            "gotcha-two": {
                "value": "Another gotcha",
                "summary": "A gotcha about Y",
                "created_at": "2026-03-10T10:00:00Z",
                "updated_at": "2026-03-10T10:00:00Z",
                "valid_at": "2026-03-10T10:00:00Z",
                "invalid_at": None,
                "tags": ["gotcha", "memory"],
                "confidence": None,
                "importance": 5,
                "source": {"type": "session", "agent_type": "sentinel"},
                "access_count": 0,
                "last_accessed": None,
                "status": "active",
                "links": [],
                "type": "gotcha",
                "created_by": None,
            },
            "old-pattern": {
                "value": "Deprecated pattern",
                "summary": "Old stuff",
                "created_at": "2026-01-01T10:00:00Z",
                "updated_at": "2026-01-01T10:00:00Z",
                "valid_at": "2026-01-01T10:00:00Z",
                "invalid_at": "2026-02-01T10:00:00Z",
                "tags": ["pattern"],
                "confidence": None,
                "importance": 3,
                "source": {"type": "session"},
                "access_count": 2,
                "last_accessed": "2026-01-15T10:00:00Z",
                "status": "superseded",
                "links": [],
                "type": "pattern",
                "created_by": None,
            },
        },
        "project": {
            "arch-decision": {
                "value": "We chose X over Y",
                "summary": "Architecture decision",
                "created_at": "2026-02-15T10:00:00Z",
                "updated_at": "2026-02-15T10:00:00Z",
                "valid_at": "2026-02-15T10:00:00Z",
                "invalid_at": None,
                "tags": ["architecture", "decision"],
                "confidence": 0.9,
                "importance": 8,
                "source": {"type": "session", "agent_type": "systems-architect"},
                "access_count": 12,
                "last_accessed": "2026-04-05T10:00:00Z",
                "status": "active",
                "links": [],
                "type": "decision",
                "created_by": None,
            },
        },
        "user": {},
        "assistant": {},
        "relationships": {},
        "tools": {},
    }


@pytest.fixture
def sample_observations(tmp_path):
    """Create a temp ObservationStore with sample observations."""
    obs_file = tmp_path / "observations.jsonl"
    observations = [
        {
            "timestamp": "2026-04-05T10:00:00Z",
            "session_id": "sess-001",
            "agent_type": "main",
            "event_type": "session_start",
            "tool_name": None,
            "classification": None,
        },
        {
            "timestamp": "2026-04-05T10:01:00Z",
            "session_id": "sess-001",
            "agent_type": "main",
            "event_type": "tool_use",
            "tool_name": "remember",
            "classification": "command",
            "outcome": "success",
        },
        {
            "timestamp": "2026-04-05T10:02:00Z",
            "session_id": "sess-001",
            "agent_type": "main",
            "event_type": "tool_use",
            "tool_name": "search",
            "classification": "command",
            "outcome": "success",
        },
        {
            "timestamp": "2026-04-05T10:03:00Z",
            "session_id": "sess-001",
            "agent_type": "sentinel",
            "event_type": "agent_start",
            "tool_name": None,
            "classification": "delegation",
        },
        {
            "timestamp": "2026-04-05T10:05:00Z",
            "session_id": "sess-001",
            "agent_type": "sentinel",
            "event_type": "tool_use",
            "tool_name": "Bash",
            "classification": "command",
            "outcome": "success",
        },
        {
            "timestamp": "2026-04-05T10:10:00Z",
            "session_id": "sess-001",
            "agent_type": "main",
            "event_type": "tool_use",
            "tool_name": "remember",
            "classification": "command",
            "outcome": "success",
        },
        {
            "timestamp": "2026-04-05T10:15:00Z",
            "session_id": "sess-001",
            "agent_type": "main",
            "event_type": "session_stop",
            "tool_name": None,
            "classification": None,
        },
        {
            "timestamp": "2026-04-05T14:00:00Z",
            "session_id": "sess-002",
            "agent_type": "main",
            "event_type": "session_start",
            "tool_name": None,
            "classification": None,
        },
        {
            "timestamp": "2026-04-05T14:05:00Z",
            "session_id": "sess-002",
            "agent_type": "researcher",
            "event_type": "tool_use",
            "tool_name": "recall",
            "classification": "command",
            "outcome": "success",
        },
        {
            "timestamp": "2026-04-05T14:10:00Z",
            "session_id": "sess-002",
            "agent_type": "main",
            "event_type": "session_stop",
            "tool_name": None,
            "classification": None,
        },
    ]
    with obs_file.open("w") as f:
        for obs in observations:
            f.write(json.dumps(obs) + "\n")

    return ObservationStore(obs_file)


# -- Store metrics tests ------------------------------------------------------


class TestStoreMetrics:
    def test_counts_active_entries(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["total_active"] == 3
        assert result["total_superseded"] == 1
        assert result["total_archived"] == 0

    def test_category_breakdown(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["by_category"]["learnings"]["active"] == 2
        assert result["by_category"]["learnings"]["superseded"] == 1
        assert result["by_category"]["project"]["active"] == 1

    def test_never_accessed(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["never_accessed"] == 1  # gotcha-two has access_count=0

    def test_importance_tiers(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        tiers = result["importance_tiers"]
        assert tiers["tier1_always (7-10)"] == 2  # importance 7 and 8
        assert tiers["tier2_budget (4-6)"] == 1  # importance 5

    def test_tag_frequency(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["tag_frequency"]["gotcha"] == 2

    def test_type_distribution(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["type_distribution"]["gotcha"] == 2
        assert result["type_distribution"]["decision"] == 1

    def test_access_buckets(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        buckets = result["access_buckets"]
        assert buckets["0"] == 1
        assert buckets["1-5"] == 1
        assert buckets["6-20"] == 1

    def test_source_types(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["source_types"]["session"] == 3

    def test_link_count(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["total_links"] == 1

    def test_confidence_tracking(self, sample_memories):
        result = _compute_store_metrics(sample_memories, "2026-04-06T00:00:00Z")
        assert result["has_confidence"] == 2  # gotcha-one and arch-decision

    def test_empty_store(self):
        result = _compute_store_metrics({}, "2026-04-06T00:00:00Z")
        assert result["total_active"] == 0
        assert result["never_accessed"] == 0


# -- Observation metrics tests ------------------------------------------------


class TestObservationMetrics:
    def test_total_count(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        assert result["total"] == 10

    def test_session_count(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        assert result["sessions"] == 2

    def test_event_types(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        assert result["event_types"]["tool_use"] == 5
        assert result["event_types"]["session_start"] == 2

    def test_agent_activity(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        assert result["agent_activity"]["main"] == 7
        assert result["agent_activity"]["sentinel"] == 2

    def test_memory_operations(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        assert result["memory_operations"]["remember"] == 2
        assert result["memory_operations"]["search"] == 1
        assert result["memory_operations"]["recall"] == 1

    def test_session_summary(self, sample_observations):
        result = _compute_observation_metrics(sample_observations)
        summaries = result["session_summary"]
        assert len(summaries) == 2
        # First session has more events
        sess1 = next(s for s in summaries if s["session_id"] == "sess-001")
        assert sess1["events"] == 7
        assert sess1["remembers"] == 2
        assert sess1["duration_s"] == 900  # 15 minutes

    def test_empty_observations(self, tmp_path):
        obs_file = tmp_path / "empty.jsonl"
        obs_file.touch()
        store = ObservationStore(obs_file)
        result = _compute_observation_metrics(store)
        assert result["total"] == 0


# -- Integration test ---------------------------------------------------------


class TestComputeMetrics:
    def test_full_metrics(self, sample_memories, sample_observations):
        data = {
            "schema_version": "2.0",
            "session_count": 5,
            "memories": sample_memories,
        }
        result = compute_metrics(data, sample_observations)

        assert "store" in result
        assert "observations" in result
        assert "summary_markdown" in result
        assert result["store"]["total_active"] == 3
        assert result["observations"]["total"] == 10

    def test_markdown_contains_sections(self, sample_memories, sample_observations):
        data = {
            "schema_version": "2.0",
            "session_count": 5,
            "memories": sample_memories,
        }
        result = compute_metrics(data, sample_observations)
        md = result["summary_markdown"]

        assert "# Memory Metrics" in md
        assert "## Store Overview" in md
        assert "## Entries by Category" in md
        assert "## Importance Tiers" in md
        assert "## Access Distribution" in md
        assert "## Memory Tool Usage" in md
        assert "## Agent Activity" in md

    def test_without_observations(self, sample_memories):
        data = {
            "schema_version": "2.0",
            "session_count": 5,
            "memories": sample_memories,
        }
        result = compute_metrics(data, obs_store=None)
        assert result["observations"] == {}
        assert "## Observations" not in result["summary_markdown"]


# -- Utility tests ------------------------------------------------------------


class TestStats:
    def test_basic_stats(self):
        result = _stats([1.0, 2.0, 3.0, 4.0, 5.0], "days")
        assert result["min"] == 1.0
        assert result["max"] == 5.0
        assert result["median"] == 3.0
        assert result["mean"] == 3.0
        assert result["count"] == 5

    def test_empty_returns_none(self):
        assert _stats([], "days") is None

    def test_single_value(self):
        result = _stats([42.0], "seconds")
        assert result["min"] == 42.0
        assert result["median"] == 42.0


class TestFmtDuration:
    def test_seconds(self):
        assert _fmt_duration(45) == "45s"

    def test_minutes(self):
        assert _fmt_duration(125) == "2m 5s"

    def test_hours(self):
        assert _fmt_duration(3725) == "1h 2m"

    def test_none(self):
        assert _fmt_duration(None) == "?"
