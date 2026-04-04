"""Tests for reconcile_ai_state.py — memory, observations, and ADR reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

# Import the script as a module
import importlib.util

_SCRIPT_PATH = Path(__file__).resolve().parent / "reconcile_ai_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reconcile_ai_state", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reconcile = _load_module()


# -- memory.json tests --------------------------------------------------------


class TestReconcileMemory:
    def _make_memory(
        self, entries: dict[str, dict[str, dict]], session_count: int = 1
    ) -> str:
        return json.dumps(
            {
                "schema_version": "2.0",
                "session_count": session_count,
                "memories": entries,
            }
        )

    def test_union_of_unique_entries(self):
        """Entries unique to each side are both preserved."""
        ours = self._make_memory(
            {
                "learnings": {
                    "key_a": {"value": "A", "updated_at": "2026-01-01T00:00:00Z"}
                }
            }
        )
        theirs = self._make_memory(
            {
                "learnings": {
                    "key_b": {"value": "B", "updated_at": "2026-01-01T00:00:00Z"}
                }
            }
        )
        result = reconcile.reconcile_memory(ours, theirs)
        entries = result["memories"]["learnings"]
        assert "key_a" in entries
        assert "key_b" in entries

    def test_duplicate_key_newer_wins(self):
        """When both sides have the same key, updated_at wins."""
        ours = self._make_memory(
            {
                "learnings": {
                    "shared": {
                        "value": "old version",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                }
            }
        )
        theirs = self._make_memory(
            {
                "learnings": {
                    "shared": {
                        "value": "new version",
                        "updated_at": "2026-02-01T00:00:00Z",
                    }
                }
            }
        )
        result = reconcile.reconcile_memory(ours, theirs)
        assert result["memories"]["learnings"]["shared"]["value"] == "new version"

    def test_session_counts_summed(self):
        """Session counts from both sides are summed."""
        ours = self._make_memory({}, session_count=3)
        theirs = self._make_memory({}, session_count=5)
        result = reconcile.reconcile_memory(ours, theirs)
        assert result["session_count"] == 8

    def test_schema_version_keeps_higher(self):
        """The higher schema version is preserved."""
        ours = json.dumps({"schema_version": "2.0", "session_count": 0, "memories": {}})
        theirs = json.dumps(
            {"schema_version": "3.0", "session_count": 0, "memories": {}}
        )
        result = reconcile.reconcile_memory(ours, theirs)
        assert result["schema_version"] == "3.0"

    def test_disjoint_categories_merged(self):
        """Categories unique to each side are both preserved."""
        ours = self._make_memory(
            {
                "user": {
                    "pref": {"value": "dark mode", "updated_at": "2026-01-01T00:00:00Z"}
                }
            }
        )
        theirs = self._make_memory(
            {
                "project": {
                    "arch": {"value": "monorepo", "updated_at": "2026-01-01T00:00:00Z"}
                }
            }
        )
        result = reconcile.reconcile_memory(ours, theirs)
        assert "user" in result["memories"]
        assert "project" in result["memories"]

    def test_empty_ours_keeps_theirs(self):
        """When ours is empty, all theirs entries are kept."""
        ours = self._make_memory({})
        theirs = self._make_memory(
            {"learnings": {"key": {"value": "V", "updated_at": "2026-01-01T00:00:00Z"}}}
        )
        result = reconcile.reconcile_memory(ours, theirs)
        assert "key" in result["memories"]["learnings"]


# -- observations.jsonl tests -------------------------------------------------


class TestReconcileObservations:
    def _make_obs(
        self, timestamp: str, session: str, event: str, tool: str = ""
    ) -> str:
        return json.dumps(
            {
                "timestamp": timestamp,
                "session_id": session,
                "event_type": event,
                "tool_name": tool,
            }
        )

    def test_dedup_identical_lines(self):
        """Identical observations from both sides produce one entry."""
        line = self._make_obs("2026-01-01T00:00:00Z", "s1", "tool_use", "Bash")
        ours = line + "\n"
        theirs = line + "\n"
        result = reconcile.reconcile_observations(ours, theirs)
        lines = [line for line in result.strip().splitlines() if line.strip()]
        assert len(lines) == 1

    def test_unique_lines_merged(self):
        """Lines unique to each side are both preserved."""
        ours = self._make_obs("2026-01-01T00:00:00Z", "s1", "tool_use", "Bash") + "\n"
        theirs = self._make_obs("2026-01-02T00:00:00Z", "s2", "session_stop") + "\n"
        result = reconcile.reconcile_observations(ours, theirs)
        lines = [line for line in result.strip().splitlines() if line.strip()]
        assert len(lines) == 2

    def test_sorted_by_timestamp(self):
        """Merged output is sorted by timestamp."""
        later = self._make_obs("2026-02-01T00:00:00Z", "s1", "tool_use")
        earlier = self._make_obs("2026-01-01T00:00:00Z", "s2", "tool_use")
        ours = later + "\n"
        theirs = earlier + "\n"
        result = reconcile.reconcile_observations(ours, theirs)
        lines = result.strip().splitlines()
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["timestamp"] < second["timestamp"]

    def test_malformed_lines_skipped(self):
        """Invalid JSON lines are silently skipped."""
        valid = self._make_obs("2026-01-01T00:00:00Z", "s1", "tool_use")
        ours = valid + "\nnot json\n"
        theirs = ""
        result = reconcile.reconcile_observations(ours, theirs)
        lines = [line for line in result.strip().splitlines() if line.strip()]
        assert len(lines) == 1

    def test_empty_inputs_produce_empty_output(self):
        """Both sides empty produces empty string."""
        result = reconcile.reconcile_observations("", "")
        assert result == ""


# -- ADR number reconciliation tests ------------------------------------------


class TestReconcileADRNumbers:
    def _make_adr(self, decisions_dir: Path, num: int, slug: str, date: str) -> Path:
        path = decisions_dir / f"{num:03d}-{slug}.md"
        path.write_text(
            f"---\nid: dec-{num:03d}\ntitle: {slug}\nstatus: accepted\n"
            f"category: architectural\ndate: {date}\n"
            f"summary: Test decision\ntags: [test]\nmade_by: agent\n---\n\n"
            f"## Context\n\nTest.\n",
            encoding="utf-8",
        )
        return path

    def test_no_duplicates_no_changes(self, tmp_path: Path):
        """No duplicate numbers means no renumbering."""
        decisions_dir = tmp_path / ".ai-state" / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "first", "2026-01-01")
        self._make_adr(decisions_dir, 2, "second", "2026-01-02")

        # Monkey-patch the module's DECISIONS_DIR
        original = reconcile.DECISIONS_DIR
        reconcile.DECISIONS_DIR = decisions_dir
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original

        assert changed is False
        assert (decisions_dir / "001-first.md").exists()
        assert (decisions_dir / "002-second.md").exists()

    def test_duplicate_numbers_renumbered(self, tmp_path: Path):
        """Duplicate NNN prefixes get renumbered to the next available."""
        decisions_dir = tmp_path / ".ai-state" / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "alpha", "2026-01-01")
        self._make_adr(decisions_dir, 1, "beta", "2026-01-02")  # duplicate!

        original = reconcile.DECISIONS_DIR
        reconcile.DECISIONS_DIR = decisions_dir
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original

        assert changed is True
        # First stays as 001, second renumbered to 002
        assert (decisions_dir / "001-alpha.md").exists()
        assert (decisions_dir / "002-beta.md").exists()
        assert not (decisions_dir / "001-beta.md").exists()

        # Verify the id field was updated in the renumbered file
        content = (decisions_dir / "002-beta.md").read_text()
        assert "id: dec-002" in content

    def test_renumbering_avoids_existing_numbers(self, tmp_path: Path):
        """Renumbered ADRs skip numbers that already exist."""
        decisions_dir = tmp_path / ".ai-state" / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "alpha", "2026-01-01")
        self._make_adr(decisions_dir, 1, "beta", "2026-01-02")  # duplicate!
        self._make_adr(decisions_dir, 2, "gamma", "2026-01-03")  # 002 already taken

        original = reconcile.DECISIONS_DIR
        reconcile.DECISIONS_DIR = decisions_dir
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original

        assert changed is True
        # beta should get 003 (since 002 is taken by gamma)
        assert (decisions_dir / "003-beta.md").exists()
        content = (decisions_dir / "003-beta.md").read_text()
        assert "id: dec-003" in content


# -- Conflict detection tests -------------------------------------------------


class TestConflictDetection:
    def test_detects_conflict_markers(self, tmp_path: Path):
        """Files with <<<<<<< and >>>>>>> are detected as conflicted."""
        f = tmp_path / "test.json"
        f.write_text('<<<<<<< HEAD\n{"a": 1}\n=======\n{"b": 2}\n>>>>>>> branch\n')
        assert reconcile.is_conflicted(f) is True

    def test_clean_file_not_conflicted(self, tmp_path: Path):
        """Normal files are not detected as conflicted."""
        f = tmp_path / "test.json"
        f.write_text('{"a": 1}\n')
        assert reconcile.is_conflicted(f) is False

    def test_missing_file_not_conflicted(self, tmp_path: Path):
        """Missing files are not detected as conflicted."""
        assert reconcile.is_conflicted(tmp_path / "nope.json") is False
