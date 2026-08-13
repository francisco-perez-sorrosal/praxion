"""Aggregate / Top-N / Trends / Per-language section rendering.

Four sections that read the numeric ``AggregateBlock``, hot-spot list, trend
deltas, and per-language breakdown off ``Report`` and render each to its own
Markdown block. Each ``render_*`` function is a section-sized entry point
``report.py`` composes into the full document.
"""

from __future__ import annotations

from typing import Any

from scripts.project_metrics._report_format import (
    EM_DASH,
    NOT_APPLICABLE_MARKER,
    NULL_CELL,
    error_marker,
    fmt_delta_cell,
    fmt_delta_pct_cell,
    fmt_float_2,
    fmt_float_raw,
    fmt_int,
    fmt_pct,
    timeout_marker,
    unavailable_marker,
)
from scripts.project_metrics.schema import AGGREGATE_COLUMNS, Report

__all__ = [
    "render_aggregate_summary",
    "render_top_n",
    "render_trends",
    "render_per_language",
]


# Aggregate-column formatting — mirrors the AggregateBlock field types.
# Strings render raw. Integers render raw. Floats render :.2f. Nulls render
# as the appropriate skip marker based on tool_availability status.
_AGGREGATE_FORMATTERS: dict[str, Any] = {
    "schema_version": fmt_float_raw,
    "timestamp": fmt_float_raw,
    "commit_sha": fmt_float_raw,
    "window_days": fmt_int,
    "sloc_total": fmt_int,
    "file_count": fmt_int,
    "language_count": fmt_int,
    "ccn_p95": fmt_float_2,
    "cognitive_p95": fmt_float_2,
    "cyclic_deps": fmt_int,
    "churn_total_90d": fmt_int,
    "change_entropy_90d": fmt_float_2,
    "truck_factor": fmt_int,
    "hotspot_top_score": fmt_float_2,
    "hotspot_gini": fmt_float_2,
    "coverage_line_pct": fmt_float_2,
}


# Which tool each nullable aggregate column depends on. When the column is
# None, the renderer looks up the tool's availability status and emits the
# matching skip marker. Columns missing from this map that carry None fall
# back to the bare em-dash.
_AGGREGATE_COLUMN_TO_TOOL: dict[str, str] = {
    "ccn_p95": "lizard",
    "cognitive_p95": "complexipy",
    "cyclic_deps": "pydeps",
    "coverage_line_pct": "coverage",
}


# ---------------------------------------------------------------------------
# Aggregate Summary section — paragraph + 16-column table.
# ---------------------------------------------------------------------------


def render_aggregate_summary(report: Report) -> str:
    aggregate = report.aggregate
    lines = ["## Aggregate Summary", ""]
    lines.append(_render_aggregate_paragraph(report))
    lines.append("")
    lines.append("| Column | Value |")
    lines.append("| --- | --- |")
    for column in AGGREGATE_COLUMNS:
        raw = getattr(aggregate, column)
        formatter = _AGGREGATE_FORMATTERS.get(column, fmt_float_raw)
        if raw is None:
            rendered = _skip_marker_for_aggregate_column(column, report)
        else:
            rendered = formatter(raw)
        lines.append(f"| {column} | {rendered} |")
    lines.append("")
    return "\n".join(lines)


def _render_aggregate_paragraph(report: Report) -> str:
    """Render the narrative one-paragraph preamble above the aggregate table."""

    aggregate = report.aggregate
    sloc = aggregate.sloc_total
    files = aggregate.file_count
    langs = aggregate.language_count
    churn = aggregate.churn_total_90d
    entropy = fmt_float_2(aggregate.change_entropy_90d)
    truck = aggregate.truck_factor
    top_score = fmt_float_2(aggregate.hotspot_top_score)
    gini = fmt_float_2(aggregate.hotspot_gini)
    coverage = aggregate.coverage_line_pct

    coverage_sentence = (
        "Coverage is not computed."
        if coverage is None
        else f"Line coverage is {fmt_pct(coverage)}."
    )
    return (
        f"The repository carries {sloc} SLOC across {files} files in "
        f"{langs} languages; 90-day churn totals {churn} changes with "
        f"change entropy {entropy}. Truck factor is {truck}; top hot-spot "
        f"score is {top_score} with Gini {gini}. {coverage_sentence}"
    )


def _skip_marker_for_aggregate_column(column: str, report: Report) -> str:
    """Return the skip marker for a null aggregate column based on tool status."""

    tool = _AGGREGATE_COLUMN_TO_TOOL.get(column)
    if tool is None:
        return NULL_CELL
    avail = report.tool_availability.get(tool)
    if avail is None:
        return NULL_CELL
    if avail.status == "unavailable":
        return unavailable_marker(tool)
    if avail.status == "not_applicable":
        return NOT_APPLICABLE_MARKER
    if avail.status == "error":
        return error_marker(avail.reason or "error")
    if avail.status == "timeout":
        return timeout_marker(0)
    return NULL_CELL


# ---------------------------------------------------------------------------
# Top-N section.
# ---------------------------------------------------------------------------


