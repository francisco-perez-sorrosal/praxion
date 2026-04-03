"""Tests for multi-signal ranked search."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from memory_mcp.schema import MAX_IMPORTANCE, SCHEMA_VERSION
from memory_mcp.search import RECENCY_DECAY_DAYS, SEARCH_WEIGHTS
from memory_mcp.store import MemoryStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    return tmp_path / "memory.json"


@pytest.fixture
def store(memory_file: Path) -> MemoryStore:
    return MemoryStore(memory_file)


def _make_entry(
    value: str,
    *,
    tags: list[str] | None = None,
    importance: int = 5,
    access_count: int = 0,
    last_accessed: str | None = None,
) -> dict:
    """Build a raw v1.3 entry dict for direct file injection."""
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "value": value,
        "created_at": now,
        "updated_at": now,
        "tags": tags or [],
        "confidence": None,
        "importance": importance,
        "source": {"type": "session", "detail": None},
        "access_count": access_count,
        "last_accessed": last_accessed,
        "status": "active",
        "links": [],
        "summary": value[:100],
        "valid_at": now,
        "invalid_at": None,
    }


def _write_store(memory_file: Path, entries_by_category: dict) -> None:
    """Write a pre-built memory store to the file for direct manipulation."""
    memories = {
        cat: {} for cat in ("user", "assistant", "project", "relationships", "tools", "learnings")
    }
    for cat, entries in entries_by_category.items():
        memories[cat] = entries
    doc = {
        "schema_version": SCHEMA_VERSION,
        "session_count": 5,
        "memories": memories,
    }
    memory_file.write_text(json.dumps(doc, indent=2) + "\n")


# -- Result structure ---------------------------------------------------------


class TestResultStructure:
    """Verify the ranked search result format."""

    def test_results_contain_score(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.search("alice")
        assert len(result["results"]) == 1
        item = result["results"][0]
        assert "score" in item
        assert isinstance(item["score"], float)

    def test_results_contain_signals(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.search("alice")
        item = result["results"][0]
        assert "signals" in item
        signals = item["signals"]
        for signal_name in SEARCH_WEIGHTS:
            assert signal_name in signals
            assert isinstance(signals[signal_name], float)

    def test_results_contain_match_reason(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("alice")
        assert "match_reason" in result["results"][0]

    def test_results_contain_category_and_key(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("alice")
        item = result["results"][0]
        assert item["category"] == "user"
        assert item["key"] == "name"
        assert "entry" in item


# -- Ranking by importance ----------------------------------------------------


class TestImportanceRanking:
    """More important entries rank higher among equal text matches."""

    def test_higher_importance_ranks_first(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "low_prio": _make_entry("python developer", importance=2),
                    "high_prio": _make_entry("python expert", importance=9),
                    "mid_prio": _make_entry("python user", importance=5),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        keys = [r["key"] for r in result["results"]]
        assert keys[0] == "high_prio"
        assert keys[-1] == "low_prio"

    def test_importance_signal_value(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev", importance=8)
        result = store.search("python")
        signals = result["results"][0]["signals"]
        expected = 8 / MAX_IMPORTANCE
        assert signals["importance"] == pytest.approx(expected, abs=0.01)


# -- Ranking by recency ------------------------------------------------------


class TestRecencyRanking:
    """Recently accessed entries rank higher."""

    def test_recently_accessed_ranks_higher(self, memory_file: Path):
        now = datetime.now(UTC)
        recent = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        old = (now - timedelta(days=60)).isoformat().replace("+00:00", "Z")

        _write_store(
            memory_file,
            {
                "learnings": {
                    "old_item": _make_entry(
                        "python pattern old",
                        importance=5,
                        access_count=1,
                        last_accessed=old,
                    ),
                    "recent_item": _make_entry(
                        "python pattern new",
                        importance=5,
                        access_count=1,
                        last_accessed=recent,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        keys = [r["key"] for r in result["results"]]
        assert keys[0] == "recent_item"

    def test_never_accessed_has_zero_recency(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev")
        result = store.search("python")
        # Signals are computed BEFORE access tracking updates, so a
        # never-accessed entry gets recency 0.0 (last_accessed was None).
        signals = result["results"][0]["signals"]
        assert signals["recency"] == 0.0

    def test_recency_exponential_decay(self, memory_file: Path):
        now = datetime.now(UTC)
        thirty_days_ago = (
            (now - timedelta(days=RECENCY_DECAY_DAYS)).isoformat().replace("+00:00", "Z")
        )

        _write_store(
            memory_file,
            {
                "user": {
                    "old_entry": _make_entry(
                        "python topic",
                        importance=5,
                        access_count=1,
                        last_accessed=thirty_days_ago,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        # Signals computed before access tracking update, so recency
        # reflects the 30-day-old last_accessed. exp(-1) ~ 0.368
        signals = result["results"][0]["signals"]
        expected = math.exp(-1)  # days/RECENCY_DECAY_DAYS = 30/30 = 1
        assert signals["recency"] == pytest.approx(expected, abs=0.05)


class TestRecencyScoreFunction:
    """Test recency scoring with controlled timestamps via direct file injection."""

    def test_recent_entry_has_higher_recency_signal(self, memory_file: Path):
        """Entries with recent last_accessed get higher recency signal than old ones."""
        now = datetime.now(UTC)
        one_day_ago = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        sixty_days_ago = (now - timedelta(days=60)).isoformat().replace("+00:00", "Z")

        _write_store(
            memory_file,
            {
                "user": {
                    "recent": _make_entry(
                        "python topic A",
                        importance=5,
                        access_count=3,
                        last_accessed=one_day_ago,
                    ),
                    "old": _make_entry(
                        "python topic B",
                        importance=5,
                        access_count=3,
                        last_accessed=sixty_days_ago,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        signals_by_key = {r["key"]: r["signals"]["recency"] for r in result["results"]}
        assert signals_by_key["recent"] > signals_by_key["old"]


# -- Ranking by tag match -----------------------------------------------------


class TestTagMatchRanking:
    """Tag overlap with query terms boosts score."""

    def test_tag_match_boosts_score(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "learnings": {
                    "no_tags": _make_entry("python basics", importance=5),
                    "tagged": _make_entry(
                        "python basics",
                        tags=["python", "basics"],
                        importance=5,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python basics")
        scores = {r["key"]: r["score"] for r in result["results"]}
        assert scores["tagged"] > scores["no_tags"]

    def test_more_tag_matches_score_higher(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "learnings": {
                    "one_tag": _make_entry(
                        "python web framework",
                        tags=["python"],
                        importance=5,
                    ),
                    "two_tags": _make_entry(
                        "python web framework",
                        tags=["python", "web"],
                        importance=5,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python web")
        scores = {r["key"]: r["signals"]["tag_match"] for r in result["results"]}
        assert scores["two_tags"] >= scores["one_tag"]


# -- Text match scoring -------------------------------------------------------


class TestTextMatchScoring:
    """Exact key match scores higher than substring match."""

    def test_exact_key_match_scores_highest(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "python": _make_entry("A programming language", importance=5),
                    "python_version": _make_entry(
                        "Currently using python 3.13",
                        importance=5,
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        signals = {r["key"]: r["signals"]["text_match"] for r in result["results"]}
        assert signals["python"] > signals["python_version"]

    def test_key_substring_scores_above_value_match(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "python_tools": _make_entry("IDE and linter setup", importance=5),
                    "editor": _make_entry("Uses python for scripting", importance=5),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        signals = {r["key"]: r["signals"]["text_match"] for r in result["results"]}
        assert signals["python_tools"] > signals["editor"]


# -- Non-matching entries NOT returned ----------------------------------------


class TestNonMatchingExcluded:
    """Entries that don't match the text query are excluded regardless of importance."""

    def test_non_matching_excluded_despite_high_importance(self, store: MemoryStore):
        store.remember("user", "name", "Alice", importance=10)
        store.remember("user", "email", "alice@example.com", importance=1)
        result = store.search("email")
        keys = {r["key"] for r in result["results"]}
        assert "name" not in keys
        assert "email" in keys

    def test_empty_results_when_no_match(self, store: MemoryStore):
        store.remember("user", "name", "Alice", importance=10)
        result = store.search("nonexistent_query_xyz")
        assert len(result["results"]) == 0


