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


def _fmt_pct(value: Any) -> str:
    """Render a ``[0.0, 1.0]`` fraction as a percentage, scaling included.

    Every producer of a ``*_pct`` field in this package emits a *fraction*:
    the Cobertura/LCOV parsers store ``line-rate`` verbatim, and the trends
    module computes ``delta / prior``. Appending ``%`` to that fraction
    understates by 100x — 0.8502 rendered as "0.85%" rather than "85.02%".
    That is not merely cosmetic: the sentinel's coverage dimension reads this
    Markdown against a 70% floor, so an 85%-covered repository files
    tech-debt rows for being catastrophically untested.

    The scaling lives in the formatter, not at each call site, so a new render
    site cannot reintroduce the bug by forgetting it.
    """
    if value is None:
        return _NULL_CELL
    return f"{float(value) * 100:.2f}%"


# Per-collector deep-dive rendering. Each entry is (key, label, formatter).
# Keys must match what the collector actually emits in ``data`` -- the
# renderer silently skips absent keys, so a typo here means the row never
# appears. Collectors with nested or per-file payloads are summarized by
# the matching entry in ``_DEEP_DIVE_SUMMARIZERS`` below; the layout map
# carries only top-level scalar fields.
_DEEP_DIVE_LAYOUT: dict[str, tuple[tuple[str, str, Any], ...]] = {
    "git": (
        ("file_count", "Files touched in window", _fmt_int),
        ("churn_total_90d", "Total churn (lines + or -)", _fmt_int),
        ("change_entropy_90d", "Change entropy (bits)", _fmt_float_2),
        ("truck_factor", "Truck factor", _fmt_int),
        ("churn_source", "Churn source", _fmt_float_raw),
    ),
    "scc": (
        ("file_count", "Files counted", _fmt_int),
        ("sloc_total", "SLOC total", _fmt_int),
        ("language_count", "Languages detected", _fmt_int),
    ),
    "lizard": (),
    # complexipy and pydeps both nest their aggregate metrics under
    # ``data["aggregate"]`` and emit per-module / per-file dicts at the
    # top level. The layout map only addresses top-level scalars, so
    # both collectors are summarized via _DEEP_DIVE_SUMMARIZERS instead.
    "complexipy": (),
    "pydeps": (),
    "coverage": (
        # The sentinel's coverage dimension reads *this* bullet, not the
        # narrative preamble, when deciding whether a project is under its
        # coverage floor — so the fraction must be scaled here too.
        ("line_pct", "Line coverage", _fmt_pct),
        ("artifact_format", "Artifact format", _fmt_float_raw),
        ("artifact_path", "Artifact path", _fmt_float_raw),
    ),
    "readiness": (
        ("level", "Agent-readiness level (1-5)", _fmt_int),
        ("pass_pct", "Overall pass %", _fmt_float_2),
        ("note", "Scoring note", _fmt_float_raw),
    ),
}


# Per-collector summarizers -- each takes the collector's ``data`` dict and
# returns a list of bullet lines that render BELOW the layout bullets.
# Summarizers exist so per-file dicts (churn_90d, ownership, files) and
# similar heavy structures collapse to a few highlight lines instead of
# being dumped wholesale into the MD report. Full per-file/per-pair detail
# remains available in the JSON sibling artifact.


