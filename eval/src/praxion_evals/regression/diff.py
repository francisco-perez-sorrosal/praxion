"""Compare a current trace summary against a committed baseline."""

from __future__ import annotations

from dataclasses import dataclass, field

from praxion_evals.regression.baselines import BaselineSummary
from praxion_evals.regression.trace_reader import TraceSummary

# Tolerance for numeric drift on span/tool counts before we call it a drift finding.
_COUNT_DRIFT_THRESHOLD = 0.15  # 15%
_DURATION_DRIFT_THRESHOLD = 0.30  # 30%


@dataclass(frozen=True)
class DiffResult:
    """Structured regression finding set."""

    task_slug: str
    findings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_drift(self) -> bool:
        return bool(self.findings)


def _drift_ratio(current: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return abs(current - baseline) / baseline


def compare_summaries(
    current: TraceSummary,
    baseline: BaselineSummary,
) -> DiffResult:
    """Return drift findings where numeric deltas exceed thresholds."""
    findings: list[str] = []

    if baseline.span_count is not None and baseline.span_count > 0:
        ratio = _drift_ratio(current.span_count, baseline.span_count)
        if ratio > _COUNT_DRIFT_THRESHOLD:
            findings.append(
                f"span_count drift: current={current.span_count} "
                f"baseline={baseline.span_count} (Δ={ratio * 100:.0f}%)"
            )

    if baseline.tool_call_count is not None and baseline.tool_call_count > 0:
        ratio = _drift_ratio(current.tool_call_count, baseline.tool_call_count)
        if ratio > _COUNT_DRIFT_THRESHOLD:
            findings.append(
                f"tool_call_count drift: current={current.tool_call_count} "
                f"baseline={baseline.tool_call_count} (Δ={ratio * 100:.0f}%)"
            )

    if baseline.agent_count is not None and baseline.agent_count > 0:
        ratio = _drift_ratio(current.agent_count, baseline.agent_count)
        if ratio > _COUNT_DRIFT_THRESHOLD:
            findings.append(
                f"agent_count drift: current={current.agent_count} "
                f"baseline={baseline.agent_count} (Δ={ratio * 100:.0f}%)"
            )

    if (
        baseline.duration_ms_p95 is not None
        and baseline.duration_ms_p95 > 0
        and current.duration_ms_p95 is not None
    ):
        ratio = _drift_ratio(current.duration_ms_p95, baseline.duration_ms_p95)
        if ratio > _DURATION_DRIFT_THRESHOLD:
            findings.append(
                f"duration_ms_p95 drift: current={current.duration_ms_p95:.0f} "
                f"baseline={baseline.duration_ms_p95:.0f} (Δ={ratio * 100:.0f}%)"
            )

    return DiffResult(task_slug=baseline.task_slug, findings=tuple(findings))
