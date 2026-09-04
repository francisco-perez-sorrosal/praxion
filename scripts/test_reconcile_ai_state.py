"""Tests for reconcile_ai_state.py — observations and ADR reconciliation."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "reconcile_ai_state.py"
_LIVE_DECISIONS_DIR = Path(__file__).resolve().parent.parent / ".ai-state" / "decisions"


def _load_module():
    spec = importlib.util.spec_from_file_location("reconcile_ai_state", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reconcile = _load_module()


def _live_decisions_fingerprint() -> list[tuple[str, int, int]]:
    """Name, size and mtime of every file in the *live* .ai-state/decisions/."""
    if not _LIVE_DECISIONS_DIR.is_dir():
        return []
    return sorted(
        (path.name, path.stat().st_size, path.stat().st_mtime_ns)
        for path in _LIVE_DECISIONS_DIR.iterdir()
        if path.is_file()
    )


@pytest.fixture(autouse=True)
def _live_repository_is_never_mutated():
    """Fail any test in this module that writes into the live repository.

    `main()` rebinds its own path constants through `apply_repo_root()`, so a
    test that monkeypatches DECISIONS_DIR but leaves the resolver to find the
    real repo has those patches silently overwritten and regenerates the
    *committed* .ai-state/decisions/DECISIONS_INDEX.md. A single run hides it:
    the index regenerates byte-identically until an unrelated ADR-shaped file
    appears in the directory, at which point every subsequent run appends a
    bogus row. Comparing mtime as well as size is deliberate -- a byte-identical
    rewrite is still a write to the live tree, and it is the only tell available
    before the damage becomes visible.

    Snapshot-and-compare converts that silent mutation into an immediate,
    named failure for any future test that reintroduces it.
    """
    before = _live_decisions_fingerprint()
    yield
    assert _live_decisions_fingerprint() == before, (
        f"this test mutated the live {_LIVE_DECISIONS_DIR}. Point the code under "
        "test at a tmp_path tree: main() calls apply_repo_root(), which overwrites "
        "monkeypatched path constants, so pass --repo-root <tmp_path> in argv."
    )


def _make_completed_process(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


# -- observations.jsonl tests -------------------------------------------------


class TestReconcileObservations:
    def _make_obs(self, timestamp: str, session: str, event: str, tool: str = "") -> str:
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

        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts

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

        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts

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


# -- observations.jsonl: blank-line skip ------------------------------------------


class TestReconcileObservationsBlankLines:
    def test_whitespace_only_lines_skipped(self):
        """Whitespace-only lines sandwiched between valid JSON lines are ignored."""
        obs_a = json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "event_type": "tool_use",
                "tool_name": "Bash",
            }
        )
        obs_b = json.dumps(
            {
                "timestamp": "2026-01-02T00:00:00Z",
                "session_id": "s2",
                "event_type": "session_stop",
                "tool_name": "",
            }
        )
        # Blank line between two valid lines — strip() won't remove it
        ours = obs_a + "\n   \n" + obs_b + "\n"
        theirs = ""
        result = reconcile.reconcile_observations(ours, theirs)
        lines = [ln for ln in result.strip().splitlines() if ln.strip()]
        assert len(lines) == 2


# -- has_drafts_directory_changed_in_merge ----------------------------------------


class TestHasDraftsDirectoryChangedInMerge:
    def test_returns_false_when_git_command_fails(self):
        """A failing git diff-tree returns False (fail-safe behaviour)."""
        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(returncode=1, stdout="")
        try:
            result = reconcile.has_drafts_directory_changed_in_merge()
        finally:
            reconcile.git = original_git
        assert result is False

    def test_returns_true_when_draft_md_changed(self):
        """A changed .md file under drafts/ returns True."""
        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(
            returncode=0,
            stdout=".ai-state/decisions/drafts/20260101-user-main-my-decision.md\n",
        )
        try:
            result = reconcile.has_drafts_directory_changed_in_merge()
        finally:
            reconcile.git = original_git
        assert result is True

    def test_claude_md_in_drafts_does_not_trigger(self):
        """A CLAUDE.md file inside drafts/ is excluded from the draft signal."""
        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(
            returncode=0,
            stdout=".ai-state/decisions/drafts/CLAUDE.md\n",
        )
        try:
            result = reconcile.has_drafts_directory_changed_in_merge()
        finally:
            reconcile.git = original_git
        assert result is False

    def test_non_draft_md_does_not_trigger(self):
        """Changed .md files outside drafts/ do not trigger the draft signal."""
        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(
            returncode=0,
            stdout=".ai-state/decisions/001-some-adr.md\n",
        )
        try:
            result = reconcile.has_drafts_directory_changed_in_merge()
        finally:
            reconcile.git = original_git
        assert result is False


# -- reconcile_adr_numbers: no decisions directory --------------------------------


class TestReconcileAdrNumbersNoDir:
    def test_returns_false_when_decisions_dir_absent(self, tmp_path: Path):
        """When the decisions directory does not exist, no renumbering occurs."""
        absent_dir = tmp_path / "decisions_nonexistent"
        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        reconcile.DECISIONS_DIR = absent_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        try:
            result = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts
        assert result is False

    def test_defers_to_finalize_when_drafts_present(self, tmp_path: Path):
        """When draft ADRs changed in merge, renumbering is deferred and returns False."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: True
        try:
            result = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts
        assert result is False


