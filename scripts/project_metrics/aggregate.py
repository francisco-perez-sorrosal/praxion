"""Compose the aggregate block by reading per-collector namespace data.

The runner initialises every non-metadata aggregate column to a type-appropriate
zero sentinel (``sloc_total=0``, ``ccn_p95=None``, etc.) because the runner
itself has no business interpreting collector output — it only orchestrates
the resolve/collect lifecycle. ``compose_aggregate`` is the post-collection
seam that reads each collector's ``CollectorResult.data`` payload and lifts the
values into the frozen aggregate columns.

Mapping (collector → aggregate column):

* ``git`` → ``churn_total_90d``, ``change_entropy_90d``, ``truck_factor`` and
  (fallback) ``file_count``
* ``scc`` → ``sloc_total``, ``language_count``, ``file_count`` (preferred when
  scc resolved available)
* ``lizard`` → ``ccn_p95`` (reads the collector's own per-repo aggregate)
* ``complexipy`` → ``cognitive_p95``
* ``pydeps`` → ``cyclic_deps``
* ``coverage`` → ``coverage_line_pct``

Hot-spot columns (``hotspot_top_score``, ``hotspot_gini``) are populated by
``hotspot.compose_hotspots`` — called **after** ``compose_aggregate`` in the
CLI pipeline so hot-spots see the newly-populated churn/complexity aggregates
if they need them.

Every read is defensive: a skipped or absent collector leaves the field at
its runner-seeded default, not an exception. Collectors that return
``status='error'`` or ``status='partial'`` still have their ``data`` inspected;
the renderer surfaces the partial/error state via ``tool_availability``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from scripts.project_metrics._stdlib_sloc import compute_stdlib_sloc
from scripts.project_metrics.schema import Report

__all__ = ["compose_aggregate"]


def _collector_data(report: Report, name: str) -> dict[str, Any] | None:
    """Return the collector's ``data`` dict, or ``None`` if not populated.

    A collector namespace can carry:
    * the uniform skip marker (``{"status": "skipped", ...}``) when Unavailable
      or NotApplicable — in that case ``data`` is absent and we return None;
    * a ``CollectorResult`` instance (runner-populated) with a ``.data``
      attribute — we unwrap;
    * in some paths the namespace value is already the data dict directly.
    We handle all three shapes defensively.
    """

    entry = report.collectors.get(name)
    if entry is None:
        return None
    # CollectorResult-shaped (runner path)
    data = getattr(entry, "data", None)
    if isinstance(data, dict):
        return data
    # Dict-shaped (skip marker or other); differentiate by presence of non-skip keys
    if isinstance(entry, dict):
        if entry.get("status") == "skipped":
            return None
        return entry  # assume it's the data dict itself
    return None


def compose_aggregate(report: Report, repo_root: Path | str | None = None) -> Report:
    """Return a new ``Report`` with aggregate columns populated from collectors.

    Non-destructive: never mutates ``report``. Uses ``dataclasses.replace``
    to produce a new ``Report`` + new ``AggregateBlock`` with the 10 lifted
    fields.

    ``repo_root`` enables the stdlib SLOC fallback: when ``scc`` did not
    populate size metrics (binary not installed, resolve returned Unavailable),
    we call ``compute_stdlib_sloc(repo_root)`` to deliver the graceful
    degradation the ADR promises. When ``repo_root`` is None, no fallback
    runs and ``sloc_total`` / ``language_count`` stay at their runner
    defaults — appropriate for unit tests that want the pre-fallback values.
    """

    git_data = _collector_data(report, "git") or {}
    scc_data = _collector_data(report, "scc") or {}
    lizard_data = _collector_data(report, "lizard") or {}
    complexipy_data = _collector_data(report, "complexipy") or {}
    pydeps_data = _collector_data(report, "pydeps") or {}
    coverage_data = _collector_data(report, "coverage") or {}

    # Size metrics — scc preferred, stdlib fallback when scc missing.
    sloc_total = scc_data.get("sloc_total", 0) or 0
    language_count = scc_data.get("language_count", 0) or 0
    file_count = scc_data.get("file_count") or git_data.get("file_count", 0) or 0
    if sloc_total == 0 and repo_root is not None:
        fallback = compute_stdlib_sloc(repo_root)
        sloc_total = fallback["sloc_total"]
        language_count = fallback["language_count"]
        if not file_count:
            file_count = fallback["file_count"]

    # Complexity p95s (inside each collector's own aggregate sub-dict).
    ccn_p95 = lizard_data.get("aggregate", {}).get("ccn_p95")
    cognitive_p95 = complexipy_data.get("aggregate", {}).get("cognitive_p95")
    cyclic_deps = pydeps_data.get("aggregate", {}).get("cyclic_deps")

    # Evolution metrics from git.
    churn_total_90d = git_data.get("churn_total_90d", 0) or 0
    change_entropy_90d = git_data.get("change_entropy_90d", 0.0) or 0.0
    truck_factor = git_data.get("truck_factor", 0) or 0

    # Quality.
    coverage_line_pct = coverage_data.get("line_pct")

    new_aggregate = replace(
        report.aggregate,
        sloc_total=int(sloc_total),
        file_count=int(file_count),
        language_count=int(language_count),
        ccn_p95=ccn_p95,
        cognitive_p95=cognitive_p95,
        cyclic_deps=cyclic_deps,
        churn_total_90d=int(churn_total_90d),
        change_entropy_90d=float(change_entropy_90d),
        truck_factor=int(truck_factor),
        coverage_line_pct=coverage_line_pct,
    )
    return replace(report, aggregate=new_aggregate)
