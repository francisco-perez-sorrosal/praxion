"""Tier 1 regression eval — Phoenix trace diff against a baseline JSON summary.

Phoenix imports are LAZY (deferred to the function call site), so importing
this package has zero Phoenix cost.
"""

from praxion_evals.regression.baselines import (
    BaselineSummary,
    load_baseline,
    write_baseline,
)
from praxion_evals.regression.diff import DiffResult, compare_summaries
from praxion_evals.regression.runner import run_regression
from praxion_evals.regression.trace_reader import (
    TraceSummary,
    read_current_summary,
    summarize_dataframe,
)

__all__ = [
    "BaselineSummary",
    "DiffResult",
    "TraceSummary",
    "compare_summaries",
    "load_baseline",
    "read_current_summary",
    "run_regression",
    "summarize_dataframe",
    "write_baseline",
]
