"""Tests for check_calibration_coverage.py -- calibration-coverage detector.

Gate-liveness contract (rules/swe/gate-liveness.md): this is a CODE gate
detecting uncalibrated pipeline work (Standard/Full-tier merges that landed
after the newest calibration_log.md row). It ships canaries — tests that feed
a known-lapsed calibration state and assert the gate bites (exit 1 / covered:false).
A detector that only passes when the log is current is indistinguishable from no gate.

All tests are hermetic: each builds a temporary git repo with controlled history
and an injected .ai-state/calibration_log.md (controlled timestamps). The real
Praxion calibration_log.md is never read; both the lapsed and the current state
are exercised via injected fixtures.

Import strategy: deferred per-test-body via importlib.util so pytest collection
succeeds before the module exists (BDD/TDD concurrent-execution RED handshake).
Each test fails individually with FileNotFoundError until the implementation lands.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent / "check_calibration_coverage.py"

# Calibration log header matching the real .ai-state/calibration_log.md format.
_CALIBRATION_HEADER = """\
# Calibration Log

Append-only tier-selection log. Each Standard/Full pipeline appends one row.

| Timestamp | Task | Signals | Recommended Tier | Actual Tier | Source | Retrospective |
|-----------|------|---------|------------------|-------------|--------|----------------|
"""


# -- Module loading -----------------------------------------------------------


def _load_module() -> Any:
    """Load check_calibration_coverage.py without requiring it on sys.path."""
    # Evict any cached version so tests that reload in the same session are clean.
    sys.modules.pop("check_calibration_coverage", None)
    spec = importlib.util.spec_from_file_location("check_calibration_coverage", _SCRIPT_PATH)
    assert spec is not None, f"Could not locate {_SCRIPT_PATH} — the detector script must exist"
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_calibration_coverage"] = mod
    spec.loader.exec_module(mod)
    return mod


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
    # Append to ensure the file always changes (different content per commit).
    current = sentinel_file.read_text() if sentinel_file.exists() else ""
    sentinel_file.write_text(current + f"{message}\n", encoding="utf-8")
    _git(repo, "add", "dummy.txt")
    _git(repo, "commit", "-m", message)


# -- Tests --------------------------------------------------------------------


def test_reports_under_coverage_when_pipeline_merged_since_last_calibration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Standard/Full pipeline commits after the newest calibration row trigger under-coverage.

    Scenario: calibration_log.md has a far-past date (2025-01-01); two feat: commits
    exist "now" (today). git log --since=2025-01-01 returns both; the detector flags
    under-coverage and --check exits 1.
    """
    _init_repo(tmp_path)
    _write_calibration_log(tmp_path, "2025-01-01")
    _git(tmp_path, "add", ".ai-state")
    _git(tmp_path, "commit", "-m", "chore: add calibration baseline")
    _make_commit(tmp_path, "feat: add authentication service")
    _make_commit(tmp_path, "feat: add payment gateway integration")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 1
    ), "Two feat: commits after calibration date must trigger under-coverage (exit 1)"


