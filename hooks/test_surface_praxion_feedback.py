"""Tests for surface_praxion_feedback.py -- SessionStart pending-feedback advisory.

The hook advises the operator at session start when the managed project has
un-filed Praxion ecosystem-defect candidates in
``.ai-state/praxion_feedback/PENDING.md``. It must be fail-safe: any error, an
absent ledger, or a ledger with no *pending* candidates all yield a silent
exit-0 no-op so a global SessionStart hook can never slow or wedge a session.
"""

from __future__ import annotations

import importlib.util
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
