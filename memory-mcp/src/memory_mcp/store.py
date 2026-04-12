"""MemoryStore: CRUD operations and file I/O for persistent memory."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from memory_mcp.consolidation import apply_actions, validate_actions
from memory_mcp.dedup import (
    _find_dedup_candidates,
    _recommend_action,
)
from memory_mcp.lifecycle import analyze as lifecycle_analyze
from memory_mcp.schema import (
    MAX_IMPORTANCE,
    MIN_IMPORTANCE,
    SCHEMA_VERSION,
    VALID_CATEGORIES,
    VALID_RELATIONS,
    MemoryEntry,
    Source,
    generate_summary,
)
from memory_mcp.search import (
    _compute_importance_score,
    _compute_recency_score,
    _compute_search_score,
    _compute_tag_match_score,
    _compute_text_match_score,
    _find_match_reasons_multi,
    _format_as_markdown,
    format_markdown_kv_index,
    format_search_results_markdown,
)

# -- Constants ----------------------------------------------------------------

JSON_INDENT = 2
BACKUP_SUFFIX = ".backup.json"
PRE_FORGET_BACKUP_SUFFIX = ".pre-forget.json"

# Auto-link constants
AUTO_LINK_TAG_OVERLAP_THRESHOLD = 2
MAX_AUTO_LINKS_PER_REMEMBER = 3
AUTO_LINK_RELATION = "related-to"


# -- Helpers ------------------------------------------------------------------


def _now_utc() -> str:
    """ISO 8601 UTC timestamp with Z suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clamp_importance(value: int) -> int:
    return max(MIN_IMPORTANCE, min(MAX_IMPORTANCE, value))


def _is_active(entry: dict) -> bool:
    """Check whether a memory entry is currently active (not soft-deleted)."""
    return entry.get("invalid_at") is None


def _human_file_size(byte_count: int) -> str:
    """Format byte count as human-readable string."""
    if byte_count < 1024:
        return f"{byte_count} B"
    kib = byte_count / 1024
    if kib < 1024:
        return f"{kib:.1f} KB"
    mib = kib / 1024
    return f"{mib:.1f} MB"


# -- MemoryStore --------------------------------------------------------------


