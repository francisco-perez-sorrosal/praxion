"""Read/write baseline JSON summaries at `.ai-state/evals/baselines/`.

A baseline is a small JSON document — NOT a raw trace dump — per dec-040. The
schema is intentionally narrow so baselines are cheap to commit and review:

```
{
  "task_slug": "phase3-quality-automation",
  "expected_phases": ["research", "architecture", "planning", "implementation", "verification"],
  "expected_deliverables": [".ai-work/<slug>/SYSTEMS_PLAN.md", ...],
  "expected_exit_status": "pass",
  "span_count": 142,
  "tool_call_count": 37,
  "duration_ms_p50": 1250,
  "duration_ms_p95": 4800,
  "agent_count": 5,
  "captured_at": "2026-04-12T18:00:00Z"
}
```

Numeric fields are optional; only ``task_slug`` and ``captured_at`` are required.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class BaselineSummary:
    """One committed baseline for a task-slug pipeline."""

    task_slug: str
    captured_at: str
    expected_phases: tuple[str, ...] = field(default_factory=tuple)
    expected_deliverables: tuple[str, ...] = field(default_factory=tuple)
    expected_exit_status: str = "pass"
    span_count: int | None = None
    tool_call_count: int | None = None
    duration_ms_p50: float | None = None
    duration_ms_p95: float | None = None
    agent_count: int | None = None


def load_baseline(path: Path) -> BaselineSummary:
    """Read a baseline JSON file into a ``BaselineSummary``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return BaselineSummary(
        task_slug=data["task_slug"],
        captured_at=data["captured_at"],
        expected_phases=tuple(data.get("expected_phases", ())),
        expected_deliverables=tuple(data.get("expected_deliverables", ())),
        expected_exit_status=data.get("expected_exit_status", "pass"),
        span_count=data.get("span_count"),
        tool_call_count=data.get("tool_call_count"),
        duration_ms_p50=data.get("duration_ms_p50"),
        duration_ms_p95=data.get("duration_ms_p95"),
        agent_count=data.get("agent_count"),
    )


def write_baseline(baseline: BaselineSummary, path: Path) -> None:
    """Persist a baseline JSON file, creating parent directories as needed."""
    payload = {k: v for k, v in asdict(baseline).items() if v is not None}
    # Convert tuples to lists for JSON serialisation.
    for key in ("expected_phases", "expected_deliverables"):
        if key in payload:
            payload[key] = list(payload[key])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    """ISO 8601 UTC timestamp suitable for ``captured_at``."""
    return datetime.now(UTC).isoformat()
