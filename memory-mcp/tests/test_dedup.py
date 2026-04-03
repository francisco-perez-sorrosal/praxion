"""Tests for deduplication-on-write in MemoryStore.remember()."""

from __future__ import annotations

from pathlib import Path

import pytest  # noqa: TC002

from memory_mcp.store import MemoryStore

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def memory_file(tmp_path: Path) -> Path:
    return tmp_path / "memory.json"


@pytest.fixture
def store(memory_file: Path) -> MemoryStore:
    return MemoryStore(memory_file)


# -- No overlap: ADD proceeds normally ----------------------------------------


class TestDedupNoOverlap:
    def test_new_entry_no_overlap_proceeds_as_add(self, store: MemoryStore):
        result = store.remember("user", "name", "Alice", tags=["identity"])
        assert result["action"] == "ADD"
        assert result["entry"]["value"] == "Alice"

    def test_unrelated_entries_no_candidates(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=["identity"])
        result = store.remember("user", "email", "alice@example.com", tags=["contact"])
        assert result["action"] == "ADD"
        assert result["entry"]["value"] == "alice@example.com"

    def test_single_tag_overlap_not_enough(self, store: MemoryStore):
        """One shared tag is below the MIN_TAG_OVERLAP_FOR_CANDIDATE threshold."""
        store.remember("user", "name", "Alice", tags=["identity", "personal"])
        result = store.remember("user", "email", "alice@example.com", tags=["identity", "contact"])
        # Only 1 tag overlap ("identity") -- below threshold of 2
        assert result["action"] == "ADD"


# -- Tag overlap: candidates returned -----------------------------------------


class TestDedupTagOverlap:
    def test_two_tag_overlap_returns_candidates(self, store: MemoryStore):
        store.remember(
            "user",
            "name",
            "Alice Wonderland",
            tags=["identity", "personal", "profile"],
        )
        result = store.remember(
            "user",
            "nickname",
            "Ally",
            tags=["identity", "personal", "shortname"],
        )
        assert result["action"] == "candidates"
        assert len(result["candidates"]) >= 1
        candidate = result["candidates"][0]
        assert candidate["key"] == "name"
        assert candidate["category"] == "user"
        assert "tag_overlap" in candidate["match_reason"]

    def test_three_tag_overlap_recommends_update(self, store: MemoryStore):
        store.remember(
            "learnings",
            "python-packaging",
            "Use hatchling for builds",
            tags=["python", "packaging", "hatchling", "build"],
        )
        result = store.remember(
            "learnings",
            "hatch-build-system",
            "Hatchling is the recommended build backend",
            tags=["python", "packaging", "hatchling"],
        )
        assert result["action"] == "candidates"
        assert result["recommendation"] == "UPDATE"

    def test_candidates_include_entry_details(self, store: MemoryStore):
        store.remember(
            "tools",
            "editor",
            "neovim",
            tags=["development", "coding", "preference"],
        )
        result = store.remember(
            "tools",
            "code-editor",
            "vscode",
            tags=["development", "coding", "ide"],
        )
        assert result["action"] == "candidates"
        candidate = result["candidates"][0]
        assert candidate["value"] == "neovim"
        assert candidate["tags"] == ["coding", "development", "preference"]
        assert "tag_overlap" in candidate


# -- Value overlap: candidates returned ---------------------------------------


class TestDedupValueOverlap:
    def test_high_value_similarity_returns_candidates(self, store: MemoryStore):
        store.remember(
            "learnings",
            "git-workflow",
            "Always use atomic commits with descriptive messages",
            tags=["git"],
        )
        result = store.remember(
            "learnings",
            "commit-style",
            "Use atomic commits with clear descriptive messages",
            tags=["vcs"],
        )
        assert result["action"] == "candidates"
        assert len(result["candidates"]) >= 1
        assert "value_similarity" in result["candidates"][0]["match_reason"]

    def test_near_exact_value_recommends_noop(self, store: MemoryStore):
        store.remember(
            "project",
            "language",
            "The project uses Python for backend",
            tags=["tech"],
        )
        result = store.remember(
            "project",
            "main-language",
            "The project uses Python for backend",
            tags=["stack"],
        )
        assert result["action"] == "candidates"
        assert result["recommendation"] == "NOOP"


# -- Exact key match: UPDATE (no dedup) ---------------------------------------


