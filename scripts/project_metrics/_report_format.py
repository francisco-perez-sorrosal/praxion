"""Shared formatting primitives for the Markdown report renderer.

Skip-marker phrasing (public UX contract — em-dash U+2014):

* Unavailable: ``_not computed — install <tool>_``
* NotApplicable: ``_not applicable for this repository_``
* Error: ``_not computed — <reason>_``
* Timeout: ``_not computed — timed out after <N>s_``

These exact strings appear wherever a skipped collector would otherwise
contribute data (deep dive, aggregate cells, per-language cells) — see
``_report_deep_dive.py`` and ``_report_sections.py`` for the call sites.

Null values in numeric cells render as a single em-dash ``—`` (U+2014).
Never the Python literal ``"None"`` or ``"null"`` or the empty string.

This module has no dependency on ``schema.Report`` — every function here
takes raw values, so it is the shared foundation both ``_report_deep_dive.py``
and ``_report_sections.py`` import from, and ``report.py`` imports it too.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "EM_DASH",
    "NULL_CELL",
    "NOT_APPLICABLE_MARKER",
    "unavailable_marker",
    "error_marker",
    "timeout_marker",
    "fmt_int",
    "fmt_float_2",
    "fmt_float_raw",
    "fmt_pct",
    "fmt_score",
    "fmt_delta_cell",
    "fmt_delta_pct_cell",
]


EM_DASH = "—"
NULL_CELL = EM_DASH
NOT_APPLICABLE_MARKER = "_not applicable for this repository_"


def unavailable_marker(tool: str) -> str:
    """Return the italic skip marker for an Unavailable collector."""

    return f"_not computed {EM_DASH} install {tool}_"


def error_marker(reason: str) -> str:
    """Return the italic skip marker for an error-status collector."""

    return f"_not computed {EM_DASH} {reason}_"


def timeout_marker(seconds: float | int) -> str:
    """Return the italic skip marker for a timed-out collector."""

    return f"_not computed {EM_DASH} timed out after {seconds}s_"


def fmt_int(value: Any) -> str:
    if value is None:
        return NULL_CELL
    return str(int(value))


def fmt_float_2(value: Any) -> str:
    if value is None:
        return NULL_CELL
    return f"{float(value):.2f}"


def fmt_float_raw(value: Any) -> str:
    if value is None:
        return NULL_CELL
    return str(value)


def fmt_pct(value: Any) -> str:
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
        return NULL_CELL
    return f"{float(value) * 100:.2f}%"


def fmt_score(value: Any) -> float:
    """Coerce a numeric-ish value to float for sorting; non-numerics become 0."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fmt_delta_cell(value: Any) -> str:
    if value is None:
        return NULL_CELL
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def fmt_delta_pct_cell(value: Any) -> str:
    # ``delta_pct`` arrives as ``delta / prior`` — a ratio, not a percentage.
    return fmt_pct(value)
