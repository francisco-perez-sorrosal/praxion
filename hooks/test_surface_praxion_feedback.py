"""Tests for surface_praxion_feedback.py -- SessionStart pending-feedback advisory.

The hook advises the operator at session start when the managed project has
un-filed Praxion ecosystem-defect candidates in
``.ai-state/praxion_feedback/PENDING.md``. It must be fail-safe: any error, an
absent ledger, or a ledger with no *pending* candidates all yield a silent
exit-0 no-op so a global SessionStart hook can never slow or wedge a session.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parent / "surface_praxion_feedback.py"
_PENDING_REL = Path(".ai-state") / "praxion_feedback" / "PENDING.md"


def _load_surface_module():
    """Load surface_praxion_feedback.py by path (hooks/ is not a package)."""
    sys.path.insert(0, str(MODULE_PATH.parent))  # so `import _hook_utils` resolves
    spec = importlib.util.spec_from_file_location(
        "surface_praxion_feedback_under_test", MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


surface = _load_surface_module()


# --- fixtures & helpers -------------------------------------------------------


@pytest.fixture
def consumer_repo(tmp_path: Path) -> Path:
    """A real git repo standing in for a managed (consumer) project."""
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _seed_candidate(repo: Path, *, artifact: str, category: str = "scripts") -> str:
    """Append a real candidate to the repo's PENDING.md via the store module.

    Uses candidate_store.append_candidate so the on-disk block format is exactly
    what the hook reads back — no hand-authored PENDING.md format assumptions.
    Returns the candidate fingerprint.
    """
    from scripts.praxion_feedback.candidate_store import append_candidate

    pending = repo / _PENDING_REL
    pending.parent.mkdir(parents=True, exist_ok=True)
    upstream = repo / ".ai-state" / "UPSTREAM_ISSUES.md"  # need not exist
    fields = {
        "category": category,
        "artifact_path": artifact,
        "error": f"boom in {artifact}",
    }
    fingerprint = append_candidate(pending, upstream, fields)
    assert fingerprint is not None
    return fingerprint


def _run_hook(
    cwd: Path, payload: dict | None = None, extra_env: dict | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess:
    """Invoke the hook as a subprocess (its true runtime shape)."""
    env = {**os.environ, **(extra_env or {})}
    body = stdin if stdin is not None else json.dumps(payload or {"cwd": str(cwd)})
    return subprocess.run(
        [sys.executable, str(MODULE_PATH)],
        input=body,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=10,
    )


def _injected_context(result: subprocess.CompletedProcess) -> str:
    parsed = json.loads(result.stdout)
    return parsed["hookSpecificOutput"]["additionalContext"]


# --- advisory text builder (unit) --------------------------------------------


class TestAdvisoryBuilder:
    """The pure advisory renderer: count, per-candidate line, bounded output."""

    def test_names_review_command_and_count(self) -> None:
        candidates = [
            {"category": "scripts", "artifact_path": "scripts/a.py", "fingerprint": "aaaa1111"},
            {"category": "hooks", "artifact_path": "hooks/b.py", "fingerprint": "bbbb2222"},
        ]
        text = surface._build_advisory(candidates)
        assert "/report-praxion-issue" in text
        assert "2" in text

    def test_line_has_category_artifact_and_short_fingerprint(self) -> None:
        candidates = [
            {
                "category": "scripts",
                "artifact_path": "scripts/foo.py",
                "fingerprint": "abcd1234deadbeef",
            }
        ]
        text = surface._build_advisory(candidates)
        assert "scripts" in text
        assert "scripts/foo.py" in text
        assert "abcd1234" in text  # short (8-char) fingerprint

    def test_bounds_the_surfaced_list(self) -> None:
        candidates = [
            {"category": "scripts", "artifact_path": f"scripts/f{i}.py", "fingerprint": f"{i:08d}"}
            for i in range(7)
        ]
        text = surface._build_advisory(candidates)
        assert "and 2 more" in text  # 7 total, top 5 shown
        assert "scripts/f6.py" not in text  # the 7th is not surfaced inline


# --- end-to-end behavior ------------------------------------------------------


class TestAdvisoryEmitted:
    def test_advisory_when_candidate_pending(self, consumer_repo: Path) -> None:
        _seed_candidate(consumer_repo, artifact="scripts/foo.py")
        result = _run_hook(consumer_repo)
        assert result.returncode == 0
        assert "/report-praxion-issue" in _injected_context(result)

    def test_line_format_end_to_end(self, consumer_repo: Path) -> None:
        fingerprint = _seed_candidate(consumer_repo, artifact="hooks/bar.py", category="hooks")
        context = _injected_context(_run_hook(consumer_repo))
        assert "hooks/bar.py" in context
        assert fingerprint[:8] in context


class TestSilent:
    def test_silent_when_pending_absent(self, consumer_repo: Path) -> None:
        result = _run_hook(consumer_repo)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_when_pending_header_only(self, consumer_repo: Path) -> None:
        pending = consumer_repo / _PENDING_REL
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("# Pending Praxion Feedback\n\nNo candidates yet.\n", encoding="utf-8")
        result = _run_hook(consumer_repo)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_silent_when_all_candidates_filed(self, consumer_repo: Path) -> None:
        from scripts.praxion_feedback.candidate_store import mark_filed

        fingerprint = _seed_candidate(consumer_repo, artifact="scripts/foo.py")
        mark_filed(consumer_repo / _PENDING_REL, fingerprint, "https://example/issues/1")
        result = _run_hook(consumer_repo)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_disable_flag_suppresses_advisory(self, consumer_repo: Path) -> None:
        _seed_candidate(consumer_repo, artifact="scripts/foo.py")
        result = _run_hook(consumer_repo, extra_env={surface.DISABLE_FLAG: "1"})
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestFailsSafe:
    """A global SessionStart hook must never raise, slow, or wedge startup."""

    def test_exits_zero_on_malformed_payload(self, consumer_repo: Path) -> None:
        result = _run_hook(consumer_repo, stdin="not-json")
        assert result.returncode == 0

    def test_exits_zero_on_empty_stdin(self, consumer_repo: Path) -> None:
        result = _run_hook(consumer_repo, stdin="")
        assert result.returncode == 0

    def test_silent_outside_git_repo(self, tmp_path: Path) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        result = _run_hook(non_git)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_exits_zero_on_corrupt_pending_md(self, consumer_repo: Path) -> None:
        pending = consumer_repo / _PENDING_REL
        pending.parent.mkdir(parents=True, exist_ok=True)
        pending.write_text("\x00### not a real block\n``unterminated fence", encoding="utf-8")
        result = _run_hook(consumer_repo)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# In-process drive of the resolution layer and main().
#
# The subprocess tests above pin the hook's runtime shape. These reach the
# parts a subprocess cannot observe: which root each mechanism resolves from,
# and that a hostile payload cannot move the caller's working directory.
#
# `_honor_payload_cwd` really does chdir, so every test that can reach it
# takes `monkeypatch.chdir` first -- monkeypatch records the directory at that
# moment and restores it at teardown regardless of what the hook did meanwhile.
# ---------------------------------------------------------------------------


def _drive_main(payload_text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `main()` in-process with `payload_text` standing in for stdin."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload_text))
    surface.main()


class TestPluginRootResolution:
    def test_plugin_root_is_added_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        plugin_root = str(MODULE_PATH.resolve().parent.parent)
        # Swap in a path list without the plugin root. Replacing the attribute
        # (rather than mutating the list) lets monkeypatch restore the original
        # list object wholesale at teardown.
        monkeypatch.setattr(sys, "path", [p for p in sys.path if p != plugin_root])
        assert plugin_root not in sys.path

        surface._ensure_plugin_root_on_path()

        assert plugin_root in sys.path

    def test_repeated_calls_do_not_grow_the_path(self) -> None:
        # This runs on every session start; an unguarded insert would make
        # sys.path grow without bound across a long-lived process.
        surface._ensure_plugin_root_on_path()
        plugin_root = str(MODULE_PATH.resolve().parent.parent)
        before = sys.path.count(plugin_root)

        surface._ensure_plugin_root_on_path()

        assert sys.path.count(plugin_root) == before


class TestPayloadCwdHandling:
    def test_honors_a_valid_directory_from_the_payload(
        self, consumer_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        surface._honor_payload_cwd(json.dumps({"cwd": str(consumer_repo)}))

        assert Path.cwd().resolve() == consumer_repo.resolve()

    @pytest.mark.parametrize(
        "raw",
        [
            "not-json",
            "[]",
            "null",
            '"a bare string"',
            "",
            "   ",
        ],
    )
    def test_a_payload_it_cannot_read_leaves_the_directory_alone(
        self, raw: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        surface._honor_payload_cwd(raw)

        assert Path.cwd().resolve() == tmp_path.resolve()

    def test_a_cwd_that_does_not_exist_leaves_the_directory_alone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        surface._honor_payload_cwd(json.dumps({"cwd": str(tmp_path / "gone")}))

        assert Path.cwd().resolve() == tmp_path.resolve()

    def test_a_directory_it_cannot_enter_is_not_fatal(
        self, consumer_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The directory passes `is_dir()` but the chdir itself fails (permissions,
        # a racing unlink, a dead network mount). A SessionStart hook cannot let
        # that surface.
        monkeypatch.chdir(tmp_path)

        def _refuse(_target: object) -> None:
            raise OSError("permission denied")

        monkeypatch.setattr(surface.os, "chdir", _refuse)

        surface._honor_payload_cwd(json.dumps({"cwd": str(consumer_repo)}))

        assert Path.cwd().resolve() == tmp_path.resolve()


class TestPendingLedgerResolution:
    def test_resolves_the_ledger_under_the_managed_project_root(
        self, consumer_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(consumer_repo)

        pending = surface._pending_md_path()

        assert pending is not None
        # Resolved from git, not from __file__ -- the hook runs out of the
        # plugin cache, so a __file__-derived root would name the plugin.
        assert pending.resolve() == (consumer_repo / _PENDING_REL).resolve()

    def test_outside_a_repository_there_is_no_ledger_to_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)

        assert surface._pending_md_path() is None

    def test_absent_ledger_yields_no_candidates(self, consumer_repo: Path) -> None:
        assert surface._pending_candidates(consumer_repo / _PENDING_REL) == []

    def test_seeded_ledger_yields_its_pending_candidate(self, consumer_repo: Path) -> None:
        fingerprint = _seed_candidate(consumer_repo, artifact="scripts/foo.py")

        candidates = surface._pending_candidates(consumer_repo / _PENDING_REL)

        assert [c["fingerprint"] for c in candidates] == [fingerprint]


class TestEmittedEnvelope:
    def test_context_is_wrapped_in_the_session_start_hook_envelope(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        surface._emit("hello")

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert parsed["hookSpecificOutput"]["additionalContext"] == "hello"


class TestMainInProcess:
    def test_advises_when_the_project_has_a_pending_candidate(
        self,
        consumer_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(consumer_repo)
        _seed_candidate(consumer_repo, artifact="hooks/bar.py", category="hooks")

        _drive_main(json.dumps({"cwd": str(consumer_repo)}), monkeypatch)

        context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
        assert "/report-praxion-issue" in context
        assert "hooks/bar.py" in context

    def test_stays_silent_when_nothing_is_pending(
        self,
        consumer_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(consumer_repo)

        _drive_main(json.dumps({"cwd": str(consumer_repo)}), monkeypatch)

        assert capsys.readouterr().out == ""

    def test_stays_silent_outside_a_managed_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)

        _drive_main(json.dumps({"cwd": str(tmp_path)}), monkeypatch)

        assert capsys.readouterr().out == ""

    def test_kill_switch_suppresses_the_advisory_before_any_work(
        self,
        consumer_repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(consumer_repo)
        _seed_candidate(consumer_repo, artifact="scripts/foo.py")
        monkeypatch.setenv(surface.DISABLE_FLAG, "1")

        _drive_main(json.dumps({"cwd": str(consumer_repo)}), monkeypatch)

        assert capsys.readouterr().out == ""