# -- Access tracking still works ----------------------------------------------


class TestAccessTrackingWithRankedSearch:
    """Search still updates access_count and last_accessed on returned entries."""

    def test_search_increments_access_count(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.search("alice")
        result = store.recall("user", "name")
        # recall adds +1, search already added +1 = 2
        assert result["entries"]["name"]["access_count"] == 2

    def test_search_sets_last_accessed(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        assert store.recall("user", "name")["entries"]["name"]["last_accessed"] is not None
        # recall sets it, but let's check search independently
        store2 = MemoryStore(store._path)
        # Hard-delete and recreate to reset
        store2.hard_delete("user", "name")
        store2.remember("user", "name", "Bob")
        # Now search and check
        store2.search("bob")
        data = json.loads(store._path.read_text())
        assert data["memories"]["user"]["name"]["last_accessed"] is not None

    def test_non_matching_entries_not_tracked(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "bob@example.com")
        store.search("alice")
        # Only "name" should have been accessed (matches "alice")
        data = json.loads(store._path.read_text())
        assert data["memories"]["user"]["name"]["access_count"] == 1
        assert data["memories"]["user"]["email"]["access_count"] == 0


# -- Combined signal ranking --------------------------------------------------


class TestCombinedRanking:
    """Verify that the weighted combination produces expected ordering."""

    def test_high_importance_beats_low_with_same_text_match(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "learnings": {
                    "trivial": _make_entry("python tip: use print", importance=1),
                    "critical": _make_entry("python tip: always test", importance=10),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python tip")
        assert result["results"][0]["key"] == "critical"
        assert result["results"][1]["key"] == "trivial"

    def test_score_is_weighted_sum_of_signals(self, store: MemoryStore):
        store.remember("user", "test_key", "unique_query_term", importance=7)
        result = store.search("unique_query_term")
        item = result["results"][0]
        signals = item["signals"]
        expected_score = sum(SEARCH_WEIGHTS[k] * v for k, v in signals.items())
        assert item["score"] == pytest.approx(expected_score, abs=0.001)

    def test_category_filter_still_works(self, store: MemoryStore):
        store.remember("user", "name", "python dev")
        store.remember("tools", "lang", "python")
        result = store.search("python", category="user")
        assert len(result["results"]) == 1
        assert result["results"][0]["category"] == "user"

    def test_results_sorted_descending_by_score(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    f"entry_{i}": _make_entry(f"python topic {i}", importance=i)
                    for i in range(1, 6)
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("python")
        scores = [r["score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)


# -- Scoring function unit tests (via store integration) ----------------------


class TestScoringEdgeCases:
    """Edge cases for individual scoring signals."""

    def test_entry_with_no_tags_has_zero_tag_score(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev")
        result = store.search("python")
        assert result["results"][0]["signals"]["tag_match"] == 0.0

    def test_importance_1_gives_minimum_score(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev", importance=1)
        result = store.search("python")
        expected = 1 / MAX_IMPORTANCE
        assert result["results"][0]["signals"]["importance"] == pytest.approx(expected, abs=0.01)

    def test_importance_10_gives_maximum_score(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev", importance=10)
        result = store.search("python")
        assert result["results"][0]["signals"]["importance"] == pytest.approx(1.0, abs=0.01)

    def test_score_between_zero_and_one(self, store: MemoryStore):
        store.remember("user", "test_key", "python dev", importance=5)
        result = store.search("python")
        score = result["results"][0]["score"]
        assert 0.0 <= score <= 1.0
