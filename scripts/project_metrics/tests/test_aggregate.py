"""Behavioral tests for ``aggregate.compose_aggregate``.

Validates that per-collector ``CollectorResult.data`` payloads get lifted into
the frozen ``AggregateBlock`` columns. Missing / skipped collectors leave
fields at their runner-seeded defaults rather than raising.
"""

from __future__ import annotations

from scripts.project_metrics.collectors.base import CollectorResult
from scripts.project_metrics.schema import AggregateBlock, Report, TrendBlock


def _build_report(**collector_data: dict | None) -> Report:
    """Construct a Report with runner-style defaults and the given collectors."""

    aggregate = AggregateBlock(
        schema_version="1.0.0",
        timestamp="2026-04-24T00:00:00+00:00",
        commit_sha="a" * 40,
        window_days=90,
        sloc_total=0,
        file_count=0,
        language_count=0,
        ccn_p95=None,
        cognitive_p95=None,
        cyclic_deps=None,
        churn_total_90d=0,
        change_entropy_90d=0.0,
        truck_factor=0,
        hotspot_top_score=None,
        hotspot_gini=None,
        coverage_line_pct=None,
    )
    collectors = {}
    for name, data in collector_data.items():
        if data is None:
            collectors[name] = {
                "status": "skipped",
                "reason": "tool_unavailable",
                "tool": name,
            }
        else:
            collectors[name] = CollectorResult(status="ok", data=data)
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors=collectors,
        trends=TrendBlock(status="first_run"),
    )


class TestAggregateLiftsCollectorData:
    def test_git_lifts_churn_entropy_truck_factor_and_file_count(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            git={
                "churn_total_90d": 1234,
                "change_entropy_90d": 12.5,
                "truck_factor": 3,
                "file_count": 42,
            },
        )
        result = compose_aggregate(report)

        assert result.aggregate.churn_total_90d == 1234
        assert result.aggregate.change_entropy_90d == 12.5
        assert result.aggregate.truck_factor == 3
        assert result.aggregate.file_count == 42

    def test_scc_lifts_sloc_language_count_and_overrides_file_count(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            git={"file_count": 42},
            scc={"sloc_total": 5000, "language_count": 3, "file_count": 50},
        )
        result = compose_aggregate(report)

        assert result.aggregate.sloc_total == 5000
        assert result.aggregate.language_count == 3
        # scc's file_count wins over git's when both present
        assert result.aggregate.file_count == 50

    def test_lizard_lifts_ccn_p95_from_nested_aggregate(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            lizard={"aggregate": {"ccn_p95": 7.5, "ccn_p75": 3.0}},
        )
        result = compose_aggregate(report)

        assert result.aggregate.ccn_p95 == 7.5

    def test_complexipy_lifts_cognitive_p95(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            complexipy={"aggregate": {"cognitive_p95": 12.0}},
        )
        result = compose_aggregate(report)

        assert result.aggregate.cognitive_p95 == 12.0

    def test_pydeps_lifts_cyclic_deps(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            pydeps={"aggregate": {"cyclic_deps": 2, "total_modules": 10}},
        )
        result = compose_aggregate(report)

        assert result.aggregate.cyclic_deps == 2

    def test_coverage_lifts_line_pct(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(
            coverage={"line_pct": 0.73, "status": "ok"},
        )
        result = compose_aggregate(report)

        assert result.aggregate.coverage_line_pct == 0.73


class TestAggregateHandlesMissingCollectors:
    def test_missing_collector_leaves_column_at_default(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report()  # no collectors at all
        result = compose_aggregate(report)

        # Defaults preserved; no exception raised.
        assert result.aggregate.sloc_total == 0
        assert result.aggregate.ccn_p95 is None
        assert result.aggregate.coverage_line_pct is None

    def test_skip_marker_collector_leaves_column_at_default(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(lizard=None, complexipy=None)  # None → skip marker
        result = compose_aggregate(report)

        assert result.aggregate.ccn_p95 is None
        assert result.aggregate.cognitive_p95 is None


class TestAggregateNonDestructive:
    def test_does_not_mutate_input_report(self) -> None:
        from scripts.project_metrics.aggregate import compose_aggregate

        report = _build_report(git={"churn_total_90d": 999})
        # Snapshot the original aggregate before the call
        original_churn = report.aggregate.churn_total_90d

        compose_aggregate(report)

        # Original report unchanged
        assert report.aggregate.churn_total_90d == original_churn == 0