def _summarize_git(data: dict[str, Any]) -> list[str]:
    """Highlights for git's heavy per-file dicts; full data lives in JSON."""

    lines: list[str] = []
    churn = data.get("churn_90d")
    if isinstance(churn, dict) and churn:
        top = sorted(churn.items(), key=lambda kv: -_fmt_score(kv[1]))[:5]
        lines.append(f"- Top {len(top)} churning files (of {len(churn)} touched):")
        for path, value in top:
            lines.append(f"    - `{path}` — {_fmt_int(value)} lines")
    coupling = data.get("change_coupling")
    if isinstance(coupling, dict):
        pairs = coupling.get("pairs", [])
        if isinstance(pairs, list) and pairs:
            top_pairs = pairs[:5]
            threshold = coupling.get("threshold", "?")
            lines.append(
                f"- Top {len(top_pairs)} co-changing pairs "
                f"(threshold ≥{threshold}, {len(pairs)} total):"
            )
            for pair in top_pairs:
                files = pair.get("files", [])
                count = pair.get("count", "?")
                if isinstance(files, list) and len(files) == 2:
                    lines.append(f"    - `{files[0]}` ↔ `{files[1]}` — {count} commits")
    ownership = data.get("ownership")
    if isinstance(ownership, dict) and ownership:
        sole = sum(
            1
            for entry in ownership.values()
            if isinstance(entry, dict)
            and isinstance(entry.get("major"), list)
            and len(entry["major"]) == 1
        )
        total = len(ownership)
        pct = (sole / total * 100.0) if total else 0.0
        lines.append(f"- Files with a single major owner: {sole}/{total} ({pct:.1f}%)")
    age = data.get("age_days")
    if isinstance(age, dict) and age:
        try:
            oldest_path, oldest_days = max(age.items(), key=lambda kv: kv[1])
            newest_path, newest_days = min(age.items(), key=lambda kv: kv[1])
            lines.append(
                f"- Oldest in window: `{oldest_path}` ({oldest_days} days); "
                f"newest: `{newest_path}` ({newest_days} days)"
            )
        except (TypeError, ValueError):
            pass
    return lines


def _summarize_lizard(data: dict[str, Any]) -> list[str]:
    """Highlights for lizard's per-file CCN map and aggregate block."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_function_count", "Functions analyzed", _fmt_int),
            ("ccn_p95", "CCN p95", _fmt_float_2),
            ("ccn_p75", "CCN p75", _fmt_float_2),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
    files = data.get("files")
    if isinstance(files, dict) and files:
        scored: list[tuple[str, float, int]] = []
        for path, file_data in files.items():
            if not isinstance(file_data, dict):
                continue
            score = file_data.get("p95_ccn")
            if score is None:
                score = file_data.get("max_ccn", 0)
            scored.append((path, _fmt_score(score), int(file_data.get("function_count", 0))))
        scored.sort(key=lambda triple: -triple[1])
        top = scored[:5]
        if top:
            lines.append(f"- Top {len(top)} most complex files by p95 CCN (of {len(files)}):")
            for path, score, fcount in top:
                score_str = f"{score:.1f}" if score % 1 else f"{int(score)}"
                lines.append(f"    - `{path}` — p95 CCN {score_str} ({fcount} functions)")
    return lines


def _summarize_complexipy(data: dict[str, Any]) -> list[str]:
    """Highlights for complexipy's per-file cognitive map and aggregate block."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_function_count", "Functions analyzed", _fmt_int),
            ("cognitive_p95", "Cognitive p95", _fmt_float_2),
            ("cognitive_p75", "Cognitive p75", _fmt_float_2),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
    files = data.get("files")
    if isinstance(files, dict) and files:
        scored: list[tuple[str, float, int]] = []
        for path, file_data in files.items():
            if not isinstance(file_data, dict):
                continue
            score = file_data.get("p95_cognitive")
            if score is None:
                score = file_data.get("max_cognitive", 0)
            scored.append((path, _fmt_score(score), int(file_data.get("function_count", 0))))
        scored.sort(key=lambda triple: -triple[1])
        top = scored[:5]
        if top:
            lines.append(
                f"- Top {len(top)} most cognitively complex files (p95 cognitive, of {len(files)}):"
            )
            for path, score, fcount in top:
                score_str = f"{score:.1f}" if score % 1 else f"{int(score)}"
                lines.append(f"    - `{path}` — p95 cognitive {score_str} ({fcount} functions)")
    return lines