# -- reconcile_file orchestrator --------------------------------------------------


class TestReconcileFile:
    def test_returns_false_when_file_absent(self, tmp_path: Path):
        """reconcile_file returns False when the target file does not exist."""
        result = reconcile.reconcile_file(
            tmp_path / "ghost.jsonl",
            ".ai-state/ghost.jsonl",
            reconcile.reconcile_observations,
            write_fn=reconcile.write_text_file,
        )
        assert result is False

    def test_conflicted_file_with_write_fn_uses_custom_writer(self, tmp_path: Path):
        """reconcile_file uses write_fn when provided (e.g. for text files)."""
        f = tmp_path / "observations.jsonl"
        f.write_text(
            '<<<<<<< HEAD\n{"timestamp":"a"}\n=======\n{"timestamp":"b"}\n>>>>>>> branch\n'
        )
        obs_a = json.dumps(
            {"timestamp": "2026-01-01T00:00:00Z", "session_id": "s1", "event_type": "e"}
        )
        obs_b = json.dumps(
            {"timestamp": "2026-02-01T00:00:00Z", "session_id": "s2", "event_type": "e"}
        )

        def fake_git(*args: str) -> subprocess.CompletedProcess[str]:
            if args[0] == "show" and ":2:" in args[1]:
                return _make_completed_process(0, stdout=obs_a + "\n")
            if args[0] == "show" and ":3:" in args[1]:
                return _make_completed_process(0, stdout=obs_b + "\n")
            return _make_completed_process(0)

        original_git = reconcile.git
        reconcile.git = fake_git
        try:
            result = reconcile.reconcile_file(
                f,
                ".ai-state/observations.jsonl",
                reconcile.reconcile_observations,
                write_fn=reconcile.write_text_file,
            )
        finally:
            reconcile.git = original_git

        assert result is True
        lines = [ln for ln in f.read_text().strip().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_conflicted_file_warns_when_git_stages_missing(self, tmp_path: Path, capsys):
        """A conflicted file with no git stages emits a warning and returns False."""
        f = tmp_path / "observations.jsonl"
        f.write_text("<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> branch\n")

        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(returncode=1)
        try:
            result = reconcile.reconcile_file(
                f,
                ".ai-state/observations.jsonl",
                reconcile.reconcile_observations,
                write_fn=reconcile.write_text_file,
            )
        finally:
            reconcile.git = original_git

        assert result is False
        out = capsys.readouterr().out
        assert "cannot extract" in out


# -- write_text_file --------------------------------------------------------------


class TestWriteTextFile:
    def test_writes_content_to_file(self, tmp_path: Path):
        """write_text_file creates the file with the given content."""
        dest = tmp_path / "out.txt"
        reconcile.write_text_file(dest, "hello\nworld\n")
        assert dest.read_text() == "hello\nworld\n"

    def test_overwrites_existing_content(self, tmp_path: Path):
        """write_text_file replaces existing file content."""
        dest = tmp_path / "out.txt"
        dest.write_text("old content\n")
        reconcile.write_text_file(dest, "new content\n")
        assert dest.read_text() == "new content\n"


# -- _check_merge_drivers ---------------------------------------------------------


class TestCheckMergeDrivers:
    def test_warns_when_driver_not_registered(self, capsys):
        """Missing merge drivers produce a warning on stdout."""
        original_git = reconcile.git
        # Simulate git config returning non-zero (driver not registered)
        reconcile.git = lambda *args: _make_completed_process(returncode=1)
        try:
            reconcile._check_merge_drivers()
        finally:
            reconcile.git = original_git
        out = capsys.readouterr().out
        assert "observations-jsonl" in out

    def test_no_warning_when_drivers_registered(self, capsys):
        """Registered merge drivers produce no warning."""
        original_git = reconcile.git
        reconcile.git = lambda *args: _make_completed_process(
            returncode=0, stdout="observations-jsonl merge driver\n"
        )
        try:
            reconcile._check_merge_drivers()
        finally:
            reconcile.git = original_git
        out = capsys.readouterr().out
        assert "not registered" not in out


# -- _reconcile_adr_and_index -----------------------------------------------------


class TestReconcileAdrAndIndex:
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

    def test_returns_false_when_decisions_dir_absent(self, tmp_path: Path):
        """No decisions directory means no changes."""
        absent = tmp_path / "no_decisions"
        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        original_script_dir = reconcile.SCRIPT_DIR
        reconcile.DECISIONS_DIR = absent
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        reconcile.SCRIPT_DIR = tmp_path  # ensure regenerate_adr_index.py not found
        try:
            result = reconcile._reconcile_adr_and_index()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts
            reconcile.SCRIPT_DIR = original_script_dir
        assert result is False

    def test_returns_true_after_renumbering_duplicates(self, tmp_path: Path):
        """Duplicate ADRs trigger renumbering and _reconcile_adr_and_index returns True."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "alpha", "2026-01-01")
        self._make_adr(decisions_dir, 1, "beta", "2026-01-02")  # duplicate

        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        original_script_dir = reconcile.SCRIPT_DIR
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        # Point SCRIPT_DIR at tmp_path where regenerate_adr_index.py does not exist
        reconcile.SCRIPT_DIR = tmp_path
        try:
            result = reconcile._reconcile_adr_and_index()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts
            reconcile.SCRIPT_DIR = original_script_dir
        assert result is True

    def test_no_duplicates_and_no_regen_script_returns_false(self, tmp_path: Path):
        """No duplicates and no regenerate script means no changes."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "only-one", "2026-01-01")

        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        original_script_dir = reconcile.SCRIPT_DIR
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        reconcile.SCRIPT_DIR = tmp_path  # no regenerate_adr_index.py here
        try:
            result = reconcile._reconcile_adr_and_index()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts
            reconcile.SCRIPT_DIR = original_script_dir
        assert result is False


# -- main entry-point modes -------------------------------------------------------


class TestMain:
    """Tests for main() — uses monkey-patching to isolate filesystem and git I/O."""

    def test_main_prints_nothing_to_reconcile_when_files_absent(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """main() with no files and no decisions reports nothing to reconcile."""
        monkeypatch.setattr(reconcile, "OBSERVATIONS_PATH", tmp_path / "observations.jsonl")
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", tmp_path / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))
        # Disable repo-root resolution so the injected path constants survive;
        # the resolver itself is covered by the consumer-layout regression tests.
        monkeypatch.setattr(reconcile, "apply_repo_root", lambda *_a, **_k: None)

        monkeypatch.setattr(sys, "argv", ["reconcile_ai_state.py"])
        reconcile.main()
        out = capsys.readouterr().out
        assert "Nothing to reconcile" in out

    def test_main_post_merge_skips_observations(self, tmp_path: Path, capsys, monkeypatch):
        """--post-merge skips observations reconciliation path."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        obs = ai_state / "observations.jsonl"
        obs.write_text("")

        monkeypatch.setattr(reconcile, "OBSERVATIONS_PATH", obs)
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", ai_state / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))
        # --repo-root anchors main()'s own apply_repo_root() on the tmp tree.
        # Without it the resolver finds the live checkout and rebinds the path
        # constants injected above, regenerating the committed DECISIONS_INDEX.md.
        monkeypatch.setattr(
            sys,
            "argv",
            ["reconcile_ai_state.py", "--post-merge", "--repo-root", str(tmp_path)],
        )
        reconcile.main()
        out = capsys.readouterr().out
        # observations.jsonl conflict handling is skipped in --post-merge mode
        assert "observations.jsonl: no conflicts" not in out

    def test_main_processes_clean_observations_file(self, tmp_path: Path, capsys, monkeypatch):
        """main() reports no conflicts for a clean observations.jsonl file."""
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir()
        obs = ai_state / "observations.jsonl"
        obs.write_text(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "session_id": "s1",
                    "event_type": "tool_use",
                    "tool_name": "Bash",
                }
            )
            + "\n"
        )

        monkeypatch.setattr(reconcile, "OBSERVATIONS_PATH", obs)
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", ai_state / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))
        # --repo-root anchors main()'s own apply_repo_root() on the tmp tree.
        # Without it the resolver finds the live checkout and rebinds the path
        # constants injected above, so this test asserted on the live repo's
        # observations.jsonl and regenerated the committed DECISIONS_INDEX.md.
        monkeypatch.setattr(sys, "argv", ["reconcile_ai_state.py", "--repo-root", str(tmp_path)])
        reconcile.main()
        out = capsys.readouterr().out
        assert "observations.jsonl: no conflicts" in out


# -- reconcile_adr_numbers: non-ADR files in decisions dir ------------------------


class TestReconcileAdrNumbersNonAdrFiles:
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

    def test_non_adr_filenames_skipped_during_iteration(self, tmp_path: Path):
        """Files that don't match NNN-slug.md pattern are ignored without error."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        # Place a file that doesn't match the ADR pattern
        (decisions_dir / "DECISIONS_INDEX.md").write_text("# Index\n")
        (decisions_dir / "README.md").write_text("# Notes\n")
        self._make_adr(decisions_dir, 1, "real-adr", "2026-01-01")

        original_dir = reconcile.DECISIONS_DIR
        original_has_drafts = reconcile.has_drafts_directory_changed_in_merge
        reconcile.DECISIONS_DIR = decisions_dir
        reconcile.has_drafts_directory_changed_in_merge = lambda: False
        try:
            changed = reconcile.reconcile_adr_numbers()
        finally:
            reconcile.DECISIONS_DIR = original_dir
            reconcile.has_drafts_directory_changed_in_merge = original_has_drafts

        assert changed is False
        # Non-ADR files must be untouched
        assert (decisions_dir / "DECISIONS_INDEX.md").exists()
        assert (decisions_dir / "README.md").exists()


# -- reconcile_file: non-JSON file (no suffix validation) -------------------------


class TestReconcileFileNonJson:
    def test_non_json_file_without_conflict_returns_false(self, tmp_path: Path):
        """A non-conflicted non-JSON file is accepted as-is and returns False."""
        f = tmp_path / "observations.jsonl"
        f.write_text(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "session_id": "s1",
                    "event_type": "tool_use",
                    "tool_name": "Bash",
                }
            )
            + "\n"
        )
        result = reconcile.reconcile_file(
            f,
            ".ai-state/observations.jsonl",
            reconcile.reconcile_observations,
            write_fn=reconcile.write_text_file,
        )
        assert result is False
        # File content must be preserved
        assert "tool_use" in f.read_text()


