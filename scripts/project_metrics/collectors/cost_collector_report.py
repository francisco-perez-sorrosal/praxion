"""Cost collector -- JSON/dict projections of the aggregate pass.

The token-totals accumulator plus every fold that turns the aggregate pass's
own data (`PipelineBucket`, `Coverage`) into the plain dict/list shapes the
runner serializes. Pure functions over in-memory values; re-exported
unchanged from `cost_collector`.

`PipelineBucket`/`Coverage` are imported only under `TYPE_CHECKING` (never at
runtime) to avoid a real circular import, since `cost_collector.py` imports
this module's functions back for its own `build_pipeline_buckets` and
`CostCollector.collect`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from scripts.project_metrics.collectors.cost_collector_read import AttributedRow

if TYPE_CHECKING:
    from scripts.project_metrics.collectors.cost_collector import Coverage, PipelineBucket

# ---------------------------------------------------------------------------
# JSON/dict projections -- the token-totals accumulator and every table fold.
# ---------------------------------------------------------------------------

_TOKEN_COMPONENT_KEYS: tuple[str, ...] = ("tokens_in", "tokens_out", "cache_read", "cache_create")


def _empty_token_totals() -> dict[str, int]:
    totals = dict.fromkeys(_TOKEN_COMPONENT_KEYS, 0)
    totals["tokens_total"] = 0
    return totals


def _accumulate_tokens(totals: dict[str, int], row: AttributedRow) -> None:
    totals["tokens_in"] += row.tokens_in
    totals["tokens_out"] += row.tokens_out
    totals["cache_read"] += row.cache_read
    totals["cache_create"] += row.cache_create
    totals["tokens_total"] += row.tokens_in + row.tokens_out + row.cache_read + row.cache_create


def _bucket_to_json(bucket: PipelineBucket) -> dict[str, Any]:
    return {
        "pipeline_slug": bucket.pipeline_slug,
        "tier": bucket.tier,
        "tier_reason": bucket.tier_reason,
        "attributed_rows": bucket.attributed_rows,
        "sessions": bucket.sessions,
        "models": sorted(bucket.models),
        "tokens": dict(bucket.tokens),
        "by_agent_type": {
            agent_type: dict(tokens) for agent_type, tokens in bucket.by_agent_type.items()
        },
    }


def _tier_projection(buckets: Sequence[PipelineBucket]) -> dict[str, Any]:
    """The per-tier table -- a fold over the same buckets, grouped by
    `tier` instead of `pipeline_slug`."""

    projection: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        entry = projection.setdefault(
            bucket.tier, {"attributed_rows": 0, "tokens": _empty_token_totals(), "pipelines": []}
        )
        entry["attributed_rows"] += bucket.attributed_rows
        for key in entry["tokens"]:
            entry["tokens"][key] += bucket.tokens[key]
        entry["pipelines"].append(bucket.pipeline_slug)
    return projection


def _agent_type_projection(buckets: Sequence[PipelineBucket]) -> dict[str, Any]:
    """The per-agent-type table -- a fold over the same buckets, grouped by
    `agent_type` instead of `pipeline_slug`."""

    projection: dict[str, dict[str, int]] = {}
    for bucket in buckets:
        for agent_type, tokens in bucket.by_agent_type.items():
            entry = projection.setdefault(agent_type, _empty_token_totals())
            for key in entry:
                entry[key] += tokens[key]
    return projection


def _coverage_to_json(coverage: Coverage) -> dict[str, Any]:
    return {
        "attributed_rows": coverage.attributed_rows,
        "total_agent_stop_rows": coverage.total_agent_stop_rows,
        "quarantine": dict(coverage.quarantine),
        "duplicate_agent_ids": list(coverage.duplicate_agent_ids),
        "sessions_durable": coverage.sessions_durable,
        "sessions_with_slug": coverage.sessions_with_slug,
        "sessions_slug_unknown": coverage.sessions_slug_unknown,
        "duplicates_dropped": coverage.duplicates_dropped,
        "sources": [
            {
                "path": source.path,
                "kind": source.kind,
                "checkout": source.checkout,
                "mtime_iso": source.mtime_iso,
                "lines_scanned": source.lines_scanned,
                "agent_stop_rows": source.agent_stop_rows,
                "attributed_rows": source.attributed_rows,
            }
            for source in coverage.sources
        ],
    }
