"""Tests for remind_calibration.py -- commit-time calibration-lag reminder hook (D2).

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate advising on
calibration-log lag at commit time. It ships a canary -- a test that feeds a known-
lagging fixture (calibration log dated far in the past + 2+ task-completing commits
since) and asserts the reminder fires -- proving the gate is not merely a no-op that
always passes on the current good state.

Contract under test (SYSTEMS_PLAN.md Interfaces): remind_calibration.py reads a stdin
JSON payload shaped like tool_input.command (identical to remind_adr.py's contract),
emits at most one stderr advisory line, and always exits 0 (fail-open -- never blocks
a commit). It reuses check_calibration_coverage.py::compute_coverage in-process and
fires only when ALL of the following hold: the pending command is a git commit,
.ai-state/calibration_log.md exists, the lag reaches K=2 uncalibrated task-completing
commits, the session is not inside a linked worktree, and the pending commit message
does not start with bump: or chore(finalize).

Hermetic-git-repo pattern (template: scripts/test_check_calibration_coverage.py):
every test builds its own temporary git repo via tmp_path, with git identity
configured and an injected .ai-state/calibration_log.md fixture. The real Praxion
calibration_log.md is never read.

Subprocess harness (template: hooks/test_worktree_guard.py): the hook is invoked as
a real subprocess with a JSON payload on stdin, mirroring exactly how commit_gate.sh
dispatches it during a real `git commit`.

BDD/TDD RED handshake: hooks/remind_calibration.py does not exist yet -- every test
below fails with FileNotFoundError (subprocess.run cannot find the script, or
Path.read_text() cannot find it for the structural check) until the implementer
lands the hook.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK_PATH = Path(__file__).resolve().parent / "remind_calibration.py"

# Calibration log header matching the real .ai-state/calibration_log.md format.
_CALIBRATION_HEADER = """\
# Calibration Log

Append-only tier-selection log. Each Standard/Full pipeline appends one row.

| Timestamp | Task | Signals | Recommended Tier | Actual Tier | Source | Retrospective |
|-----------|------|---------|------------------|-------------|--------|----------------|
"""


# -- Git / repo helpers -------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> Path:
    """Initialise a bare-minimum git repo suitable for git-log queries."""
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    _git(path, "config", "commit.gpgsign", "false")
    return path


def _write_calibration_log(repo: Path, newest_timestamp: str) -> None:
    """Write a synthetic calibration_log.md with one row at newest_timestamp."""
    state_dir = repo / ".ai-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    row = (
        f"| {newest_timestamp} | wave-test | signals | Standard | Standard"
        " | test | retrospective |\n"
    )
    (state_dir / "calibration_log.md").write_text(_CALIBRATION_HEADER + row, encoding="utf-8")


def _make_commit(repo: Path, message: str) -> None:
    """Create a file change and commit it with the given message."""
    sentinel_file = repo / "dummy.txt"
    current = sentinel_file.read_text() if sentinel_file.exists() else ""
    sentinel_file.write_text(current + f"{message}\n", encoding="utf-8")
    _git(repo, "add", "dummy.txt")
    _git(repo, "commit", "-m", message)


def _build_lagging_repo(tmp_path: Path) -> Path:
    """A hermetic repo with a far-past calibration log and 2 uncalibrated task commits.

    Matches the known-bad canary fixture in test_check_calibration_coverage.py:
    calibration_log.md dated 2025-01-01, plus two feat: commits landed since --
    reaching the K=2 under-coverage threshold.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_calibration_log(repo, "2025-01-01")
    _git(repo, "add", ".ai-state")
    _git(repo, "commit", "-m", "chore: add calibration baseline")
    _make_commit(repo, "feat: add authentication service")
    _make_commit(repo, "feat: add payment gateway integration")
    return repo


# -- Hook invocation helpers ---------------------------------------------------


