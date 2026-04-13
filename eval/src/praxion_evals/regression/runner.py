"""Top-level regression eval entrypoint — never mutates traces."""

from __future__ import annotations

from pathlib import Path

from praxion_evals.regression.baselines import BaselineSummary, load_baseline
from praxion_evals.regression.diff import DiffResult, compare_summaries
from praxion_evals.regression.trace_reader import (
    TraceSummary,
    read_current_summary,
)


def run_regression(
    baseline_path: Path,
    current_summary: TraceSummary | None = None,
    project_name: str | None = None,
) -> DiffResult:
    """Load a baseline, fetch (or accept) a current summary, and compare.

    ``current_summary`` exists so tests can inject a synthetic TraceSummary
    without touching Phoenix. In production, callers pass only ``baseline_path``
    and the function pulls the current summary lazily.
    """
    baseline: BaselineSummary = load_baseline(baseline_path)
    if current_summary is None:
        summary = read_current_summary(project_name or baseline.task_slug)
    else:
        summary = current_summary
    return compare_summaries(summary, baseline)
