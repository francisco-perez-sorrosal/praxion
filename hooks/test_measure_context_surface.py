"""Tests for hooks/measure_context_surface.py — SessionStart observability hook.

Verifies measurement correctness, graceful degradation, and the path-scope
filter that distinguishes always-loaded rules from path-scoped ones.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
HOOK_SCRIPT_PATH = HOOKS_DIR / "measure_context_surface.py"


def _load_module():
    """Load measure_context_surface.py as a module inside a test body."""
    spec = importlib.util.spec_from_file_location(
        "measure_context_surface", HOOK_SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Frontmatter detection
# ---------------------------------------------------------------------------


class TestFrontmatterDetection:
    def test_inline_paths_returns_true(self):
        m = _load_module()
        content = '---\npaths: ["docs/**/*.md"]\n---\n\n## Rule\n'
        assert m._has_paths_frontmatter(content) is True

    def test_block_style_paths_returns_true(self):
        m = _load_module()
        content = '---\npaths:\n  - "docs/**"\n  - "src/**"\n---\n\n## Rule\n'
        assert m._has_paths_frontmatter(content) is True

    def test_no_frontmatter_returns_false(self):
        m = _load_module()
        content = "## Rule\n\nBody.\n"
        assert m._has_paths_frontmatter(content) is False

    def test_frontmatter_without_paths_returns_false(self):
        m = _load_module()
        content = "---\nname: foo\nowner: bar\n---\n\n## Rule\n"
        assert m._has_paths_frontmatter(content) is False

    def test_paths_appearing_in_body_does_not_count(self):
        """Only frontmatter `paths:` triggers — body mentions do not."""
        m = _load_module()
        content = "## Rule\n\nDocument with `paths:` mentioned in body.\n"
        assert m._has_paths_frontmatter(content) is False


# ---------------------------------------------------------------------------
# Surface collection
# ---------------------------------------------------------------------------


class TestCollectAlwaysLoaded:
    def test_counts_unscoped_rules_skips_scoped_ones(self, tmp_path: Path):
        m = _load_module()

        rules_dir = tmp_path / "rules"
        (rules_dir / "swe").mkdir(parents=True)

        (rules_dir / "always-loaded.md").write_text(
            "## Always Loaded\n\nNo paths frontmatter.\n", encoding="utf-8"
        )
        (rules_dir / "swe" / "path-scoped.md").write_text(
            '---\npaths: ["src/**"]\n---\n\n## Path Scoped\n', encoding="utf-8"
        )
        (rules_dir / "README.md").write_text(
            "# Rules\n\nDirectory README — not loaded.\n", encoding="utf-8"
        )

        project_md = tmp_path / "CLAUDE.md"
        project_md.write_text("# Project\n", encoding="utf-8")
        global_md = tmp_path / "global_CLAUDE.md"
        global_md.write_text("# Global\n", encoding="utf-8")

        total, records = m._collect_always_loaded(project_md, global_md, rules_dir)

        kinds = {r["type"] for r in records}
        assert "claude_md_project" in kinds
        assert "claude_md_global" in kinds
        assert "rule" in kinds

        rule_paths = [r["path"] for r in records if r["type"] == "rule"]
        assert any("always-loaded.md" in p for p in rule_paths)
        assert not any("path-scoped.md" in p for p in rule_paths)
        assert not any("README.md" in p for p in rule_paths)

        # Total bytes equals the sum of records' bytes — sanity check.
        assert total == sum(r["bytes"] for r in records)

    def test_missing_files_skipped_silently(self, tmp_path: Path):
        m = _load_module()
        missing_project = tmp_path / "does-not-exist.md"
        missing_global = tmp_path / "also-missing.md"
        missing_rules = tmp_path / "no-rules-dir"

        total, records = m._collect_always_loaded(
            missing_project, missing_global, missing_rules
        )

        assert total == 0
        assert records == []

    def test_unicode_bytes_counted_correctly(self, tmp_path: Path):
        """Multi-byte chars (em dash, accented vowels) count as actual bytes,
        not character count, so token estimates stay realistic."""
        m = _load_module()

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        # 4 ASCII chars + em dash (3 bytes in UTF-8) = 7 bytes total in body
        unicode_md = rules_dir / "unicode.md"
        unicode_md.write_text("hi — there\n", encoding="utf-8")

        project_md = tmp_path / "p.md"
        project_md.write_text("", encoding="utf-8")
        global_md = tmp_path / "g.md"
        global_md.write_text("", encoding="utf-8")

        total, records = m._collect_always_loaded(project_md, global_md, rules_dir)
        rule_record = next(r for r in records if r["type"] == "rule")
        # "hi — there\n" → 13 bytes: 'hi ' (3) + em-dash (3) + ' there\n' (7).
        # Char count is 11; byte count is 13. The hook reports bytes, not chars,
        # which keeps token estimates honest for non-ASCII content.
        assert rule_record["bytes"] == 13


# ---------------------------------------------------------------------------
# End-to-end: stdin payload → observations.jsonl row
# ---------------------------------------------------------------------------


class TestMainEntry:
    def _stub_stdin(self, payload: dict, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "stdin", _StringIO(json.dumps(payload)))

    def test_writes_observation_on_session_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()

        # Set up a project tree with .ai-state/ so the hook does not bail.
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project\n", encoding="utf-8")

        # Point the global rules dir at an empty path so collection is bounded.
        monkeypatch.setattr(m, "_GLOBAL_RULES_DIR", tmp_path / "no-rules-dir")
        monkeypatch.setattr(m, "_GLOBAL_CLAUDE_MD", tmp_path / "no-global.md")

        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "test-session-id",
            "agent_type": "main",
        }
        self._stub_stdin(payload, monkeypatch)

        m.main()

        obs_path = ai_state / "observations.jsonl"
        assert obs_path.exists()
        line = obs_path.read_text(encoding="utf-8").strip()
        observation = json.loads(line)
        assert observation["event_type"] == "context_surface_measurement"
        assert observation["session_id"] == "test-session-id"
        assert "Always-loaded surface" in observation["summary"]
        assert any("CLAUDE.md" in p for p in observation["file_paths"])

    def test_skips_when_ai_state_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        # No .ai-state/ created.
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()  # Should not raise.
        # Nothing written.
        assert not (tmp_path / ".ai-state" / "observations.jsonl").exists()

    def test_skips_non_session_start_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        payload = {
            "hook_event_name": "Stop",  # Not SessionStart
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()
        assert not (ai_state / "observations.jsonl").exists()

    def test_disabled_by_observability_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        monkeypatch.setenv("PRAXION_DISABLE_OBSERVABILITY", "1")
        payload = {
            "hook_event_name": "SessionStart",
            "cwd": str(tmp_path),
            "session_id": "x",
        }
        self._stub_stdin(payload, monkeypatch)
        m.main()
        assert not (ai_state / "observations.jsonl").exists()

    def test_malformed_stdin_does_not_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        m = _load_module()
        monkeypatch.setattr(sys, "stdin", _StringIO("not-json{"))
        m.main()  # No raise = pass.


class _StringIO:
    """Minimal stdin stub — sys.stdin.read() returns the captured string."""

    def __init__(self, text: str) -> None:
        self._text = text

    def read(self, *_args: object) -> str:
        return self._text