def _run_hook(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_calibration.py as a subprocess, mirroring commit_gate.sh's dispatch.

    Payload shape matches remind_adr.py's stdin contract exactly: a JSON object with
    tool_input.command. The subprocess cwd stands in for the shell cwd commit_gate.sh
    runs from during a real `git commit`.
    """
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


def _run_hook_raw_stdin(raw_input: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke remind_calibration.py with an arbitrary raw stdin body (non-JSON cases)."""
    return subprocess.run(
        [sys.executable, str(_HOOK_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        timeout=10,
    )


# -- Tests ----------------------------------------------------------------------


def test_flags_lagging_calibration_log(tmp_path: Path) -> None:
    """Gate-liveness canary: a known-lagging fixture must fire the stderr reminder.

    Scenario: calibration_log.md dated 2025-01-01, two feat: commits landed since
    (the K=2 threshold reached), and the pending commit (on stdin) is itself another
    feat: commit with no suppression predicate active. A gate that never fires on
    known-bad input is indistinguishable from no gate (rules/swe/gate-liveness.md).

    Self-test: if the hook's lag check were gutted, stderr would stay empty and this
    test would fail. The contrast against the test_suppresses_reminder_* tests below
    (same lagging fixture, only the suppression predicate varies) rules out a hook
    that fires unconditionally regardless of coverage state.
    """
    repo = _build_lagging_repo(tmp_path)

    result = _run_hook('git commit -m "feat: add rate limiting"', repo)

    assert result.returncode == 0, "the hook must always exit 0 (fail-open, advisory-only)"
    assert result.stderr.strip() != "", (
        "a lagging calibration log with an unsuppressed pending commit must "
        "produce a stderr reminder"
    )
    assert (
        "calibration_log.md" in result.stderr
    ), "the reminder must point at .ai-state/calibration_log.md"
    assert (
        "retrospective" in result.stderr.lower()
    ), "the reminder must name the Retrospective cell as the micro-capture slot"


def test_suppresses_reminder_inside_linked_worktree(tmp_path: Path) -> None:
    """A linked worktree suppresses the reminder even when the calibration log lags.

    Direct-tier work happens only in the canonical checkout (isolation table);
    linked (pipeline/scratch) worktrees append their calibration row at pipeline
    completion, not per-commit, so per-commit nudging inside one would be noise.
    """
    main_repo = _build_lagging_repo(tmp_path)
    linked = tmp_path / "linked"
    subprocess.run(
        ["git", "-C", str(main_repo), "worktree", "add", "-q", str(linked), "-b", "feature"],
        check=True,
        capture_output=True,
        text=True,
    )

    result = _run_hook('git commit -m "feat: work done inside the worktree"', linked)

    assert result.returncode == 0
    assert result.stderr.strip() == "", (
        "a linked worktree must suppress the reminder even with a lagging "
        f"calibration log; got stderr={result.stderr!r}"
    )


@pytest.mark.parametrize(
    "message",
    [
        'git commit -m "bump: version 0.11.3 -> 0.12.0"',
        'git commit -m "chore(finalize): promote draft ADR to dec-999"',
    ],
    ids=["bump", "chore-finalize"],
)
def test_suppresses_reminder_for_release_and_finalize_commits(tmp_path: Path, message: str) -> None:
    """bump: and chore(finalize) commits suppress the reminder even when lagging.

    Release-automation and ADR-finalize bookkeeping commits are not task-completing
    work (mirrors the _EXCLUDED_PREFIXES exclusion in check_calibration_coverage.py);
    nudging on them would be pure noise on every version bump or ADR promotion.
    """
    repo = _build_lagging_repo(tmp_path)

    result = _run_hook(message, repo)

    assert result.returncode == 0
    assert result.stderr.strip() == "", (
        "bump:/chore(finalize) pending commits must suppress the reminder even "
        f"with a lagging calibration log; got stderr={result.stderr!r}"
    )


def test_silent_when_calibration_log_absent(tmp_path: Path) -> None:
    """Absent .ai-state/calibration_log.md produces no output and exit 0.

    Existence-gating (inherited from compute_coverage's covered=True-when-absent
    behavior): a project that has never onboarded the calibration log has no
    baseline to nudge against and must not be penalised at bootstrap.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_commit(repo, "feat: initial commit -- no calibration log exists yet")

    result = _run_hook('git commit -m "feat: second commit, still no log"', repo)

    assert result.returncode == 0
    assert (
        result.stderr.strip() == ""
    ), f"absent calibration_log.md must produce no output; got stderr={result.stderr!r}"


def test_malformed_stdin_json_never_raises(tmp_path: Path) -> None:
    """Malformed stdin JSON never raises and always exits 0 (fail-open).

    Mirrors remind_adr.py's contract: main() is wrapped in except Exception: pass so
    a hook bug can never wedge or block a commit.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    result = _run_hook_raw_stdin("not-json{{{", repo)

    assert result.returncode == 0, "malformed stdin must never cause a non-zero exit"
    assert (
        "Traceback" not in result.stderr
    ), f"malformed stdin must not leak a Python traceback; got stderr={result.stderr!r}"


def test_resolves_consumer_repo_root_via_git(tmp_path: Path) -> None:
    """Structural: the consumer repo root must be resolved via git, not __file__.

    Mirrors the structural-assertion style in
    test_check_calibration_coverage.py::test_runs_to_verdict_without_sentinel.
    remind_calibration.py is reached through a symlinked plugin-cache install in
    every managed project's commit_gate.sh chain -- Path(__file__).resolve() would
    follow the symlink back to the PLUGIN's own checkout, not the consumer repo (the
    plugin-cache lesson), silently pointing the reminder at the wrong calibration
    log. __file__ is legitimate ONLY to locate the sibling scripts/ module for the
    in-process compute_coverage import -- never to resolve the consumer repo root,
    which must come from `git rev-parse --show-toplevel`
    (e.g. via scripts/_repo_root.py::git_toplevel_from_cwd).
    """
    source = _HOOK_PATH.read_text(encoding="utf-8")

    assert "show-toplevel" in source or "git_toplevel_from_cwd" in source, (
        "remind_calibration.py must resolve the consumer repo root via git "
        "(git rev-parse --show-toplevel / git_toplevel_from_cwd), not __file__"
    )
