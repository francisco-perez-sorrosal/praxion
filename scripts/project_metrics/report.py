"""Markdown renderer that projects the canonical JSON report into a human-readable view.

Two public entry points:

* ``render_markdown(report) -> str`` — produces a human-readable MD string
  with a deterministic nine-section order. Byte-stable modulo the single
  ``Generated at <timestamp>`` line, which embeds wall-clock time.
* ``render_json(report) -> bytes`` — produces the deterministic JSON bytes
  whose root is the flat shape the downstream UI consumes:
  ``{"git": {...}, "scc": {...}, ...}`` at root rather than nested under
  ``{"collectors": {...}}``. The flattening is a render-layer concern —
  the runner intentionally emits the nested shape and this module flattens
  it at render time.

Skip-marker phrasing (public UX contract — em-dash U+2014):

* Unavailable: ``_not computed — install <tool>_``
* NotApplicable: ``_not applicable for this repository_``
* Error: ``_not computed — <reason>_``
* Timeout: ``_not computed — timed out after <N>s_``

These exact strings appear wherever a skipped collector would otherwise
contribute data (deep dive, aggregate cells, per-language cells).

Null values in numeric cells render as a single em-dash ``—`` (U+2014).
Never the Python literal ``"None"`` or ``"null"`` or the empty string.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from scripts.project_metrics.schema import (
    AGGREGATE_COLUMNS,
    Report,
)

__all__ = ["render_markdown", "render_json"]


# ---------------------------------------------------------------------------
# Public-UX string constants — em-dash (U+2014) usage is part of the contract.
# ---------------------------------------------------------------------------

_EM_DASH = "—"
_NULL_CELL = _EM_DASH
_NOT_APPLICABLE_MARKER = "_not applicable for this repository_"


def _unavailable_marker(tool: str) -> str:
    """Return the italic skip marker for an Unavailable collector."""

    return f"_not computed {_EM_DASH} install {tool}_"


def _error_marker(reason: str) -> str:
    """Return the italic skip marker for an error-status collector."""

    return f"_not computed {_EM_DASH} {reason}_"


def _timeout_marker(seconds: float | int) -> str:
    """Return the italic skip marker for a timed-out collector."""

    return f"_not computed {_EM_DASH} timed out after {seconds}s_"


# ---------------------------------------------------------------------------
# Reserved root JSON keys — collector names must not shadow these.
# ---------------------------------------------------------------------------

_RESERVED_ROOT_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "aggregate",
        "tool_availability",
        "hotspots",
        "trends",
        "run_metadata",
    }
)


# ---------------------------------------------------------------------------
# Install-to-improve: short human-readable description per tool, appended
# in parentheses to the install-hint line. These are stable blurbs tied to
# the tool, not dynamic per-run content.
# ---------------------------------------------------------------------------

_TOOL_INSTALL_BLURB: dict[str, str] = {
    "complexipy": "cognitive complexity per function",
    "lizard": "cross-language cyclomatic complexity",
    "pydeps": "Python import graph + cyclic SCC detection",
    "scc": "source lines of code + language breakdown",
    "coverage": "line coverage from coverage.xml / lcov.info",
    "git": "commits, authors, churn, change entropy",
}


# ---------------------------------------------------------------------------
# Deep-Dive per-collector label/format map. For each collector, the map
# enumerates the data-dict keys we surface and the human-readable label +
# formatting we apply. Keys absent from the collector's data dict are
# silently skipped; the renderer degrades gracefully when a collector's
# payload is lighter than advertised.
# ---------------------------------------------------------------------------


def _fmt_int(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    return str(int(value))


def _fmt_float_2(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    return f"{float(value):.2f}"


def _fmt_float_raw(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    return str(value)


def _fmt_list_csv(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


# Per-collector deep-dive rendering. Each entry is (key, label, formatter).
_DEEP_DIVE_LAYOUT: dict[str, tuple[tuple[str, str, Any], ...]] = {
    "git": (
        ("commits_in_window", "Total commits in window", _fmt_int),
        ("unique_authors", "Unique authors", _fmt_int),
        ("change_entropy", "Change entropy", _fmt_float_2),
    ),
    "scc": (
        ("files_counted", "Files counted", _fmt_int),
        ("sloc_total", "SLOC total", _fmt_int),
        ("languages", "Languages", _fmt_list_csv),
    ),
    "lizard": (
        ("functions_analyzed", "Functions analyzed", _fmt_int),
        ("ccn_p95", "CCN p95", _fmt_float_2),
        ("ccn_max", "CCN max", _fmt_float_raw),
    ),
    "complexipy": (
        ("functions_analyzed", "Functions analyzed", _fmt_int),
        ("cognitive_p95", "Cognitive p95", _fmt_float_2),
        ("cognitive_max", "Cognitive max", _fmt_float_raw),
    ),
    "pydeps": (
        ("modules", "Modules", _fmt_int),
        ("cyclic_sccs", "Cyclic SCCs", _fmt_int),
    ),
    "coverage": (
        ("line_coverage_pct", "Line coverage %", _fmt_float_2),
        ("files_covered", "Files covered", _fmt_int),
    ),
}


# Aggregate-column formatting — mirrors the AggregateBlock field types.
# Strings render raw. Integers render raw. Floats render :.2f. Nulls render
# as the appropriate skip marker based on tool_availability status.
_AGGREGATE_FORMATTERS: dict[str, Any] = {
    "schema_version": _fmt_float_raw,
    "timestamp": _fmt_float_raw,
    "commit_sha": _fmt_float_raw,
    "window_days": _fmt_int,
    "sloc_total": _fmt_int,
    "file_count": _fmt_int,
    "language_count": _fmt_int,
    "ccn_p95": _fmt_float_2,
    "cognitive_p95": _fmt_float_2,
    "cyclic_deps": _fmt_int,
    "churn_total_90d": _fmt_int,
    "change_entropy_90d": _fmt_float_2,
    "truck_factor": _fmt_int,
    "hotspot_top_score": _fmt_float_2,
    "hotspot_gini": _fmt_float_2,
    "coverage_line_pct": _fmt_float_2,
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
# Public render_markdown entry point.
# ---------------------------------------------------------------------------


def render_markdown(report: Report) -> str:
    """Render ``report`` as a deterministic nine-section Markdown document."""

    sections: list[str] = [
        _render_header(report),
        _render_tool_availability(report),
        _render_install_to_improve(report),
        _render_aggregate_summary(report),
        _render_top_n(report),
        _render_trends(report),
        _render_deep_dive(report),
        _render_per_language(report),
        _render_run_metadata(report),
    ]
    # Each section already ends with one newline (joined from lines ending
    # with ""), so joining with "\n" produces one blank line between every
    # section. No trailing "\n" is appended — the final section's terminal
    # newline is the file-terminating newline.
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Header section.
# ---------------------------------------------------------------------------


def _render_header(report: Report) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    aggregate = report.aggregate
    lines = [
        "# Project Metrics Report",
        "",
        f"Generated at {generated_at}",
        "",
        f"- Commit: `{aggregate.commit_sha}`",
        f"- Schema version: `{report.schema_version}`",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool Availability section.
# ---------------------------------------------------------------------------


def _render_tool_availability(report: Report) -> str:
    lines = [
        "## Tool Availability",
        "",
        "| Tool | Status | Version | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for name, avail in report.tool_availability.items():
        version = avail.version if avail.version else _EM_DASH
        detail = avail.reason if avail.reason else _EM_DASH
        lines.append(f"| {name} | {avail.status} | {version} | {detail} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Install-to-improve section — Unavailable tools only.
# ---------------------------------------------------------------------------


def _render_install_to_improve(report: Report) -> str:
    lines = ["## Install to improve", ""]
    for name, avail in report.tool_availability.items():
        if avail.status != "unavailable":
            continue
        hint = avail.hint or ""
        blurb = _TOOL_INSTALL_BLURB.get(name)
        if blurb:
            lines.append(f"- `{name}`: `{hint}` ({blurb})")
        else:
            lines.append(f"- `{name}`: `{hint}`")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aggregate Summary section — paragraph + 16-column table.
# ---------------------------------------------------------------------------


def _render_aggregate_summary(report: Report) -> str:
    aggregate = report.aggregate
    lines = ["## Aggregate Summary", ""]
    lines.append(_render_aggregate_paragraph(report))
    lines.append("")
    lines.append("| Column | Value |")
    lines.append("| --- | --- |")
    for column in AGGREGATE_COLUMNS:
        raw = getattr(aggregate, column)
        formatter = _AGGREGATE_FORMATTERS.get(column, _fmt_float_raw)
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
    entropy = _fmt_float_2(aggregate.change_entropy_90d)
    truck = aggregate.truck_factor
    top_score = _fmt_float_2(aggregate.hotspot_top_score)
    gini = _fmt_float_2(aggregate.hotspot_gini)
    coverage = aggregate.coverage_line_pct

    coverage_sentence = (
        "Coverage is not computed."
        if coverage is None
        else f"Line coverage is {_fmt_float_2(coverage)}%."
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
        return _NULL_CELL
    avail = report.tool_availability.get(tool)
    if avail is None:
        return _NULL_CELL
    if avail.status == "unavailable":
        return _unavailable_marker(tool)
    if avail.status == "not_applicable":
        return _NOT_APPLICABLE_MARKER
    if avail.status == "error":
        return _error_marker(avail.reason or "error")
    if avail.status == "timeout":
        return _timeout_marker(0)
    return _NULL_CELL


# ---------------------------------------------------------------------------
# Top-N section.
# ---------------------------------------------------------------------------


def _render_top_n(report: Report) -> str:
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
        churn = _fmt_int(row.get("churn_90d"))
        complexity = _fmt_float_raw(row.get("complexity"))
        score = _fmt_float_2(row.get("hotspot_score"))
        lines.append(f"| {rank} | `{path}` | {churn} | {complexity} | {score} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trends section — three branches (first_run / schema_mismatch / computed).
# ---------------------------------------------------------------------------


def _render_trends(report: Report) -> str:
    trends = report.trends
    lines = ["## Trends", ""]

    if trends.status == "first_run":
        lines.append(f"_first run {_EM_DASH} no deltas_")
        lines.append("")
        return "\n".join(lines)

    if trends.status == "schema_mismatch":
        prior = trends.prior_schema or "?"
        current = trends.current_schema or "?"
        lines.append(
            f"⚠ Trend delta deferred {_EM_DASH} prior report used schema "
            f"{prior}, current is {current}."
        )
        lines.append("")
        return "\n".join(lines)

    if trends.status == "no_prior_readable":
        reason = trends.error or "unreadable prior report"
        lines.append(f"_trend delta deferred {_EM_DASH} {reason}_")
        lines.append("")
        return "\n".join(lines)

    # computed path — delta table
    lines.append("| Metric | Current | Prior | Delta | Delta % |")
    lines.append("| --- | --- | --- | --- | --- |")
    for metric, payload in trends.deltas.items():
        current = _fmt_delta_cell(payload.get("current"))
        prior = _fmt_delta_cell(payload.get("prior"))
        delta = _fmt_delta_cell(payload.get("delta"))
        delta_pct = _fmt_delta_pct_cell(payload.get("delta_pct"))
        lines.append(f"| {metric} | {current} | {prior} | {delta} | {delta_pct} |")
    lines.append("")
    return "\n".join(lines)


def _fmt_delta_cell(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fmt_delta_pct_cell(value: Any) -> str:
    if value is None:
        return _NULL_CELL
    return f"{float(value):.2f}%"


# ---------------------------------------------------------------------------
# Per-collector Deep Dive section.
# ---------------------------------------------------------------------------


def _render_deep_dive(report: Report) -> str:
    lines = ["## Per-collector Deep Dive", ""]
    for name, result in report.collectors.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.extend(_render_collector_body(name, result, report))
        lines.append("")
    return "\n".join(lines)


def _render_collector_body(name: str, result: Any, report: Report) -> list[str]:
    """Return body lines for one collector's deep-dive subsection."""

    avail = report.tool_availability.get(name)
    if avail is not None and avail.status == "unavailable":
        return [_unavailable_marker(name)]
    if avail is not None and avail.status == "not_applicable":
        return [_NOT_APPLICABLE_MARKER]
    if result.status == "error":
        # Namespace carries a skip marker when the runner/collector produced
        # a uniform skip payload. Otherwise emit a generic error marker.
        data = result.data or {}
        if isinstance(data, dict) and data.get("status") == "skipped":
            # Distinguish unavailable vs not_applicable via tool_availability.
            if avail is not None and avail.status == "unavailable":
                return [_unavailable_marker(name)]
            if avail is not None and avail.status == "not_applicable":
                return [_NOT_APPLICABLE_MARKER]
            return [_unavailable_marker(name)]
        reason = str(data.get("reason", "error")) if isinstance(data, dict) else "error"
        return [_error_marker(reason)]
    if result.status == "timeout":
        seconds = 0
        if isinstance(result.data, dict):
            seconds = result.data.get("timeout_seconds", 0)
        return [_timeout_marker(seconds)]

    # status == ok / partial — render bullet list from data per layout map.
    layout = _DEEP_DIVE_LAYOUT.get(name)
    if layout is None:
        return _render_generic_bullets(result.data)
    bullets: list[str] = []
    data = result.data or {}
    for key, label, formatter in layout:
        if key not in data:
            continue
        rendered = formatter(data[key])
        bullets.append(f"- {label}: {rendered}")
    if not bullets:
        return _render_generic_bullets(data)
    return bullets


