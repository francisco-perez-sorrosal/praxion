"""Consolidation engine: validate and apply structured memory actions."""

from __future__ import annotations

from datetime import UTC, datetime

# -- Action type constants ----------------------------------------------------

ACTION_MERGE = "merge"
ACTION_ARCHIVE = "archive"
ACTION_ADJUST_CONFIDENCE = "adjust_confidence"
ACTION_UPDATE_SUMMARY = "update_summary"

VALID_ACTION_TYPES = frozenset(
    {
        ACTION_MERGE,
        ACTION_ARCHIVE,
        ACTION_ADJUST_CONFIDENCE,
        ACTION_UPDATE_SUMMARY,
    }
)


# -- Helpers ------------------------------------------------------------------


def _now_utc() -> str:
    """ISO 8601 UTC timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _resolve_entry(memories: dict, category: str, key: str) -> dict | None:
    """Look up an entry in the memories dict. Returns None if not found."""
    return memories.get(category, {}).get(key)


# -- Validation ---------------------------------------------------------------


def validate_actions(actions: list[dict], memories: dict) -> dict:
    """Validate a list of consolidation actions against the current store.

    Checks that every referenced entry exists and action structure is valid.
    Returns ``{"valid": True, "errors": []}`` or ``{"valid": False, "errors": [...]}``.
    """
    errors: list[str] = []

    for i, action in enumerate(actions):
        action_type = action.get("type")
        if action_type not in VALID_ACTION_TYPES:
            errors.append(f"Action {i}: unknown type '{action_type}'")
            continue

        if action_type == ACTION_MERGE:
            _validate_merge(i, action, memories, errors)
        elif action_type == ACTION_ARCHIVE:
            _validate_single_target(i, action, memories, errors)
        elif action_type == ACTION_ADJUST_CONFIDENCE:
            _validate_adjust_confidence(i, action, memories, errors)
        elif action_type == ACTION_UPDATE_SUMMARY:
            _validate_update_summary(i, action, memories, errors)

    return {"valid": len(errors) == 0, "errors": errors}


def _validate_merge(index: int, action: dict, memories: dict, errors: list[str]) -> None:
    """Validate a merge action's sources and target."""
    target_cat = action.get("target_category")
    target_key = action.get("target_key")
    if not target_cat or not target_key:
        errors.append(f"Action {index}: merge requires target_category and target_key")
        return
    if _resolve_entry(memories, target_cat, target_key) is None:
        errors.append(f"Action {index}: target '{target_cat}.{target_key}' not found")

    sources = action.get("sources", [])
    if not sources:
        errors.append(f"Action {index}: merge requires at least one source")
    for src in sources:
        src_cat = src.get("category")
        src_key = src.get("key")
        if not src_cat or not src_key:
            errors.append(f"Action {index}: source missing category or key")
            continue
        if _resolve_entry(memories, src_cat, src_key) is None:
            errors.append(f"Action {index}: source '{src_cat}.{src_key}' not found")


def _validate_single_target(index: int, action: dict, memories: dict, errors: list[str]) -> None:
    """Validate an action that targets a single entry (archive)."""
    cat = action.get("category")
    key = action.get("key")
    if not cat or not key:
        errors.append(f"Action {index}: requires category and key")
        return
    if _resolve_entry(memories, cat, key) is None:
        errors.append(f"Action {index}: entry '{cat}.{key}' not found")


def _validate_adjust_confidence(
    index: int, action: dict, memories: dict, errors: list[str]
) -> None:
    """Validate an adjust_confidence action."""
    _validate_single_target(index, action, memories, errors)
    confidence = action.get("confidence")
    if confidence is None:
        errors.append(f"Action {index}: adjust_confidence requires 'confidence' field")


def _validate_update_summary(index: int, action: dict, memories: dict, errors: list[str]) -> None:
    """Validate an update_summary action."""
    _validate_single_target(index, action, memories, errors)
    summary = action.get("summary")
    if summary is None:
        errors.append(f"Action {index}: update_summary requires 'summary' field")


# -- Execution ----------------------------------------------------------------


def apply_actions(actions: list[dict], memories: dict) -> dict:
    """Apply validated consolidation actions to the memories dict (mutates in place).

    Returns ``{"applied": N, "skipped": N, "changelog": [...]}``.
    """
    applied = 0
    skipped = 0
    changelog: list[str] = []
    now = _now_utc()

    for action in actions:
        action_type = action["type"]

        if action_type == ACTION_MERGE:
            _apply_merge(action, memories, now, changelog)
            applied += 1
        elif action_type == ACTION_ARCHIVE:
            _apply_archive(action, memories, now, changelog)
            applied += 1
        elif action_type == ACTION_ADJUST_CONFIDENCE:
            _apply_adjust_confidence(action, memories, now, changelog)
            applied += 1
        elif action_type == ACTION_UPDATE_SUMMARY:
            _apply_update_summary(action, memories, now, changelog)
            applied += 1
        else:
            skipped += 1

    return {"applied": applied, "skipped": skipped, "changelog": changelog}


def _apply_merge(action: dict, memories: dict, now: str, changelog: list[str]) -> None:
    """Merge source entries into a target entry, then soft-delete sources."""
    target_cat = action["target_category"]
    target_key = action["target_key"]
    target = memories[target_cat][target_key]

    for src in action["sources"]:
        src_cat = src["category"]
        src_key = src["key"]
        source = memories[src_cat][src_key]

        # Concatenate values
        target["value"] = target["value"] + "\n\n" + source["value"]

        # Union tags
        merged_tags = list(set(target.get("tags", [])) | set(source.get("tags", [])))
        target["tags"] = sorted(merged_tags)

        # Take max importance
        target["importance"] = max(
            target.get("importance", 5),
            source.get("importance", 5),
        )

        # Keep latest timestamps
        if source.get("updated_at", "") > target.get("updated_at", ""):
            target["updated_at"] = source["updated_at"]

        # Soft-delete the source
        source["invalid_at"] = now
        source["status"] = "superseded"

        # Add supersedes link on target
        target_links = target.setdefault("links", [])
        supersedes_ref = f"{src_cat}.{src_key}"
        target_links.append({"target": supersedes_ref, "relation": "supersedes"})

        changelog.append(f"Merged {src_cat}.{src_key} into {target_cat}.{target_key}")

    target["updated_at"] = now


def _apply_archive(action: dict, memories: dict, now: str, changelog: list[str]) -> None:
    """Set an entry's status to archived."""
    cat = action["category"]
    key = action["key"]
    entry = memories[cat][key]
    entry["status"] = "archived"
    entry["updated_at"] = now
    changelog.append(f"Archived {cat}.{key}")


def _apply_adjust_confidence(action: dict, memories: dict, now: str, changelog: list[str]) -> None:
    """Update an entry's confidence score."""
    cat = action["category"]
    key = action["key"]
    entry = memories[cat][key]
    old_confidence = entry.get("confidence")
    entry["confidence"] = action["confidence"]
    entry["updated_at"] = now
    changelog.append(
        f"Adjusted confidence of {cat}.{key}: {old_confidence} -> {action['confidence']}"
    )


def _apply_update_summary(action: dict, memories: dict, now: str, changelog: list[str]) -> None:
    """Replace an entry's summary field."""
    cat = action["category"]
    key = action["key"]
    entry = memories[cat][key]
    old_summary = entry.get("summary", "")
    entry["summary"] = action["summary"]
    entry["updated_at"] = now
    changelog.append(f"Updated summary of {cat}.{key}: '{old_summary}' -> '{action['summary']}'")