class MemoryStore:
    """Persistent memory store backed by a single JSON file.

    Provides CRUD operations, access tracking, atomic writes, and link management.
    Requires schema v2.0 -- migration from v1.x schemas runs automatically on load
    (see ``_auto_migrate_if_needed``).
    """

    def __init__(self, file_path: Path) -> None:
        self._path = Path(file_path)
        self._ensure_file_exists()
        self._auto_migrate_if_needed()

    # -- File I/O (private) ---------------------------------------------------

    def _ensure_file_exists(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            empty_doc = {
                "schema_version": SCHEMA_VERSION,
                "session_count": 0,
                "memories": {cat: {} for cat in VALID_CATEGORIES},
            }
            self._save(empty_doc)

    def _load(self) -> dict:
        """Read and validate the JSON memory file."""
        text = self._path.read_text(encoding="utf-8")
        data = json.loads(text)
        if "schema_version" not in data:
            msg = f"Missing 'schema_version' in {self._path}"
            raise ValueError(msg)
        if "memories" not in data:
            msg = f"Missing 'memories' in {self._path}"
            raise ValueError(msg)
        return data

    def _save(self, data: dict) -> None:
        """Atomic write: temp file in same directory, then os.replace()."""
        content = json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n"
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=".memory_tmp_",
            suffix=".json",
        )
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            os.replace(tmp_path, self._path)
        except BaseException:
            os.close(fd) if not _is_fd_closed(fd) else None
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    @contextlib.contextmanager
    def _lock(self):
        """Exclusive file lock for read-modify-write safety."""
        lock_path = self._path.with_suffix(".lock")
        lock_path.touch(exist_ok=True)
        lock_fd = lock_path.open("w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def _auto_migrate_if_needed(self) -> None:
        """Migrate older schema versions to 2.0, or raise on unknown versions."""
        data = self._load()
        version = data.get("schema_version")

        if version == SCHEMA_VERSION:
            return

        if version and version.startswith("1."):
            self._migrate_v1_to_v2(data)
            return

        msg = (
            f"Unsupported schema version '{version}' in {self._path}. Expected '{SCHEMA_VERSION}'."
        )
        raise ValueError(msg)

    def _migrate_v1_to_v2(self, data: dict) -> None:
        """Migrate v1.x memory.json to v2.0 schema in-place.

        v1.x entries lack: summary, valid_at, invalid_at, type, created_by,
        and source may be missing agent_type/agent_id/session_id fields.
        All are added with safe defaults. The file is rewritten atomically.
        """
        for entries in data.get("memories", {}).values():
            for entry in entries.values():
                if "summary" not in entry:
                    entry["summary"] = generate_summary(entry.get("value", ""))
                if "valid_at" not in entry:
                    entry["valid_at"] = entry.get("created_at")
                if "invalid_at" not in entry:
                    entry["invalid_at"] = None
                if "type" not in entry:
                    entry["type"] = None
                if "created_by" not in entry:
                    entry["created_by"] = None
                source = entry.get("source", {})
                if isinstance(source, str):
                    source = {"type": "session", "detail": source}
                    entry["source"] = source
                source.setdefault("agent_type", None)
                source.setdefault("agent_id", None)
                source.setdefault("session_id", None)

        # Ensure all v2.0 categories exist
        memories = data.setdefault("memories", {})
        for cat in VALID_CATEGORIES:
            memories.setdefault(cat, {})

        data["schema_version"] = SCHEMA_VERSION
        self._save(data)

    def _read_modify_write(self, mutator):
        """Lock, load, apply mutator, save. Returns mutator's return value."""
        with self._lock():
            data = self._load()
            result = mutator(data)
            self._save(data)
            return result

    # -- Validation helpers ---------------------------------------------------

    @staticmethod
    def _validate_category(category: str) -> None:
        if category not in VALID_CATEGORIES:
            msg = f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}"
            raise ValueError(msg)

    # -- Public API -----------------------------------------------------------

    def session_start(self) -> dict:
        """Increment session_count and return full memory summary."""

        def _mutate(data: dict) -> dict:
            data["session_count"] = data.get("session_count", 0) + 1
            memories = data.get("memories", {})
            categories = {}
            total = 0
            for cat_name in VALID_CATEGORIES:
                count = len(memories.get(cat_name, {}))
                categories[cat_name] = count
                total += count
            return {
                "session_count": data["session_count"],
                "categories": categories,
                "total": total,
                "schema_version": data.get("schema_version", SCHEMA_VERSION),
            }

        return self._read_modify_write(_mutate)

    def remember(
        self,
        category: str,
        key: str,
        value: str,
        *,
        tags: list[str] | None = None,
        importance: int = 5,
        source_type: str = "session",
        confidence: float | None = None,
        force: bool = False,
        broad: bool = False,
        summary: str | None = None,
        entry_type: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        """Create or update a memory entry.

        When the key already exists, updates in place (no dedup check).
        For new keys, scans for overlapping entries and returns candidates
        unless ``force=True`` bypasses the check.
        Set ``broad=True`` to search across all categories instead of just
        the target category.
        """
        self._validate_category(category)
        importance = _clamp_importance(importance)
        resolved_tags = sorted(tags) if tags else []

        if not force:
            candidates = self._find_candidates(category, key, value, resolved_tags, broad=broad)
            if candidates:
                recommendation = _recommend_action(candidates, value)
                if recommendation != "ADD":
                    return {
                        "action": "candidates",
                        "candidates": candidates,
                        "recommendation": recommendation,
                    }
                # ADD recommendation: proceed to write — no second call needed

        return self._do_remember(
            category,
            key,
            value,
            tags=resolved_tags,
            importance=importance,
            source_type=source_type,
            confidence=confidence,
            summary=summary,
            entry_type=entry_type,
            created_by=created_by,
        )

    def _find_candidates(
        self,
        category: str,
        key: str,
        value: str,
        tags: list[str],
        *,
        broad: bool = False,
    ) -> list[dict]:
        """Scan for dedup candidates (read-only, no file mutation)."""
        data = self._load()
        memories = data.get("memories", {})

        # Check if exact key exists -- skip dedup entirely
        cat_entries = memories.get(category, {})
        if key in cat_entries:
            return []

        all_candidates: list[dict] = []
        if broad:
            for cat_name in VALID_CATEGORIES:
                entries = memories.get(cat_name, {})
                all_candidates.extend(_find_dedup_candidates(key, value, tags, entries, cat_name))
        else:
            all_candidates = _find_dedup_candidates(key, value, tags, cat_entries, category)

        return all_candidates

    def _do_remember(
        self,
        category: str,
        key: str,
        value: str,
        *,
        tags: list[str],
        importance: int,
        source_type: str,
        confidence: float | None,
        summary: str | None = None,
        entry_type: str | None = None,
        created_by: str | None = None,
    ) -> dict:
        """Unconditionally create or update a memory entry (no dedup check).

        For new entries (ADD), scans the same category for tag-matched entries
        and auto-creates ``related-to`` links when 2+ tags overlap.
        """
        now = _now_utc()
        resolved_summary = summary if summary is not None else generate_summary(value)

        def _mutate(data: dict) -> dict:
            memories = data.setdefault("memories", {})
            cat_entries = memories.setdefault(category, {})

            if key in cat_entries:
                existing = cat_entries[key]
                existing["value"] = value
                existing["updated_at"] = now
                existing["summary"] = resolved_summary
                if tags:
                    merged = list(set(existing.get("tags", [])) | set(tags))
                    existing["tags"] = sorted(merged)
                existing["importance"] = importance
                if confidence is not None:
                    existing["confidence"] = confidence
                if entry_type is not None:
                    existing["type"] = entry_type
                if created_by is not None:
                    existing["created_by"] = created_by
                return {"action": "UPDATE", "entry": dict(existing)}

            entry = MemoryEntry(
                value=value,
                created_at=now,
                updated_at=now,
                tags=list(tags),
                confidence=confidence,
                importance=importance,
                source=Source(type=source_type),
                access_count=0,
                last_accessed=None,
                status="active",
                summary=resolved_summary,
                valid_at=now,
                invalid_at=None,
                type=entry_type,
                created_by=created_by,
            )
            entry_dict = entry.to_dict()
            cat_entries[key] = entry_dict

            # Auto-link: find tag-matched entries in the same category
            auto_links = _find_auto_links(category, key, tags, cat_entries)
            if auto_links:
                entry_dict["links"] = auto_links

            return {"action": "ADD", "entry": dict(entry_dict)}

        return self._read_modify_write(_mutate)

    def forget(self, category: str, key: str) -> dict:
        """Soft-delete a memory entry by setting invalid_at and status.

        The entry remains in the store with status="superseded" and an
        ``invalid_at`` timestamp.  Links are preserved for historical queries.
        A pre-mutation backup is created.
        """
        self._validate_category(category)
        now = _now_utc()

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})
            cat_entries = memories.get(category, {})
            if key not in cat_entries:
                msg = f"Key '{key}' not found in category '{category}'"
                raise KeyError(msg)

            # Create backup before mutation
            backup_path = self._path.with_name(self._path.stem + PRE_FORGET_BACKUP_SUFFIX)
            backup_content = json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n"
            backup_path.write_text(backup_content, encoding="utf-8")

            entry = cat_entries[key]
            entry["invalid_at"] = now
            entry["status"] = "superseded"

            return {
                "action": "soft_deleted",
                "entry": dict(entry),
                "backup_path": str(backup_path),
            }

        return self._read_modify_write(_mutate)

    def hard_delete(self, category: str, key: str) -> dict:
        """Permanently remove a memory entry and clean up incoming links.

        Creates a backup before removal. Use this for entries that must be
        fully erased (e.g., sensitive data).
        """
        self._validate_category(category)
        target_ref = f"{category}.{key}"

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})
            cat_entries = memories.get(category, {})
            if key not in cat_entries:
                msg = f"Key '{key}' not found in category '{category}'"
                raise KeyError(msg)

            removed = cat_entries.pop(key)

            # Clean up incoming links from all entries pointing to the deleted entry
            _remove_incoming_links(memories, target_ref)

            backup_path = self._path.with_name(self._path.stem + BACKUP_SUFFIX)
            backup_content = json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n"
            backup_path.write_text(backup_content, encoding="utf-8")

            return {"removed": removed, "backup_path": str(backup_path)}

        return self._read_modify_write(_mutate)

    def recall(self, category: str, key: str | None = None) -> dict:
        """Retrieve entries with access tracking."""
        self._validate_category(category)
        now = _now_utc()

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})
            cat_entries = memories.get(category, {})

            if key is not None:
                if key not in cat_entries:
                    msg = f"Key '{key}' not found in category '{category}'"
                    raise KeyError(msg)
                entry = cat_entries[key]
                entry["access_count"] = entry.get("access_count", 0) + 1
                entry["last_accessed"] = now
                return {"entries": {key: dict(entry)}}

            for entry in cat_entries.values():
                entry["access_count"] = entry.get("access_count", 0) + 1
                entry["last_accessed"] = now
            return {"entries": {k: dict(v) for k, v in cat_entries.items()}}

        return self._read_modify_write(_mutate)

    def search(
        self,
        query: str,
        category: str | None = None,
        *,
        detail: str = "full",
        include_historical: bool = False,
        since: str | None = None,
        entry_type: str | None = None,
    ) -> dict:
        """Multi-signal ranked search across keys, values, tags, and summaries.

        Entries must match the text query to be included. Among matches,
        results are ranked by a weighted combination of text match quality,
        tag overlap, importance, and recency signals.

        Args:
            query: Search text. Multi-term queries match if ANY term matches
                ANY field (key, value, tags, summary).
            category: Optional category filter.
            detail: ``"index"`` returns Markdown-formatted summaries;
                ``"full"`` returns complete entry dicts (default).
            include_historical: When True, include soft-deleted entries.
            since: Optional ISO 8601 timestamp. Only entries with
                ``created_at >= since`` are included.
            entry_type: Optional type filter. Only entries whose ``type`` field
                matches are included.
        """
        if category is not None:
            self._validate_category(category)
        now_str = _now_utc()
        now_dt = datetime.now(UTC)
        query_lower = query.lower()
        query_terms = [t for t in query_lower.split() if t]

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})
            categories_to_search = {category: memories.get(category, {})} if category else memories

            results = []
            for cat_name, entries in categories_to_search.items():
                for entry_key, entry in entries.items():
                    # Filter inactive entries unless include_historical
                    if not _is_active(entry) and not include_historical:
                        continue

                    # Filter by created_at >= since
                    if since is not None and entry.get("created_at", "") < since:
                        continue

                    # Filter by type
                    if entry_type is not None and entry.get("type") != entry_type:
                        continue

                    match_reasons = _find_match_reasons_multi(
                        entry_key,
                        entry,
                        query_lower,
                        query_terms,
                    )
                    if not match_reasons:
                        continue

                    # Compute signals BEFORE updating access tracking
                    # so recency reflects the entry's pre-search state
                    signals = {
                        "text_match": _compute_text_match_score(
                            entry_key,
                            entry,
                            query_lower,
                        ),
                        "tag_match": _compute_tag_match_score(
                            entry,
                            query_terms,
                        ),
                        "importance": _compute_importance_score(entry),
                        "recency": _compute_recency_score(entry, now_dt),
                    }
                    score = _compute_search_score(signals)

                    # Track access after scoring
                    entry["access_count"] = entry.get("access_count", 0) + 1
                    entry["last_accessed"] = now_str

                    results.append(
                        {
                            "category": cat_name,
                            "key": entry_key,
                            "entry": dict(entry),
                            "score": round(score, 4),
                            "signals": {k: round(v, 4) for k, v in signals.items()},
                            "match_reason": ", ".join(match_reasons),
                        }
                    )

            results.sort(key=lambda r: r["score"], reverse=True)

            if detail == "index":
                markdown = format_search_results_markdown(results, query)
                return {"results_markdown": markdown, "count": len(results)}

            return {"results": results}

        return self._read_modify_write(_mutate)

    def status(self) -> dict:
        """Return store status with category counts and metadata."""
        data = self._load()
        memories = data.get("memories", {})
        categories = {}
        total = 0
        for cat_name in VALID_CATEGORIES:
            count = len(memories.get(cat_name, {}))
            categories[cat_name] = count
            total += count

        file_size = self._path.stat().st_size if self._path.exists() else 0

        return {
            "categories": categories,
            "total": total,
            "schema_version": data.get("schema_version", SCHEMA_VERSION),
            "session_count": data.get("session_count", 0),
            "file_size": _human_file_size(file_size),
        }

    def export(self, output_format: str = "markdown") -> dict:
        """Export all memories as markdown or JSON."""
        data = self._load()
        if output_format == "json":
            return {"content": json.dumps(data, indent=JSON_INDENT, ensure_ascii=False)}

        return {"content": _format_as_markdown(data)}

    def browse_index(self, include_historical: bool = False) -> dict:
        """Return a Markdown-KV index of all memory entries grouped by category.

        Soft-deleted entries are excluded by default. Set *include_historical*
        to include them with an annotation.
        """
        data = self._load()
        memories = data.get("memories", {})

        # Count active (and optionally historical) entries per category
        categories: dict[str, int] = {}
        total = 0
        for cat_name, entries in memories.items():
            count = 0
            for entry in entries.values():
                if _is_active(entry) or include_historical:
                    count += 1
            if count:
                categories[cat_name] = count
                total += count

        index_md = format_markdown_kv_index(memories, include_historical=include_historical)
        return {
            "index": index_md,
            "entry_count": total,
            "categories": categories,
        }

    def consolidate(self, actions: list[dict], *, dry_run: bool = False) -> dict:
        """Validate and apply consolidation actions atomically.

        Creates a timestamped backup before mutation. Actions are validated
        first -- if any fail, no changes are made.

        Args:
            actions: List of action dicts (merge, archive, adjust_confidence,
                update_summary).
            dry_run: When True, validate and preview without mutating.
        """
        # Pre-validate against current state (read-only)
        data = self._load()
        memories = data.get("memories", {})
        validation = validate_actions(actions, memories)

        if not validation["valid"]:
            return {"valid": False, "errors": validation["errors"]}

        if dry_run:
            return {"valid": True, "dry_run": True, "action_count": len(actions), "errors": []}

        def _mutate(data: dict) -> dict:
            # Create pre-consolidation backup
            now_stamp = _now_utc().replace(":", "-")
            backup_name = f"{self._path.stem}.pre-consolidation-{now_stamp}.json"
            backup_path = self._path.with_name(backup_name)
            backup_content = json.dumps(data, indent=JSON_INDENT, ensure_ascii=False) + "\n"
            backup_path.write_text(backup_content, encoding="utf-8")

            mems = data.get("memories", {})
            result = apply_actions(actions, mems)
            result["backup_path"] = str(backup_path)
            return result

        return self._read_modify_write(_mutate)

    def about_me(self) -> dict:
        """Aggregate user profile from user, relationships, and tools categories."""
        data = self._load()
        memories = data.get("memories", {})
        lines = []

        user_entries = memories.get("user", {})
        if user_entries:
            lines.append("## User Profile")
            for key, entry in user_entries.items():
                lines.append(f"- **{key}**: {entry['value']}")

        rel_entries = memories.get("relationships", {})
        user_facing = {k: v for k, v in rel_entries.items() if "user-facing" in v.get("tags", [])}
        if user_facing:
            lines.append("")
            lines.append("## Relationship Context")
            for key, entry in user_facing.items():
                lines.append(f"- **{key}**: {entry['value']}")

        tools_entries = memories.get("tools", {})
        user_prefs = {
            k: v for k, v in tools_entries.items() if "user-preference" in v.get("tags", [])
        }
        if user_prefs:
            lines.append("")
            lines.append("## Tool Preferences")
            for key, entry in user_prefs.items():
                lines.append(f"- **{key}**: {entry['value']}")

        profile = "\n".join(lines) if lines else "No user profile data found."
        return {"profile": profile}

    def about_us(self) -> dict:
        """Aggregate relationship and relevant assistant entries."""
        data = self._load()
        memories = data.get("memories", {})
        lines = []

        rel_entries = memories.get("relationships", {})
        if rel_entries:
            lines.append("## Our Relationship")
            for key, entry in rel_entries.items():
                lines.append(f"- **{key}**: {entry['value']}")

        assistant_entries = memories.get("assistant", {})
        if assistant_entries:
            lines.append("")
            lines.append("## Assistant Identity")
            for key, entry in assistant_entries.items():
                lines.append(f"- **{key}**: {entry['value']}")

        profile = "\n".join(lines) if lines else "No relationship data found."
        return {"profile": profile}

    def reflect(self) -> dict:
        """Run lifecycle analysis on the memory store. Read-only -- no writes."""
        data = self._load()
        session_count = data.get("session_count", 0)
        return lifecycle_analyze(data, session_count)

    # -- Link operations ------------------------------------------------------

    def add_link(
        self,
        source_category: str,
        source_key: str,
        target_category: str,
        target_key: str,
        relation: str,
    ) -> dict:
        """Create a unidirectional link from source entry to target entry."""
        self._validate_category(source_category)
        self._validate_category(target_category)
        if relation not in VALID_RELATIONS:
            msg = f"Invalid relation '{relation}'. Must be one of: {', '.join(VALID_RELATIONS)}"
            raise ValueError(msg)

        target_ref = f"{target_category}.{target_key}"
        source_ref = f"{source_category}.{source_key}"

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})

            # Validate source exists
            src_entries = memories.get(source_category, {})
            if source_key not in src_entries:
                msg = f"Source entry '{source_ref}' not found"
                raise KeyError(msg)

            # Validate target exists
            tgt_entries = memories.get(target_category, {})
            if target_key not in tgt_entries:
                msg = f"Target entry '{target_ref}' not found"
                raise KeyError(msg)

            source_entry = src_entries[source_key]
            links = source_entry.setdefault("links", [])

            # Prevent duplicate links (same target + relation)
            for existing_link in links:
                if existing_link["target"] == target_ref and existing_link["relation"] == relation:
                    return {
                        "link_created": False,
                        "reason": "duplicate",
                        "source": source_ref,
                        "target": target_ref,
                        "relation": relation,
                    }

            links.append({"target": target_ref, "relation": relation})
            return {
                "link_created": True,
                "source": source_ref,
                "target": target_ref,
                "relation": relation,
            }

        return self._read_modify_write(_mutate)

    def remove_link(
        self,
        source_category: str,
        source_key: str,
        target_category: str,
        target_key: str,
    ) -> dict:
        """Remove a link from source entry to target entry."""
        self._validate_category(source_category)
        self._validate_category(target_category)

        target_ref = f"{target_category}.{target_key}"
        source_ref = f"{source_category}.{source_key}"

        def _mutate(data: dict) -> dict:
            memories = data.get("memories", {})
            src_entries = memories.get(source_category, {})

            if source_key not in src_entries:
                msg = f"Source entry '{source_ref}' not found"
                raise KeyError(msg)

            source_entry = src_entries[source_key]
            links = source_entry.get("links", [])
            original_count = len(links)
            source_entry["links"] = [lk for lk in links if lk["target"] != target_ref]

            if len(source_entry["links"]) == original_count:
                msg = f"No link from '{source_ref}' to '{target_ref}'"
                raise KeyError(msg)

            return {"link_removed": True, "source": source_ref, "target": target_ref}

        return self._read_modify_write(_mutate)

    def connections(self, category: str, key: str) -> dict:
        """Find all outgoing and incoming links for an entry."""
        self._validate_category(category)
        target_ref = f"{category}.{key}"

        data = self._load()
        memories = data.get("memories", {})

        # Validate entry exists
        cat_entries = memories.get(category, {})
        if key not in cat_entries:
            msg = f"Entry '{target_ref}' not found"
            raise KeyError(msg)

        entry = cat_entries[key]

        # Outgoing links
        outgoing = []
        for link in entry.get("links", []):
            target = link["target"]
            relation = link["relation"]
            tgt_cat, tgt_key = target.split(".", 1)
            tgt_entry = memories.get(tgt_cat, {}).get(tgt_key, {})
            outgoing.append(
                {
                    "target": target,
                    "relation": relation,
                    "entry_summary": tgt_entry.get("value", ""),
                }
            )

        # Incoming links (reverse lookup)
        incoming = _find_incoming_links(memories, target_ref)

        return {"outgoing": outgoing, "incoming": incoming}