def _summarize_pydeps(data: dict[str, Any]) -> list[str]:
    """Highlights for pydeps's import-graph rollup."""

    lines: list[str] = []
    aggregate = data.get("aggregate")
    if isinstance(aggregate, dict):
        for key, label, formatter in (
            ("total_modules", "Modules analyzed", _fmt_int),
            ("cyclic_deps", "Non-trivial cyclic SCCs", _fmt_int),
        ):
            if key in aggregate and aggregate[key] is not None:
                lines.append(f"- {label}: {formatter(aggregate[key])}")
    cyclic_sccs = data.get("cyclic_sccs")
    if isinstance(cyclic_sccs, list) and cyclic_sccs:
        lines.append(f"- Cyclic SCCs detected ({len(cyclic_sccs)}):")
        for index, scc in enumerate(cyclic_sccs[:5], start=1):
            if not isinstance(scc, list):
                continue
            members = ", ".join(f"`{m}`" for m in scc[:6])
            extra = "" if len(scc) <= 6 else f" (+{len(scc) - 6} more)"
            lines.append(f"    - SCC {index} ({len(scc)} modules): {members}{extra}")
    modules = data.get("modules")
    if isinstance(modules, dict) and modules:
        # Top 5 most-coupled modules by Ce + Ca.
        coupling: list[tuple[str, float, int, int]] = []
        for name, entry in modules.items():
            if not isinstance(entry, dict):
                continue
            ca = int(entry.get("afferent_coupling", 0) or 0)
            ce = int(entry.get("efferent_coupling", 0) or 0)
            coupling.append((name, float(ca + ce), ca, ce))
        coupling.sort(key=lambda quad: -quad[1])
        top = coupling[:5]
        if top:
            lines.append(f"- Top {len(top)} most-coupled modules by Ca + Ce (of {len(modules)}):")
            for name, total, ca, ce in top:
                lines.append(f"    - `{name}` — Ca {ca} + Ce {ce} = {int(total)}")
    return lines


