"""Tests for browse_index() with Markdown-KV formatting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_mcp.schema import SCHEMA_VERSION
from memory_mcp.search import EMPTY_INDEX_MESSAGE
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
        "importance": 5,
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


# -- Markdown format output ---------------------------------------------------


class TestBrowseIndexMarkdownFormat:
    def test_returns_category_headers_with_counts(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "name": _make_entry("Alice", summary="User's name"),
                    "email": _make_entry("alice@example.com", summary="User email"),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        assert "## user (2 entries)" in result["index"]

    def test_entries_formatted_with_summary_and_tags(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "tools": {
                    "editor": _make_entry(
                        "vim",
                        summary="Preferred editor",
                        tags=["coding", "terminal"],
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        assert "- **editor**: Preferred editor [coding, terminal]" in result["index"]

    def test_entries_sorted_alphabetically(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "z_entry": _make_entry("last"),
                    "a_entry": _make_entry("first"),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        a_pos = result["index"].index("a_entry")
        z_pos = result["index"].index("z_entry")
        assert a_pos < z_pos

    def test_categories_sorted_alphabetically(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {"name": _make_entry("Alice")},
                "tools": {"editor": _make_entry("vim")},
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        tools_pos = result["index"].index("## tools")
        user_pos = result["index"].index("## user")
        assert tools_pos < user_pos

    def test_entry_count_in_result(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {"name": _make_entry("Alice")},
                "tools": {"editor": _make_entry("vim")},
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        assert result["entry_count"] == 2
        assert result["categories"]["user"] == 1
        assert result["categories"]["tools"] == 1


# -- Soft-deleted entries filtered by default ----------------------------------


class TestBrowseIndexSoftDeleteFiltering:
    def test_excludes_soft_deleted_by_default(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "active_entry": _make_entry("Alice"),
                    "deleted_entry": _make_entry(
                        "Bob",
                        invalid_at="2026-04-01T00:00:00Z",
                        status="superseded",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        assert "active_entry" in result["index"]
        assert "deleted_entry" not in result["index"]
        assert result["entry_count"] == 1

    def test_include_historical_shows_soft_deleted(self, memory_file: Path):
        _write_store(
            memory_file,
            {
                "user": {
                    "active_entry": _make_entry("Alice"),
                    "deleted_entry": _make_entry(
                        "Bob",
                        invalid_at="2026-04-01T00:00:00Z",
                        status="superseded",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index(include_historical=True)
        assert "active_entry" in result["index"]
        assert "deleted_entry" in result["index"]
        assert "superseded" in result["index"]
        assert result["entry_count"] == 2

    def test_all_soft_deleted_category_hidden(self, memory_file: Path):
        """A category with only soft-deleted entries is not shown."""
        _write_store(
            memory_file,
            {
                "user": {
                    "deleted": _make_entry(
                        "Gone",
                        invalid_at="2026-04-01T00:00:00Z",
                        status="superseded",
                    ),
                },
            },
        )
        store = MemoryStore(memory_file)
        result = store.browse_index()
        assert "user" not in result["index"]
        assert result["entry_count"] == 0


# -- Empty store ---------------------------------------------------------------


class TestBrowseIndexEmpty:
    def test_empty_store(self, store: MemoryStore):
        result = store.browse_index()
        assert result["index"] == EMPTY_INDEX_MESSAGE
        assert result["entry_count"] == 0
        assert result["categories"] == {}
