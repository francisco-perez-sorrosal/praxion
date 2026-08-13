"""Tests for `check_metrics_freshness.py`, including canaries that must bite.

The gate's claim is: *a metrics report that no longer describes current HEAD is
detected before its hotspots become ledger rows.* Per `rules/swe/gate-liveness.md`
a CODE gate ships proof it **fails** on a known-bad input, not merely that it
passes on the current good state — so the canaries below construct real git
histories and assert the checker flags them.

The headline canary reconstructs the incident this gate exists for: a report
ranks a file #1, a later commit rewrites that file, and the checker must flag it
while a day-based staleness rule would still call the report fresh.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_metrics_freshness import evaluate_freshness, main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures — a real git repo, because the gate's whole subject is git distance.
# ---------------------------------------------------------------------------


def _git(repo: Path, *argv: str) -> str:
    completed = subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True, check=True
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one committed file and an initialized identity."""

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "hot.py").write_text("x = 1\n")
    (root / "cold.py").write_text("y = 1\n")
    _git(root, "add", "hot.py", "cold.py")
    _git(root, "commit", "-q", "-m", "seed")
    return root


def _write_report(
    reports_dir: Path,
    *,
    stamp: str = "2026-07-29_22-11-31",
    commit: str | None = None,
    paths: list[str] | None = None,
    dirty: bool | None = False,
) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_metadata: dict[str, object] = {
        "command_version": "1.0.0",
        "python_version": "3.11.5",
        "wall_clock_seconds": 1.0,
        "window_days": 90,
        "top_n": 10,
    }
    if commit is not None:
        run_metadata["commit"] = commit
        run_metadata["generated_at"] = "2026-07-29T22:11:31+00:00"
        run_metadata["dirty"] = dirty
    payload = {
        "schema_version": "1.2.1",
        "run_metadata": run_metadata,
        "hotspots": {
            "status": "ok",
            "top_n": [
                {
                    "path": p,
                    "rank": i + 1,
                    "churn_90d": 100,
                    "complexity": 10,
                    "hotspot_score": 1000.0,
                }
                for i, p in enumerate(paths or ["hot.py"])
            ],
        },
    }
    path = reports_dir / f"METRICS_REPORT_{stamp}.json"
    path.write_text(json.dumps(payload))
    return path


# ---------------------------------------------------------------------------
# Canaries — each asserts the gate FLAGS a known-bad input.
# ---------------------------------------------------------------------------


def test_canary_flags_hotspot_rewritten_after_the_report(repo: Path, tmp_path: Path) -> None:
    """The incident this gate exists for, reconstructed end to end.

    A report ranks `hot.py` #1 at commit A. A later commit rewrites `hot.py`.
    The checker must report `stale` and name that path — otherwise the sentinel
    files debt against a file whose debt a commit already resolved.
    """

    head_at_report = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, commit=head_at_report, paths=["hot.py", "cold.py"])

    # The decomposition commit — the analogue of the real one.
    (repo / "hot.py").write_text("# decomposed\n")
    _git(repo, "add", "hot.py")
    _git(repo, "commit", "-q", "-m", "refactor: decompose hot.py")

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "stale"
    flagged = {e["path"] for e in result["hotspots_touched"]}
    assert "hot.py" in flagged, "the rewritten hotspot must be flagged"
    assert "cold.py" not in flagged, "an untouched hotspot must NOT be flagged"
    assert result["findings"][0]["kind"] == "hotspot-moved-since-report"


def test_canary_day_based_freshness_would_have_passed_this(repo: Path, tmp_path: Path) -> None:
    """The discriminating case: fresh by age, stale by commit distance.

    This is the exact gap the 14-day rule left open. The report is one day old —
    any age-based threshold calls it fresh — yet its ranked hotspot has already
    been rewritten. If this test ever passes with `status == "fresh"`, the gate
    has silently reverted to measuring time.
    """

    head_at_report = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d_%H-%M-%S")
    _write_report(reports, stamp=yesterday, commit=head_at_report, paths=["hot.py"])

    (repo / "hot.py").write_text("# rewritten\n")
    _git(repo, "add", "hot.py")
    _git(repo, "commit", "-q", "-m", "rewrite")

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["age_days"] <= 1, "precondition: the report is fresh by any day-based rule"
    assert result["status"] == "stale", "commit distance must override apparent age-freshness"


