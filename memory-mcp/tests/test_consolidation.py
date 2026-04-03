"""Tests for the consolidation engine (merge, archive, adjust, update_summary)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_mcp.store import MemoryStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    return tmp_path / "memory.json"


@pytest.fixture
def store(memory_file: Path) -> MemoryStore:
    return MemoryStore(memory_file)


def _seed_entries(store: MemoryStore) -> None:
    """Create a set of entries for consolidation tests."""
    store.remember("learnings", "tip-a", "Use pytest fixtures", tags=["python", "testing"])
    store.remember(
        "learnings",
        "tip-b",
        "Use pytest parametrize",
        tags=["python", "testing", "parametrize"],
        force=True,
    )
    store.remember(
        "learnings", "tip-c", "Use pytest marks", tags=["python", "testing", "marks"], force=True
    )
    store.remember("user", "name", "Alice", summary="User name is Alice")


# -- Merge action -------------------------------------------------------------


class TestMergeAction:
    def test_merge_combines_values(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "merge",
                "target_category": "learnings",
                "target_key": "tip-a",
                "sources": [
                    {"category": "learnings", "key": "tip-b"},
                ],
            },
        ]
        result = store.consolidate(actions)
        assert result["applied"] == 1

        data = json.loads(memory_file.read_text())
        target = data["memories"]["learnings"]["tip-a"]
        assert "Use pytest fixtures" in target["value"]
        assert "Use pytest parametrize" in target["value"]

    def test_merge_unions_tags(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "merge",
                "target_category": "learnings",
                "target_key": "tip-a",
                "sources": [
                    {"category": "learnings", "key": "tip-b"},
                ],
            },
        ]
        store.consolidate(actions)

        data = json.loads(memory_file.read_text())
        target = data["memories"]["learnings"]["tip-a"]
        assert "parametrize" in target["tags"]
        assert "python" in target["tags"]
        assert "testing" in target["tags"]

    def test_merge_soft_deletes_sources(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "merge",
                "target_category": "learnings",
                "target_key": "tip-a",
                "sources": [
                    {"category": "learnings", "key": "tip-b"},
                ],
            },
        ]
        store.consolidate(actions)

        data = json.loads(memory_file.read_text())
        source = data["memories"]["learnings"]["tip-b"]
        assert source["invalid_at"] is not None
        assert source["status"] == "superseded"

    def test_merge_adds_supersedes_links(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "merge",
                "target_category": "learnings",
                "target_key": "tip-a",
                "sources": [
                    {"category": "learnings", "key": "tip-b"},
                ],
            },
        ]
        store.consolidate(actions)

        data = json.loads(memory_file.read_text())
        target = data["memories"]["learnings"]["tip-a"]
        links = target.get("links", [])
        supersedes = [lk for lk in links if lk["relation"] == "supersedes"]
        assert len(supersedes) == 1
        assert supersedes[0]["target"] == "learnings.tip-b"

    def test_merge_takes_max_importance(self, store: MemoryStore, memory_file: Path):
        store.remember("learnings", "low", "low importance", importance=2)
        store.remember("learnings", "high", "high importance", importance=9, force=True)
        actions = [
            {
                "type": "merge",
                "target_category": "learnings",
                "target_key": "low",
                "sources": [{"category": "learnings", "key": "high"}],
            },
        ]
        store.consolidate(actions)

        data = json.loads(memory_file.read_text())
        target = data["memories"]["learnings"]["low"]
        assert target["importance"] == 9


# -- Archive action -----------------------------------------------------------


class TestArchiveAction:
    def test_archive_sets_status(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "tip-c"},
        ]
        result = store.consolidate(actions)
        assert result["applied"] == 1

        data = json.loads(memory_file.read_text())
        entry = data["memories"]["learnings"]["tip-c"]
        assert entry["status"] == "archived"


# -- Adjust confidence action -------------------------------------------------


class TestAdjustConfidenceAction:
    def test_adjust_confidence_updates_field(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "adjust_confidence",
                "category": "user",
                "key": "name",
                "confidence": 0.95,
            },
        ]
        result = store.consolidate(actions)
        assert result["applied"] == 1

        data = json.loads(memory_file.read_text())
        entry = data["memories"]["user"]["name"]
        assert entry["confidence"] == 0.95


# -- Update summary action ----------------------------------------------------


class TestUpdateSummaryAction:
    def test_update_summary_replaces_field(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {
                "type": "update_summary",
                "category": "user",
                "key": "name",
                "summary": "New summary for Alice",
            },
        ]
        result = store.consolidate(actions)
        assert result["applied"] == 1

        data = json.loads(memory_file.read_text())
        entry = data["memories"]["user"]["name"]
        assert entry["summary"] == "New summary for Alice"


# -- Dry run ------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_returns_preview(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "tip-c"},
        ]
        result = store.consolidate(actions, dry_run=True)
        assert result["valid"] is True
        assert result["dry_run"] is True
        assert result["action_count"] == 1

        # Verify no mutation occurred
        data = json.loads(memory_file.read_text())
        entry = data["memories"]["learnings"]["tip-c"]
        assert entry["status"] == "active"


# -- Validation errors --------------------------------------------------------


class TestValidationErrors:
    def test_nonexistent_key_returns_error(self, store: MemoryStore):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "nonexistent"},
        ]
        result = store.consolidate(actions)
        assert result["valid"] is False
        assert len(result["errors"]) >= 1
        assert "not found" in result["errors"][0]

    def test_unknown_action_type_returns_error(self, store: MemoryStore):
        _seed_entries(store)
        actions = [
            {"type": "unknown_action", "category": "user", "key": "name"},
        ]
        result = store.consolidate(actions)
        assert result["valid"] is False
        assert "unknown type" in result["errors"][0]


# -- Backup creation ----------------------------------------------------------


class TestConsolidationBackup:
    def test_backup_created_before_mutation(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "tip-c"},
        ]
        result = store.consolidate(actions)
        assert "backup_path" in result

        backup_path = Path(result["backup_path"])
        assert backup_path.exists()

        backup_data = json.loads(backup_path.read_text())
        # In the backup, the entry should still be active (pre-mutation)
        assert backup_data["memories"]["learnings"]["tip-c"]["status"] == "active"


# -- Changelog ----------------------------------------------------------------


class TestChangelog:
    def test_changelog_contains_entries(self, store: MemoryStore):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "tip-a"},
            {"type": "archive", "category": "learnings", "key": "tip-b"},
        ]
        result = store.consolidate(actions)
        assert len(result["changelog"]) == 2
        assert "Archived" in result["changelog"][0]

    def test_multiple_actions_applied_atomically(self, store: MemoryStore, memory_file: Path):
        _seed_entries(store)
        actions = [
            {"type": "archive", "category": "learnings", "key": "tip-a"},
            {
                "type": "update_summary",
                "category": "user",
                "key": "name",
                "summary": "Updated Alice",
            },
        ]
        result = store.consolidate(actions)
        assert result["applied"] == 2

        data = json.loads(memory_file.read_text())
        assert data["memories"]["learnings"]["tip-a"]["status"] == "archived"
        assert data["memories"]["user"]["name"]["summary"] == "Updated Alice"
