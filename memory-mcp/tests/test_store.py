"""Tests for MemoryStore CRUD operations and file I/O."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_mcp.schema import SCHEMA_VERSION, VALID_CATEGORIES
from memory_mcp.store import MemoryStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    """Return a path for a new memory file (not yet created)."""
    return tmp_path / "memory.json"


@pytest.fixture
def store(memory_file: Path) -> MemoryStore:
    """Return a MemoryStore backed by a fresh empty file."""
    return MemoryStore(memory_file)


# -- Init and file creation ---------------------------------------------------


class TestStoreInit:
    def test_creates_file_if_missing(self, memory_file: Path):
        assert not memory_file.exists()
        MemoryStore(memory_file)
        assert memory_file.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        deep_path = tmp_path / "a" / "b" / "c" / "memory.json"
        MemoryStore(deep_path)
        assert deep_path.exists()

    def test_new_file_has_valid_structure(self, memory_file: Path):
        MemoryStore(memory_file)
        data = json.loads(memory_file.read_text())
        assert data["schema_version"] == SCHEMA_VERSION
        assert data["session_count"] == 0
        assert set(data["memories"].keys()) == set(VALID_CATEGORIES)

    def test_loads_existing_v2_0_file(self, memory_file: Path):
        existing = {
            "schema_version": "2.0",
            "session_count": 5,
            "memories": {
                "user": {
                    "name": {
                        "value": "Test",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "tags": [],
                        "confidence": None,
                        "importance": 5,
                        "source": {"type": "session", "detail": None},
                        "access_count": 0,
                        "last_accessed": None,
                        "status": "active",
                        "links": [],
                        "summary": "Test",
                        "valid_at": "2026-01-01T00:00:00Z",
                        "invalid_at": None,
                        "type": None,
                        "created_by": None,
                    }
                }
            },
        }
        memory_file.write_text(json.dumps(existing, indent=2) + "\n")
        store = MemoryStore(memory_file)
        result = store.status()
        assert result["session_count"] == 5

    def test_migrates_v1_2_to_v2_0(self, memory_file: Path):
        old = {
            "schema_version": "1.2",
            "session_count": 3,
            "memories": {
                "user": {},
                "learnings": {
                    "test-entry": {
                        "value": "A test learning that should survive migration",
                        "created_at": "2026-01-15T10:00:00Z",
                        "updated_at": "2026-01-15T10:00:00Z",
                        "tags": ["testing"],
                        "confidence": None,
                        "importance": 7,
                        "source": {"type": "session", "detail": None},
                        "access_count": 0,
                        "last_accessed": None,
                        "status": "active",
                        "links": [],
                    }
                },
            },
        }
        memory_file.write_text(json.dumps(old, indent=2) + "\n")
        store = MemoryStore(memory_file)
        data = json.loads(memory_file.read_text())
        assert data["schema_version"] == "2.0"
        assert data["session_count"] == 3
        entry = data["memories"]["learnings"]["test-entry"]
        assert entry["value"] == "A test learning that should survive migration"
        assert entry["summary"] != ""
        assert entry["valid_at"] == "2026-01-15T10:00:00Z"
        assert entry["invalid_at"] is None
        assert entry["type"] is None
        assert entry["created_by"] is None
        assert entry["source"]["agent_type"] is None
        # All v2.0 categories exist after migration
        assert set(data["memories"].keys()) == set(VALID_CATEGORIES)
        # Store is functional after migration
        result = store.status()
        assert result["total"] == 1

    def test_migrates_v1_3_to_v2_0(self, memory_file: Path):
        v1_3 = {
            "schema_version": "1.3",
            "session_count": 3,
            "memories": {"user": {}},
        }
        memory_file.write_text(json.dumps(v1_3, indent=2) + "\n")
        MemoryStore(memory_file)
        data = json.loads(memory_file.read_text())
        assert data["schema_version"] == "2.0"

    def test_rejects_unknown_schema_version(self, memory_file: Path):
        unknown = {
            "schema_version": "3.0",
            "session_count": 0,
            "memories": {"user": {}},
        }
        memory_file.write_text(json.dumps(unknown, indent=2) + "\n")
        with pytest.raises(ValueError, match="Unsupported schema version"):
            MemoryStore(memory_file)

    def test_migration_handles_string_source(self, memory_file: Path):
        old = {
            "schema_version": "1.0",
            "session_count": 1,
            "memories": {
                "learnings": {
                    "entry": {
                        "value": "Test",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "source": "implementer",
                        "tags": [],
                        "importance": 5,
                        "access_count": 0,
                        "last_accessed": None,
                        "status": "active",
                        "links": [],
                    }
                }
            },
        }
        memory_file.write_text(json.dumps(old, indent=2) + "\n")
        MemoryStore(memory_file)
        data = json.loads(memory_file.read_text())
        source = data["memories"]["learnings"]["entry"]["source"]
        assert isinstance(source, dict)
        assert source["type"] == "session"
        assert source["detail"] == "implementer"


# -- CRUD cycle: remember -> recall -> forget ---------------------------------


class TestCRUDCycle:
    def test_remember_creates_new_entry(self, store: MemoryStore):
        result = store.remember("user", "name", "Alice", tags=["identity"])
        assert result["action"] == "ADD"
        assert result["entry"]["value"] == "Alice"
        assert "identity" in result["entry"]["tags"]

    def test_remember_sets_summary_on_create(self, store: MemoryStore):
        result = store.remember("user", "name", "Alice Wonderland")
        assert result["entry"]["summary"] == "Alice Wonderland"

    def test_remember_auto_generates_summary(self, store: MemoryStore):
        long_value = "word " * 30  # 150 chars
        result = store.remember("user", "bio", long_value.strip())
        summary = result["entry"]["summary"]
        assert summary.endswith("...")
        assert len(summary) <= 103  # 100 + "..."

    def test_remember_accepts_custom_summary(self, store: MemoryStore):
        result = store.remember(
            "user",
            "name",
            "Alice Wonderland",
            summary="Custom summary",
        )
        assert result["entry"]["summary"] == "Custom summary"

    def test_remember_sets_valid_at_on_create(self, store: MemoryStore):
        result = store.remember("user", "name", "Alice")
        assert result["entry"]["valid_at"] is not None
        assert result["entry"]["invalid_at"] is None

    def test_remember_updates_existing_entry(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.remember("user", "name", "Bob", tags=["updated"])
        assert result["action"] == "UPDATE"
        assert result["entry"]["value"] == "Bob"
        assert "identity" in result["entry"]["tags"]
        assert "updated" in result["entry"]["tags"]

    def test_remember_updates_summary_on_update(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.remember("user", "name", "Bob")
        assert result["entry"]["summary"] == "Bob"

    def test_remember_preserves_created_at_on_update(self, store: MemoryStore):
        add_result = store.remember("user", "name", "Alice")
        created_at = add_result["entry"]["created_at"]
        update_result = store.remember("user", "name", "Bob")
        assert update_result["entry"]["created_at"] == created_at
        assert update_result["entry"]["updated_at"] != created_at

    def test_recall_single_entry(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.recall("user", "name")
        assert "name" in result["entries"]
        assert result["entries"]["name"]["value"] == "Alice"

    def test_recall_all_entries_in_category(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "alice@example.com")
        result = store.recall("user")
        assert len(result["entries"]) == 2
        assert "name" in result["entries"]
        assert "email" in result["entries"]

    def test_forget_soft_deletes_entry(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        result = store.forget("user", "name")
        assert result["action"] == "soft_deleted"
        assert result["entry"]["value"] == "Alice"
        assert result["entry"]["invalid_at"] is not None
        assert result["entry"]["status"] == "superseded"
        assert "backup_path" in result

        # Entry still exists in the file -- soft delete, not removal
        data = json.loads(memory_file.read_text())
        assert "name" in data["memories"]["user"]

    def test_forget_creates_backup_file(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        result = store.forget("user", "name")
        backup_path = Path(result["backup_path"])
        assert backup_path.exists()
        backup_data = json.loads(backup_path.read_text())
        assert "memories" in backup_data

    def test_forget_nonexistent_key_raises(self, store: MemoryStore):
        with pytest.raises(KeyError):
            store.forget("user", "nonexistent")

    def test_recall_nonexistent_key_raises(self, store: MemoryStore):
        with pytest.raises(KeyError):
            store.recall("user", "nonexistent")


# -- Access tracking ----------------------------------------------------------


class TestAccessTracking:
    def test_recall_increments_access_count(self, store: MemoryStore):
        store.remember("user", "name", "Alice")

        result1 = store.recall("user", "name")
        assert result1["entries"]["name"]["access_count"] == 1

        result2 = store.recall("user", "name")
        assert result2["entries"]["name"]["access_count"] == 2

    def test_recall_sets_last_accessed(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.recall("user", "name")
        assert result["entries"]["name"]["last_accessed"] is not None

    def test_recall_all_increments_each_entry(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "alice@example.com")

        store.recall("user")

        result = store.recall("user")
        for entry in result["entries"].values():
            assert entry["access_count"] == 2

    def test_search_increments_access_count(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.search("Alice")

        result = store.recall("user", "name")
        # recall adds +1, search already added +1 = 2
        assert result["entries"]["name"]["access_count"] == 2

    def test_access_count_persisted_to_file(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        store.recall("user", "name")

        data = json.loads(memory_file.read_text())
        assert data["memories"]["user"]["name"]["access_count"] == 1


# -- Search -------------------------------------------------------------------


class TestSearch:
    def test_search_by_value(self, store: MemoryStore):
        store.remember("user", "name", "Alice Wonderland")
        result = store.search("alice")
        assert len(result["results"]) == 1
        assert "value" in result["results"][0]["match_reason"]

    def test_search_by_key(self, store: MemoryStore):
        store.remember("user", "email", "test@example.com")
        result = store.search("email")
        assert len(result["results"]) == 1
        assert "key" in result["results"][0]["match_reason"]

    def test_search_by_tag(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.search("identity")
        assert len(result["results"]) == 1
        assert "tag" in result["results"][0]["match_reason"]

    def test_search_within_category(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("tools", "editor", "Alice-editor")
        result = store.search("alice", category="user")
        assert len(result["results"]) == 1
        assert result["results"][0]["category"] == "user"

    def test_search_no_results(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.search("nonexistent")
        assert len(result["results"]) == 0

    def test_search_case_insensitive(self, store: MemoryStore):
        store.remember("user", "name", "ALICE")
        result = store.search("alice")
        assert len(result["results"]) == 1


# -- Session start ------------------------------------------------------------


class TestSessionStart:
    def test_increments_session_count(self, store: MemoryStore):
        result1 = store.session_start()
        assert result1["session_count"] == 1
        result2 = store.session_start()
        assert result2["session_count"] == 2

    def test_returns_category_summary(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.session_start()
        assert result["categories"]["user"] == 1
        assert result["total"] == 1

    def test_session_count_persisted(self, store: MemoryStore, memory_file: Path):
        store.session_start()
        store.session_start()
        data = json.loads(memory_file.read_text())
        assert data["session_count"] == 2


# -- Atomic write -------------------------------------------------------------


class TestAtomicWrite:
    def test_file_exists_after_save(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        assert memory_file.exists()

    def test_file_contains_valid_json(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        data = json.loads(memory_file.read_text())
        assert data["memories"]["user"]["name"]["value"] == "Alice"

    def test_file_has_trailing_newline(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        content = memory_file.read_text()
        assert content.endswith("\n")

    def test_file_uses_two_space_indent(self, store: MemoryStore, memory_file: Path):
        store.remember("user", "name", "Alice")
        content = memory_file.read_text()
        # Check that the JSON uses 2-space indentation (not 4)
        assert '  "schema_version"' in content


# -- Validation ---------------------------------------------------------------


class TestValidation:
    def test_invalid_category_raises(self, store: MemoryStore):
        with pytest.raises(ValueError, match="Invalid category"):
            store.remember("invalid_cat", "key", "value")

    def test_importance_clamped_to_range(self, store: MemoryStore):
        result_low = store.remember("user", "low", "test", importance=0)
        assert result_low["entry"]["importance"] == 1

        result_high = store.remember("user", "high", "test", importance=99)
        assert result_high["entry"]["importance"] == 10


# -- Status -------------------------------------------------------------------


class TestStatus:
    def test_status_returns_counts(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("tools", "editor", "vim")
        result = store.status()
        assert result["categories"]["user"] == 1
        assert result["categories"]["tools"] == 1
        assert result["total"] == 2
        assert result["schema_version"] == SCHEMA_VERSION

    def test_status_returns_file_size(self, store: MemoryStore):
        result = store.status()
        assert "file_size" in result
        assert "B" in result["file_size"] or "KB" in result["file_size"]


# -- Export -------------------------------------------------------------------


class TestExport:
    def test_export_markdown(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.export("markdown")
        assert "# Memory Export" in result["content"]
        assert "Alice" in result["content"]
        assert "identity" in result["content"]

    def test_export_json(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        result = store.export("json")
        data = json.loads(result["content"])
        assert data["memories"]["user"]["name"]["value"] == "Alice"


# -- About me / about us -----------------------------------------------------


class TestAboutMe:
    def test_aggregates_user_entries(self, store: MemoryStore):
        store.remember("user", "name", "Alice")
        store.remember("user", "email", "alice@example.com")
        result = store.about_me()
        assert "Alice" in result["profile"]
        assert "alice@example.com" in result["profile"]

    def test_includes_user_facing_relationships(self, store: MemoryStore):
        store.remember("relationships", "style", "direct", tags=["user-facing"])
        result = store.about_me()
        assert "direct" in result["profile"]
        assert "Relationship Context" in result["profile"]

    def test_includes_user_preference_tools(self, store: MemoryStore):
        store.remember("tools", "editor", "vim", tags=["user-preference"])
        result = store.about_me()
        assert "vim" in result["profile"]
        assert "Tool Preferences" in result["profile"]

    def test_excludes_non_user_facing_relationships(self, store: MemoryStore):
        store.remember("relationships", "internal", "hidden", tags=["internal-only"])
        result = store.about_me()
        assert "hidden" not in result["profile"] or "Relationship Context" not in result["profile"]

    def test_empty_profile(self, store: MemoryStore):
        result = store.about_me()
        assert result["profile"] == "No user profile data found."


class TestAboutUs:
    def test_aggregates_relationships(self, store: MemoryStore):
        store.remember("relationships", "style", "collaborative")
        result = store.about_us()
        assert "collaborative" in result["profile"]
        assert "Our Relationship" in result["profile"]

    def test_includes_assistant_identity(self, store: MemoryStore):
        store.remember("assistant", "name", "Kael")
        result = store.about_us()
        assert "Kael" in result["profile"]
        assert "Assistant Identity" in result["profile"]

    def test_empty_profile(self, store: MemoryStore):
        result = store.about_us()
        assert result["profile"] == "No relationship data found."


# -- v2.0: remember with type and created_by ----------------------------------


class TestRememberV2:
    def test_remember_with_type(self, store: MemoryStore):
        result = store.remember("learnings", "tip", "Use fixtures", entry_type="pattern")
        assert result["action"] == "ADD"
        assert result["entry"]["type"] == "pattern"

    def test_remember_with_created_by(self, store: MemoryStore):
        result = store.remember("learnings", "tip", "Use fixtures", created_by="implementer")
        assert result["action"] == "ADD"
        assert result["entry"]["created_by"] == "implementer"

    def test_remember_with_type_and_created_by(self, store: MemoryStore):
        result = store.remember(
            "learnings",
            "decision-log",
            "Chose JSONL for observations",
            entry_type="decision",
            created_by="systems-architect",
        )
        assert result["entry"]["type"] == "decision"
        assert result["entry"]["created_by"] == "systems-architect"

    def test_remember_type_defaults_to_none(self, store: MemoryStore):
        result = store.remember("user", "name", "Alice")
        assert result["entry"]["type"] is None
        assert result["entry"]["created_by"] is None

    def test_remember_update_preserves_type_when_not_provided(self, store: MemoryStore):
        store.remember("learnings", "tip", "Use fixtures", entry_type="pattern")
        result = store.remember("learnings", "tip", "Use fixtures v2")
        assert result["action"] == "UPDATE"
        assert result["entry"]["type"] == "pattern"

    def test_remember_update_overwrites_type_when_provided(self, store: MemoryStore):
        store.remember("learnings", "tip", "Use fixtures", entry_type="pattern")
        result = store.remember("learnings", "tip", "Use fixtures v2", entry_type="convention")
        assert result["action"] == "UPDATE"
        assert result["entry"]["type"] == "convention"

    def test_remember_update_preserves_created_by_when_not_provided(self, store: MemoryStore):
        store.remember("learnings", "tip", "Use fixtures", created_by="implementer")
        result = store.remember("learnings", "tip", "Use fixtures v2")
        assert result["action"] == "UPDATE"
        assert result["entry"]["created_by"] == "implementer"

    def test_remember_invalid_type_stored_as_is(self, store: MemoryStore):
        """type is not validated -- just a string field."""
        result = store.remember("user", "name", "Alice", entry_type="nonstandard")
        assert result["entry"]["type"] == "nonstandard"


# -- v2.0: search with since and type filters ---------------------------------


class TestSearchV2:
    def test_search_with_since_filter(self, store: MemoryStore, memory_file: Path):
        # Create entries with specific timestamps via direct file manipulation
        data = json.loads(memory_file.read_text())
        memories = data["memories"]
        memories["learnings"]["old-tip"] = {
            "value": "python old tip",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "tags": ["python"],
            "confidence": None,
            "importance": 5,
            "source": {"type": "session", "detail": None},
            "access_count": 0,
            "last_accessed": None,
            "status": "active",
            "links": [],
            "summary": "python old tip",
            "valid_at": "2026-01-01T00:00:00Z",
            "invalid_at": None,
            "type": None,
            "created_by": None,
        }
        memories["learnings"]["new-tip"] = {
            "value": "python new tip",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "tags": ["python"],
            "confidence": None,
            "importance": 5,
            "source": {"type": "session", "detail": None},
            "access_count": 0,
            "last_accessed": None,
            "status": "active",
            "links": [],
            "summary": "python new tip",
            "valid_at": "2026-04-01T00:00:00Z",
            "invalid_at": None,
            "type": None,
            "created_by": None,
        }
        memory_file.write_text(json.dumps(data, indent=2) + "\n")

        store2 = MemoryStore(memory_file)
        result = store2.search("python", since="2026-03-01T00:00:00Z")
        keys = {r["key"] for r in result["results"]}
        assert "new-tip" in keys
        assert "old-tip" not in keys

    def test_search_with_type_filter(self, store: MemoryStore):
        store.remember("learnings", "tip-a", "Use fixtures", entry_type="pattern")
        store.remember("learnings", "tip-b", "Use parametrize", entry_type="gotcha", force=True)
        result = store.search("use", entry_type="pattern")
        keys = {r["key"] for r in result["results"]}
        assert "tip-a" in keys
        assert "tip-b" not in keys

    def test_search_with_since_and_type(self, store: MemoryStore, memory_file: Path):
        data = json.loads(memory_file.read_text())
        memories = data["memories"]
        memories["learnings"]["old-pattern"] = {
            "value": "python old pattern",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "tags": ["python"],
            "confidence": None,
            "importance": 5,
            "source": {"type": "session", "detail": None},
            "access_count": 0,
            "last_accessed": None,
            "status": "active",
            "links": [],
            "summary": "python old pattern",
            "valid_at": "2026-01-01T00:00:00Z",
            "invalid_at": None,
            "type": "pattern",
            "created_by": None,
        }
        memories["learnings"]["new-pattern"] = {
            "value": "python new pattern",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "tags": ["python"],
            "confidence": None,
            "importance": 5,
            "source": {"type": "session", "detail": None},
            "access_count": 0,
            "last_accessed": None,
            "status": "active",
            "links": [],
            "summary": "python new pattern",
            "valid_at": "2026-04-01T00:00:00Z",
            "invalid_at": None,
            "type": "pattern",
            "created_by": None,
        }
        memories["learnings"]["new-gotcha"] = {
            "value": "python new gotcha",
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "tags": ["python"],
            "confidence": None,
            "importance": 5,
            "source": {"type": "session", "detail": None},
            "access_count": 0,
            "last_accessed": None,
            "status": "active",
            "links": [],
            "summary": "python new gotcha",
            "valid_at": "2026-04-01T00:00:00Z",
            "invalid_at": None,
            "type": "gotcha",
            "created_by": None,
        }
        memory_file.write_text(json.dumps(data, indent=2) + "\n")

        store2 = MemoryStore(memory_file)
        result = store2.search("python", since="2026-03-01T00:00:00Z", entry_type="pattern")
        keys = {r["key"] for r in result["results"]}
        assert "new-pattern" in keys
        assert "old-pattern" not in keys
        assert "new-gotcha" not in keys

    def test_search_no_type_filter_matches_all(self, store: MemoryStore):
        store.remember("learnings", "tip-a", "Use fixtures", entry_type="pattern")
        store.remember("learnings", "tip-b", "Use parametrize", entry_type=None, force=True)
        result = store.search("use")
        keys = {r["key"] for r in result["results"]}
        assert "tip-a" in keys
        assert "tip-b" in keys

    def test_search_with_provenance_source_fields(self, store: MemoryStore):
        """Entries created with type and created_by are retrievable."""
        store.remember(
            "learnings",
            "decision-1",
            "Chose JSONL format",
            entry_type="decision",
            created_by="architect",
        )
        result = store.recall("learnings", "decision-1")
        entry = result["entries"]["decision-1"]
        assert entry["type"] == "decision"
        assert entry["created_by"] == "architect"
