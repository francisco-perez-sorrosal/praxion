"""Tests for progressive disclosure in search and improved text matching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_mcp.schema import SCHEMA_VERSION
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
    summary: str | None = None,
    importance: int = 5,
    invalid_at: str | None = None,
    status: str = "active",
) -> dict:
    """Build a raw v1.3 entry dict for direct file injection."""
    return {
        "value": value,
        "created_at": "2026-02-10T06:35:00Z",
        "updated_at": "2026-02-10T06:35:00Z",
        "tags": tags or [],
        "confidence": None,
        "importance": importance,
        "source": {"type": "session", "detail": None},
        "access_count": 0,
        "last_accessed": None,
        "status": status,
        "links": [],
        "summary": summary if summary is not None else value[:100],
        "valid_at": "2026-02-10T06:35:00Z",
        "invalid_at": invalid_at,
    }


def _write_store(memory_file: Path, entries_by_category: dict) -> None:
    """Write a pre-built memory store to the file."""
    memories = {
        cat: {} for cat in ("user", "assistant", "project", "relationships", "tools", "learnings")
    }
    for cat, entries in entries_by_category.items():
        memories[cat] = entries
    doc = {
        "schema_version": SCHEMA_VERSION,
        "session_count": 1,
        "memories": memories,
    }
    memory_file.write_text(json.dumps(doc, indent=2) + "\n")


# -- detail="index" returns Markdown -----------------------------------------


class TestDetailIndex:
    def test_returns_markdown_with_scores(self, store: MemoryStore):
        store.remember("user", "name", "Alice Wonderland", tags=["identity"])
        result = store.search("alice", detail="index")
        assert "results_markdown" in result
        assert "count" in result
        assert result["count"] == 1
        assert "**name**" in result["results_markdown"]
        assert "score:" in result["results_markdown"]

    def test_no_results_returns_message(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("nonexistent_xyz", detail="index")
        assert result["count"] == 0
        assert "No results" in result["results_markdown"]

    def test_multiple_results_numbered(self, store: MemoryStore):
        store.remember("user", "name", "python dev")
        store.remember("tools", "lang", "python 3.13")
        result = store.search("python", detail="index")
        assert result["count"] == 2
        assert "1." in result["results_markdown"]
        assert "2." in result["results_markdown"]


# -- detail="full" returns list of dicts (backward-compatible) ----------------


class TestDetailFull:
    def test_returns_results_list(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("alice", detail="full")
        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) == 1
        assert result["results"][0]["key"] == "name"

    def test_default_detail_is_full(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("alice")
        assert "results" in result


# -- Multi-term query matching ------------------------------------------------


class TestMultiTermSearch:
    def test_multi_term_matches_entry_with_either_term(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "learnings": {
                    "auth-flow": _make_entry(
                        "OAuth2 authentication flow for user login",
                        tags=["auth", "oauth"],
                        summary="OAuth2 auth flow",
                    ),
                    "database": _make_entry(
                        "PostgreSQL connection pooling",
                        tags=["database", "postgres"],
                        summary="DB connection pooling",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("auth login")
        assert len(result["results"]) >= 1
        keys = {r["key"] for r in result["results"]}
        assert "auth-flow" in keys

    def test_multi_term_does_not_match_unrelated(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "learnings": {
                    "database": _make_entry(
                        "PostgreSQL connection pooling",
                        tags=["database"],
                        summary="DB connection pooling",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("auth login")
        assert len(result["results"]) == 0

    def test_single_term_still_works(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("alice")
        assert len(result["results"]) == 1


# -- Search matches against summary field -------------------------------------


class TestSummaryFieldSearch:
    def test_matches_summary_field(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "tools": {
                    "editor": _make_entry(
                        "Configuration details for the code editor",
                        summary="Preferred code editor setup",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        # "preferred" is only in the summary, not the value
        result = store.search("preferred")
        assert len(result["results"]) == 1
        assert result["results"][0]["key"] == "editor"


# -- include_historical includes soft-deleted entries -------------------------


class TestIncludeHistorical:
    def test_excludes_soft_deleted_by_default(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "active": _make_entry("Alice is active"),
                    "deleted": _make_entry(
                        "Bob was deleted",
                        invalid_at="2026-04-01T00:00:00Z",
                        status="superseded",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("active deleted", detail="full", include_historical=False)
        keys = {r["key"] for r in result["results"]}
        assert "active" in keys
        assert "deleted" not in keys

    def test_includes_soft_deleted_when_requested(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "active": _make_entry("Alice is active"),
                    "deleted": _make_entry(
                        "Bob was deleted",
                        invalid_at="2026-04-01T00:00:00Z",
                        status="superseded",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.search("deleted", detail="full", include_historical=True)
        keys = {r["key"] for r in result["results"]}
        assert "deleted" in keys