# -- _reconcile_adr_and_index: regen script paths ---------------------------------


class TestReconcileAdrAndIndexRegenScript:
    def _make_adr(self, decisions_dir: Path, num: int, slug: str) -> Path:
        path = decisions_dir / f"{num:03d}-{slug}.md"
        path.write_text(
            f"---\nid: dec-{num:03d}\ntitle: {slug}\nstatus: accepted\n"
            f"category: architectural\ndate: 2026-01-01\n"
            f"summary: Test\ntags: [test]\nmade_by: agent\n---\n\n## Context\n\nTest.\n",
            encoding="utf-8",
        )
        return path

    def test_regen_script_success_returns_true(self, tmp_path: Path, monkeypatch):
        """When regenerate_adr_index.py exists and succeeds, returns True."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "one-adr")

        # Create a stub regen script that exits successfully
        regen_script = tmp_path / "regenerate_adr_index.py"
        regen_script.write_text("import sys; sys.exit(0)\n")

        monkeypatch.setattr(reconcile, "DECISIONS_DIR", decisions_dir)
        monkeypatch.setattr(reconcile, "SCRIPT_DIR", tmp_path)
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))

        result = reconcile._reconcile_adr_and_index()
        assert result is True

    def test_regen_script_failure_warns_and_returns_false(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """When regenerate_adr_index.py fails, a warning is emitted and changes=False."""
        decisions_dir = tmp_path / "decisions"
        decisions_dir.mkdir(parents=True)
        self._make_adr(decisions_dir, 1, "one-adr")

        # Create a stub regen script that exits with failure
        regen_script = tmp_path / "regenerate_adr_index.py"
        regen_script.write_text("import sys; print('regen failed', file=sys.stderr); sys.exit(1)\n")

        monkeypatch.setattr(reconcile, "DECISIONS_DIR", decisions_dir)
        monkeypatch.setattr(reconcile, "SCRIPT_DIR", tmp_path)
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))

        result = reconcile._reconcile_adr_and_index()
        assert result is False
        out = capsys.readouterr().out
        assert "regeneration failed" in out


# -- main: observations changed path and ADR-driven completion --------------------


class TestMainObservationsAndAdrChanges:
    def test_main_reports_complete_when_observations_conflict_resolved(
        self, tmp_path: Path, capsys, monkeypatch
    ):
        """main() prints 'Reconciliation complete' when a conflicted observations file is resolved."""
        obs = tmp_path / "observations.jsonl"
        obs.write_text("<<<<<<< HEAD\n{...}\n=======\n{...}\n>>>>>>> branch\n")

        obs_a = json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "event_type": "tool_use",
                "tool_name": "Bash",
            }
        )
        obs_b = json.dumps(
            {
                "timestamp": "2026-02-01T00:00:00Z",
                "session_id": "s2",
                "event_type": "session_stop",
                "tool_name": "",
            }
        )

        def fake_git(*args: str) -> subprocess.CompletedProcess[str]:
            if args[0] == "show" and ":2:" in args[1]:
                return _make_completed_process(0, stdout=obs_a + "\n")
            if args[0] == "show" and ":3:" in args[1]:
                return _make_completed_process(0, stdout=obs_b + "\n")
            return _make_completed_process(0)

        monkeypatch.setattr(reconcile, "OBSERVATIONS_PATH", obs)
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", tmp_path / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", fake_git)
        # Disable repo-root resolution so the injected path constants survive;
        # the resolver itself is covered by the consumer-layout regression tests.
        monkeypatch.setattr(reconcile, "apply_repo_root", lambda *_a, **_k: None)
        monkeypatch.setattr(sys, "argv", ["reconcile_ai_state.py"])
        reconcile.main()

        out = capsys.readouterr().out
        assert "Reconciliation complete" in out
        # Post-condition: merged file has both entries
        lines = [ln for ln in obs.read_text().strip().splitlines() if ln.strip()]
        assert len(lines) == 2


# -- --target-mount: reinstated merge-back reconciliation --------------------
#
# `ARCH_WT_RULING.md` § 8 walks back the "shared live tree" no-op: at
# merge-back, on the sidecar side, against the mount, this reconciler has a
# real job again. Every fixture below drives *real* `git worktree` / `git
# merge` -- nothing about git is mocked here, because the behaviour under
# test is the sidecar's own union merge driver resolving an
# `observations.jsonl` conflict during `git merge`, which a mocked
# subprocess cannot exercise (this deliberately departs from the rest of
# this file's importlib/monkeypatch style -- see `test_sidecar_mount.py` and
# `test_state_repo.py` for the precedent of driving real git for this class
# of behaviour).
#
# `--target-mount` does not exist yet (concurrent BDD/TDD with the paired
# implementation work): confirmed empirically before writing these tests
# that the flag is silently ignored by the current hand-rolled argv parser
# (no argparse here) -- so every assertion below that depends on `--target-mount`
# actually routing reconciliation to the mount is RED today. Every
# invocation below pins its subprocess `cwd` at a throwaway, unrelated git
# repository (never the mount, never a project, never this checkout) and
# passes no `--repo-root`, so today's silent-ignore-plus-git-root-from-cwd
# fallback can only ever resolve to that throwaway repo -- it cannot
# coincidentally reach the mount under test and cannot fall through to the
# live Praxion checkout this suite runs from.

_DRIVER_SCRIPT_PATH = Path(__file__).resolve().parent / "merge_driver_observations.py"
_TM_IDENTITY_ARGS = ("-c", "user.email=test@example.com", "-c", "user.name=Test")


def _tm_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _tm_git_ok(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _tm_git(cwd, *args)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd} failed: {result.stderr}")
    return result


def _tm_configure_identity(repo: Path) -> None:
    _tm_git_ok(repo, "config", "user.email", "test@example.com")
    _tm_git_ok(repo, "config", "user.name", "Test")


def _tm_commit_all(repo: Path, message: str) -> None:
    _tm_git_ok(repo, "add", "-A")
    _tm_git_ok(repo, *_TM_IDENTITY_ARGS, "commit", "-q", "-m", message)


def _tm_init_sidecar(sidecar_root: Path) -> None:
    """Seed a sidecar repo: two observation lines, one finalized ADR, the
    union merge driver registered and `.gitattributes` routing to it -- then
    detach `main` so it is free for the mounts below (mirrors
    `praxion-sidecar init`'s own sequence, `ARCH_WT_RULING.md` § 5).

    The driver is registered against THIS worktree's real
    `merge_driver_observations.py`, at the exact invocation string
    `skills/onboard-project/references/phases-core.md` § Phase 3 documents
    for onboarding: `python3 <path>/scripts/merge_driver_observations.py
    %O %A %B`. Registration happens once, in the sidecar's own git config,
    which every worktree of that sidecar shares -- exactly the load-bearing
    property `ARCH_WT_RULING.md` § 8 names.
    """
    _tm_git_ok(sidecar_root, "init", "-q", "-b", "main")
    _tm_configure_identity(sidecar_root)
    ai_state = sidecar_root / ".ai-state"
    (ai_state / "decisions").mkdir(parents=True)
    seed_lines = [
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "session_id": "s1",
                "event_type": "a",
                "tool_name": "",
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-01-02T00:00:00Z",
                "session_id": "s2",
                "event_type": "b",
                "tool_name": "",
            }
        ),
    ]
    (ai_state / "observations.jsonl").write_text("\n".join(seed_lines) + "\n")
    (ai_state / "decisions" / "001-example.md").write_text(
        "---\nid: dec-001\ntitle: Example\nstatus: accepted\n"
        "category: architectural\ndate: 2026-01-01\n"
        "summary: Example decision\ntags: [test]\nmade_by: agent\n---\n\n"
        "## Context\n\nTest.\n"
    )
    (sidecar_root / ".gitattributes").write_text(
        ".ai-state/observations.jsonl merge=observations-jsonl\n"
    )
    _tm_commit_all(sidecar_root, "seed sidecar state")
    _tm_git_ok(
        sidecar_root,
        "config",
        "merge.observations-jsonl.driver",
        f"python3 {_DRIVER_SCRIPT_PATH} %O %A %B",
    )
    _tm_git_ok(sidecar_root, "checkout", "-q", "--detach")


def _tm_init_project(project_root: Path) -> None:
    _tm_git_ok(project_root, "init", "-q", "-b", "main")
    _tm_configure_identity(project_root)
    (project_root / "app.py").write_text("code\n")
    _tm_commit_all(project_root, "init")


def _tm_mount(sidecar_root: Path, dest: Path, branch: str, *, base: str | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["worktree", "add", "-q"]
    args += [str(dest), branch] if base is None else ["-b", branch, str(dest), base]
    _tm_git_ok(sidecar_root, *args)
    _tm_configure_identity(dest)
    return dest


def _tm_append_observation(mount: Path, *, session_id: str, event: str, timestamp: str) -> None:
    obs = mount / ".ai-state" / "observations.jsonl"
    line = json.dumps(
        {"timestamp": timestamp, "session_id": session_id, "event_type": event, "tool_name": ""}
    )
    with obs.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _tm_safe_cwd(tmp_path: Path) -> Path:
    """A throwaway, unrelated git repo used only as subprocess `cwd`.

    Guarantees `--target-mount`'s current silent-ignore fallback
    (`git rev-parse --show-toplevel` from cwd, when neither `--target-mount`
    nor `--repo-root` is honoured) can only ever resolve here -- never to
    the mount under test, never to the live checkout this suite runs from.
    """
    anchor = tmp_path / "cwd_anchor"
    anchor.mkdir()
    _tm_git_ok(anchor, "init", "-q", "-b", "main")
    _tm_configure_identity(anchor)
    return anchor


def _tm_write_manifest(
    sidecar_root: Path, project_root: Path, *, project_id: str = "local--abc123"
) -> None:
    manifest_path = sidecar_root / ".git" / "praxion-sidecar.yaml"
    manifest_path.write_text(
        "schema: 1\n"
        "project:\n"
        "  origin: null\n"
        f'  id: "{project_id}"\n'
        f'  roots: ["{project_root.resolve()}"]\n'
    )


@dataclasses.dataclass(frozen=True)
class _TargetMountFixture:
    sidecar_root: Path
    project_root: Path
    main_mount: Path
    wt_mount: Path
    safe_cwd: Path


def _tm_build_diverged_fixture(tmp_path: Path) -> _TargetMountFixture:
    """Sidecar + main mount + a second `wt/x` mount, unmerged, with real
    diverged `observations.jsonl` content on each side: `main` gets one
    unique entry; `wt/x` gets an IDENTICAL duplicate of that entry plus one
    entry unique to it, and a distinct draft ADR. This shape is what lets a
    single merge prove two things at once: the union driver resolves a real
    conflict (both sides touched the same file), and its dedup collapses an
    identical entry rather than doubling it.

    `wt/x`'s mount sits at a plain directory, `<project>/.claude/worktrees/
    x/.praxion-state` -- not a real linked *project* worktree, since nothing under
    test here needs project-side branch tracking.
    """
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    sidecar_root.mkdir()
    project_root.mkdir()
    _tm_init_sidecar(sidecar_root)
    _tm_init_project(project_root)

    main_mount = _tm_mount(sidecar_root, project_root / ".praxion-state", "main")
    wt_mount = _tm_mount(
        sidecar_root,
        project_root / ".claude" / "worktrees" / "x" / ".praxion-state",
        "wt/x",
        base="main",
    )

    _tm_append_observation(main_mount, session_id="sM", event="m", timestamp="2026-01-03T00:00:00Z")
    _tm_commit_all(main_mount, "main: add M")

    _tm_append_observation(wt_mount, session_id="sM", event="m", timestamp="2026-01-03T00:00:00Z")
    _tm_commit_all(wt_mount, "wt: add M (identical duplicate)")
    _tm_append_observation(wt_mount, session_id="sW", event="w", timestamp="2026-01-04T00:00:00Z")
    drafts_dir = wt_mount / ".ai-state" / "decisions" / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    (drafts_dir / "20260104-test-wtx-draft.md").write_text(
        "---\nid: dec-draft-abc12345\ntitle: Draft\nstatus: proposed\n"  # id-citation-discipline:ignore
        "category: implementation\ndate: 2026-01-04\n"
        "summary: A draft from wt/x\ntags: [test]\nmade_by: agent\n---\n\n"
        "## Context\n\nTest draft.\n"
    )
    _tm_commit_all(wt_mount, "wt: add W and a draft")

    return _TargetMountFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        wt_mount=wt_mount,
        safe_cwd=_tm_safe_cwd(tmp_path),
    )


def _tm_merge_wt_into_main(fixture: _TargetMountFixture) -> subprocess.CompletedProcess[str]:
    return _tm_git(fixture.main_mount, "merge", "-q", "--no-edit", "wt/x")


def _tm_build_merged_mount_fixture(tmp_path: Path) -> _TargetMountFixture:
    """The diverged fixture, already merged cleanly through the sidecar's
    own union driver -- the state every `--target-mount` reconciliation test
    starts from. Asserts the precondition itself holds, so a broken fixture
    never masquerades as a `--target-mount` failure."""
    fixture = _tm_build_diverged_fixture(tmp_path)
    result = _tm_merge_wt_into_main(fixture)
    assert result.returncode == 0, f"precondition merge failed: {result.stderr}"
    obs_text = (fixture.main_mount / ".ai-state" / "observations.jsonl").read_text()
    assert "<<<<<<<" not in obs_text, "precondition merge left conflict markers"
    return fixture


def _tm_build_sidecar_owned_fixture(tmp_path: Path) -> _TargetMountFixture:
    """A minimal, fully-wired `SidecarOwned` project -- mount, manifest,
    shadow symlink -- for the project-side call-site tests. No `wt/x`
    branch: the project-side no-op does not depend on branch divergence."""
    sidecar_root = tmp_path / "sidecar"
    project_root = tmp_path / "project"
    sidecar_root.mkdir()
    project_root.mkdir()
    _tm_init_sidecar(sidecar_root)
    _tm_init_project(project_root)
    main_mount = _tm_mount(sidecar_root, project_root / ".praxion-state", "main")
    _tm_write_manifest(sidecar_root, project_root)
    (project_root / ".ai-state").symlink_to(
        Path(".praxion-state") / ".ai-state", target_is_directory=True
    )

    return _TargetMountFixture(
        sidecar_root=sidecar_root,
        project_root=project_root,
        main_mount=main_mount,
        wt_mount=main_mount,
        safe_cwd=_tm_safe_cwd(tmp_path),
    )


def _tm_run(safe_cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        cwd=safe_cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class TestTargetMountMergeBackPrecondition:
    """The precondition every `--target-mount` test below assumes: the
    sidecar's own union merge driver resolves a real `observations.jsonl`
    divergence during `git merge`, deduplicating an identical entry rather
    than leaving conflict markers or a literal duplicate. Not a
    `--target-mount` behaviour itself -- proven independently so a
    `--target-mount` failure is never confused with a broken fixture."""

    def test_union_driver_merges_diverged_branches_without_conflict_markers(self, tmp_path: Path):
        fixture = _tm_build_diverged_fixture(tmp_path)

        result = _tm_merge_wt_into_main(fixture)

        assert result.returncode == 0, result.stderr
        obs_text = (fixture.main_mount / ".ai-state" / "observations.jsonl").read_text()
        assert "<<<<<<<" not in obs_text
        assert ">>>>>>>" not in obs_text
        lines = [ln for ln in obs_text.strip().splitlines() if ln.strip()]
        session_ids = sorted(json.loads(ln)["session_id"] for ln in lines)
        # 2 seed + M (deduped from an identical append on both branches) + W
        # -- not 5, which is what a naive concat-without-dedup would produce.
        assert session_ids == ["s1", "s2", "sM", "sW"]


class TestTargetMountReconciliation:
    """`reconcile_ai_state.py --target-mount <mount>` after a clean
    merge-back: the reinstated, retargeted reconciler (`ARCH_WT_RULING.md`
    § 8) runs its own job -- ADR/index reconciliation -- against the MOUNT,
    never the project repository."""

    def test_completes_cleanly_and_preserves_deduped_observations(self, tmp_path: Path):
        fixture = _tm_build_merged_mount_fixture(tmp_path)
        index_path = fixture.main_mount / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"

        result = _tm_run(fixture.safe_cwd, "--target-mount", str(fixture.main_mount))

        assert result.returncode == 0, result.stderr
        # Proof the run actually reached the mount (not merely that the
        # fixture's own pre-existing merge state happened to look right):
        # nothing but this script writes DECISIONS_INDEX.md.
        assert index_path.exists()
        obs_text = (fixture.main_mount / ".ai-state" / "observations.jsonl").read_text()
        assert "<<<<<<<" not in obs_text
        lines = [ln for ln in obs_text.strip().splitlines() if ln.strip()]
        assert len(lines) == 4  # 2 seed + M (deduped) + W -- not 5

    def test_regenerates_decisions_index_in_the_mount(self, tmp_path: Path):
        fixture = _tm_build_merged_mount_fixture(tmp_path)
        index_path = fixture.main_mount / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"

        result = _tm_run(fixture.safe_cwd, "--target-mount", str(fixture.main_mount))

        assert result.returncode == 0, result.stderr
        assert index_path.exists()
        assert "dec-001" in index_path.read_text()

    def test_leaves_the_project_repository_untouched(self, tmp_path: Path):
        fixture = _tm_build_merged_mount_fixture(tmp_path)
        index_path = fixture.main_mount / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
        before_head = _tm_git_ok(fixture.project_root, "rev-parse", "HEAD").stdout
        before_status = _tm_git_ok(fixture.project_root, "status", "--porcelain").stdout

        result = _tm_run(fixture.safe_cwd, "--target-mount", str(fixture.main_mount))

        assert result.returncode == 0, result.stderr
        # Proof the run actually reached the mount -- otherwise "the project
        # is untouched" would hold trivially even if --target-mount were a
        # complete no-op.
        assert index_path.exists()
        after_head = _tm_git_ok(fixture.project_root, "rev-parse", "HEAD").stdout
        after_status = _tm_git_ok(fixture.project_root, "status", "--porcelain").stdout
        assert after_head == before_head
        assert after_status == before_status

    def test_stages_its_own_changes_in_the_mount_not_the_project(self, tmp_path: Path):
        fixture = _tm_build_merged_mount_fixture(tmp_path)

        result = _tm_run(fixture.safe_cwd, "--target-mount", str(fixture.main_mount))

        assert result.returncode == 0, result.stderr
        mount_staged = _tm_git_ok(fixture.main_mount, "diff", "--cached", "--name-only").stdout
        project_staged = _tm_git_ok(fixture.project_root, "diff", "--cached", "--name-only").stdout
        assert "DECISIONS_INDEX.md" in mount_staged
        assert project_staged == ""


class TestTargetMountRefusesInvalidPaths:
    """`--target-mount` validates its argument -- it must name a real state
    mount, never a path that merely resolves into (or through) one. The
    exact refusal wording is an implementation choice; these tests pin only
    the observable contract: refuse loudly (non-zero exit), never proceed
    silently as if the path were the mount."""

    def test_refuses_a_directory_that_is_not_a_sidecar_worktree(self, tmp_path: Path):
        safe_cwd = _tm_safe_cwd(tmp_path)
        not_a_mount = tmp_path / "plain_dir"
        not_a_mount.mkdir()

        result = _tm_run(safe_cwd, "--target-mount", str(not_a_mount))

        assert result.returncode != 0
        combined = (result.stdout + result.stderr).lower()
        assert "mount" in combined

    def test_refuses_a_shadow_symlink_path_instead_of_the_mount_itself(self, tmp_path: Path):
        fixture = _tm_build_sidecar_owned_fixture(tmp_path)
        shadow_path = fixture.project_root / ".ai-state"
        assert shadow_path.is_symlink()

        result = _tm_run(fixture.safe_cwd, "--target-mount", str(shadow_path))

        assert result.returncode != 0
        combined = (result.stdout + result.stderr).lower()
        assert "mount" in combined


class TestProjectSideSkipsUnderSidecarOwnership:
    """`reconcile_ai_state.py --repo-root <project>` (no `--target-mount`)
    on a `SidecarOwned` project is a no-op: the project repository does not
    own `.ai-state/` -- reconciliation runs at merge-back, against the
    mount, not here (`ARCH_WT_RULING.md` § 8).

    Today this is NOT a no-op: confirmed empirically before writing these
    tests that `--repo-root <project>` blindly follows the `.ai-state`
    shadow symlink and mutates the mount (writes and stages a fresh
    `DECISIONS_INDEX.md` there) -- reproduced by
    `test_touches_nothing_in_the_mount` below, which fails today for
    exactly that reason.
    """

    def test_skips_with_the_corrected_reason(self, tmp_path: Path):
        fixture = _tm_build_sidecar_owned_fixture(tmp_path)

        result = _tm_run(fixture.safe_cwd, "--repo-root", str(fixture.project_root))

        assert result.returncode == 0, result.stderr
        combined = (result.stdout + result.stderr).lower()
        assert "does not own" in combined
        assert ".ai-state" in combined

    def test_touches_nothing_in_the_mount(self, tmp_path: Path):
        fixture = _tm_build_sidecar_owned_fixture(tmp_path)
        before_status = _tm_git_ok(fixture.main_mount, "status", "--porcelain").stdout

        _tm_run(fixture.safe_cwd, "--repo-root", str(fixture.project_root))

        after_status = _tm_git_ok(fixture.main_mount, "status", "--porcelain").stdout
        assert after_status == before_status
