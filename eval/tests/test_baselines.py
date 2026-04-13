"""Tests for baseline JSON load/write round-trip."""

from __future__ import annotations

from pathlib import Path

from praxion_evals.regression.baselines import (
    BaselineSummary,
    load_baseline,
    utc_now,
    write_baseline,
)


def test_round_trip_preserves_fields(tmp_path: Path):
    target = tmp_path / "baseline.json"
    original = BaselineSummary(
        task_slug="demo",
        captured_at=utc_now(),
        expected_phases=("research", "architecture"),
        expected_deliverables=(".ai-work/demo/SYSTEMS_PLAN.md",),
        span_count=142,
        tool_call_count=37,
        duration_ms_p50=1250.0,
        duration_ms_p95=4800.0,
        agent_count=5,
    )
    write_baseline(original, target)
    loaded = load_baseline(target)
    assert loaded.task_slug == original.task_slug
    assert loaded.expected_phases == original.expected_phases
    assert loaded.expected_deliverables == original.expected_deliverables
    assert loaded.span_count == original.span_count
    assert loaded.duration_ms_p95 == original.duration_ms_p95


def test_optional_fields_default_to_none(tmp_path: Path):
    target = tmp_path / "baseline.json"
    minimal = BaselineSummary(task_slug="demo", captured_at=utc_now())
    write_baseline(minimal, target)
    loaded = load_baseline(target)
    assert loaded.span_count is None
    assert loaded.duration_ms_p95 is None
    assert loaded.expected_phases == ()