def _render_generic_bullets(data: Any) -> list[str]:
    """Fallback renderer when no layout is registered for a collector."""

    if not isinstance(data, dict) or not data:
        return [_NULL_CELL]
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            rendered = _fmt_list_csv(value)
        elif isinstance(value, float):
            rendered = _fmt_float_2(value)
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return lines


# ---------------------------------------------------------------------------
# Per-language Breakdown section.
# ---------------------------------------------------------------------------


def _render_per_language(report: Report) -> str:
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
            f"{_fmt_float_2(ccn) if ccn is not None else _NULL_CELL} | "
            f"{cognitive if language == 'Python' else _NULL_CELL} |"
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


def _lookup_language_counts(
    language: str, breakdown: dict[str, dict[str, int]]
) -> tuple[str, str]:
    entry = breakdown.get(language)
    if isinstance(entry, dict):
        files = _fmt_int(entry.get("file_count"))
        sloc = _fmt_int(entry.get("sloc"))
        return files, sloc
    return _NULL_CELL, _NULL_CELL


def _cognitive_cell_default(avail: Any) -> str:
    if avail is None:
        return _NULL_CELL
    if avail.status == "unavailable":
        return _unavailable_marker("complexipy")
    if avail.status == "not_applicable":
        return _NOT_APPLICABLE_MARKER
    return _NULL_CELL


