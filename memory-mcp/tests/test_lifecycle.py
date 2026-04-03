"""Tests for lifecycle analysis engine."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

from memory_mcp.lifecycle import (
    HIGH_ACCESS_THRESHOLD,
    HIGH_CONFIDENCE_FLOOR,
    LOW_CONFIDENCE_CEILING,
    LOW_IMPORTANCE_CEILING,
    STALENESS_DAYS_THRESHOLD,
    USER_STATED_MINIMUM_CONFIDENCE,
    analyze,
)

# -- Helpers ------------------------------------------------------------------


def _ts(days_ago: int = 0) -> str:
    """Return an ISO 8601 UTC timestamp from `days_ago` days before now."""
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat().replace("+00:00", "Z")


def _make_entry(
    *,
    value: str = "test value",
    days_ago: int = 0,
    access_count: int = 0,
    importance: int = 5,
    confidence: float | None = None,
    source_type: str = "session",
    status: str = "active",
    last_accessed: str | None = None,
) -> dict:
    """Build a memory entry dict with reasonable defaults."""
    created = _ts(days_ago)
    return {
        "value": value,
        "created_at": created,
        "updated_at": created,
        "tags": [],
        "confidence": confidence,
        "importance": importance,
        "source": {"type": source_type, "detail": None},
        "access_count": access_count,
        "last_accessed": last_accessed,
        "status": status,
    }


def _wrap_data(entries_by_category: dict[str, dict[str, dict]]) -> dict:
    """Wrap category entries into a full memory document."""
    memories = {
        "user": {},
        "assistant": {},
        "project": {},
        "relationships": {},
        "tools": {},
        "learnings": {},
    }
    for cat, entries in entries_by_category.items():
        memories[cat] = entries
    return {
        "schema_version": "1.1",
        "session_count": 10,
        "memories": memories,
    }


# -- Staleness detection ------------------------------------------------------


class TestStalenessDetection:
    def test_old_unaccessed_entry_is_stale(self):
        data = _wrap_data(
            {
                "user": {"old_entry": _make_entry(days_ago=10, access_count=0)},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["stale_entries"]) == 1
        stale = result["stale_entries"][0]
        assert stale["category"] == "user"
        assert stale["key"] == "old_entry"
        assert stale["days_old"] >= 10.0

    def test_recently_created_entry_not_stale(self):
        data = _wrap_data(
            {
                "user": {"new_entry": _make_entry(days_ago=2, access_count=0)},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["stale_entries"]) == 0

    def test_accessed_entry_not_stale(self):
        data = _wrap_data(
            {
                "user": {"accessed": _make_entry(days_ago=30, access_count=3)},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["stale_entries"]) == 0

    def test_entry_at_exact_threshold_is_stale(self):
        data = _wrap_data(
            {
                "user": {
                    "boundary": _make_entry(days_ago=STALENESS_DAYS_THRESHOLD, access_count=0)
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["stale_entries"]) == 1

    def test_entry_just_below_threshold_not_stale(self):
        data = _wrap_data(
            {
                "user": {
                    "recent": _make_entry(days_ago=STALENESS_DAYS_THRESHOLD - 1, access_count=0)
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["stale_entries"]) == 0


# -- Archival candidates ------------------------------------------------------


class TestArchivalCandidates:
    def test_low_importance_unaccessed_active_flagged(self):
        data = _wrap_data(
            {
                "learnings": {
                    "trivial": _make_entry(importance=2, access_count=0, status="active")
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 1
        candidate = result["archival_candidates"][0]
        assert candidate["category"] == "learnings"
        assert candidate["key"] == "trivial"
        assert "Low importance" in candidate["reason"]

    def test_high_importance_entry_not_flagged(self):
        data = _wrap_data(
            {
                "user": {"important": _make_entry(importance=8, access_count=0, status="active")},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 0

    def test_accessed_low_importance_not_flagged(self):
        data = _wrap_data(
            {
                "tools": {"used": _make_entry(importance=2, access_count=1, status="active")},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 0

    def test_archived_entry_not_flagged(self):
        data = _wrap_data(
            {
                "learnings": {"old": _make_entry(importance=1, access_count=0, status="archived")},
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 0

    def test_importance_at_ceiling_included(self):
        data = _wrap_data(
            {
                "project": {
                    "borderline": _make_entry(
                        importance=LOW_IMPORTANCE_CEILING, access_count=0, status="active"
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 1

    def test_importance_above_ceiling_excluded(self):
        data = _wrap_data(
            {
                "project": {
                    "above": _make_entry(
                        importance=LOW_IMPORTANCE_CEILING + 1, access_count=0, status="active"
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["archival_candidates"]) == 0


# -- Confidence adjustments ---------------------------------------------------


class TestConfidenceBump:
    def test_high_access_low_confidence_proposes_bump(self):
        data = _wrap_data(
            {
                "user": {
                    "popular": _make_entry(access_count=HIGH_ACCESS_THRESHOLD, confidence=0.5)
                },
            }
        )
        result = analyze(data, session_count=10)
        updates = result["confidence_updates"]
        bump = [u for u in updates if u["reason"] == "frequently accessed"]
        assert len(bump) == 1
        assert bump[0]["proposed_confidence"] == HIGH_CONFIDENCE_FLOOR
        assert bump[0]["current_confidence"] == 0.5

    def test_high_access_high_confidence_no_bump(self):
        data = _wrap_data(
            {
                "user": {"solid": _make_entry(access_count=10, confidence=0.9)},
            }
        )
        result = analyze(data, session_count=10)
        bump = [u for u in result["confidence_updates"] if u["reason"] == "frequently accessed"]
        assert len(bump) == 0

    def test_low_access_no_bump(self):
        data = _wrap_data(
            {
                "user": {
                    "rarely_used": _make_entry(
                        access_count=HIGH_ACCESS_THRESHOLD - 1, confidence=0.3
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        bump = [u for u in result["confidence_updates"] if u["reason"] == "frequently accessed"]
        assert len(bump) == 0


class TestConfidenceReduction:
    def test_zero_access_old_entry_proposes_reduction(self):
        data = _wrap_data(
            {
                "tools": {"unused": _make_entry(days_ago=14, access_count=0, confidence=0.7)},
            }
        )
        result = analyze(data, session_count=10)
        reductions = [u for u in result["confidence_updates"] if u["reason"] == "never accessed"]
        assert len(reductions) == 1
        assert reductions[0]["proposed_confidence"] == 0.55

    def test_zero_access_recent_entry_no_reduction(self):
        data = _wrap_data(
            {
                "tools": {"new_tool": _make_entry(days_ago=2, access_count=0, confidence=0.7)},
            }
        )
        result = analyze(data, session_count=10)
        reductions = [u for u in result["confidence_updates"] if u["reason"] == "never accessed"]
        assert len(reductions) == 0

    def test_low_confidence_no_reduction(self):
        data = _wrap_data(
            {
                "tools": {
                    "low_conf": _make_entry(
                        days_ago=30, access_count=0, confidence=LOW_CONFIDENCE_CEILING
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        reductions = [u for u in result["confidence_updates"] if u["reason"] == "never accessed"]
        assert len(reductions) == 0

    def test_reduction_does_not_go_below_zero(self):
        data = _wrap_data(
            {
                "tools": {"almost_zero": _make_entry(days_ago=30, access_count=0, confidence=0.05)},
            }
        )
        result = analyze(data, session_count=10)
        # confidence 0.05 is below LOW_CONFIDENCE_CEILING (0.3), so no reduction
        reductions = [u for u in result["confidence_updates"] if u["reason"] == "never accessed"]
        assert len(reductions) == 0


class TestUserStatedConfidence:
    def test_user_stated_low_confidence_proposes_minimum(self):
        data = _wrap_data(
            {
                "user": {"stated": _make_entry(source_type="user-stated", confidence=0.6)},
            }
        )
        result = analyze(data, session_count=10)
        user_stated = [u for u in result["confidence_updates"] if u["reason"] == "user-stated fact"]
        assert len(user_stated) == 1
        assert user_stated[0]["proposed_confidence"] == USER_STATED_MINIMUM_CONFIDENCE

    def test_user_stated_high_confidence_no_change(self):
        data = _wrap_data(
            {
                "user": {"confident": _make_entry(source_type="user-stated", confidence=0.95)},
            }
        )
        result = analyze(data, session_count=10)
        user_stated = [u for u in result["confidence_updates"] if u["reason"] == "user-stated fact"]
        assert len(user_stated) == 0

    def test_non_user_stated_no_minimum(self):
        data = _wrap_data(
            {
                "user": {"inferred": _make_entry(source_type="inferred", confidence=0.5)},
            }
        )
        result = analyze(data, session_count=10)
        user_stated = [u for u in result["confidence_updates"] if u["reason"] == "user-stated fact"]
        assert len(user_stated) == 0


# -- Multiple proposals for same entry ----------------------------------------


class TestMultipleProposals:
    def test_entry_can_have_multiple_confidence_proposals(self):
        """A user-stated entry with high access and low confidence gets two proposals."""
        data = _wrap_data(
            {
                "user": {
                    "multi": _make_entry(
                        source_type="user-stated",
                        access_count=HIGH_ACCESS_THRESHOLD,
                        confidence=0.5,
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        updates = [u for u in result["confidence_updates"] if u["key"] == "multi"]
        reasons = {u["reason"] for u in updates}
        assert "frequently accessed" in reasons
        assert "user-stated fact" in reasons


# -- No mutation guarantee ----------------------------------------------------


class TestNoMutation:
    def test_analyze_does_not_mutate_input(self):
        data = _wrap_data(
            {
                "user": {
                    "stale": _make_entry(days_ago=30, access_count=0, confidence=0.7),
                    "low": _make_entry(importance=1, access_count=0),
                },
            }
        )
        original = copy.deepcopy(data)
        analyze(data, session_count=10)
        assert data == original


# -- Empty store ---------------------------------------------------------------


class TestEmptyStore:
    def test_empty_memories(self):
        data = _wrap_data({})
        result = analyze(data, session_count=0)
        assert result["stale_entries"] == []
        assert result["archival_candidates"] == []
        assert result["confidence_updates"] == []
        assert result["summary"]["total_entries"] == 0
        assert result["summary"]["active"] == 0
        assert result["summary"]["archived"] == 0

    def test_empty_categories(self):
        data = {
            "schema_version": "1.1",
            "session_count": 5,
            "memories": {},
        }
        result = analyze(data, session_count=5)
        assert result["summary"]["total_entries"] == 0


# -- Summary correctness -------------------------------------------------------


class TestSummary:
    def test_summary_counts_match(self):
        data = _wrap_data(
            {
                "user": {
                    "stale1": _make_entry(days_ago=30, access_count=0),
                    "active1": _make_entry(days_ago=1, access_count=5),
                },
                "tools": {
                    "archived1": _make_entry(status="archived"),
                },
                "learnings": {
                    "archival_target": _make_entry(importance=1, access_count=0, status="active"),
                },
            }
        )
        result = analyze(data, session_count=10)
        summary = result["summary"]
        assert summary["total_entries"] == 4
        assert summary["active"] == 3
        assert summary["archived"] == 1
        assert summary["stale_count"] == len(result["stale_entries"])
        assert summary["archival_candidate_count"] == len(result["archival_candidates"])
        assert summary["confidence_update_count"] == len(result["confidence_updates"])


# -- Null confidence entries ---------------------------------------------------


class TestNullConfidence:
    def test_entry_with_null_confidence_skips_adjustments(self):
        data = _wrap_data(
            {
                "user": {
                    "no_conf": _make_entry(
                        days_ago=30,
                        access_count=0,
                        confidence=None,
                        source_type="user-stated",
                    )
                },
            }
        )
        result = analyze(data, session_count=10)
        assert len(result["confidence_updates"]) == 0