class TestDedupExactKeyMatch:
    def test_exact_key_match_updates_directly(self, store: MemoryStore):
        store.remember(
            "user",
            "name",
            "Alice",
            tags=["identity", "personal", "profile"],
        )
        result = store.remember(
            "user",
            "name",
            "Bob",
            tags=["identity", "personal", "profile"],
        )
        assert result["action"] == "UPDATE"
        assert result["entry"]["value"] == "Bob"

    def test_exact_key_match_never_returns_candidates(self, store: MemoryStore):
        store.remember(
            "learnings",
            "pattern",
            "Use dependency injection",
            tags=["design", "patterns", "architecture"],
        )
        result = store.remember(
            "learnings",
            "pattern",
            "Prefer dependency injection over service locator",
            tags=["design", "patterns", "architecture"],
        )
        assert result["action"] == "UPDATE"
        assert "candidates" not in result


# -- Force bypass -------------------------------------------------------------


class TestDedupForceBypass:
    def test_force_bypasses_dedup_check(self, store: MemoryStore):
        store.remember(
            "user",
            "name",
            "Alice Wonderland",
            tags=["identity", "personal", "profile"],
        )
        result = store.remember(
            "user",
            "nickname",
            "Ally",
            tags=["identity", "personal", "shortname"],
            force=True,
        )
        assert result["action"] == "ADD"
        assert result["entry"]["value"] == "Ally"

    def test_force_allows_similar_value_entry(self, store: MemoryStore):
        store.remember(
            "learnings",
            "git-workflow",
            "Always use atomic commits with descriptive messages",
            tags=["git"],
        )
        result = store.remember(
            "learnings",
            "commit-style",
            "Use atomic commits with clear descriptive messages",
            tags=["vcs"],
            force=True,
        )
        assert result["action"] == "ADD"

    def test_force_with_existing_key_still_updates(self, store: MemoryStore):
        """Force does not change behavior for exact key matches -- always UPDATE."""
        store.remember("user", "name", "Alice")
        result = store.remember("user", "name", "Bob", force=True)
        assert result["action"] == "UPDATE"
        assert result["entry"]["value"] == "Bob"


# -- Broad (cross-category) dedup --------------------------------------------


class TestDedupBroad:
    def test_broad_finds_candidates_across_categories(self, store: MemoryStore):
        store.remember(
            "learnings",
            "python-patterns",
            "Use dataclasses for value objects",
            tags=["python", "patterns", "dataclass"],
        )
        result = store.remember(
            "project",
            "coding-style",
            "Prefer dataclasses for simple value objects",
            tags=["python", "patterns", "style"],
            broad=True,
        )
        assert result["action"] == "candidates"
        assert any(c["category"] == "learnings" for c in result["candidates"])

    def test_broad_false_does_not_cross_categories(self, store: MemoryStore):
        store.remember(
            "learnings",
            "python-patterns",
            "Use dataclasses for value objects",
            tags=["python", "patterns", "dataclass"],
        )
        # Same entry but in a different category -- without broad, no candidates
        result = store.remember(
            "project",
            "coding-style",
            "Prefer dataclasses for simple value objects",
            tags=["python", "patterns", "style"],
            broad=False,
        )
        assert result["action"] == "ADD"

    def test_broad_with_force_bypasses(self, store: MemoryStore):
        store.remember(
            "learnings",
            "tip",
            "Use immutable data structures",
            tags=["functional", "immutable", "patterns"],
        )
        result = store.remember(
            "project",
            "convention",
            "Prefer immutable data structures",
            tags=["functional", "immutable", "coding"],
            broad=True,
            force=True,
        )
        assert result["action"] == "ADD"


# -- Edge cases ---------------------------------------------------------------


class TestDedupEdgeCases:
    def test_empty_store_no_candidates(self, store: MemoryStore):
        result = store.remember(
            "user",
            "name",
            "Alice",
            tags=["identity", "personal"],
        )
        assert result["action"] == "ADD"

    def test_empty_tags_no_tag_overlap(self, store: MemoryStore):
        store.remember("user", "name", "Alice", tags=[])
        result = store.remember("user", "email", "alice@example.com", tags=[])
        assert result["action"] == "ADD"

    def test_short_values_no_false_positives(self, store: MemoryStore):
        """Very short values should not trigger value similarity."""
        store.remember("user", "name", "Al", tags=["name"])
        result = store.remember("user", "nick", "Al", tags=["nick"])
        # "Al" has no significant words (< MIN_WORD_LENGTH=3), so no value match
        assert result["action"] == "ADD"

    def test_recommendation_add_for_moderate_overlap(self, store: MemoryStore):
        """Two-tag overlap but low value similarity should recommend ADD."""
        store.remember(
            "tools",
            "editor",
            "neovim for terminal editing",
            tags=["development", "coding", "terminal"],
        )
        result = store.remember(
            "tools",
            "debugger",
            "lldb for native debugging",
            tags=["development", "coding", "debugging"],
        )
        assert result["action"] == "candidates"
        assert result["recommendation"] == "ADD"
