"""Churn x complexity hotspot composition, Top-N selection, and Gini concentration.

This module is the composer stage of the project-metrics pipeline: it consumes
a fully-collected ``Report`` and produces the ``hotspots`` block plus the two
``aggregate`` hotspot columns (``hotspot_top_score`` and ``hotspot_gini``).

Formula
-------
For each file that appears in BOTH the git churn map AND the complexity map::

    hotspot_score = churn_90d_lines * complexity

Complexity is preferentially sourced from ``lizard.files[path].max_ccn``. When
the lizard namespace carries a skip marker, the composer falls back to
``scc.per_file_sloc[path]`` and labels the output
``complexity_source = "scc_fallback"``. When both sources are skipped, the
hotspots block carries ``status = "skipped"`` and the two aggregate columns
become ``None``.

Determinism
-----------
Files tied on score sort lexicographically ascending by path so two runs over
identical input always emit the same Top-N list (required for the same-SHA
determinism property downstream consumers depend on).

Gini
----
For sorted-ascending scores ``[s_1, s_2, ..., s_n]`` with total ``S``::

    Gini = (2 * sum_{i=1..n}(i * s_i) - (n + 1) * S) / (n * S)

By convention, when ``S == 0`` (all scores zero, or no scores at all) Gini is
``0.0`` — no inequality is measurable.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from scripts.project_metrics.schema import Report

__all__ = ["compose_hotspots"]


_DEFAULT_TOP_N = 10
_SKIP_STATUS = "skipped"
_OK_STATUS = "ok"
_SCC_FALLBACK_MARKER = "scc_fallback"
_LIZARD_MARKER = "lizard"


def compose_hotspots(report: Report) -> Report:
    """Compose hotspot Top-N and aggregate hotspot columns.

    Reads churn from the git collector namespace and complexity from either
    the lizard namespace (preferred) or the scc namespace (fallback). Returns
    a new ``Report`` — the input is never mutated. Callers should bind the
    returned value (``report = compose_hotspots(report)``).
    """

    churn_by_path = _extract_churn(report)
    complexity_by_path, complexity_source = _extract_complexity(report)

    if complexity_by_path is None:
        return _apply_skip(report)

    scored = _score_files(churn_by_path, complexity_by_path)
    top_n = _build_top_n(
        scored, report.run_metadata.top_n if report.run_metadata else _DEFAULT_TOP_N
    )
    scores = [score for _, _, _, score in scored]

    hotspots_block: dict[str, Any] = {
        "status": _OK_STATUS,
        "top_n": top_n,
        "complexity_source": complexity_source,
    }
    top_score = max(scores) if scores else 0.0
    gini = _gini(scores)

    new_aggregate = replace(
        report.aggregate,
        hotspot_top_score=top_score,
        hotspot_gini=gini,
    )
    return replace(report, aggregate=new_aggregate, hotspots=hotspots_block)


def _namespace_data(report: Report, name: str) -> dict[str, Any] | None:
    """Return the flat data dict for a collector namespace regardless of carrier shape.

    The runner stores either a `CollectorResult` (successful collect) or a
    plain 3-key skip-marker dict (unavailable / not-applicable resolve) under
    `report.collectors[name]`. Callers that want to read a single data field
    should go through this helper so they do not have to branch on carrier
    shape at every call site. Returns ``None`` when the namespace is absent.
    """

    entry = report.collectors.get(name)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry
    return entry.data


def _extract_churn(report: Report) -> dict[str, int]:
    """Pull the per-file churn map from the git collector namespace.

    Returns an empty dict when the git namespace is absent or carries a skip
    marker. The composer treats this as "no hotspots to compute" — scored
    files will be empty and top_n will be an empty list, but the skip path
    is reserved for the complexity dimension per the hotspot ADR.
    """

    data = _namespace_data(report, "git")
    if data is None:
        return {}
    if data.get("status") == _SKIP_STATUS:
        return {}
    churn = data.get("churn_90d", {})
    if not isinstance(churn, dict):
        return {}
    return churn


def _extract_complexity(
    report: Report,
) -> tuple[dict[str, int | float] | None, str]:
    """Pull the per-file complexity map with provenance label.

    Returns ``(None, "")`` when neither lizard nor scc carry a usable payload;
    the caller maps this to the skipped-hotspots path.
    """

    lizard_map = _extract_lizard_complexity(report)
    if lizard_map is not None:
        return lizard_map, _LIZARD_MARKER

    scc_map = _extract_scc_complexity(report)
    if scc_map is not None:
        return scc_map, _SCC_FALLBACK_MARKER

    return None, ""


def _extract_lizard_complexity(report: Report) -> dict[str, int | float] | None:
    """Read ``lizard.files[path].max_ccn`` into a flat per-path map.

    Returns ``None`` when the lizard namespace is missing or carries the
    uniform skip marker; the caller will then try the scc fallback.
    """

    data = _namespace_data(report, "lizard")
    if data is None:
        return None
    if data.get("status") == _SKIP_STATUS:
        return None
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        return None
    out: dict[str, int | float] = {}
    for path, entry in files.items():
        if not isinstance(entry, dict):
            continue
        max_ccn = entry.get("max_ccn")
        if isinstance(max_ccn, (int, float)):
            out[path] = max_ccn
    return out if out else None


def _extract_scc_complexity(report: Report) -> dict[str, int | float] | None:
    """Read ``scc.per_file_sloc`` as the scc-fallback complexity proxy.

    The hotspot ADR mentions "branch-count per file" but ``SccCollector``
    emits ``per_file_sloc`` — treating sloc as the scc proxy preserves the
    "honest source label" principle in the ADR while matching the collector
    reality.
    """

    data = _namespace_data(report, "scc")
    if data is None:
        return None
    if data.get("status") == _SKIP_STATUS:
        return None
    per_file = data.get("per_file_sloc")
    if not isinstance(per_file, dict) or not per_file:
        return None
    out: dict[str, int | float] = {}
    for path, value in per_file.items():
        if isinstance(value, (int, float)):
            out[path] = value
    return out if out else None


def _score_files(
    churn_by_path: dict[str, int],
    complexity_by_path: dict[str, int | float],
) -> list[tuple[str, int, int | float, float]]:
    """Join churn and complexity by path; compute score per file.

    Files appearing in only one dimension are excluded — a hot-spot requires
    both axes to be meaningful. Sorted descending by score with ties broken
    lexicographically ascending by path so the output is byte-deterministic
    on equivalent input.
    """

    shared_paths = churn_by_path.keys() & complexity_by_path.keys()
    scored: list[tuple[str, int, int | float, float]] = []
    for path in shared_paths:
        churn = churn_by_path[path]
        complexity = complexity_by_path[path]
        score = float(churn) * float(complexity)
        scored.append((path, churn, complexity, score))
    # Sort by descending score, then ascending path — negate score for desc.
    scored.sort(key=lambda entry: (-entry[3], entry[0]))
    return scored


def _build_top_n(
    scored: list[tuple[str, int, int | float, float]],
    top_n: int,
) -> list[dict[str, Any]]:
    """Convert the ordered score list into the Top-N dict list with ranks."""

    truncated = scored[:top_n]
    return [
        {
            "path": path,
            "churn_90d": churn,
            "complexity": complexity,
            "hotspot_score": score,
            "rank": rank,
        }
        for rank, (path, churn, complexity, score) in enumerate(truncated, start=1)
    ]


def _gini(scores: list[float]) -> float:
    """Compute Gini concentration coefficient over the score distribution.

    Implements the pinned formula (sorted-ascending, 1-indexed)::

        Gini = (2 * sum(i * s_i) - (n + 1) * S) / (n * S)

    Returns ``0.0`` when the total is zero (no inequality is measurable, and
    the division would be undefined).
    """

    if not scores:
        return 0.0
    sorted_scores = sorted(scores)
    total = sum(sorted_scores)
    if total == 0:
        return 0.0
    n = len(sorted_scores)
    weighted_sum = sum(
        index * value for index, value in enumerate(sorted_scores, start=1)
    )
    numerator = 2.0 * weighted_sum - (n + 1) * total
    denominator = n * total
    return numerator / denominator


def _apply_skip(report: Report) -> Report:
    """Return a new report with hotspots marked skipped and aggregate nullified."""

    hotspots_block: dict[str, Any] = {
        "status": _SKIP_STATUS,
        "top_n": [],
    }
    new_aggregate = replace(
        report.aggregate,
        hotspot_top_score=None,
        hotspot_gini=None,
    )
    return replace(report, aggregate=new_aggregate, hotspots=hotspots_block)
