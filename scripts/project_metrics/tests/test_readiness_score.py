"""Behavioral tests for the readiness scorer.

The scorer turns per-criterion verdict dicts into the level / pass% / pillar
breakdown payload. These tests build synthetic verdict lists (not real repo
scans) so each scoring behavior is isolated from the check layer:

* the 80%-per-level gate,
* exclusion of non-applicable and LLM-pending criteria from denominators,
* Pillar-9 manageability computed separately and never folded into the level,
* ``recompute()`` merging LLM verdicts in place and staying idempotent.
"""

from __future__ import annotations

from typing import Any

from scripts.project_metrics.collectors.readiness import score


def _verdict(
    crit_id: str,
    pillar: str,
    level: int,
    *,
    applicable: bool = True,
    passed: bool | None = True,
    llm: bool = False,
) -> dict[str, Any]:
    return {
        "id": crit_id,
        "pillar": pillar,
        "level": level,
        "scope": "repo",
        "applicable": applicable,
        "passed": passed,
        "llm": llm,
        "rationale": None,
    }


# ---------------------------------------------------------------------------
# 80%-per-level gate.
# ---------------------------------------------------------------------------


def test_all_level1_passing_reaches_at_least_level_1() -> None:
    verdicts = [
        _verdict("a", "style_validation", 1, passed=True),
        _verdict("b", "build_system", 1, passed=True),
    ]
    assert score.compute_level(verdicts) == 1


def test_failing_level1_gate_floors_at_level_1() -> None:
    # 1 of 4 passing at level 1 = 25% < 80% — the level floors at 1.
    verdicts = [
        _verdict("a", "style_validation", 1, passed=True),
        _verdict("b", "build_system", 1, passed=False),
        _verdict("c", "testing", 1, passed=False),
        _verdict("d", "documentation", 1, passed=False),
    ]
    assert score.compute_level(verdicts) == 1


def test_gate_unlocks_consecutive_levels() -> None:
    # Levels 1, 2, 3 each have 5/5 passing → reaches level 3; level 4 fails.
    verdicts: list[dict[str, Any]] = []
    for level in (1, 2, 3):
        for i in range(5):
            verdicts.append(_verdict(f"l{level}-{i}", "style_validation", level, passed=True))
    for i in range(5):
        verdicts.append(_verdict(f"l4-{i}", "style_validation", 4, passed=(i == 0)))
    assert score.compute_level(verdicts) == 3


def test_level_gate_blocks_progression_past_first_failure() -> None:
    # Level 1 passes (80%), level 2 fails (0%), level 3 passes — must stop at 1.
    verdicts = [
        _verdict("l1a", "style_validation", 1, passed=True),
        _verdict("l1b", "style_validation", 1, passed=True),
        _verdict("l1c", "style_validation", 1, passed=True),
        _verdict("l1d", "style_validation", 1, passed=True),
        _verdict("l1e", "style_validation", 1, passed=False),
        _verdict("l2a", "style_validation", 2, passed=False),
        _verdict("l3a", "style_validation", 3, passed=True),
    ]
    assert score.compute_level(verdicts) == 1


def test_exactly_80_percent_meets_the_gate() -> None:
    # 4 of 5 = 80% — the gate is inclusive (>= 0.8).
    verdicts = [_verdict(f"l1-{i}", "style_validation", 1, passed=(i != 4)) for i in range(5)]
    assert score.compute_level(verdicts) == 1


# ---------------------------------------------------------------------------
# Denominator exclusion: non-applicable + LLM-pending criteria.
# ---------------------------------------------------------------------------


def test_non_applicable_excluded_from_denominator() -> None:
    # 1 applicable passing + 3 non-applicable → 100% pass (1/1), not 25%.
    verdicts = [
        _verdict("a", "testing", 1, applicable=True, passed=True),
        _verdict("b", "testing", 1, applicable=False, passed=None),
        _verdict("c", "testing", 1, applicable=False, passed=None),
        _verdict("d", "testing", 1, applicable=False, passed=None),
    ]
    pillars = score.build_pillars(verdicts)
    testing = next(p for p in pillars if p["id"] == "testing")
    assert testing["numerator"] == 1
    assert testing["denominator"] == 1
    assert testing["pass_pct"] == 1.0


def test_llm_pending_passed_none_excluded_from_denominator() -> None:
    # An applicable LLM criterion with passed=None must not count.
    verdicts = [
        _verdict("a", "documentation", 1, applicable=True, passed=True),
        _verdict("b", "documentation", 1, applicable=True, passed=None, llm=True),
    ]
    pillars = score.build_pillars(verdicts)
    docs = next(p for p in pillars if p["id"] == "documentation")
    assert docs["denominator"] == 1
    assert docs["pass_pct"] == 1.0