def test_canary_withholds_when_report_predates_provenance(repo: Path, tmp_path: Path) -> None:
    """A pre-provenance report must withhold, never report fresh.

    Absent provenance and confirmed-current are different claims. Collapsing
    them is how the original gap stayed invisible, so `withheld` must be a
    distinct status carrying a named reason.
    """

    reports = tmp_path / "reports"
    _write_report(reports, commit=None, paths=["hot.py"])

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "withheld"
    assert result["commits_since"] is None
    reasons = {w["field"] for w in result["withheld"]}
    assert {"commits_since", "hotspots_touched"} <= reasons
    assert any("unrecoverable" in w["reason"] for w in result["withheld"])


def test_canary_withholds_when_commit_is_unreachable(repo: Path, tmp_path: Path) -> None:
    """A commit this repo has never seen must withhold, not crash or pass."""

    reports = tmp_path / "reports"
    _write_report(reports, commit="0" * 40, paths=["hot.py"])

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "withheld"
    assert any("not present in this repository" in w["reason"] for w in result["withheld"])


def test_canary_unreadable_report_withholds(repo: Path, tmp_path: Path) -> None:
    """Malformed JSON withholds rather than reporting a clean verdict."""

    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "METRICS_REPORT_2026-07-29_22-11-31.json").write_text("{not json")

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "withheld"


# ---------------------------------------------------------------------------
# Inverse guards — the gate must NOT fire on good input.
# ---------------------------------------------------------------------------


def test_fresh_when_no_ranked_hotspot_has_moved(repo: Path, tmp_path: Path) -> None:
    """Commits that touch nothing ranked leave the report fresh.

    The inverse of the headline canary: distance alone is not staleness. A
    hundred commits elsewhere in the tree do not invalidate a hotspot ranking,
    and a gate that fired on distance would flood TD01 with noise.
    """

    head_at_report = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, commit=head_at_report, paths=["hot.py"])

    for i in range(3):
        (repo / f"unrelated_{i}.py").write_text(f"z = {i}\n")
        _git(repo, "add", f"unrelated_{i}.py")
        _git(repo, "commit", "-q", "-m", f"unrelated {i}")

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "fresh"
    assert result["commits_since"] == 3, "distance is reported as context"
    assert result["hotspots_touched"] == []


def test_absent_reports_directory_is_not_a_failure(repo: Path, tmp_path: Path) -> None:
    """A project that never ran /project-metrics is skipped, not flagged."""

    result = evaluate_freshness(repo, reports_dir=tmp_path / "nope")

    assert result["status"] == "absent"
    assert result["findings"] == []


def test_newest_report_is_the_one_judged(repo: Path, tmp_path: Path) -> None:
    """Selection is by filename timestamp, so an older stale report is ignored."""

    stale_head = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, stamp="2026-01-01_00-00-00", commit=stale_head, paths=["hot.py"])

    (repo / "hot.py").write_text("# moved\n")
    _git(repo, "add", "hot.py")
    _git(repo, "commit", "-q", "-m", "move")
    new_head = _git(repo, "rev-parse", "HEAD")
    _write_report(reports, stamp="2026-12-31_23-59-59", commit=new_head, paths=["hot.py"])

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["report"] == "METRICS_REPORT_2026-12-31_23-59-59.json"
    assert result["status"] == "fresh"


def test_dirty_capture_is_surfaced(repo: Path, tmp_path: Path) -> None:
    """A report captured on a dirty tree says so — it anchors near, not at, a commit."""

    head = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, commit=head, paths=["hot.py"], dirty=True)

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["dirty"] is True


# ---------------------------------------------------------------------------
# Classification robustness — absent-directory and malformed-filename edges.
#
# These are still "absent" / context-field paths, not new statuses, but a
# false "clean" verdict on any of them is the same un-bars-a-TD01-filing risk
# named in td-135: an existing-but-empty reports dir, or a report whose
# filename doesn't carry a parseable timestamp, must degrade gracefully
# rather than crash or silently misreport.
# ---------------------------------------------------------------------------


