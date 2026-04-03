"""Search scoring, ranking, text matching, and Markdown formatting for memory entries."""

from __future__ import annotations

import math
from datetime import datetime

from memory_mcp.schema import DEFAULT_IMPORTANCE, MAX_IMPORTANCE

EMPTY_INDEX_MESSAGE = "No memory entries found."

# BM25 pre-filter threshold: below this entry count, return all matches
# without BM25 scoring. BM25 adds value only with many entries.
BM25_ENTRY_THRESHOLD = 200

# -- Constants ----------------------------------------------------------------

# Search ranking weights (each signal normalized to 0.0-1.0)
SEARCH_WEIGHTS = {
    "text_match": 0.4,
    "tag_match": 0.2,
    "importance": 0.25,
    "recency": 0.15,
}

# Recency exponential decay: half-life ~21 days (score ~0.37 at 30 days)
RECENCY_DECAY_DAYS = 30


# -- Scoring functions --------------------------------------------------------


def _compute_text_match_score(
    key: str,
    entry: dict,
    query_lower: str,
) -> float:
    """Score text match: 1.0 for exact key, 0.7 for key substring, 0.5 for value/tag match."""
    if key.lower() == query_lower:
        return 1.0
    if query_lower in key.lower():
        return 0.7
    if query_lower in entry.get("value", "").lower():
        return 0.5
    tags = entry.get("tags", [])
    if any(query_lower in tag.lower() for tag in tags):
        return 0.5
    return 0.0


def _compute_tag_match_score(entry: dict, query_terms: list[str]) -> float:
    """Fraction of entry tags that match any query term."""
    if not query_terms:
        return 0.0
    tags_lower = {t.lower() for t in entry.get("tags", [])}
    if not tags_lower:
        return 0.0
    matching = sum(1 for term in query_terms if any(term in tag for tag in tags_lower))
    return min(matching / max(len(query_terms), 1), 1.0)


def _compute_importance_score(entry: dict) -> float:
    """Normalize importance from 1-10 scale to 0.0-1.0."""
    importance = entry.get("importance", DEFAULT_IMPORTANCE)
    return importance / MAX_IMPORTANCE


def _compute_recency_score(entry: dict, now: datetime) -> float:
    """Exponential decay based on last_accessed. 0.0 if never accessed."""
    last_accessed = entry.get("last_accessed")
    if not last_accessed:
        return 0.0
    accessed_str = last_accessed.replace("Z", "+00:00")
    accessed_dt = datetime.fromisoformat(accessed_str)
    days_since = (now - accessed_dt).total_seconds() / 86400
    return math.exp(-days_since / RECENCY_DECAY_DAYS)


def _compute_search_score(signals: dict[str, float]) -> float:
    """Weighted combination of individual signal scores."""
    return sum(SEARCH_WEIGHTS[signal] * score for signal, score in signals.items())


# -- Match reasons ------------------------------------------------------------


def _find_match_reasons(key: str, entry: dict, query_lower: str) -> list[str]:
    """Return list of match reasons for a search query against an entry."""
    reasons = []
    if query_lower in key.lower():
        reasons.append("key")
    if query_lower in entry.get("value", "").lower():
        reasons.append("value")
    tags = entry.get("tags", [])
    if any(query_lower in tag.lower() for tag in tags):
        reasons.append("tag")
    return reasons


def _find_match_reasons_multi(
    key: str,
    entry: dict,
    query_lower: str,
    query_terms: list[str],
) -> list[str]:
    """Return match reasons using multi-term matching.

    An entry matches if ANY individual term matches ANY searchable field
    (key, value, tags, summary). Falls back to the original whole-query
    matching when query_terms is empty or has a single term.
    """
    reasons: list[str] = []
    key_lower = key.lower()
    value_lower = entry.get("value", "").lower()
    summary_lower = entry.get("summary", "").lower()
    tags_lower = [t.lower() for t in entry.get("tags", [])]

    # Check whole query first (preserves backward-compatible ordering)
    if query_lower in key_lower:
        reasons.append("key")
    if query_lower in value_lower:
        reasons.append("value")
    if any(query_lower in tag for tag in tags_lower):
        reasons.append("tag")
    if query_lower in summary_lower:
        if "value" not in reasons:
            reasons.append("summary")

    if reasons:
        return reasons

    # Multi-term matching: any term in any field
    for term in query_terms:
        if term in key_lower and "key" not in reasons:
            reasons.append("key")
        if term in value_lower and "value" not in reasons:
            reasons.append("value")
        if any(term in tag for tag in tags_lower) and "tag" not in reasons:
            reasons.append("tag")
        if term in summary_lower and "summary" not in reasons:
            reasons.append("summary")

    return reasons


def _format_as_markdown(data: dict) -> str:
    """Format full memory data as markdown (used by export)."""
    lines = [f"# Memory Export (schema {data.get('schema_version', '?')})"]
    lines.append(f"Session count: {data.get('session_count', 0)}")
    lines.append("")

    memories = data.get("memories", {})
    for cat_name, entries in memories.items():
        if not entries:
            continue
        lines.append(f"## {cat_name}")
        for key, entry in entries.items():
            tags_str = ", ".join(entry.get("tags", []))
            tag_suffix = f" [{tags_str}]" if tags_str else ""
            lines.append(f"- **{key}**: {entry.get('value', '')}{tag_suffix}")
        lines.append("")

    return "\n".join(lines)


# -- Markdown formatters ------------------------------------------------------

SOFT_DELETED_ANNOTATION = " ~~superseded~~"


def format_markdown_kv_index(
    memories: dict,
    include_historical: bool = False,
) -> str:
    """Format all memory entries as a Markdown-KV index grouped by category.

    Each category becomes a ``## category (N entries)`` heading.
    Each entry is ``- **key**: summary [tag1, tag2]``.
    Soft-deleted entries are excluded unless *include_historical* is True,
    in which case they are annotated.
    """
    lines: list[str] = []

    for cat_name in sorted(memories.keys()):
        entries = memories.get(cat_name, {})
        if not entries:
            continue

        visible: list[tuple[str, dict]] = []
        for key in sorted(entries.keys()):
            entry = entries[key]
            is_active = entry.get("invalid_at") is None
            if is_active or include_historical:
                visible.append((key, entry))

        if not visible:
            continue

        lines.append(f"## {cat_name} ({len(visible)} entries)")
        for key, entry in visible:
            summary = entry.get("summary") or entry.get("value", "")[:100]
            tags = entry.get("tags", [])
            tag_suffix = f" [{', '.join(tags)}]" if tags else ""
            annotation = "" if entry.get("invalid_at") is None else SOFT_DELETED_ANNOTATION
            lines.append(f"- **{key}**: {summary}{tag_suffix}{annotation}")
        lines.append("")

    if not lines:
        return EMPTY_INDEX_MESSAGE
    return "\n".join(lines)


def format_search_results_markdown(results: list[dict], query: str) -> str:
    """Format search results as a numbered Markdown list with scores.

    Each result: ``N. **key** (category) -- summary [score: X.XX]``
    """
    if not results:
        return f"No results for '{query}'."

    lines: list[str] = []
    for i, result in enumerate(results, 1):
        key = result["key"]
        category = result["category"]
        entry = result.get("entry", {})
        summary = entry.get("summary") or entry.get("value", "")[:100]
        score = result.get("score", 0.0)
        lines.append(f"{i}. **{key}** ({category}) -- {summary} [score: {score:.2f}]")

    return "\n".join(lines)