# -- Module-level helpers (kept out of class for readability) -----------------


def _find_auto_links(
    category: str,
    new_key: str,
    new_tags: list[str],
    cat_entries: dict[str, dict],
) -> list[dict]:
    """Find entries in the same category with 2+ tag overlap for auto-linking.

    Returns a list of link dicts (max MAX_AUTO_LINKS_PER_REMEMBER).
    """
    if not new_tags:
        return []

    new_tag_set = {t.lower() for t in new_tags}
    auto_links: list[dict] = []

    for existing_key, entry in cat_entries.items():
        if existing_key == new_key:
            continue

        existing_tags = {t.lower() for t in entry.get("tags", [])}
        overlap = len(new_tag_set & existing_tags)
        if overlap >= AUTO_LINK_TAG_OVERLAP_THRESHOLD:
            target_ref = f"{category}.{existing_key}"
            auto_links.append(
                {
                    "target": target_ref,
                    "relation": AUTO_LINK_RELATION,
                }
            )
            if len(auto_links) >= MAX_AUTO_LINKS_PER_REMEMBER:
                break

    return auto_links


def _remove_incoming_links(memories: dict, target_ref: str) -> None:
    """Remove all links pointing to target_ref from all entries in the store."""
    for _cat_name, entries in memories.items():
        for _key, entry in entries.items():
            links = entry.get("links", [])
            if links:
                entry["links"] = [lk for lk in links if lk["target"] != target_ref]


def _find_incoming_links(memories: dict, target_ref: str) -> list[dict]:
    """Scan all entries for links pointing to target_ref (reverse lookup)."""
    incoming: list[dict] = []
    for cat_name, entries in memories.items():
        for entry_key, entry in entries.items():
            for link in entry.get("links", []):
                if link["target"] == target_ref:
                    source_ref = f"{cat_name}.{entry_key}"
                    incoming.append(
                        {
                            "source": source_ref,
                            "relation": link["relation"],
                            "entry_summary": entry.get("value", ""),
                        }
                    )
    return incoming


def _is_fd_closed(fd: int) -> bool:
    """Check if a file descriptor is already closed."""
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False