def test_no_warning_when_log_is_current(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A calibration log dated in the future suppresses false under-coverage warnings.

    No-false-positive control: calibration_log.md newest row at 2030-01-01; git log
    --since=2030-01-01 returns no commits (none come from the future). Detector must
    exit 0 even when feat: commits exist in the repo.
    """
    _init_repo(tmp_path)
    _write_calibration_log(tmp_path, "2030-01-01")
    _git(tmp_path, "add", ".ai-state")
    _git(tmp_path, "commit", "-m", "chore: baseline with current calibration")
    _make_commit(tmp_path, "feat: some pipeline work already covered")
    _make_commit(tmp_path, "feat: more pipeline work also covered")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert (
        exc.value.code == 0
    ), "Current calibration log (future timestamp) must not report under-coverage"


def test_no_warning_on_docs_or_chore_only_merges(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """docs: and chore: commits are not Standard/Full pipeline work and must not trigger the gate.

    Scenario: calibration log is old (2025-01-01) but every commit since is docs: or chore:.
    The detector filters by feat:/fix: prefix; no pipeline work means exit 0.
    """
    _init_repo(tmp_path)
    _write_calibration_log(tmp_path, "2025-01-01")
    _git(tmp_path, "add", ".ai-state")
    _git(tmp_path, "commit", "-m", "chore: add calibration baseline")
    _make_commit(tmp_path, "docs: update README")
    _make_commit(tmp_path, "docs: revise architecture documentation")
    _make_commit(tmp_path, "chore: upgrade CI action pins")
    _make_commit(tmp_path, "chore: bump dependency versions")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 0, (
        "docs:/chore: only merges must not trigger under-coverage — "
        "only feat:/fix: pipeline commits count as uncalibrated work"
    )


def test_runs_to_verdict_without_sentinel(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The calibration coverage detector is standalone: it never invokes sentinel.

    The dependency direction is sentinel-calls-detector, not detector-calls-sentinel.
    Verified behaviorally (exits with a definite code without sentinel infra) and
    structurally (source has no sentinel import or reference).
    """
    _init_repo(tmp_path)
    _write_calibration_log(tmp_path, "2030-01-01")
    _git(tmp_path, "add", ".ai-state")
    _git(tmp_path, "commit", "-m", "chore: baseline")

    mod = _load_module()

    # Behavioral: exits with a definite verdict without needing sentinel running.
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path)])
    assert exc.value.code in {
        0,
        1,
    }, "Detector must produce a definite exit code — 0 (covered) or 1 (under-coverage)"

    # Structural: source must not import sentinel or invoke it as a subprocess.
    # (A docstring noting "called by sentinel CA03" is fine and expected.)
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert (
        "import sentinel" not in source
    ), "check_calibration_coverage.py must not import sentinel as a module"
    assert (
        "agents/sentinel.md" not in source
    ), "check_calibration_coverage.py must not subprocess-invoke agents/sentinel.md"


def test_canary_stale_log_bites(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Gate-liveness canary: known-lapsed calibration state must yield covered=false.

    A gate that never fires on known-bad input is indistinguishable from no gate
    (rules/swe/gate-liveness.md). This canary feeds a definite known-bad fixture —
    far-past calibration date plus one feat: and one fix: commit — and asserts the
    JSON output flags under-coverage with an uncalibrated commit count of at least 2.
    """
    _init_repo(tmp_path)
    _write_calibration_log(tmp_path, "2025-01-01")
    _git(tmp_path, "add", ".ai-state")
    _git(tmp_path, "commit", "-m", "chore: add calibration baseline")
    _make_commit(tmp_path, "feat: ship authentication module (Standard pipeline)")
    _make_commit(tmp_path, "fix: patch payment race condition (Standard pipeline)")

    mod = _load_module()
    with pytest.raises(SystemExit):
        mod.main(["--repo-root", str(tmp_path), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["covered"] is False, (
        "Known-lapsed calibration state (far-past date + 2 pipeline commits) "
        "must report covered=false"
    )
    assert (
        payload["uncalibrated_commits"] >= 2
    ), "Must count at least 2 uncalibrated pipeline commits in the known-bad canary fixture"


def test_exits_zero_when_no_calibration_log_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Absent calibration_log.md triggers skip-with-INFO, not an under-coverage warning.

    Conditional-activation on absent substrate: a project that has never logged a
    calibration row has no baseline to compare against. The detector must exit 0
    (INFO note only) rather than false-firing on a missing substrate.
    """
    _init_repo(tmp_path)
    # No .ai-state/calibration_log.md written intentionally.
    _make_commit(tmp_path, "feat: initial commit — no calibration log exists yet")

    mod = _load_module()
    with pytest.raises(SystemExit) as exc:
        mod.main(["--repo-root", str(tmp_path), "--check"])

    assert exc.value.code == 0, (
        "Absent calibration_log.md must exit 0 (skip-with-INFO), "
        "not WARN/FAIL — no substrate means no verdict"
    )
