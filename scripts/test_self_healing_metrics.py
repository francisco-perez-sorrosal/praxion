"""Tests for self_healing_metrics.py — the P6 metrics-baseline collector.

The metric math (`compute_metrics`) is a pure function over a fetched-payload
dict, so every case here feeds a hand-built `raw` fixture and a fixed `now` —
no `gh`, no network, deterministic. Rendering + append-log are exercised against
tmp_path. Import mirrors scripts/test_finalize_adrs.py (importlib.util so the
script needs no sys.path entry).
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent / "self_healing_metrics.py"


def _load():
    spec = importlib.util.spec_from_file_location("self_healing_metrics", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shm = _load()

NOW = datetime(2026, 7, 28, 0, 0, 0, tzinfo=timezone.utc)  # since (90d) = 2026-04-29


def _run(created: str, conclusion: str = "success", branch: str = "main") -> dict:
    return {
        "createdAt": created,
        "conclusion": conclusion,
        "status": "completed",
        "headBranch": branch,
        "databaseId": 1,
    }


def _pr(head: str, created: str, merged: str | None = None, state: str = "OPEN") -> dict:
    return {
        "headRefName": head,
        "createdAt": created,
        "mergedAt": merged,
        "closedAt": None,
        "state": state,
        "number": 1,
        "labels": [],
    }


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_parse_ts_handles_z_suffix_and_none():
    assert shm.parse_ts("2026-07-26T05:04:36Z") == datetime(
        2026, 7, 26, 5, 4, 36, tzinfo=timezone.utc
    )
    assert shm.parse_ts(None) is None
    assert shm.parse_ts("not-a-date") is None


def test_in_window_boundary():
    since = datetime(2026, 4, 29, tzinfo=timezone.utc)
    assert shm._in_window("2026-07-26T00:00:00Z", since) is True
    assert shm._in_window("2026-01-01T00:00:00Z", since) is False
    assert shm._in_window(None, since) is False


def test_tally_conclusions_falls_back_to_status_then_unknown():
    runs = [
        _run("x", "success"),
        _run("x", "failure"),
        _run("x", "success"),
        {"status": "completed"},
        {},
    ]
    tally = shm._tally_conclusions(runs)
    assert tally["success"] == 2
    assert tally["failure"] == 1
    assert tally["completed"] == 1  # no conclusion key -> status
    assert tally["unknown"] == 1  # neither


def test_median_even_and_odd_and_empty():
    assert shm._median([]) is None
    assert shm._median([5.0]) == 5.0
    assert shm._median([1.0, 3.0, 2.0]) == 2.0
    assert shm._median([1.0, 2.0, 3.0, 4.0]) == 2.5


# --------------------------------------------------------------------------- #
# compute_metrics — the load-bearing surface
# --------------------------------------------------------------------------- #
def test_empty_raw_yields_zero_counts_and_null_rates():
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["fix_success"]["autofix_runs_total"] == 0
    assert m["fix_success"]["fix_prs_opened"] == 0
    assert m["fix_success"]["fix_success_rate"] is None  # no divide-by-zero
    assert m["gate"]["runs_total"] == 0
    assert m["time_to_green"]["median_hours"] is None


def test_deferred_fields_are_null_with_notes_never_fabricated_zero():
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["gate"]["verdicts_classified"] is None
    assert m["gate"]["_note"]  # deferred field carries a reason, never a bare null
    assert m["credit_burn"]["cursor_credits"] is None
    assert m["credit_burn"]["_note"]
    assert m["override_rate"]["value"] is None
    assert m["override_rate"]["_note"]
    assert m["cost_per_fix"]["value"] is None
    assert m["cost_per_fix"]["_note"]


def test_attempts_exclude_skipped_cancelled_and_unconcluded():
    runs = [
        _run("2026-07-26T00:00:00Z", "success"),
        _run("2026-07-26T00:00:00Z", "failure"),
        _run("2026-07-26T00:00:00Z", "skipped"),
        _run("2026-07-26T00:00:00Z", "cancelled"),
        {"createdAt": "2026-07-26T00:00:00Z", "conclusion": None},
    ]  # in-progress
    attempts = shm._attempts(runs)
    assert len(attempts) == 2  # success + failure only
    assert shm._count_failures(attempts) == 1


def test_autofix_attempts_strip_skips_from_saturated_count():
    # 3 skips + 1 success + 1 failure -> total 5, attempts 2, failures 1.
    raw = {
        "autofix_runs": [
            _run("2026-07-26T00:00:00Z", c)
            for c in ("skipped", "skipped", "skipped", "success", "failure")
        ],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    fs = shm.compute_metrics(raw, window_days=90, now=NOW)["fix_success"]
    assert fs["autofix_runs_total"] == 5
    assert fs["autofix_attempts"] == 2
    assert fs["autofix_failures"] == 1


def test_provenance_flags_saturated_sources():
    raw = {
        "autofix_runs": [_run("2026-07-26T00:00:00Z") for _ in range(3)],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    prov = shm._provenance(raw, [], window_days=90, now=NOW, commit_sha="abc1234", limit=3)
    assert "autofix_runs" in prov["saturated_sources"]  # count 3 == limit 3
    assert "gate_runs" not in prov["saturated_sources"]  # count 0 < limit


def test_window_excludes_old_runs():
    raw = {
        "autofix_runs": [_run("2026-07-26T00:00:00Z"), _run("2026-01-01T00:00:00Z")],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["fix_success"]["autofix_runs_total"] == 1  # old one filtered out


def test_fix_pr_prefixes_and_success_rate():
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [
            _pr(
                "ci-autofix/123",
                "2026-07-26T00:00:00Z",
                merged="2026-07-26T06:00:00Z",
                state="MERGED",
            ),
            _pr("issue-autofix/45-autofix", "2026-07-26T00:00:00Z"),  # opened, not merged
            _pr(
                "dependabot/npm/x", "2026-07-26T00:00:00Z", merged="2026-07-26T01:00:00Z"
            ),  # not a fixer branch
        ],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    fs = m["fix_success"]
    assert fs["fix_prs_opened"] == 2  # dependabot excluded
    assert fs["fix_prs_merged"] == 1
    assert fs["fix_success_rate"] == 0.5


def test_declines_counted_within_window():
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [
            _pr("dependabot/x", "2026-07-26T00:00:00Z"),
            _pr("dependabot/y", "2026-01-01T00:00:00Z"),
        ],
        "all_prs": [],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["fix_success"]["declines_total"] == 1


def test_default_branch_decline_issues_are_counted():
    """A decline recorded as a labelled ISSUE counts toward declines.

    The default-branch autofix surface has no PR to label, so it records a
    decline as an issue. That surface's fixer crash now exits green via
    `continue-on-error`, which removes it from `autofix_failures` — if the
    issue were not counted here, a degrading fixer would look like an
    improving one. The in-window PR decline is the control: it proves the
    totals are summed across both surfaces rather than one replacing the
    other, and the out-of-window issue proves the window filter still applies.
    """
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [_pr("dependabot/x", "2026-07-26T00:00:00Z")],
        "declined_issues": [
            {
                "number": 1,
                "title": "CI autofix declined: run 111",
                "createdAt": "2026-07-26T00:00:00Z",
            },
            {
                "number": 2,
                "title": "CI autofix declined: run 222",
                "createdAt": "2026-01-01T00:00:00Z",
            },
        ],
        "all_prs": [],
    }
    fs = shm.compute_metrics(raw, window_days=90, now=NOW)["fix_success"]
    assert fs["declines_prs"] == 1, "the PR-surface control must still be counted"
    assert fs["declines_issues"] == 1, "the out-of-window decline issue must be filtered"
    assert fs["declines_total"] == 2, "totals must sum both surfaces, not replace one"


def test_declines_absent_issue_key_degrades_to_zero():
    """A payload predating the issue query counts zero issue declines rather
    than raising — an older snapshot must stay readable."""
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [_pr("dependabot/x", "2026-07-26T00:00:00Z")],
        "all_prs": [],
    }
    fs = shm.compute_metrics(raw, window_days=90, now=NOW)["fix_success"]
    assert fs["declines_issues"] == 0
    assert fs["declines_total"] == 1


def test_time_to_green_median_from_merged_fix_prs():
    raw = {
        "autofix_runs": [],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [
            _pr(
                "ci-autofix/1",
                "2026-07-26T00:00:00Z",
                merged="2026-07-26T06:00:00Z",
                state="MERGED",
            ),
            _pr(
                "ci-autofix/2",
                "2026-07-26T00:00:00Z",
                merged="2026-07-26T02:00:00Z",
                state="MERGED",
            ),
        ],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["time_to_green"]["sample_size"] == 2
    assert m["time_to_green"]["median_hours"] == 4.0  # (6 + 2) / 2


def test_gate_conclusion_tally():
    raw = {
        "autofix_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
        "gate_runs": [
            _run("2026-07-26T00:00:00Z", "success"),
            _run("2026-07-26T00:00:00Z", "success"),
            _run("2026-07-26T00:00:00Z", "failure"),
        ],
    }
    m = shm.compute_metrics(raw, window_days=90, now=NOW)
    assert m["gate"]["runs_total"] == 3
    assert m["gate"]["runs_by_conclusion"] == {"success": 2, "failure": 1}


# --------------------------------------------------------------------------- #
# rendering + log
# --------------------------------------------------------------------------- #
def _sample_metrics():
    raw = {
        "autofix_runs": [_run("2026-07-26T00:00:00Z", "failure")],
        "gate_runs": [],
        "issue_autofix_runs": [],
        "declined_prs": [],
        "all_prs": [],
    }
    return shm.compute_metrics(raw, window_days=90, now=NOW)


def _sample_provenance():
    return shm._provenance(
        {
            "autofix_runs": [],
            "gate_runs": [],
            "issue_autofix_runs": [],
            "declined_prs": [],
            "all_prs": [],
        },
        [],
        window_days=90,
        now=NOW,
        commit_sha="abc1234",
        limit=200,
    )


def test_render_md_and_json_are_strings_with_key_headers():
    md = shm.render_md(_sample_metrics(), _sample_provenance())
    assert "Self-Healing Loop Metrics" in md
    assert "Cross-model gate" in md
    js = shm.render_json(_sample_metrics(), _sample_provenance())
    assert '"provenance"' in js
    assert '"metrics"' in js


def test_render_outputs_end_with_trailing_newline():
    # The "all files end with a newline" convention (end-of-file-fixer) — a
    # committed snapshot must not be rewritten by the commit gate.
    assert shm.render_json(_sample_metrics(), _sample_provenance()).endswith("\n")
    assert shm.render_md(_sample_metrics(), _sample_provenance()).endswith("\n")


def test_append_log_writes_header_once_then_appends(tmp_path):
    log = tmp_path / "SELF_HEALING_LOG.md"
    metrics, prov = _sample_metrics(), _sample_provenance()
    shm.append_log(log, shm.log_row(metrics, prov, "SELF_HEALING_REPORT_x.md"))
    shm.append_log(log, shm.log_row(metrics, prov, "SELF_HEALING_REPORT_y.md"))
    text = log.read_text()
    assert text.count("schema_version | generated_at") == 1  # header exactly once
    # Each row renders the report name as a markdown link [name](name) — one row each.
    assert text.count("[SELF_HEALING_REPORT_x.md](SELF_HEALING_REPORT_x.md)") == 1
    assert text.count("[SELF_HEALING_REPORT_y.md](SELF_HEALING_REPORT_y.md)") == 1
