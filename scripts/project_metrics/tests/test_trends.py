"""Behavioral tests for `trends.compute_trends(current, ai_state_dir)`.

Encodes the Trend Computation Policy from SYSTEMS_PLAN plus the storage-schema
ADR's schema-versioning + delta-mismatch policy. Tests are designed from the
behavioral spec; production `trends.py` is not read while authoring.

Four outcome classes from the ADR's discriminated TrendBlock union are covered:

* ``first_run`` — no prior report exists on disk.
* ``schema_mismatch`` — prior's ``schema_version`` differs at the major OR
  minor level (patch differences do NOT trigger mismatch).
* ``computed`` — prior's ``schema_version`` is major/minor-compatible; numeric
  deltas are produced per aggregate column, with a ``null_input`` sentinel
  when either side is null.
* ``no_prior_readable`` — prior file exists on disk but cannot be parsed
  (malformed JSON, truncated, missing required keys).

A fifth class exercises *most-recent-prior selection*: with multiple prior
reports on disk, the most-recent-strictly-before-current must be chosen, and
any file carrying a timestamp at or after current must be excluded.

Import strategy: each test imports ``compute_trends`` inside its body
(deferred import). This is deliberate — during the BDD/TDD RED handshake, the
``trends`` module has no ``compute_trends`` export and top-of-module imports
would break pytest collection for every test in this file simultaneously.
Deferred imports give per-test RED/GREEN resolution. See the schema-module
tests for the established precedent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixture helpers — minimal valid `Report` construction and on-disk prior
# report serialization. Each helper is pure and does no I/O unless named
# otherwise, so fixtures compose without order-dependence.
# ---------------------------------------------------------------------------


def _aggregate_kwargs(
    *,
    schema_version: str = "1.0.0",
    timestamp: str = "2026-04-23T12:00:00Z",
    sloc_total: int = 1000,
    file_count: int = 40,
    language_count: int = 3,
    ccn_p95: float | None = 7.0,
    cognitive_p95: float | None = 9.0,
    cyclic_deps: int | None = 0,
    churn_total_90d: int = 500,
    change_entropy_90d: float = 2.0,
    truck_factor: int = 2,
    hotspot_top_score: float = 100.0,
    hotspot_gini: float = 0.7,
    coverage_line_pct: float | None = 0.80,
) -> dict[str, Any]:
    """Return kwargs for AggregateBlock with sensible defaults.

    Nullable columns (`ccn_p95`, `cognitive_p95`, `cyclic_deps`,
    `coverage_line_pct`) accept ``None`` so null-delta tests can force
    specific fields to null on either side.
    """
    return {
        "schema_version": schema_version,
        "timestamp": timestamp,
        "commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
        "window_days": 90,
        "sloc_total": sloc_total,
        "file_count": file_count,
        "language_count": language_count,
        "ccn_p95": ccn_p95,
        "cognitive_p95": cognitive_p95,
        "cyclic_deps": cyclic_deps,
        "churn_total_90d": churn_total_90d,
        "change_entropy_90d": change_entropy_90d,
        "truck_factor": truck_factor,
        "hotspot_top_score": hotspot_top_score,
        "hotspot_gini": hotspot_gini,
        "coverage_line_pct": coverage_line_pct,
    }


def _build_report(**overrides: Any) -> Any:
    """Construct a `Report` with optional aggregate field overrides.

    Overrides flow through to `_aggregate_kwargs`. `Report.schema_version`
    mirrors `AggregateBlock.schema_version` (both present per the ADR).
    """
    from scripts.project_metrics.schema import AggregateBlock, Report

    agg = AggregateBlock(**_aggregate_kwargs(**overrides))
    return Report(
        schema_version=agg.schema_version,
        aggregate=agg,
        tool_availability={},
        collectors={},
    )


def _filename_from_timestamp(ts_iso: str) -> str:
    """Convert an ISO-8601 timestamp to the canonical METRICS_REPORT filename.

    ``2026-04-23T12:00:00Z`` -> ``METRICS_REPORT_2026-04-23_12-00-00.json``.
    Colons are illegal in filenames on macOS/Windows per the timestamp
    convention in the coding-style rule, so the `T`/`:` are normalized to
    `_`/`-`.
    """
    # Strip the trailing Z, split on T, replace colons with dashes.
    core = ts_iso.rstrip("Z")
    date_part, _, time_part = core.partition("T")
    time_part = time_part.replace(":", "-")
    return f"METRICS_REPORT_{date_part}_{time_part}.json"


def _write_prior_report(
    ai_state_dir: Path,
    *,
    timestamp: str,
    schema_version: str = "1.0.0",
    overrides: dict[str, Any] | None = None,
    raw_payload: dict[str, Any] | str | None = None,
) -> Path:
    """Write a prior METRICS_REPORT JSON to `ai_state_dir` and return the path.

    Two modes:

    * Default — serialize a synthesized `Report` via `scripts.project_metrics.schema.to_json`.
      `overrides` is forwarded to aggregate field overrides (e.g., to pin
      `sloc_total` for delta arithmetic in the happy-path test).
    * `raw_payload` — write arbitrary bytes or a pre-built dict directly.
      Used by the `no_prior_readable` tests to inject corrupted content
      the schema serializer would never emit.

    Filename is derived from `timestamp` via `_filename_from_timestamp` so
    filename-based timestamp parsing and embedded-timestamp parsing yield
    the same ordering (the production code is free to pick either).
    """
    ai_state_dir.mkdir(parents=True, exist_ok=True)
    path = ai_state_dir / _filename_from_timestamp(timestamp)

    if raw_payload is not None:
        if isinstance(raw_payload, str):
            path.write_text(raw_payload)
        else:
            path.write_text(json.dumps(raw_payload))
        return path

    from scripts.project_metrics.schema import to_json

    merged_overrides: dict[str, Any] = {
        "schema_version": schema_version,
        "timestamp": timestamp,
    }
    if overrides:
        merged_overrides.update(overrides)
    report = _build_report(**merged_overrides)
    path.write_bytes(to_json(report))
    return path


@pytest.fixture
def ai_state(tmp_path: Path) -> Path:
    """Return a fresh (empty) ``.ai-state/`` directory under `tmp_path`.

    Using a fixture rather than inline construction keeps every test
    hermetic: no test can pollute another's ``.ai-state/`` state.
    """
    d = tmp_path / ".ai-state"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Outcome class 1: first_run — no prior METRICS_REPORT files on disk.
# ---------------------------------------------------------------------------


class TestTrendsFirstRun:
    """Given no prior METRICS_REPORT_*.json files, `compute_trends` must
    return a ``first_run`` TrendBlock with no ``prior_report`` reference
    and no numeric deltas. The downstream UI reads this status and
    renders ``"first run — no deltas"``."""

    def test_empty_ai_state_dir_yields_first_run_status(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        current = _build_report()
        trend = compute_trends(current, ai_state)

        assert trend.status == "first_run"

    def test_empty_ai_state_dir_leaves_prior_report_unset(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        current = _build_report()
        trend = compute_trends(current, ai_state)

        assert trend.prior_report is None, (
            "first_run must not reference any prior file on disk -- "
            "the UI renders an unconditional 'first run' banner."
        )

    def test_empty_ai_state_dir_yields_no_deltas(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        current = _build_report()
        trend = compute_trends(current, ai_state)

        assert trend.deltas == {}, (
            "first_run must never fabricate numeric deltas -- the deltas "
            "map must stay empty when no prior is available."
        )

    def test_unrelated_files_in_ai_state_dir_are_ignored(self, ai_state: Path) -> None:
        """Files that do not match the METRICS_REPORT_*.json pattern must
        be invisible to the prior-report glob. Common neighbors in
        ``.ai-state/`` include `SENTINEL_LOG.md`, `DECISIONS_INDEX.md`,
        and the `METRICS_LOG.md` append log itself -- none of these are
        prior reports."""
        from scripts.project_metrics.trends import compute_trends

        (ai_state / "SENTINEL_LOG.md").write_text("# sentinel log\n")
        (ai_state / "METRICS_LOG.md").write_text("# metrics log\n")
        (ai_state / "METRICS_REPORT_summary.txt").write_text("not json\n")

        current = _build_report()
        trend = compute_trends(current, ai_state)

        assert trend.status == "first_run"
        assert trend.prior_report is None


# ---------------------------------------------------------------------------
# Outcome class 2: schema_mismatch — prior's schema differs at major or
# minor level. Patch-level differences are NOT a mismatch (tested separately).
# ---------------------------------------------------------------------------


class TestTrendsSchemaMismatchMajor:
    """A prior report whose ``schema_version`` differs at the major level
    must defer numeric delta computation. The ADR is explicit: we never
    fabricate cross-schema deltas. The TrendBlock surfaces both schema
    strings and the prior filename so the UI can render a specific
    "deferred — schema changed from X to Y" banner."""

    def test_major_version_bump_yields_schema_mismatch_status(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="2.0.0",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.status == "schema_mismatch"

    def test_major_version_bump_exposes_both_schema_strings(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="2.0.0",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.prior_schema == "2.0.0"
        assert trend.current_schema == "1.0.0"

    def test_major_version_bump_references_prior_filename(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        prior_path = _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="2.0.0",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        # prior_report may be either bare filename or relative/absolute
        # path; the contract is "the UI can surface this". Accept either
        # shape by checking the filename component.
        assert trend.prior_report is not None
        assert Path(trend.prior_report).name == prior_path.name

    def test_major_version_bump_produces_no_numeric_deltas(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="2.0.0",
            overrides={"sloc_total": 500},
        )
        current = _build_report(schema_version="1.0.0", sloc_total=1500)

        trend = compute_trends(current, ai_state)

        assert trend.deltas == {}, (
            "schema_mismatch must suppress all per-field deltas -- "
            "cross-schema numeric comparisons are meaningless."
        )

    def test_minor_version_bump_yields_schema_mismatch_status(
        self, ai_state: Path
    ) -> None:
        """Per the schema-versioning policy, minor-version differences
        trigger schema_mismatch exactly as major-version differences do.
        The ADR's "additive-only amendment" policy applies to patch-level
        bumps only; any minor bump may add columns that break numeric
        comparisons against older rows."""
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.1.0",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.status == "schema_mismatch"
        assert trend.prior_schema == "1.1.0"
        assert trend.current_schema == "1.0.0"


# ---------------------------------------------------------------------------
# Outcome class 3: patch-level differences are NOT a mismatch — normal
# delta computation proceeds.
# ---------------------------------------------------------------------------


class TestTrendsSchemaMatchPatch:
    """Patch-version differences (e.g., 1.0.0 vs 1.0.1) must NOT trigger
    schema_mismatch. The frozen-aggregate-columns contract applies at the
    major/minor level; patch bumps are reserved for non-structural fixes
    that preserve the aggregate shape."""

    def test_patch_version_difference_does_not_yield_schema_mismatch(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
        )
        current = _build_report(schema_version="1.0.1")

        trend = compute_trends(current, ai_state)

        assert trend.status != "schema_mismatch", (
            "Patch-level version differences preserve the aggregate "
            "contract -- deltas must be computed, not deferred."
        )

    def test_patch_version_difference_produces_numeric_deltas(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 800},
        )
        current = _build_report(schema_version="1.0.1", sloc_total=1000)

        trend = compute_trends(current, ai_state)

        assert trend.deltas, (
            "Patch-level compatibility must produce a non-empty deltas "
            "map -- an empty map would be indistinguishable from "
            "schema_mismatch at the UI layer."
        )


# ---------------------------------------------------------------------------
# Outcome class 4: computed — exact schema match yields numeric deltas
# with explicit null-handling sentinels.
# ---------------------------------------------------------------------------


class TestTrendsSchemaMatchExact:
    """Prior and current both at the same major/minor schema -> per-aggregate
    delta = current - prior with delta_pct = delta / prior when prior != 0.
    Null on either side yields ``{"delta": null, "reason": "null_input"}``.
    These sentinels are contract: the UI distinguishes "0 delta" (a real
    measurement) from "no delta computable" (a null on one side)."""

    def test_exact_match_yields_computed_or_nonmismatch_status(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        # The ADR's TrendBlock enumerates "computed" as the canonical
        # success status. Accept "computed" specifically here -- a looser
        # `status != "schema_mismatch"` check is in the patch-version
        # test. This assertion pins the happy-path status label.
        assert trend.status == "computed"

    def test_exact_match_computes_absolute_delta_for_sloc(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 800},
        )
        current = _build_report(schema_version="1.0.0", sloc_total=1000)

        trend = compute_trends(current, ai_state)

        assert "sloc_total" in trend.deltas
        entry = trend.deltas["sloc_total"]
        assert entry["delta"] == 200, (
            f"sloc_total delta must be 1000 - 800 = 200, got {entry!r}"
        )

    def test_exact_match_computes_delta_pct_when_prior_nonzero(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 800},
        )
        current = _build_report(schema_version="1.0.0", sloc_total=1000)

        trend = compute_trends(current, ai_state)

        entry = trend.deltas["sloc_total"]
        # 200 / 800 = 0.25 exactly (binary-representable).
        assert entry["delta_pct"] == pytest.approx(0.25)

    def test_exact_match_returns_null_delta_when_prior_field_is_null(
        self, ai_state: Path
    ) -> None:
        """If the prior side of the comparison is null, the plan mandates
        a ``{"delta": null, "reason": "null_input"}`` sentinel rather
        than fabricating a zero or omitting the key entirely."""
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"coverage_line_pct": None},
        )
        current = _build_report(schema_version="1.0.0", coverage_line_pct=0.85)

        trend = compute_trends(current, ai_state)

        entry = trend.deltas["coverage_line_pct"]
        assert entry["delta"] is None
        assert entry["reason"] == "null_input"

    def test_exact_match_returns_null_delta_when_current_field_is_null(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"coverage_line_pct": 0.85},
        )
        current = _build_report(schema_version="1.0.0", coverage_line_pct=None)

        trend = compute_trends(current, ai_state)

        entry = trend.deltas["coverage_line_pct"]
        assert entry["delta"] is None
        assert entry["reason"] == "null_input"


# ---------------------------------------------------------------------------
# Outcome class 5: no_prior_readable — prior file exists but cannot be
# parsed. The policy is "never fabricate deltas" even when the prior is
# corrupted; surface the error string so the UI can render "prior report
# unreadable — deltas skipped".
# ---------------------------------------------------------------------------


class TestTrendsNoPriorReadable:
    """Prior files that fail to parse must be surfaced explicitly rather
    than silently skipped (which would look like first_run) or silently
    errored (which would break the run). The ``no_prior_readable`` status
    carries both the filename and a non-empty error message."""

    def test_malformed_json_yields_no_prior_readable_status(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            raw_payload="{not valid json at all",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.status == "no_prior_readable"

    def test_malformed_json_references_the_offending_file(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        prior_path = _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            raw_payload="}}}truncated",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.prior_report is not None
        assert Path(trend.prior_report).name == prior_path.name

    def test_malformed_json_populates_nonempty_error_string(
        self, ai_state: Path
    ) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            raw_payload="{bad",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.error, (
            "no_prior_readable must carry a non-empty error string so "
            "the UI can render diagnostic context rather than an "
            "unexplained missing-deltas banner."
        )

    def test_missing_required_keys_yields_no_prior_readable_status(
        self, ai_state: Path
    ) -> None:
        """A JSON payload that parses but lacks the aggregate block (or
        schema_version) cannot be used as a prior for delta computation;
        it must be reported as unreadable rather than silently treated
        as first_run."""
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            raw_payload={"unrelated": "payload"},
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.status == "no_prior_readable"

    def test_malformed_json_produces_no_numeric_deltas(self, ai_state: Path) -> None:
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            raw_payload="not json",
        )
        current = _build_report(schema_version="1.0.0")

        trend = compute_trends(current, ai_state)

        assert trend.deltas == {}, (
            "no_prior_readable must suppress all numeric deltas -- the "
            "prior file content is unusable."
        )


# ---------------------------------------------------------------------------
# Outcome class 5 (selection): most-recent-strictly-prior selection among
# multiple candidate files. The runner's contract is to exclude files
# dated at or after `current.aggregate.timestamp`.
# ---------------------------------------------------------------------------


class TestTrendsMostRecentPriorSelection:
    """When multiple METRICS_REPORT_*.json files exist, the selector must
    pick the one closest to -- but strictly before -- the current run's
    timestamp. Files carrying a timestamp at or after current are excluded
    entirely (they are either the current run's own file, a future run,
    or a clock-skew anomaly; in any case they are not a valid prior)."""

    def test_three_prior_files_selects_most_recent_among_them(
        self, ai_state: Path
    ) -> None:
        """T1 < T2 < T3 all strictly before current; T3 must be selected."""
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-10T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 700},
        )
        _write_prior_report(
            ai_state,
            timestamp="2026-04-15T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 800},
        )
        t3_path = _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 900},
        )
        current = _build_report(
            timestamp="2026-04-23T12:00:00Z",
            schema_version="1.0.0",
            sloc_total=1000,
        )

        trend = compute_trends(current, ai_state)

        assert trend.prior_report is not None
        assert Path(trend.prior_report).name == t3_path.name, (
            "Among three strictly-prior files, the most recent (T3) "
            "must be selected; T1/T2 are obsolete."
        )
        # Sanity-check: sloc delta reflects T3's prior value (900), not
        # T1's (700) or T2's (800).
        assert trend.deltas["sloc_total"]["delta"] == 100

    def test_file_dated_at_or_after_current_is_excluded_from_selection(
        self, ai_state: Path
    ) -> None:
        """Given T1 < T2 < current < T3, the selector must pick T2 and
        ignore T3 entirely. T3 represents a future-timestamped or
        already-written current-run artifact and must never be chosen."""
        from scripts.project_metrics.trends import compute_trends

        _write_prior_report(
            ai_state,
            timestamp="2026-04-10T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 700},
        )
        t2_path = _write_prior_report(
            ai_state,
            timestamp="2026-04-20T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 850},
        )
        _write_prior_report(
            # T3 is after current -- must be excluded.
            ai_state,
            timestamp="2026-04-25T12:00:00Z",
            schema_version="1.0.0",
            overrides={"sloc_total": 950},
        )
        current = _build_report(
            timestamp="2026-04-23T12:00:00Z",
            schema_version="1.0.0",
            sloc_total=1000,
        )

        trend = compute_trends(current, ai_state)

        assert trend.prior_report is not None
        assert Path(trend.prior_report).name == t2_path.name, (
            "Files timestamped at or after the current run must never "
            "be selected as a prior -- T2 is the correct choice."
        )
        # Sanity-check: sloc delta reflects T2's prior value (850).
        assert trend.deltas["sloc_total"]["delta"] == 150
