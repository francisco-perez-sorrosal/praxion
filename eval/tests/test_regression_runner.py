"""Regression runner: ensures the comparator never tries to write back to Phoenix."""

from __future__ import annotations

from pathlib import Path

import pytest

from praxion_evals.regression.baselines import (
    BaselineSummary,
    utc_now,
    write_baseline,
)
from praxion_evals.regression.runner import run_regression
from praxion_evals.regression.trace_reader import TraceSummary


def test_runner_with_injected_summary_reports_drift(tmp_path: Path):
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at=utc_now(),
        span_count=100,
    )
    path = tmp_path / "baseline.json"
    write_baseline(baseline, path)

    current = TraceSummary(project_name="demo", span_count=300)
    result = run_regression(path, current_summary=current)
    assert result.has_drift is True
    assert result.task_slug == "demo"


def test_runner_never_calls_phoenix_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If the runner ever tries to mutate Phoenix, explode loudly."""
    baseline = BaselineSummary(
        task_slug="demo",
        captured_at=utc_now(),
        span_count=100,
    )
    path = tmp_path / "baseline.json"
    write_baseline(baseline, path)

    # Monkey-patch px.Client.log_evaluations to fail loudly if called.
    import sys
    from types import SimpleNamespace

    def _fail(*_args: object, **_kwargs: object):
        raise AssertionError("regression eval must not call log_evaluations")

    fake_client = SimpleNamespace(log_evaluations=_fail, get_spans_dataframe=lambda **_: None)
    monkeypatch.setitem(
        sys.modules,
        "phoenix",
        SimpleNamespace(Client=lambda *_a, **_k: fake_client),
    )

    current = TraceSummary(project_name="demo", span_count=100)
    result = run_regression(path, current_summary=current)
    assert result.has_drift is False