def test_absent_when_reports_directory_has_no_matching_reports(repo: Path, tmp_path: Path) -> None:
    """An existing but empty reports directory is `absent`, not a crash.

    Distinct from the missing-directory case above: this is the
    directory-created-but-no-report-yet path (e.g. right after `mkdir -p`
    but before the first `/project-metrics` run writes a file), which takes
    a different branch through `_latest_report` than a wholly-absent path.
    """

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "not_a_report.txt").write_text("noise")

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["status"] == "absent"
    assert result["findings"] == []
    assert "METRICS_REPORT_" in result["note"]


def test_age_days_withheld_for_non_timestamp_filename(repo: Path, tmp_path: Path) -> None:
    """A report filename with no parseable timestamp reports no age, not a crash.

    `age_days` is documented as context, never the gate — but a caller that
    does read it must see an honest `None` rather than a wrong number from a
    misparsed name. The overall verdict (`fresh`/`stale`) is unaffected,
    since that classification runs on `run_metadata.commit`, not the
    filename.
    """

    head = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, stamp="latest", commit=head, paths=["hot.py"])

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["report"] == "METRICS_REPORT_latest.json"
    assert result["age_days"] is None
    assert result["status"] == "fresh"


def test_age_days_none_for_filename_with_invalid_calendar_date(repo: Path, tmp_path: Path) -> None:
    """A syntactically-dated but calendar-invalid filename reports no age.

    The filename regex checks digit *shape* only (`\\d{2}` accepts "13" as a
    month); `strptime` is what rejects it. That gap must degrade to unknown
    age, not raise past the caller and abort the whole freshness check.
    """

    head = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, stamp="2026-13-40_25-70-99", commit=head, paths=["hot.py"])

    result = evaluate_freshness(repo, reports_dir=reports)

    assert result["age_days"] is None
    assert result["status"] == "fresh"


# ---------------------------------------------------------------------------
# CLI (`main`) — exit codes and both render modes.
#
# `evaluate_freshness` is the classification; `main` is what the sentinel
# and a human operator actually invoke, so its exit code and both render
# paths (`--json` and human) are part of the gate's contract, not incidental
# plumbing.
# ---------------------------------------------------------------------------


def test_main_json_reports_fresh_status_and_exits_zero(repo: Path, tmp_path: Path, capsys) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, commit=head, paths=["hot.py"])

    exit_code = main(["--repo-root", str(repo), "--reports-dir", str(reports), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "fresh"


def test_main_human_output_lists_stale_hotspot_and_exits_one(
    repo: Path, tmp_path: Path, capsys
) -> None:
    head_at_report = _git(repo, "rev-parse", "HEAD")
    reports = tmp_path / "reports"
    _write_report(reports, commit=head_at_report, paths=["hot.py"])

    (repo / "hot.py").write_text("# decomposed\n")
    _git(repo, "add", "hot.py")
    _git(repo, "commit", "-q", "-m", "refactor: decompose hot.py")

    exit_code = main(["--repo-root", str(repo), "--reports-dir", str(reports)])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "STALE #1 hot.py" in out


def test_main_human_output_shows_withheld_reason(repo: Path, tmp_path: Path, capsys) -> None:
    """A withheld verdict renders its reason in the human format, not a blank line."""

    reports = tmp_path / "reports"
    _write_report(reports, commit=None, paths=["hot.py"])

    exit_code = main(["--repo-root", str(repo), "--reports-dir", str(reports)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "WITHHELD commits_since" in out


def test_main_refuses_plugin_cache_repo_root(tmp_path: Path) -> None:
    """A resolved repo root inside an installed-plugin cache is refused (exit 2).

    This is the hard backstop from `_repo_root.is_plugin_cache_path` — the
    gate must never evaluate or mutate shared plugin state.
    """

    fake_plugin_root = tmp_path / "plugins" / "cache" / "acme" / "widget" / "1.0.0"

    exit_code = main(["--repo-root", str(fake_plugin_root)])

    assert exit_code == 2
