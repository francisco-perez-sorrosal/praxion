"""Read Phoenix traces for a project and distill them to a summary.

Phoenix imports are **lazy** — ``from phoenix`` only fires inside
``read_current_summary()``. The import pattern mirrors ``trajectory_eval.py``
lines 57-73 (preserved shim) and guarantees that importing
``praxion_evals.regression`` does not pay Phoenix cold-import cost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceSummary:
    """Lightweight distillation of Phoenix trace data for one project."""

    project_name: str
    span_count: int = 0
    tool_call_count: int = 0
    agent_count: int = 0
    duration_ms_p50: float | None = None
    duration_ms_p95: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def summarize_dataframe(project_name: str, spans_df: Any) -> TraceSummary:
    """Distil a pandas DataFrame of spans into a ``TraceSummary``.

    Separated from ``read_current_summary`` so tests can monkey-patch Phoenix
    and feed a canned DataFrame without touching the network.
    """
    if spans_df is None or getattr(spans_df, "empty", True):
        return TraceSummary(project_name=project_name, notes=("no-spans-found",))

    span_count = int(len(spans_df))

    # Tool calls: OpenInference TOOL spans.
    tool_call_count = 0
    if "span_kind" in spans_df.columns:
        tool_call_count = int((spans_df["span_kind"] == "TOOL").sum())
    elif "attributes.openinference.span.kind" in spans_df.columns:
        tool_call_count = int((spans_df["attributes.openinference.span.kind"] == "TOOL").sum())

    # Agent count: distinct AGENT spans by name, when available.
    agent_count = 0
    if "span_kind" in spans_df.columns and "name" in spans_df.columns:
        agent_mask = spans_df["span_kind"] == "AGENT"
        agent_count = int(spans_df.loc[agent_mask, "name"].nunique())

    # Duration percentiles: derived from start/end timestamps when present.
    duration_p50: float | None = None
    duration_p95: float | None = None
    if "start_time" in spans_df.columns and "end_time" in spans_df.columns:
        try:
            durations = (spans_df["end_time"] - spans_df["start_time"]).dt.total_seconds() * 1000.0
            duration_p50 = float(durations.quantile(0.5))
            duration_p95 = float(durations.quantile(0.95))
        except (AttributeError, TypeError):
            # Start/end aren't datetimes — skip silently; summary still valid.
            pass

    return TraceSummary(
        project_name=project_name,
        span_count=span_count,
        tool_call_count=tool_call_count,
        agent_count=agent_count,
        duration_ms_p50=duration_p50,
        duration_ms_p95=duration_p95,
    )


def read_current_summary(project_name: str) -> TraceSummary:
    """Pull current spans from Phoenix and return the distilled summary.

    Performs a lazy import of ``phoenix`` — any ImportError surfaces as an
    empty summary with a note, so callers never crash on missing Phoenix.
    """
    try:
        # Lazy import — see module docstring. Typed as Any so pyright does not
        # require phoenix stubs at type-check time (we don't ship them).
        import importlib

        px: Any = importlib.import_module("phoenix")
    except ImportError:
        return TraceSummary(
            project_name=project_name,
            notes=("phoenix-not-installed",),
        )

    try:
        client = px.Client()
        spans_df = client.get_spans_dataframe(project_name=project_name)
    except Exception as exc:  # pragma: no cover — network/env-dependent
        return TraceSummary(
            project_name=project_name,
            notes=(f"phoenix-client-error: {exc}",),
        )

    return summarize_dataframe(project_name, spans_df)