def test_scored_llm_criterion_counts_in_denominator() -> None:
    verdicts = [
        _verdict("a", "documentation", 1, applicable=True, passed=True),
        _verdict("b", "documentation", 1, applicable=True, passed=False, llm=True),
    ]
    pillars = score.build_pillars(verdicts)
    docs = next(p for p in pillars if p["id"] == "documentation")
    assert docs["denominator"] == 2
    assert docs["numerator"] == 1
    assert docs["pass_pct"] == 0.5


# ---------------------------------------------------------------------------
# Pillar 9 manageability — separate sub-score, never folded into the level.
# ---------------------------------------------------------------------------


def test_manageability_computed_separately() -> None:
    verdicts = [
        _verdict("c.manage.claudemd", "manageability", 1, passed=True),
        _verdict("c.manage.git_hooks", "manageability", 3, passed=False),
    ]
    manage = score.compute_manageability(verdicts)
    assert manage["numerator"] == 1
    assert manage["denominator"] == 2
    assert manage["pass_pct"] == 0.5


def test_manageability_not_folded_into_factory_level() -> None:
    # Failing manageability criteria must not lower the 8-pillar level when
    # every Factory criterion passes.
    verdicts = [
        _verdict("f1", "style_validation", 1, passed=True),
        _verdict("m1", "manageability", 1, passed=False),
        _verdict("m2", "manageability", 1, passed=False),
    ]
    assert score.compute_level(verdicts) == 1


def test_agents_md_failure_does_not_penalize_manageability() -> None:
    # The AGENTS.md criterion is info-not-fail: a failing verdict is excluded
    # from the manageability denominator rather than counted as a failure.
    verdicts = [
        _verdict("c.manage.claudemd", "manageability", 1, passed=True),
        _verdict("c.manage.agents_md", "manageability", 2, passed=False),
    ]
    manage = score.compute_manageability(verdicts)
    assert manage["numerator"] == 1
    assert manage["denominator"] == 1
    assert manage["pass_pct"] == 1.0


# ---------------------------------------------------------------------------
# Full payload + recompute.
# ---------------------------------------------------------------------------


def test_score_from_criteria_returns_full_payload_shape() -> None:
    verdicts = [_verdict("f1", "style_validation", 1, passed=True)]
    payload = score.score_from_criteria(verdicts)
    assert set(payload) == {"level", "pass_pct", "pillars", "manageability"}
    assert len(payload["pillars"]) == 8
    assert payload["manageability"]["note"]


def test_recompute_merges_llm_verdicts_in_place() -> None:
    data: dict[str, Any] = {
        "level": 1,
        "pass_pct": 0.0,
        "criteria": [
            _verdict("f1", "documentation", 1, applicable=True, passed=True),
            _verdict("f2", "documentation", 1, applicable=True, passed=None, llm=True),
        ],
        "pillars": [],
        "manageability": {},
        "llm": {"status": "pending"},
    }
    # Simulate the LLM enrichment filling the pending verdict.
    data["criteria"][1]["passed"] = False
    score.recompute(data)
    docs = next(p for p in data["pillars"] if p["id"] == "documentation")
    assert docs["denominator"] == 2
    assert docs["numerator"] == 1
    # llm block is owned by the caller; recompute must not touch it.
    assert data["llm"] == {"status": "pending"}


def test_recompute_is_idempotent() -> None:
    data: dict[str, Any] = {
        "criteria": [
            _verdict("f1", "style_validation", 1, passed=True),
            _verdict("f2", "build_system", 1, passed=True),
        ],
    }
    score.recompute(data)
    first_level = data["level"]
    first_pillars = data["pillars"]
    score.recompute(data)
    assert data["level"] == first_level
    assert data["pillars"] == first_pillars


def test_recompute_handles_mechanical_only_with_all_llm_none() -> None:
    # Mechanical-only path: every LLM criterion stays passed=None and is
    # excluded; recompute must not raise and must produce a valid level.
    data: dict[str, Any] = {
        "criteria": [
            _verdict("f1", "style_validation", 1, applicable=True, passed=True),
            _verdict("naming", "style_validation", 3, applicable=True, passed=None, llm=True),
            _verdict("tq", "testing", 4, applicable=True, passed=None, llm=True),
            _verdict("rq", "documentation", 2, applicable=True, passed=None, llm=True),
            _verdict("daf", "documentation", 4, applicable=True, passed=None, llm=True),
        ],
    }
    score.recompute(data)
    assert isinstance(data["level"], int)
    assert score.MIN_LEVEL <= data["level"] <= score.MAX_LEVEL
