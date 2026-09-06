"""Per-collector Deep Dive section — layout map, summarizers, and rendering.

Per-collector rendering is the single largest concern in the report renderer:
each collector (``git``, ``scc``, ``lizard``, ``complexipy``, ``pydeps``,
``coverage``, ``readiness``) gets its own layout of top-level scalar fields
plus a summarizer that collapses heavy per-file or nested structures into a
handful of highlight bullets. Full per-file/per-pair detail always remains
available in the JSON sibling artifact — summarizers deliberately surface
only the top-N items.

``render_deep_dive(report)`` is the sole entry point ``report.py`` calls.
"""

from __future__ import annotations

from typing import Any

from scripts.project_metrics._deep_dive_summaries import (
    _pydeps_coverage_line,
    _summarize_complexipy,
    _summarize_coverage,
    _summarize_coverage_scope,
    _summarize_git,
    _summarize_lizard,
    _summarize_pydeps,
    _summarize_readiness,
    _summarize_scc,
)
from scripts.project_metrics._report_format import (
    NOT_APPLICABLE_MARKER,
    NULL_CELL,
    error_marker,
    fmt_float_2,
    fmt_float_raw,
    fmt_int,
    fmt_pct,
    timeout_marker,
    unavailable_marker,
)
from scripts.project_metrics.schema import Report, ToolAvailability

__all__ = ["render_deep_dive"]

# The nine summarizer imports above are re-exports, not re-implementations:
# callers that reach into this module's private names for them — pre-dating
# their move to ``_deep_dive_summaries.py`` — keep resolving unchanged.
# Listed in ``__all__`` only so the linter's unused-import check treats the
# re-export as intentional; new code should import from
# ``_deep_dive_summaries`` directly rather than through this pass-through.
__all__ += [
    "_pydeps_coverage_line",
    "_summarize_complexipy",
    "_summarize_coverage",
    "_summarize_coverage_scope",
    "_summarize_git",
    "_summarize_lizard",
    "_summarize_pydeps",
    "_summarize_readiness",
    "_summarize_scc",
]


# ---------------------------------------------------------------------------
# Deep-Dive per-collector label/format map. For each collector, the map
# enumerates the data-dict keys we surface and the human-readable label +
# formatting we apply. Keys absent from the collector's data dict are
# silently skipped; the renderer degrades gracefully when a collector's
# payload is lighter than advertised.
# ---------------------------------------------------------------------------

_DEEP_DIVE_LAYOUT: dict[str, tuple[tuple[str, str, Any], ...]] = {
    "git": (
        ("file_count", "Files touched in window", fmt_int),
        ("churn_total_90d", "Total churn (lines + or -)", fmt_int),
        ("change_entropy_90d", "Change entropy (bits)", fmt_float_2),
        ("truck_factor", "Truck factor", fmt_int),
        ("churn_source", "Churn source", fmt_float_raw),
    ),
    "scc": (
        ("file_count", "Files counted", fmt_int),
        ("sloc_total", "SLOC total", fmt_int),
        ("language_count", "Languages detected", fmt_int),
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
        ("line_pct", "Line coverage", fmt_pct),
        ("artifact_format", "Artifact format", fmt_float_raw),
        ("artifact_path", "Artifact path", fmt_float_raw),
    ),
    "readiness": (
        ("level", "Agent-readiness level (1-5)", fmt_int),
        ("pass_pct", "Overall pass %", fmt_float_2),
        ("note", "Scoring note", fmt_float_raw),
    ),
}


# Per-collector summarizers now live in ``_deep_dive_summaries.py`` (td-166);
# imported above and registered here by name, unchanged.

_DEEP_DIVE_SUMMARIZERS: dict[str, Any] = {
    "git": _summarize_git,
    "scc": _summarize_scc,
    "lizard": _summarize_lizard,
    "complexipy": _summarize_complexipy,
    "pydeps": _summarize_pydeps,
    "coverage": _summarize_coverage,
    "readiness": _summarize_readiness,
}


# ---------------------------------------------------------------------------
# Public render_deep_dive entry point.
# ---------------------------------------------------------------------------


def render_deep_dive(report: Report) -> str:
    lines = ["## Per-collector Deep Dive", ""]
    for name, result in report.collectors.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.extend(_render_collector_body(name, result, report))
        lines.append("")
    return "\n".join(lines)


def _collector_marker(name: str, result: Any, avail: ToolAvailability | None) -> list[str] | None:
    """Return the short-circuit marker line(s) for one collector, or ``None`` to continue.

    Checks the five-way availability/status ladder in order — unavailable,
    not_applicable, error (with the skipped-payload sub-case), timeout — and
    returns ``None`` only for the "ok, render the full body" case.

    The skipped-payload sub-case falls back to the unavailable marker
    unconditionally: by this point ``avail`` has already failed both the
    unavailable and not_applicable checks above, so re-testing its status
    here can never select a different branch — the prior code duplicated
    that dead pair inline.
    """

    if avail is not None and avail.status == "unavailable":
        return [unavailable_marker(name)]
    if avail is not None and avail.status == "not_applicable":
        return [NOT_APPLICABLE_MARKER]
    if result.status == "error":
        # Namespace carries a skip marker when the runner/collector produced
        # a uniform skip payload. Otherwise emit a generic error marker.
        data = result.data or {}
        if isinstance(data, dict) and data.get("status") == "skipped":
            return [unavailable_marker(name)]
        reason = str(data.get("reason", "error")) if isinstance(data, dict) else "error"
        return [error_marker(reason)]
    if result.status == "timeout":
        seconds = 0
        if isinstance(result.data, dict):
            seconds = result.data.get("timeout_seconds", 0)
        return [timeout_marker(seconds)]
    return None


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

    Skip / error / timeout collectors short-circuit to ``_collector_marker``'s
    single marker line and do not emit a JSON pointer (there is nothing to
    point at).
    """

    avail = report.tool_availability.get(name)
    marker = _collector_marker(name, result, avail)
    if marker is not None:
        return marker

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
        return [NULL_CELL]
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, bool) or isinstance(value, (int, float, str)):
            rendered = fmt_float_2(value) if isinstance(value, float) else str(value)
            lines.append(f"- {key}: {rendered}")
        elif isinstance(value, list):
            lines.append(f"- {key}: {len(value)} items (see JSON)")
        elif isinstance(value, dict):
            lines.append(f"- {key}: {len(value)} entries (see JSON)")
        elif value is None:
            lines.append(f"- {key}: {NULL_CELL}")
        else:
            lines.append(f"- {key}: <see JSON>")
    return lines


def _json_pointer_line(namespace: str) -> str:
    """Italic one-line pointer to the JSON sibling artifact for a namespace."""

    return (
        f"_Full payload for `{namespace}` lives in the sibling "
        f"`METRICS_REPORT_<timestamp>.json` under the `{namespace}` key._"
    )
