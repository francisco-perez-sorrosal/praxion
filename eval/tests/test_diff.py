"""Tests for the baseline diff comparator."""

from __future__ import annotations

from praxion_evals.regression.baselines import BaselineSummary
from praxion_evals.regression.diff import compare_summaries
from praxion_evals.regression.trace_reader import TraceSummary


def test_no_drift_when_counts_match_baseline():
    current = TraceSummary(project_name="demo", span_count=100, tool_call_count=20)
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at="2026-04-12T00:00:00Z",
        span_count=100,
        tool_call_count=20,
    )
    result = compare_summaries(current, baseline)
    assert result.has_drift is False
    assert result.findings == ()


def test_span_count_drift_detected_above_threshold():
    current = TraceSummary(project_name="demo", span_count=200)
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at="2026-04-12T00:00:00Z",
        span_count=100,
    )
    result = compare_summaries(current, baseline)
    assert result.has_drift is True
    assert any("span_count drift" in f for f in result.findings)


def test_tool_call_count_drift_detected():
    current = TraceSummary(project_name="demo", span_count=100, tool_call_count=5)
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at="2026-04-12T00:00:00Z",
        span_count=100,
        tool_call_count=50,
    )
    result = compare_summaries(current, baseline)
    assert any("tool_call_count drift" in f for f in result.findings)


def test_duration_p95_drift_detected():
    current = TraceSummary(
        project_name="demo",
        span_count=100,
        duration_ms_p95=5000.0,
    )
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at="2026-04-12T00:00:00Z",
        span_count=100,
        duration_ms_p95=1000.0,
    )
    result = compare_summaries(current, baseline)
    assert any("duration_ms_p95 drift" in f for f in result.findings)
