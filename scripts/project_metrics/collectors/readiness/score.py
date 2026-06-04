"""Pure scoring: applicability filter, per-pillar pass%, 80%-per-level gate.

The scorer turns a list of per-criterion verdict dicts into the ``readiness``
``data`` payload: the 8-pillar ``level`` (1-5), overall ``pass_pct``, per-pillar
breakdowns, and the separate Pillar-9 ``manageability`` sub-score.

Two contracts are load-bearing:

* **Pillar 9 is never folded into the 8-pillar level.** Manageability is
  computed independently and reported under ``data["manageability"]``; the
  Factory ``level`` reflects only the eight Factory pillars.
* **Non-applicable and skipped (LLM-pending) criteria are excluded from every
  denominator** — they are neither passes nor failures, so a project is not
  penalized for a criterion that does not apply or could not be judged offline.

The 80%-per-level gate: a project reaches level *L* only if it passes ≥80% of
the applicable criteria at every level ``1..L`` (across the eight Factory
pillars combined). The level is the highest *L* meeting that gate for all
prior levels.

``recompute(data)`` re-runs the scoring in place after the LLM enrichment step
has filled the ``passed`` fields of the LLM criteria — it reads the criteria
list already present in ``data`` rather than re-deriving from the rubric.
"""

from __future__ import annotations

from typing import Any

from scripts.project_metrics.collectors.readiness.criteria import (
    CRITERIA,
    FACTORY_PILLARS,
    INFO_NOT_FAIL_CRITERIA,
    MANAGEABILITY_PILLAR,
    PILLAR_NAMES,
)

__all__ = [
    "LEVEL_GATE",
    "MAX_LEVEL",
    "MIN_LEVEL",
    "build_pillars",
    "compute_level",
    "compute_manageability",
    "recompute",
    "score_from_criteria",
]


# The Factory gate: pass ≥80% of each level's applicable criteria to unlock it.
LEVEL_GATE: float = 0.8
MIN_LEVEL: int = 1
MAX_LEVEL: int = 5


# ---------------------------------------------------------------------------
# Verdict helpers — a "verdict" is a per-criterion dict carrying at least
# {id, pillar, level, applicable, passed}. `passed` is bool | None; None means
# "not scored" (LLM-pending) and is excluded from denominators.
# ---------------------------------------------------------------------------


def _is_scored(verdict: dict[str, Any]) -> bool:
    """True when the criterion is applicable and has a non-None pass verdict."""

    return bool(verdict.get("applicable")) and verdict.get("passed") is not None


def _counts_against_denominator(verdict: dict[str, Any]) -> bool:
    """True when the verdict participates in a pass% denominator.

    Excludes non-applicable criteria, LLM-pending (passed is None) criteria,
    and info-not-fail criteria whose failure must not penalize the score.
    """

    if not _is_scored(verdict):
        return False
    if verdict["id"] in INFO_NOT_FAIL_CRITERIA and not verdict.get("passed"):
        return False
    return True


def _pass_pct(verdicts: list[dict[str, Any]]) -> tuple[float, int, int]:
    """Return (pass_pct, numerator, denominator) over the scored verdicts."""

    scored = [v for v in verdicts if _counts_against_denominator(v)]
    denominator = len(scored)
    numerator = sum(1 for v in scored if v.get("passed"))
    pct = (numerator / denominator) if denominator > 0 else 0.0
    return pct, numerator, denominator


# ---------------------------------------------------------------------------
# Per-pillar breakdown.
# ---------------------------------------------------------------------------


