"""Canonical JSON schema: dataclasses, SCHEMA_VERSION, and aggregate column contract.

The aggregate-block column set is **frozen on first release** by the schema ADR.
The 16 columns enumerated in `AGGREGATE_COLUMNS` are the canonical time-series
axis for `METRICS_LOG.md`; any drift would produce ragged log charts and invalidate
trend-delta computation. The test suite asserts this tuple verbatim against a
hardcoded golden copy — reorder at your peril.

Serialization is deterministic by contract: `to_json(report)` must return
byte-identical output for byte-identical input. Downstream consumers (delta
diffing, content-hash-based storage, golden-file tests) rely on this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any

# `CollectorResult` is re-exported from the protocol layer (collectors/base.py)
# as the single source of truth. The schema module owns the canonical JSON
# shape; the protocol module owns the collector output wrapper. Re-exporting
# here keeps `schema.CollectorResult` a valid import for consumers that type
# `Report.collectors` values without forcing them to reach into the protocol
# package for the concrete type.
from scripts.project_metrics.collectors.base import CollectorResult

__all__ = [
    "SCHEMA_VERSION",
    "AGGREGATE_COLUMNS",
    "AggregateBlock",
    "ToolAvailability",
    "CollectorResult",
    "RunMetadata",
    "TrendBlock",
    "Report",
    "to_json",
    "aggregate_header_for_log",
]


SCHEMA_VERSION = "1.0.0"


# Frozen aggregate-block column order — matches the schema ADR row-by-row.
# This tuple IS the authoritative declaration order for both
# `AggregateBlock` field order and the `METRICS_LOG.md` table header.
# Reordering requires an ADR amendment.
AGGREGATE_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "timestamp",
    "commit_sha",
    "window_days",
    "sloc_total",
    "file_count",
    "language_count",
    "ccn_p95",
    "cognitive_p95",
    "cyclic_deps",
    "churn_total_90d",
    "change_entropy_90d",
    "truck_factor",
    "hotspot_top_score",
    "hotspot_gini",
    "coverage_line_pct",
)


@dataclass(frozen=True)
class AggregateBlock:
    """The 16 frozen columns that feed `METRICS_LOG.md`.

    Field declaration order MUST match `AGGREGATE_COLUMNS`. Nullable columns
    carry `None` when the underlying collector is unavailable or not applicable.
    """

    schema_version: str
    timestamp: str
    commit_sha: str
    window_days: int
    sloc_total: int
    file_count: int
    language_count: int
    ccn_p95: float | None
    cognitive_p95: float | None
    cyclic_deps: int | None
    churn_total_90d: int
    change_entropy_90d: float
    truck_factor: int
    hotspot_top_score: float | None
    hotspot_gini: float | None
    coverage_line_pct: float | None


@dataclass(frozen=True)
class ToolAvailability:
    """Per-tool resolution outcome recorded once per run.

    `status` is one of: `available`, `unavailable`, `not_applicable`,
    `error`, `timeout`. Other fields carry per-status detail (version,
    reason, hint, traceback_excerpt, timeout_seconds, ...). The
    `tool_availability` block in the root JSON is a mapping from tool name
    (string) to this record.

    Per-collector *content* states like `no_artifact` or `stale` (coverage
    artifact absent vs present-but-stale) live inside the collector's own
    namespace block (e.g., `coverage.status`), not here. Tool availability
    tracks whether the tool ran; namespace status tracks what the tool found.
    """

    status: str
    version: str | None = None
    reason: str | None = None
    hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunMetadata:
    """Execution context for one /project-metrics invocation."""

    command_version: str
    python_version: str
    wall_clock_seconds: float
    window_days: int
    top_n: int


@dataclass(frozen=True)
class TrendBlock:
    """Tagged union for the trends block, discriminated by `status`.

    Possible `status` values:
      - `first_run` — no prior report existed; `prior` is `None`.
      - `schema_mismatch` — prior schema major/minor differs; numeric deltas
        intentionally absent. `prior_schema`, `current_schema`, `prior_report`
        populated; `deltas` is empty.
      - `computed` (normal) — prior schema compatible; `prior_report` set,
        `deltas` populated with per-aggregate-column values.
      - `no_prior_readable` — prior file existed but failed to parse; `error`
        populated; numeric deltas absent.

    Representing this as a single dataclass with a `status` discriminator is
    simpler to serialize than a class hierarchy and yields a flat JSON shape.
    """

    status: str
    prior_report: str | None = None
    prior_schema: str | None = None
    current_schema: str | None = None
    error: str | None = None
    deltas: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Report:
    """Root canonical report — the single source of truth for one run.

    The JSON rendering of this dataclass is what downstream consumers (UI,
    trends, future agents) read. The MD rendering is derived from the JSON;
    the append-only `METRICS_LOG.md` row is derived from `aggregate`.
    """

    schema_version: str
    aggregate: AggregateBlock
    tool_availability: dict[str, ToolAvailability]
    collectors: dict[str, CollectorResult]
    hotspots: dict[str, Any] = field(default_factory=dict)
    trends: TrendBlock = field(default_factory=lambda: TrendBlock(status="first_run"))
    run_metadata: RunMetadata | None = None


def to_json(report: Report) -> bytes:
    """Serialize `report` to deterministic UTF-8 JSON bytes.

    Same input -> same output bytes on every call. Keys are sorted alphabetically
    at every nesting level; separators are the compact `(",", ":")` pair so
    whitespace drift cannot change the hash. Returned as `bytes` (not `str`) so
    callers can write to disk or compute a content hash without re-encoding.
    """

    payload = asdict(report)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def aggregate_header_for_log() -> str:
    """Return the pipe-separated markdown table header for `METRICS_LOG.md`.

    The header is derived from `AGGREGATE_COLUMNS` plus a trailing
    `report_file` link column, so there is no way for the log header and the
    aggregate-column contract to drift. Includes the separator row (a second
    line of pipes and dashes) — callers write the two-line block verbatim when
    creating a new `METRICS_LOG.md`.
    """

    columns = list(AGGREGATE_COLUMNS) + ["report_file"]
    header_row = "| " + " | ".join(columns) + " |"
    separator_row = "| " + " | ".join(["---"] * len(columns)) + " |"
    return header_row + "\n" + separator_row
