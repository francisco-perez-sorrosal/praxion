"""Agent-readiness engine package — criteria, mechanical checks, and scoring.

This package holds the stdlib-only readiness rubric engine that the
``ReadinessCollector`` (in the parent ``collectors`` package) wraps. It is
nested under the collector that owns it so the engine stays private to the
metrics package and implies no standalone CLI.

Layers:

* :mod:`criteria` — the 8 Factory pillars + Pillar 9 rubric as data.
* :mod:`checks` — pure, deterministic mechanical check functions.
* :mod:`score` — applicability filter, per-pillar pass%, 80%-per-level gate.
* :mod:`judge` — the optional stdlib-``urllib`` Anthropic Messages API judge
  for the four LLM-scored criteria (no SDK, no subprocess).

The collector adapter and the non-deterministic enrichment step deliberately
live *outside* this package (in ``readiness_collector.py`` and ``cli.py``) so
the engine itself carries no runner coupling — the judge here exposes the
transport, but the orchestration of when to call it lives in ``cli.py``.
"""

from __future__ import annotations

from scripts.project_metrics.collectors.readiness import (
    checks,
    criteria,
    judge,
    score,
)

__all__ = ["checks", "criteria", "judge", "score"]
