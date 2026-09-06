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

This module is the orchestration shell: it owns the four small sections
(header, tool availability, install-to-improve, run metadata) plus the
``render_markdown``/``render_json`` entry points, and composes in the two
larger concerns that live in sibling modules:

* ``_report_deep_dive.py`` — the per-collector "Deep Dive" section.
* ``_report_sections.py`` — the aggregate/top-n/trends/per-language sections.

Shared formatting primitives (skip markers, numeric formatters) live in
``_report_format.py`` and are imported by all three.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone

from scripts.project_metrics._report_deep_dive import render_deep_dive
from scripts.project_metrics._report_format import EM_DASH, NULL_CELL
from scripts.project_metrics._report_sections import (
    render_aggregate_summary,
    render_per_language,
    render_top_n,
    render_trends,
)
from scripts.project_metrics.schema import Report

__all__ = ["render_markdown", "render_json"]


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
# Coverage staleness note — a `--refresh-coverage` attempt that timed out or
# failed leaves the pre-existing `coverage.xml` in place; without this note
# the aggregate summary's coverage sentence would present that stale
# artifact's numbers as current.
# ---------------------------------------------------------------------------

_STALE_COVERAGE_REFRESH_STATUSES: frozenset[str] = frozenset({"timed-out", "failed"})


def _render_coverage_staleness_note(report: Report) -> str | None:
    """Return a Markdown note flagging stale coverage data, or ``None``.

    Rendered as its own section immediately before the aggregate summary
    (the "Line coverage is X%." sentence) so it sits next to the figures it
    qualifies. Returns ``None`` on ``"fresh"`` or absent (no refresh
    attempted) — a successful refresh must not carry a staleness marker.
    """

    if report.coverage_refresh not in _STALE_COVERAGE_REFRESH_STATUSES:
        return None
    lines = [
        "## Coverage Data Is Stale",
        "",
        f"The `--refresh-coverage` attempt {report.coverage_refresh} for this run; "
        "the coverage figures below reflect the pre-existing `coverage.xml` "
        "artifact, not a fresh measurement.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public render_markdown entry point.
# ---------------------------------------------------------------------------


def render_markdown(report: Report) -> str:
    """Render ``report`` as a deterministic nine-section Markdown document."""

    sections: list[str] = [
        _render_header(report),
        _render_tool_availability(report),
        _render_install_to_improve(report),
    ]
    staleness_note = _render_coverage_staleness_note(report)
    if staleness_note is not None:
        sections.append(staleness_note)
    sections.extend(
        [
            render_aggregate_summary(report),
            render_top_n(report),
            render_trends(report),
            render_deep_dive(report),
            render_per_language(report),
            _render_run_metadata(report),
        ]
    )
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
        version = avail.version if avail.version else EM_DASH
        detail = avail.reason if avail.reason else EM_DASH
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
# Run Metadata section.
# ---------------------------------------------------------------------------


def _render_run_metadata(report: Report) -> str:
    lines = ["## Run Metadata", ""]
    meta = report.run_metadata
    if meta is None:
        lines.append(NULL_CELL)
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
    lines.append(f"- Commit: {meta.commit or NULL_CELL}")
    if meta.dirty:
        lines.append("- Working tree: **dirty** (describes no single commit)")
    elif meta.dirty is False:
        lines.append("- Working tree: clean")
    else:
        lines.append(f"- Working tree: {NULL_CELL}")
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
