"""MCP server definition, tool registration, and resource endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from memory_mcp.metrics import compute_metrics
from memory_mcp.narrative import build_session_narrative, build_timeline
from memory_mcp.observations import ObservationStore
from memory_mcp.schema import (
    SCHEMA_VERSION,
    VALID_CATEGORIES,
    VALID_RELATIONS,
    VALID_STATUSES,
    VALID_TYPES,
)
from memory_mcp.store import MemoryStore

# -- Server instance ----------------------------------------------------------

mcp = FastMCP("Memory")

# -- Lazy store initialization ------------------------------------------------

DEFAULT_MEMORY_FILE = ".ai-state/memory.json"

_store: MemoryStore | None = None


def _get_store() -> MemoryStore:
    """Return the singleton MemoryStore, creating it on first call."""
    global _store  # noqa: PLW0603
    if _store is None:
        memory_file = os.environ.get("MEMORY_FILE", DEFAULT_MEMORY_FILE)
        _store = MemoryStore(Path(memory_file))
    return _store


# -- Lazy observation store initialization ------------------------------------

DEFAULT_OBSERVATIONS_FILE = ".ai-state/observations.jsonl"

_obs_store: ObservationStore | None = None


def _get_observation_store() -> ObservationStore:
    """Return the singleton ObservationStore, creating it on first call."""
    global _obs_store  # noqa: PLW0603
    if _obs_store is None:
        obs_file = os.environ.get("OBSERVATIONS_FILE", DEFAULT_OBSERVATIONS_FILE)
        _obs_store = ObservationStore(Path(obs_file))
    return _obs_store


# -- MCP Tools ----------------------------------------------------------------


@mcp.tool()
def session_start() -> dict:
    """Start or resume a memory session.

    Increments the session counter and returns a summary of all stored memories
    including category counts, total entries, and schema version.
    Call this at the beginning of each conversation.
    """
    try:
        return _get_store().session_start()
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def remember(
    category: str,
    key: str,
    value: str,
    tags: list[str] | None = None,
    importance: int = 5,
    source_type: str = "session",
    confidence: float | None = None,
    force: bool = False,
    broad: bool = False,
    summary: str | None = None,
    type: str | None = None,  # noqa: A002
    created_by: str | None = None,
) -> dict:
    """Store a new memory or update an existing one.

    Creates or updates a memory entry in the specified category.
    If the key already exists, its value is updated and tags are merged.

    For new keys, checks for similar existing entries first. If candidates
    are found, returns them with a recommendation instead of writing.
    Call again with force=True to bypass the check, or use the existing
    key to update the matched entry.

    Args:
        category: One of: user, assistant, project, relationships, tools, learnings.
        key: Unique identifier within the category (e.g., "preferred-language").
        value: The memory content to store.
        tags: Optional list of tags for categorization and search.
        importance: Priority from 1 (low) to 10 (critical). Default 5.
        source_type: Origin: "session", "user-stated", "inferred", or "codebase".
        confidence: Optional confidence score (0.0 to 1.0).
        force: If True, skip deduplication check and write immediately.
        broad: If True, check for duplicates across all categories (not just target).
        summary: Optional one-line summary (~100 chars). Auto-generated from value if omitted.
        type: Optional knowledge type (decision, gotcha, pattern, convention,
            preference, correction, insight).
        created_by: Optional identifier for the agent or user that created this entry.
    """
    try:
        return _get_store().remember(
            category,
            key,
            value,
            tags=tags,
            importance=importance,
            source_type=source_type,
            confidence=confidence,
            force=force,
            broad=broad,
            summary=summary,
            entry_type=type,
            created_by=created_by,
        )
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def forget(category: str, key: str) -> dict:
    """Soft-delete a memory entry.

    Sets invalid_at timestamp and status to 'superseded' instead of removing.
    The entry remains queryable via search(include_historical=True).
    Creates a backup before mutation.

    Args:
        category: The category containing the entry.
        key: The key of the entry to soft-delete.
    """
    try:
        return _get_store().forget(category, key)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def recall(category: str, key: str | None = None) -> dict:
    """Retrieve stored memories with access tracking.

    Returns entries from a category, optionally filtered by key.
    Each recalled entry has its access count incremented and last-accessed
    timestamp updated.

    Args:
        category: The category to recall from.
        key: Optional specific key. If omitted, returns all entries in the category.
    """
    try:
        return _get_store().recall(category, key)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def search(
    query: str,
    category: str | None = None,
    detail: str = "index",
    include_historical: bool = False,
    since: str | None = None,
    type: str | None = None,  # noqa: A002
) -> dict:
    """Search memories by text across keys, values, tags, and summaries.

    Tokenizes multi-term queries and matches individual terms. Returns
    Markdown-formatted summaries by default for token efficiency, or full
    entry data when detail="full".

    Args:
        query: Search text to match against entries.
        category: Optional category filter. If omitted, searches all categories.
        detail: Response format -- "index" (Markdown summaries) or "full" (complete entries).
        include_historical: If True, include soft-deleted entries in results.
        since: Optional ISO 8601 timestamp. Only entries created at or after
            this time are included.
        type: Optional type filter (decision, gotcha, pattern, convention,
            preference, correction, insight).
    """
    try:
        return _get_store().search(
            query,
            category,
            detail=detail,
            include_historical=include_historical,
            since=since,
            entry_type=type,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def status() -> dict:
    """Return memory store status.

    Shows category counts, total entries, schema version, session count,
    and file size. Use this for a quick health check.
    """
    try:
        return _get_store().status()
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def export_memories(output_format: str = "markdown") -> dict:
    """Export all memories as markdown or JSON.

    Args:
        output_format: Export format -- "markdown" (default) or "json".
    """
    try:
        return _get_store().export(output_format)
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def about_me() -> dict:
    """Get a profile summary of the user.

    Aggregates entries from user, relationships (user-facing tagged),
    and tools (user-preference tagged) categories into a readable profile.
    """
    try:
        return _get_store().about_me()
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def about_us() -> dict:
    """Get a summary of the user-assistant relationship.

    Aggregates relationship entries and assistant identity entries
    into a readable relationship profile.
    """
    try:
        return _get_store().about_us()
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def reflect() -> dict:
    """Analyze memory health and suggest lifecycle actions.

    Returns a structured analysis of the memory store including:
    - Stale entries (never accessed, created 7+ days ago)
    - Archival candidates (low importance, never accessed, still active)
    - Proposed confidence adjustments based on access patterns and source type

    Read-only -- does not modify any entries. Use the results to decide
    which entries to archive, update, or remove.
    """
    try:
        return _get_store().reflect()
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def connections(category: str, key: str) -> dict:
    """Show all links to and from a memory entry.

    Returns outgoing links (from this entry to others) and incoming links
    (from other entries pointing to this one). Each link includes the
    target/source reference, relation type, and a summary of the linked entry.

    Args:
        category: The category of the entry.
        key: The key of the entry.
    """
    try:
        return _get_store().connections(category, key)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def add_link(
    source_category: str,
    source_key: str,
    target_category: str,
    target_key: str,
    relation: str,
) -> dict:
    """Create a unidirectional link between two memory entries.

    Links express semantic relationships between entries. The link is stored
    on the source entry and points to the target.

    Args:
        source_category: Category of the source entry.
        source_key: Key of the source entry.
        target_category: Category of the target entry.
        target_key: Key of the target entry.
        relation: One of: supersedes, elaborates, contradicts, related-to, depends-on.
    """
    try:
        return _get_store().add_link(
            source_category, source_key, target_category, target_key, relation
        )
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def remove_link(
    source_category: str,
    source_key: str,
    target_category: str,
    target_key: str,
) -> dict:
    """Remove a link between two memory entries.

    Removes all links from the source entry that point to the target entry,
    regardless of relation type.

    Args:
        source_category: Category of the source entry.
        source_key: Key of the source entry.
        target_category: Category of the target entry.
        target_key: Key of the target entry.
    """
    try:
        return _get_store().remove_link(source_category, source_key, target_category, target_key)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def browse_index(include_historical: bool = False) -> dict:
    """Browse the full memory index as a compact Markdown summary.

    Returns all entry summaries in Markdown-KV format grouped by category.
    This is the most token-efficient way to see the entire memory store.
    Each entry is shown as: - **key**: summary [tags]

    Args:
        include_historical: If True, include soft-deleted entries with annotation.
    """
    try:
        return _get_store().browse_index(include_historical=include_historical)
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def hard_delete(category: str, key: str) -> dict:
    """Permanently remove a memory entry.

    Unlike forget() which soft-deletes, this permanently removes the entry
    and cleans up all incoming links. Use for sensitive data or errors.
    Creates a backup before removal.

    Args:
        category: The category containing the entry.
        key: The key of the entry to permanently remove.
    """
    try:
        return _get_store().hard_delete(category, key)
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def consolidate(actions: str, dry_run: bool = False) -> dict:
    """Execute structured consolidation actions on the memory store.

    Accepts a JSON string of actions to perform (merge, archive,
    adjust_confidence, update_summary). Creates a backup before any
    mutation. Use dry_run=True to preview changes without applying.

    Action types:
    - merge: {action: "merge", sources: [{category, key}], target: {category, key}, merged_value: str, merged_summary: str}
    - archive: {action: "archive", category: str, key: str}
    - adjust_confidence: {action: "adjust_confidence", category: str, key: str, confidence: float}
    - update_summary: {action: "update_summary", category: str, key: str, summary: str}

    Args:
        actions: JSON string containing a list of action objects.
        dry_run: If True, validate and preview without applying changes.
    """
    try:
        parsed_actions = json.loads(actions)
        if not isinstance(parsed_actions, list):
            return {"error": "actions must be a JSON array of action objects"}
        return _get_store().consolidate(parsed_actions, dry_run=dry_run)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON in actions: {exc}"}
    except (ValueError, KeyError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def timeline(
    since: str | None = None,
    until: str | None = None,
    session_id: str | None = None,
    tool_filter: str | None = None,
    classification: str | None = None,
    limit: int = 100,
) -> dict:
    """View chronological observation history as a compact Markdown timeline.

    Returns tool events and lifecycle events grouped by date. Each line:
    ``HH:MM [agent_type] tool_name -> outcome (files)``

    Filter by date range, session, tool name, or classification.

    Args:
        since: Optional ISO 8601 start timestamp (inclusive).
        until: Optional ISO 8601 end timestamp (inclusive).
        session_id: Optional session ID to filter by.
        tool_filter: Optional tool name to filter by.
        classification: Optional classification to filter by
            (e.g., "decision", "implementation", "test").
        limit: Maximum number of observations to return (default 100).
    """
    try:
        obs_store = _get_observation_store()
        observations = obs_store.query(
            since=since,
            until=until,
            session_id=session_id,
            tool_filter=tool_filter,
            classification=classification,
            limit=limit,
        )
        md = build_timeline(observations)
        return {"timeline": md, "count": len(observations)}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def session_narrative(session_id: str | None = None) -> dict:
    """Get a structured narrative summary of a session.

    Summarizes what was done, files touched, decisions made, and outcome.
    Uses the most recent session if session_id is not specified.

    Args:
        session_id: Optional session ID. If omitted, uses the most recent session.
    """
    try:
        obs_store = _get_observation_store()
        if session_id is None:
            recent = obs_store.query(event_type="session_start", limit=1)
            if recent:
                session_id = recent[0].get("session_id", "")
        observations = obs_store.session_observations(session_id or "")
        md = build_session_narrative(observations)
        return {
            "narrative": md,
            "observation_count": len(observations),
            "session_id": session_id or "",
        }
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


@mcp.tool()
def metrics() -> dict:
    """Compute comprehensive memory system metrics.

    Analyzes both the curated memory store (memory.json) and the observation
    layer (observations.jsonl) to produce structured statistics including:

    - Entry counts by category, status, type, importance tier
    - Access frequency distribution and never-accessed entries
    - Tag frequency, knowledge types, source provenance
    - Memory tool usage (remember/recall/search/forget counts)
    - Per-agent activity breakdown
    - Top sessions by event count with duration and memory op counts
    - Work classification breakdown

    Returns structured JSON with a pre-formatted summary_markdown field
    for direct terminal display.
    """
    try:
        store = _get_store()
        data = store._load()  # noqa: SLF001
        obs_store = _get_observation_store()
        return compute_metrics(data, obs_store)
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


# -- MCP Resources ------------------------------------------------------------


@mcp.resource("memory://schema")
def schema_resource() -> str:
    """Memory schema version and field documentation.

    Returns the current schema version, valid categories, statuses,
    and a description of each field in a memory entry.
    """
    schema_info = {
        "schema_version": SCHEMA_VERSION,
        "categories": list(VALID_CATEGORIES),
        "statuses": list(VALID_STATUSES),
        "types": list(VALID_TYPES),
        "entry_fields": {
            "value": "The memory content (string, required)",
            "summary": "One-line description (~100 chars) for index browsing",
            "created_at": "ISO 8601 UTC timestamp when the entry was created",
            "updated_at": "ISO 8601 UTC timestamp of the last modification",
            "valid_at": "ISO 8601 UTC timestamp when entry became valid (set on creation)",
            "invalid_at": "ISO 8601 UTC timestamp when entry was soft-deleted (null if active)",
            "tags": "List of string tags for categorization and search",
            "confidence": "Confidence score from 0.0 to 1.0 (null if unset)",
            "importance": "Priority from 1 (low) to 10 (critical), default 5",
            "source": ("Origin metadata: {type, detail, agent_type, agent_id, session_id}"),
            "access_count": "Number of times this entry has been recalled/searched",
            "last_accessed": "ISO 8601 UTC timestamp of last access (null if never)",
            "status": "Entry lifecycle: active, archived, or superseded",
            "links": "Array of {target, relation} linking to other entries",
            "type": (
                "Knowledge type: decision, gotcha, pattern, convention, "
                "preference, correction, insight (null if unset)"
            ),
            "created_by": "Identifier for the agent or user that created this entry (null if unset)",
        },
        "valid_relations": list(VALID_RELATIONS),
    }
    return json.dumps(schema_info, indent=2)


@mcp.resource("memory://stats")
def stats_resource() -> str:
    """Memory store statistics.

    Returns category counts, total entries, session count,
    and last modified timestamp.
    """
    try:
        store = _get_store()
        store_status = store.status()
        stats = {
            "categories": store_status["categories"],
            "total": store_status["total"],
            "session_count": store_status["session_count"],
            "schema_version": store_status["schema_version"],
            "file_size": store_status["file_size"],
        }
        return json.dumps(stats, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