# ---------------------------------------------------------------------------
# Run Metadata section.
# ---------------------------------------------------------------------------


def _render_run_metadata(report: Report) -> str:
    lines = ["## Run Metadata", ""]
    meta = report.run_metadata
    if meta is None:
        lines.append(_NULL_CELL)
        lines.append("")
        return "\n".join(lines)
    lines.append(f"- Command version: {meta.command_version}")
    lines.append(f"- Python version: {meta.python_version}")
    lines.append(f"- Wall clock: {meta.wall_clock_seconds:.2f}s")
    lines.append(f"- Window days: {meta.window_days}")
    lines.append(f"- Top-N: {meta.top_n}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public render_json entry point — flatten collectors to root.
# ---------------------------------------------------------------------------


def render_json(report: Report) -> bytes:
    """Serialize ``report`` to deterministic UTF-8 JSON bytes with a flat root.

    Flattens ``report.collectors`` so each collector namespace lands at the
    JSON root next to ``schema_version``, ``aggregate``, ``tool_availability``,
    ``hotspots``, ``trends``, and ``run_metadata``. A collector name that
    collides with one of those reserved keys raises ``ValueError`` — the
    downstream UI cannot distinguish a shadowed root key from a collector
    payload, so shadowing is a hard error rather than a silent overwrite.
    """

    payload = asdict(report)
    collectors = payload.pop("collectors", {}) or {}
    conflicts = set(collectors) & _RESERVED_ROOT_KEYS
    if conflicts:
        raise ValueError(
            "Collector namespace collides with reserved root JSON key(s): "
            f"{sorted(conflicts)}. Rename the collector(s) to avoid shadowing."
        )
    payload.update(collectors)
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
