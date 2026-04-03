"""Deduplication candidate detection and recommendation for memory entries."""

from __future__ import annotations

import re

# -- Constants ----------------------------------------------------------------

MIN_TAG_OVERLAP_FOR_CANDIDATE = 2
STRONG_TAG_OVERLAP_THRESHOLD = 3
MIN_WORD_LENGTH = 3
HIGH_VALUE_SIMILARITY_RATIO = 0.6
MIN_SIGNIFICANT_WORDS_FOR_VALUE_MATCH = 3
STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "shall",
        "can",
        "and",
        "but",
        "or",
        "not",
        "no",
        "so",
        "if",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "as",
        "into",
        "that",
        "this",
        "it",
        "its",
    }
)


# -- Helpers ------------------------------------------------------------------


def _extract_significant_words(text: str) -> set[str]:
    """Extract significant words from text, filtering stopwords and short tokens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= MIN_WORD_LENGTH and w not in STOP_WORDS}


def _tag_overlap_count(tags_a: list[str], tags_b: list[str]) -> int:
    """Count shared tags between two tag lists (case-insensitive)."""
    set_a = {t.lower() for t in tags_a}
    set_b = {t.lower() for t in tags_b}
    return len(set_a & set_b)


def _value_similarity_ratio(new_words: set[str], existing_words: set[str]) -> float:
    """Fraction of new_words that appear in existing_words. Returns 0.0 if no words."""
    if not new_words:
        return 0.0
    return len(new_words & existing_words) / len(new_words)


def _find_dedup_candidates(
    new_key: str,
    new_value: str,
    new_tags: list[str],
    entries: dict[str, dict],
    category: str,
) -> list[dict]:
    """Scan entries for overlap with the proposed new entry.

    Returns a list of candidate dicts with match_reason and overlap details.
    Skips the entry whose key matches new_key (exact key match is handled separately).
    """
    new_words = _extract_significant_words(new_value)
    candidates = []

    for existing_key, entry in entries.items():
        if existing_key == new_key:
            continue

        reasons = []
        existing_tags = entry.get("tags", [])
        tag_overlap = _tag_overlap_count(new_tags, existing_tags)
        if tag_overlap >= MIN_TAG_OVERLAP_FOR_CANDIDATE:
            reasons.append(f"tag_overlap({tag_overlap})")

        existing_words = _extract_significant_words(entry.get("value", ""))
        similarity = _value_similarity_ratio(new_words, existing_words)
        has_enough_words = len(new_words) >= MIN_SIGNIFICANT_WORDS_FOR_VALUE_MATCH
        if has_enough_words and similarity >= HIGH_VALUE_SIMILARITY_RATIO:
            reasons.append(f"value_similarity({similarity:.0%})")

        if reasons:
            candidates.append(
                {
                    "category": category,
                    "key": existing_key,
                    "value": entry.get("value", ""),
                    "tags": existing_tags,
                    "match_reason": ", ".join(reasons),
                    "tag_overlap": tag_overlap,
                    "value_similarity": round(similarity, 2),
                }
            )

    return candidates


def _recommend_action(candidates: list[dict], new_value: str) -> str:
    """Choose ADD, UPDATE, or NOOP recommendation based on candidate overlap."""
    new_words = _extract_significant_words(new_value)

    for candidate in candidates:
        existing_words = _extract_significant_words(candidate["value"])
        has_substance = len(new_words) >= MIN_SIGNIFICANT_WORDS_FOR_VALUE_MATCH
        if has_substance and new_words == existing_words:
            return "NOOP"

    for candidate in candidates:
        if candidate["tag_overlap"] >= STRONG_TAG_OVERLAP_THRESHOLD:
            return "UPDATE"
        if candidate["value_similarity"] >= HIGH_VALUE_SIMILARITY_RATIO:
            return "UPDATE"

    return "ADD"
