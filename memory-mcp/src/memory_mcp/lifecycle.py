"""Lifecycle analysis engine for memory entries.

Pure analysis module -- reads data, returns findings, never mutates.
"""

from __future__ import annotations

from datetime import UTC, datetime

from memory_mcp.schema import VALID_CATEGORIES

# -- Constants ----------------------------------------------------------------

STALENESS_DAYS_THRESHOLD = 7
LOW_IMPORTANCE_CEILING = 3
HIGH_ACCESS_THRESHOLD = 5
HIGH_CONFIDENCE_FLOOR = 0.8
LOW_CONFIDENCE_CEILING = 0.3
CONFIDENCE_REDUCTION_STEP = 0.15
USER_STATED_MINIMUM_CONFIDENCE = 0.9


# -- Public API ---------------------------------------------------------------


def analyze(data: dict, session_count: int) -> dict:
    """Analyze memory data and return lifecycle findings.

    Returns structured analysis with stale entries, archival candidates,
    and proposed confidence adjustments. Never mutates the input data.
    """
    now = datetime.now(UTC)
    memories = data.get("memories", {})

    stale_entries: list[dict] = []
    archival_candidates: list[dict] = []
    confidence_updates: list[dict] = []
    total = 0
    active_count = 0
    archived_count = 0

    for cat_name in VALID_CATEGORIES:
        entries = memories.get(cat_name, {})
        for key, entry in entries.items():
            total += 1
            entry_status = entry.get("status", "active")
            if entry_status == "active":
                active_count += 1
            elif entry_status == "archived":
                archived_count += 1

            stale = _check_staleness(cat_name, key, entry, now)
            if stale is not None:
                stale_entries.append(stale)

            archival = _check_archival_candidate(cat_name, key, entry)
            if archival is not None:
                archival_candidates.append(archival)

            adjustments = _check_confidence_adjustments(cat_name, key, entry, now)
            confidence_updates.extend(adjustments)

    return {
        "stale_entries": stale_entries,
        "archival_candidates": archival_candidates,
        "confidence_updates": confidence_updates,
        "summary": {
            "total_entries": total,
            "active": active_count,
            "archived": archived_count,
            "stale_count": len(stale_entries),
            "archival_candidate_count": len(archival_candidates),
            "confidence_update_count": len(confidence_updates),
        },
    }


# -- Internal checks ----------------------------------------------------------


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to a datetime object."""
    if ts is None:
        return None
    try:
        cleaned = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except (ValueError, TypeError):
        return None


def _days_since(dt: datetime, now: datetime) -> float:
    """Return the number of days between dt and now."""
    delta = now - dt
    return delta.total_seconds() / 86400


def _check_staleness(category: str, key: str, entry: dict, now: datetime) -> dict | None:
    """Flag entries with access_count == 0 that were created over 7 days ago."""
    access_count = entry.get("access_count", 0)
    if access_count > 0:
        return None

    created_at = _parse_timestamp(entry.get("created_at"))
    if created_at is None:
        return None

    days_old = _days_since(created_at, now)
    if days_old < STALENESS_DAYS_THRESHOLD:
        return None

    return {
        "category": category,
        "key": key,
        "created_at": entry.get("created_at"),
        "days_old": round(days_old, 1),
        "reason": f"Never accessed, created {round(days_old, 1)} days ago",
    }


def _check_archival_candidate(category: str, key: str, entry: dict) -> dict | None:
    """Flag low-importance, never-accessed, active entries for archival."""
    importance = entry.get("importance", 5)
    access_count = entry.get("access_count", 0)
    status = entry.get("status", "active")

    if status != "active":
        return None
    if importance > LOW_IMPORTANCE_CEILING:
        return None
    if access_count > 0:
        return None

    return {
        "category": category,
        "key": key,
        "importance": importance,
        "reason": f"Low importance ({importance}) and never accessed",
    }


def _check_confidence_adjustments(
    category: str, key: str, entry: dict, now: datetime
) -> list[dict]:
    """Propose confidence adjustments based on access patterns and source type."""
    confidence = entry.get("confidence")
    if confidence is None:
        return []

    proposals: list[dict] = []
    access_count = entry.get("access_count", 0)
    source = entry.get("source", {})
    source_type = source.get("type", "session") if isinstance(source, dict) else "session"

    # Frequently accessed entries deserve higher confidence
    if access_count >= HIGH_ACCESS_THRESHOLD and confidence < HIGH_CONFIDENCE_FLOOR:
        proposals.append(
            {
                "category": category,
                "key": key,
                "current_confidence": confidence,
                "proposed_confidence": HIGH_CONFIDENCE_FLOOR,
                "reason": "frequently accessed",
            }
        )

    # Never-accessed old entries should lose confidence
    if access_count == 0 and confidence > LOW_CONFIDENCE_CEILING:
        created_at = _parse_timestamp(entry.get("created_at"))
        if created_at is not None:
            days_old = _days_since(created_at, now)
            if days_old >= STALENESS_DAYS_THRESHOLD:
                reduced = round(confidence - CONFIDENCE_REDUCTION_STEP, 2)
                proposals.append(
                    {
                        "category": category,
                        "key": key,
                        "current_confidence": confidence,
                        "proposed_confidence": max(reduced, 0.0),
                        "reason": "never accessed",
                    }
                )

    # User-stated facts should have high confidence
    if source_type == "user-stated" and confidence < USER_STATED_MINIMUM_CONFIDENCE:
        proposals.append(
            {
                "category": category,
                "key": key,
                "current_confidence": confidence,
                "proposed_confidence": USER_STATED_MINIMUM_CONFIDENCE,
                "reason": "user-stated fact",
            }
        )

    return proposals