def build_pillars(verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the per-pillar breakdown for the eight Factory pillars.

    Each entry carries ``{id, name, pass_pct, numerator, denominator,
    level_pass}`` where ``level_pass`` is a 5-element list of booleans — one
    per maturity level — recording whether that level's gate was met within
    the pillar.
    """

    pillars: list[dict[str, Any]] = []
    for pillar_id in FACTORY_PILLARS:
        pillar_verdicts = [v for v in verdicts if v.get("pillar") == pillar_id]
        pct, numerator, denominator = _pass_pct(pillar_verdicts)
        level_pass = [
            _level_gate_met(pillar_verdicts, level)
            for level in range(MIN_LEVEL, MAX_LEVEL + 1)
        ]
        pillars.append(
            {
                "id": pillar_id,
                "name": PILLAR_NAMES[pillar_id],
                "pass_pct": round(pct, 6),
                "numerator": numerator,
                "denominator": denominator,
                "level_pass": level_pass,
            }
        )
    return pillars


def _level_gate_met(verdicts: list[dict[str, Any]], level: int) -> bool:
    """True when the 80% gate is met for ``level`` over the given verdicts.

    A level with no applicable criteria is treated as met (vacuously true) so
    a pillar with sparse coverage at one level does not block progression.
    """

    level_verdicts = [v for v in verdicts if v.get("level") == level]
    pct, _, denominator = _pass_pct(level_verdicts)
    if denominator == 0:
        return True
    return pct >= LEVEL_GATE


# ---------------------------------------------------------------------------
# Overall 8-pillar level.
# ---------------------------------------------------------------------------


def compute_level(verdicts: list[dict[str, Any]]) -> int:
    """Compute the overall Factory level (1-5) over the eight pillars combined.

    The level is the highest ``L`` such that the 80% gate is met at every
    level ``1..L`` across all Factory-pillar criteria combined. Manageability
    (Pillar 9) criteria are excluded. A project that fails the level-1 gate is
    still reported at level 1 (the floor) — levels are a 1-5 scale, not 0-5.
    """

    factory_verdicts = [v for v in verdicts if v.get("pillar") in FACTORY_PILLARS]
    evidence_ceiling = _highest_scored_level(factory_verdicts)
    reached = MIN_LEVEL
    for level in range(MIN_LEVEL, evidence_ceiling + 1):
        if _level_gate_met(factory_verdicts, level):
            reached = level
        else:
            break
    return reached


def _highest_scored_level(verdicts: list[dict[str, Any]]) -> int:
    """Return the highest maturity level that carries scored evidence.

    A level with no scored criteria cannot lift the reached level — otherwise a
    project with only level-1 evidence would vacuously satisfy the empty gates
    at levels 2-5 and report level 5. Floors at :data:`MIN_LEVEL` so the scan in
    :func:`compute_level` always runs at least once.
    """

    levels = [int(v["level"]) for v in verdicts if _counts_against_denominator(v)]
    return max(levels) if levels else MIN_LEVEL


def compute_manageability(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the Pillar-9 sub-score — never folded into the Factory level."""

    manage_verdicts = [v for v in verdicts if v.get("pillar") == MANAGEABILITY_PILLAR]
    pct, numerator, denominator = _pass_pct(manage_verdicts)
    return {
        "pass_pct": round(pct, 6),
        "numerator": numerator,
        "denominator": denominator,
        "note": "Praxion-native; not in 8-pillar level",
    }


# ---------------------------------------------------------------------------
# Top-level entry points.
# ---------------------------------------------------------------------------


def score_from_criteria(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble the full scoring payload from per-criterion verdicts.

    Returns the ``level``, overall ``pass_pct`` (Factory pillars only), the
    per-pillar breakdown, and the separate ``manageability`` sub-score. The
    caller is responsible for attaching the ``criteria`` list and ``llm`` block.
    """

    factory_verdicts = [v for v in verdicts if v.get("pillar") in FACTORY_PILLARS]
    overall_pct, _, _ = _pass_pct(factory_verdicts)
    return {
        "level": compute_level(verdicts),
        "pass_pct": round(overall_pct, 6),
        "pillars": build_pillars(verdicts),
        "manageability": compute_manageability(verdicts),
    }


def recompute(data: dict[str, Any]) -> None:
    """Re-score ``data`` in place from its own ``criteria`` list.

    Called after the LLM enrichment step fills the ``passed`` fields of the
    LLM-judged criteria. Reads ``data["criteria"]`` (the per-criterion verdict
    dicts) and overwrites ``level``, ``pass_pct``, ``pillars``, and
    ``manageability``. Idempotent: re-running with the same criteria yields the
    same scores. The ``llm`` block and ``note`` are owned by the caller and
    left untouched here.
    """

    verdicts = data.get("criteria", [])
    scored = score_from_criteria(verdicts)
    data["level"] = scored["level"]
    data["pass_pct"] = scored["pass_pct"]
    data["pillars"] = scored["pillars"]
    data["manageability"] = scored["manageability"]


# Re-export the rubric size so the collector can sanity-check it built one
# verdict per criterion without importing criteria directly in two places.
CRITERIA_COUNT: int = len(CRITERIA)
__all__.append("CRITERIA_COUNT")
