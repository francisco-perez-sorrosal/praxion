"""Tests for soft delete (forget), hard_delete, and _is_active filtering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_mcp.store import MemoryStore, _is_active

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    return tmp_path / "memory.json"


@pytest.fixture
def store(memory_file: Path) -> MemoryStore:
    return MemoryStore(memory_file)


# -- _is_active helper -------------------------------------------------------


class TestIsActive:
    def test_active_entry_returns_true(self):
        entry = {"invalid_at": None, "status": "active"}
        assert _is_active(entry) is True

    def test_superseded_entry_returns_false(self):
        entry = {"invalid_at": "2026-04-03T00:00:00Z", "status": "superseded"}
        assert _is_active(entry) is False

    def test_missing_invalid_at_returns_true(self):
        entry = {"status": "active"}
        assert _is_active(entry) is True

    def test_invalid_at_set_with_active_status_returns_false(self):
        """Primary check is invalid_at, not status."""
        entry = {"invalid_at": "2026-04-03T00:00:00Z", "status": "active"}
        assert _is_active(entry) is False


# -- Soft delete (forget) ----------------------------------------------------


class TestSoftDelete:
    def test_forget_sets_invalid_at(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        result = store.forget("user", "name")

        assert result["entry"]["invalid_at"] is not None
        assert result["entry"]["status"] == "superseded"

        # Verify persisted in file
        data = json.loads(memory_file.read_text())
        entry = data["memories"]["user"]["name"]
        assert entry["invalid_at"] is not None
        assert entry["status"] == "superseded"

    def test_forget_returns_soft_deleted_action(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.forget("user", "name")
        assert result["action"] == "soft_deleted"
        assert result["entry"]["value"] == "Alice"

    def test_forget_entry_remains_in_store(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        store.forget("user", "name")

        data = json.loads(memory_file.read_text())
        assert "name" in data["memories"]["user"]

    def test_forget_creates_backup(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.forget("user", "name")

        backup_path = Path(result["backup_path"])
        assert backup_path.exists()
        backup_data = json.loads(backup_path.read_text())
        assert "memories" in backup_data

    def test_forget_preserves_links(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "alice@example.com")
        store.add_link("user", "name", "user", "email", "related-to")

        store.forget("user", "name")

        data = json.loads(memory_file.read_text())
        links = data["memories"]["user"]["name"]["links"]
        assert len(links) == 1
        assert links[0]["target"] == "user.email"

    def test_forget_nonexistent_raises(self, store: MemoryStore):
        with pytest.raises(KeyError):
            store.forget("user", "nonexistent")


# -- Hard delete --------------------------------------------------------------


class TestHardDelete:
    def test_hard_delete_removes_entry(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        result = store.hard_delete("user", "name")

        assert result["removed"]["value"] == "Alice"
        assert "backup_path" in result

        data = json.loads(memory_file.read_text())
        assert "name" not in data["memories"]["user"]

    def test_hard_delete_cleans_up_incoming_links(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "alice@example.com")
        store.add_link("user", "email", "user", "name", "elaborates")

        store.hard_delete("user", "name")

        data = json.loads(memory_file.read_text())
        email_links = data["memories"]["user"]["email"]["links"]
        assert len(email_links) == 0

    def test_hard_delete_creates_backup(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.hard_delete("user", "name")

        backup_path = Path(result["backup_path"])
        assert backup_path.exists()

    def test_hard_delete_nonexistent_raises(self, store: MemoryStore):
        with pytest.raises(KeyError):
            store.hard_delete("user", "nonexistent")

    def test_hard_delete_recall_raises(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.hard_delete("user", "name")

        with pytest.raises(KeyError):
            store.recall("user", "name")