def _summarize_scc(data: dict[str, Any]) -> list[str]:
    """Highlights for scc's language breakdown; full table lives further down and in JSON."""

    lines: list[str] = []
    breakdown = data.get("language_breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        return lines
    scored: list[tuple[str, int, int]] = []
    for name, entry in breakdown.items():
        if not isinstance(entry, dict):
            continue
        try:
            sloc_int = int(entry.get("sloc", 0))
        except (TypeError, ValueError):
            sloc_int = 0
        try:
            file_int = int(entry.get("file_count", 0))
        except (TypeError, ValueError):
            file_int = 0
        scored.append((str(name), file_int, sloc_int))
    scored.sort(key=lambda triple: -triple[2])
    top = scored[:5]
    if not top:
        return lines
    lines.append(f"- Top {len(top)} languages by SLOC (of {len(breakdown)}):")
    for language, files, sloc in top:
        lines.append(f"    - {language} — {_fmt_int(files)} files, {_fmt_int(sloc)} SLOC")
    return lines


def _summarize_readiness(data: dict[str, Any]) -> list[str]:
    """Highlights for agent-readiness: LLM scoring status + recommendations.

    Renders the LLM tier status and a bounded list of failing criteria with
    their remediation guidance — the human-readable face of the recommendations
    the evaluation embeds per-criterion. Full per-criterion detail (explanation,
    pass/fail, scope) lives in the JSON sibling artifact.
    """

    lines: list[str] = []

    if data.get("weighting_active"):
        adj_pct = data.get("adjusted_pass_pct")
        adj_level = data.get("adjusted_level")
        canon_pct = data.get("pass_pct")
        canon_level = data.get("level")
        if isinstance(adj_pct, (int, float)) and isinstance(canon_pct, (int, float)):
            lines.append(
                f"- Adjusted (your weights): {adj_pct * 100:.0f}% · L{adj_level} "
                f"(canonical Factory: {canon_pct * 100:.0f}% · L{canon_level})"
            )
        weights = data.get("pillar_weights")
        if isinstance(weights, dict):
            tuned = [f"{p} ×{w:g}" for p, w in sorted(weights.items()) if w != 1.0]
            if tuned:
                lines.append(f"- Pillar weights: {', '.join(tuned)} (others ×1)")

    llm = data.get("llm")
    if isinstance(llm, dict):
        status = llm.get("status")
        model = llm.get("model")
        if status == "scored" and model:
            lines.append(f"- LLM scoring: scored via `{model}`")
        elif status:
            lines.append(f"- LLM scoring: {status}")

    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        return lines
    failing = [
        c
        for c in criteria
        if isinstance(c, dict) and c.get("passed") is False and c.get("remediation")
    ]
    if not failing:
        return lines
    failing.sort(key=lambda c: (int(c.get("level", 1)), str(c.get("id", ""))))
    shown = failing[:10]
    lines.append(f"- Recommendations for {len(failing)} unmet criteria:")
    for crit in shown:
        tag = " (AI-tailored)" if crit.get("remediation_source") == "llm" else ""
        lines.append(
            f"    - L{crit.get('level')} `{crit.get('id')}`{tag}: {crit.get('remediation')}"
        )
    if len(failing) > len(shown):
        lines.append(f"    - …and {len(failing) - len(shown)} more (see JSON sibling)")
    return lines


_DEEP_DIVE_SUMMARIZERS: dict[str, Any] = {
    "git": _summarize_git,
    "scc": _summarize_scc,
    "lizard": _summarize_lizard,
    "complexipy": _summarize_complexipy,
    "pydeps": _summarize_pydeps,
    "readiness": _summarize_readiness,
}


def _fmt_score(value: Any) -> float:
    """Coerce a numeric-ish value to float for sorting; non-numerics become 0."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        else f"Line coverage is {_fmt_pct(coverage)}."
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
    # ``delta_pct`` arrives as ``delta / prior`` — a ratio, not a percentage.
    return _fmt_pct(value)


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
    """Return body lines for one collector's deep-dive subsection.

    The body is composed of three pieces, in order:

    1. **Layout bullets** — top-level scalar fields per ``_DEEP_DIVE_LAYOUT``.
    2. **Summarizer bullets** — highlights derived from heavy per-file or
       nested structures, per ``_DEEP_DIVE_SUMMARIZERS``. Summaries
       deliberately surface only the top-N items; the full data is
       available in the JSON sibling artifact.
    3. **JSON pointer footer** — a one-line italic reminder that the
       canonical machine-readable payload lives in the JSON.

    Skip / error / timeout collectors short-circuit to a single marker
    line and do not emit a JSON pointer (there is nothing to point at).
    """

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

    data = result.data or {}
    bullets: list[str] = []

    layout = _DEEP_DIVE_LAYOUT.get(name, ())
    for key, label, formatter in layout:
        if key not in data:
            continue
        rendered = formatter(data[key])
        bullets.append(f"- {label}: {rendered}")

    summarizer = _DEEP_DIVE_SUMMARIZERS.get(name)
    if summarizer is not None:
        bullets.extend(summarizer(data))

    if not bullets:
        bullets = _render_safe_fallback(data)

    bullets.append("")
    bullets.append(_json_pointer_line(name))
    return bullets


def _render_safe_fallback(data: Any) -> list[str]:
    """Safe fallback when no layout / summarizer registered for a collector.

    Never dumps a dict via ``str(value)``: lists and dicts are summarized as
    ``<N items>`` / ``<N entries>`` and the reader is referred to the JSON
    for full content. Scalars render as themselves. The result is bounded
    in size regardless of how deep the input payload is.
    """

    if not isinstance(data, dict) or not data:
        return [_NULL_CELL]
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool) or isinstance(value, (int, float, str)):
            rendered = _fmt_float_2(value) if isinstance(value, float) else str(value)
            lines.append(f"- {key}: {rendered}")
        elif isinstance(value, list):
            lines.append(f"- {key}: {len(value)} items (see JSON)")
        elif isinstance(value, dict):
            lines.append(f"- {key}: {len(value)} entries (see JSON)")
        elif value is None:
            lines.append(f"- {key}: {_NULL_CELL}")
        else:
            lines.append(f"- {key}: <see JSON>")
    return lines


def _json_pointer_line(namespace: str) -> str:
    """Italic one-line pointer to the JSON sibling artifact for a namespace."""

    return (
        f"_Full payload for `{namespace}` lives in the sibling "
        f"`METRICS_REPORT_<timestamp>.json` under the `{namespace}` key._"
    )


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


def _lookup_language_counts(language: str, breakdown: dict[str, dict[str, int]]) -> tuple[str, str]:
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
    # Provenance — what state this report describes, as distinct from how the
    # run was configured. Rendered even when absent, and labelled as such: a
    # reader must be able to tell "no provenance recorded" from "current",
    # because a report that omits its subject reads as current by default.
    # `generated_at` is deliberately not repeated here — the document header
    # already carries it. The commit does not appear anywhere else, and it is
    # the field a consumer needs to measure staleness in commits rather than
    # in days.
    lines.append(f"- Commit: {meta.commit or _NULL_CELL}")
    if meta.dirty:
        lines.append("- Working tree: **dirty** (describes no single commit)")
    elif meta.dirty is False:
        lines.append("- Working tree: clean")
    else:
        lines.append(f"- Working tree: {_NULL_CELL}")
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
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