def render_top_n(report: Report) -> str:
    rows = list(report.hotspots.get("top_n", []))
    n = len(rows)
    lines = [
        f"## Top-{n} Hot-spots",
        "",
        "| # | Path | Churn | Complexity | Score |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        rank = row.get("rank", "")
        path = row.get("path", "")
        churn = fmt_int(row.get("churn_90d"))
        complexity = fmt_float_raw(row.get("complexity"))
        score = fmt_float_2(row.get("hotspot_score"))
        lines.append(f"| {rank} | `{path}` | {churn} | {complexity} | {score} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trends section — three branches (first_run / schema_mismatch / computed).
# ---------------------------------------------------------------------------


def render_trends(report: Report) -> str:
    trends = report.trends
    lines = ["## Trends", ""]

    if trends.status == "first_run":
        lines.append(f"_first run {EM_DASH} no deltas_")
        lines.append("")
        return "\n".join(lines)

    if trends.status == "schema_mismatch":
        prior = trends.prior_schema or "?"
        current = trends.current_schema or "?"
        lines.append(
            f"⚠ Trend delta deferred {EM_DASH} prior report used schema "
            f"{prior}, current is {current}."
        )
        lines.append("")
        return "\n".join(lines)

    if trends.status == "no_prior_readable":
        reason = trends.error or "unreadable prior report"
        lines.append(f"_trend delta deferred {EM_DASH} {reason}_")
        lines.append("")
        return "\n".join(lines)

    # computed path — delta table
    lines.append("| Metric | Current | Prior | Delta | Delta % |")
    lines.append("| --- | --- | --- | --- | --- |")
    for metric, payload in trends.deltas.items():
        current = fmt_delta_cell(payload.get("current"))
        prior = fmt_delta_cell(payload.get("prior"))
        delta = fmt_delta_cell(payload.get("delta"))
        delta_pct = fmt_delta_pct_cell(payload.get("delta_pct"))
        lines.append(f"| {metric} | {current} | {prior} | {delta} | {delta_pct} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-language Breakdown section.
# ---------------------------------------------------------------------------


def render_per_language(report: Report) -> str:
    lines = ["## Per-language Breakdown", ""]
    lines.append("| Language | Files | SLOC | CCN p95 | Cognitive p95 |")
    lines.append("| --- | --- | --- | --- | --- |")

    languages = _collect_language_names(report)
    scc_breakdown = _extract_scc_breakdown(report)
    lizard_lang_ccn = _extract_lizard_lang_p95(report)
    cognitive_avail = report.tool_availability.get("complexipy")
    cognitive_cell_default = _cognitive_cell_default(cognitive_avail)

    for language in languages:
        files, sloc = _lookup_language_counts(language, scc_breakdown)
        ccn = lizard_lang_ccn.get(language)
        cognitive = cognitive_cell_default
        lines.append(
            f"| {language} | {files} | {sloc} | "
            f"{fmt_float_2(ccn) if ccn is not None else NULL_CELL} | "
            f"{cognitive if language == 'Python' else NULL_CELL} |"
        )
    lines.append("")
    return "\n".join(lines)


def _namespace_data(report: Report, name: str) -> dict[str, Any]:
    """Return the flat data dict for a collector namespace regardless of carrier shape.

    When the runner skips a collector (unavailable / not-applicable), it
    stores a 3-key dict under `report.collectors[name]` instead of a
    `CollectorResult`. Callers that want to read data fields should
    normalize via this helper rather than branch on carrier type.
    Returns an empty dict when the namespace is absent.
    """

    entry = report.collectors.get(name)
    if entry is None:
        return {}
    if isinstance(entry, dict):
        return entry
    return entry.data or {}


def _collect_language_names(report: Report) -> list[str]:
    data = _namespace_data(report, "scc")
    if not data:
        return []
    if "language_breakdown" in data and isinstance(data["language_breakdown"], dict):
        return list(data["language_breakdown"].keys())
    if "languages" in data and isinstance(data["languages"], list):
        return list(data["languages"])
    return []


def _extract_scc_breakdown(report: Report) -> dict[str, dict[str, int]]:
    data = _namespace_data(report, "scc")
    breakdown = data.get("language_breakdown")
    if isinstance(breakdown, dict):
        return breakdown
    return {}


def _extract_lizard_lang_p95(report: Report) -> dict[str, float]:
    data = _namespace_data(report, "lizard")
    per_lang = data.get("per_language_ccn_p95")
    if isinstance(per_lang, dict):
        return per_lang
    # Fallback: map the global p95 to Python when no per-language split exists.
    ccn_p95 = data.get("ccn_p95")
    if ccn_p95 is not None:
        return {"Python": float(ccn_p95)}
    return {}


def _lookup_language_counts(language: str, breakdown: dict[str, dict[str, int]]) -> tuple[str, str]:
    entry = breakdown.get(language)
    if isinstance(entry, dict):
        files = fmt_int(entry.get("file_count"))
        sloc = fmt_int(entry.get("sloc"))
        return files, sloc
    return NULL_CELL, NULL_CELL


def _cognitive_cell_default(avail: Any) -> str:
    if avail is None:
        return NULL_CELL
    if avail.status == "unavailable":
        return unavailable_marker("complexipy")
    if avail.status == "not_applicable":
        return NOT_APPLICABLE_MARKER
    return NULL_CELL
