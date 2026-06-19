"""Tests for reconcile_ai_state.py — observations and ADR reconciliation."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent / "reconcile_ai_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("reconcile_ai_state", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reconcile = _load_module()


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
        obs = tmp_path / "observations.jsonl"
        obs.write_text("")

        monkeypatch.setattr(reconcile, "OBSERVATIONS_PATH", obs)
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", tmp_path / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))
        monkeypatch.setattr(sys, "argv", ["reconcile_ai_state.py", "--post-merge"])
        reconcile.main()
        out = capsys.readouterr().out
        # observations.jsonl conflict handling is skipped in --post-merge mode
        assert "observations.jsonl: no conflicts" not in out

    def test_main_processes_clean_observations_file(self, tmp_path: Path, capsys, monkeypatch):
        """main() reports no conflicts for a clean observations.jsonl file."""
        obs = tmp_path / "observations.jsonl"
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
        monkeypatch.setattr(reconcile, "DECISIONS_DIR", tmp_path / "decisions")
        monkeypatch.setattr(reconcile, "has_drafts_directory_changed_in_merge", lambda: False)
        monkeypatch.setattr(reconcile, "git", lambda *args: _make_completed_process(0))
        monkeypatch.setattr(sys, "argv", ["reconcile_ai_state.py"])
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
