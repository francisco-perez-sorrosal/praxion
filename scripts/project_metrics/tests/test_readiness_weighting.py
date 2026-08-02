"""Tests for per-project pillar weighting (config + weighted scoring).

Covers:

* ``config.load_pillar_weights`` — missing file, valid, exclude (0), fractional,
  invalid values (negative / non-numeric), unknown pillar, malformed JSON,
* weighted scoring — uniform weights reduce to the canonical score, weight-0
  excludes a pillar, ``score_with_weights`` emits both canonical and adjusted,
* ``build_pillars`` carries ``weight``/``excluded``,
* the collector embeds the weighting block when a config is present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.project_metrics.collectors.base import CollectionContext
from scripts.project_metrics.collectors.readiness import config, score
from scripts.project_metrics.collectors.readiness.criteria import FACTORY_PILLARS
from scripts.project_metrics.collectors.readiness_collector import ReadinessCollector


def _verdict(
    crit_id: str,
    pillar: str,
    level: int,
    *,
    passed: bool | None = True,
    applicable: bool = True,
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
    }


def _write_config(repo_root: Path, payload: dict[str, Any]) -> None:
    ai_state = repo_root / ".ai-state"
    ai_state.mkdir(parents=True, exist_ok=True)
    (ai_state / config.CONFIG_BASENAME).write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Config loading.
# ---------------------------------------------------------------------------


class TestLoadPillarWeights:
    def test_missing_file_returns_all_ones(self, tmp_path: Path) -> None:
        weights = config.load_pillar_weights(tmp_path)
        assert weights == dict.fromkeys(FACTORY_PILLARS, 1.0)

    def test_valid_config_applies_weights(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"pillar_weights": {"observability": 0, "security": 0.5}})
        weights = config.load_pillar_weights(tmp_path)
        assert weights["observability"] == 0.0
        assert weights["security"] == 0.5
        assert weights["testing"] == 1.0  # unlisted → default

    def test_negative_weight_falls_back_to_one(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"pillar_weights": {"security": -2}})
        assert config.load_pillar_weights(tmp_path)["security"] == 1.0

    def test_non_numeric_weight_falls_back_to_one(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"pillar_weights": {"security": "heavy"}})
        assert config.load_pillar_weights(tmp_path)["security"] == 1.0

    def test_boolean_weight_falls_back_to_one(self, tmp_path: Path) -> None:
        # bool is an int subclass — must be rejected, not coerced to 0/1.
        _write_config(tmp_path, {"pillar_weights": {"security": True}})
        assert config.load_pillar_weights(tmp_path)["security"] == 1.0

    def test_unknown_pillar_is_ignored(self, tmp_path: Path) -> None:
        _write_config(tmp_path, {"pillar_weights": {"not_a_pillar": 0}})
        weights = config.load_pillar_weights(tmp_path)
        assert weights == dict.fromkeys(FACTORY_PILLARS, 1.0)

    def test_malformed_json_degrades_to_defaults(self, tmp_path: Path) -> None:
        ai_state = tmp_path / ".ai-state"
        ai_state.mkdir(parents=True)
        (ai_state / config.CONFIG_BASENAME).write_text("{not json", encoding="utf-8")
        assert config.load_pillar_weights(tmp_path) == dict.fromkeys(FACTORY_PILLARS, 1.0)


# ---------------------------------------------------------------------------
# Weighted scoring.
# ---------------------------------------------------------------------------


class TestWeightedScoring:
    def test_uniform_weights_match_unweighted(self) -> None:
        verdicts = [
            _verdict("a", "testing", 1, passed=True),
            _verdict("b", "observability", 1, passed=False),
        ]
        uniform = dict.fromkeys(FACTORY_PILLARS, 1.0)
        plain, _, _ = score._pass_pct(verdicts)
        weighted, _, _ = score._pass_pct(verdicts, uniform)
        assert weighted == plain

    def test_weight_zero_excludes_pillar_from_pass_pct(self) -> None:
        verdicts = [
            _verdict("a", "testing", 1, passed=True),
            _verdict("b", "observability", 1, passed=False),
        ]
        weights = dict.fromkeys(FACTORY_PILLARS, 1.0)
        weights["observability"] = 0.0
        weighted, _, _ = score._pass_pct(verdicts, weights)
        # The failing observability criterion drops out → 100% over what remains.
        assert weighted == 1.0

    def test_score_with_weights_reports_canonical_and_adjusted(self) -> None:
        verdicts = [
            _verdict("a", "testing", 1, passed=True),
            _verdict("b", "observability", 1, passed=False),
        ]
        weights = dict.fromkeys(FACTORY_PILLARS, 1.0)
        weights["observability"] = 0.0
        payload = score.score_with_weights(verdicts, weights)
        assert payload["pass_pct"] == 0.5  # canonical: 1 of 2
        assert payload["adjusted_pass_pct"] == 1.0  # adjusted: observability excluded
        assert payload["weighting_active"] is True
        assert payload["pillar_weights"]["observability"] == 0.0

    def test_no_weighting_marks_inactive_and_equal_scores(self) -> None:
        verdicts = [_verdict("a", "testing", 1, passed=True)]
        payload = score.score_with_weights(verdicts, dict.fromkeys(FACTORY_PILLARS, 1.0))
        assert payload["weighting_active"] is False
        assert payload["adjusted_pass_pct"] == payload["pass_pct"]
        assert payload["adjusted_level"] == payload["level"]

    def test_build_pillars_carries_weight_and_excluded(self) -> None:
        verdicts = [_verdict("a", "observability", 1, passed=True)]
        weights = dict.fromkeys(FACTORY_PILLARS, 1.0)
        weights["observability"] = 0.0
        pillars = score.build_pillars(verdicts, weights)
        obs = next(p for p in pillars if p["id"] == "observability")
        assert obs["weight"] == 0.0
        assert obs["excluded"] is True
        testing = next(p for p in pillars if p["id"] == "testing")
        assert testing["excluded"] is False

    def test_recompute_reads_persisted_weights(self) -> None:
        data: dict[str, Any] = {
            "criteria": [
                _verdict("a", "testing", 1, passed=True),
                _verdict("b", "observability", 1, passed=False),
            ],
            "pillar_weights": {
                **dict.fromkeys(FACTORY_PILLARS, 1.0),
                "observability": 0.0,
            },
        }
        score.recompute(data)
        assert data["pass_pct"] == 0.5
        assert data["adjusted_pass_pct"] == 1.0
        assert data["weighting_active"] is True


# ---------------------------------------------------------------------------
# Collector integration.
# ---------------------------------------------------------------------------


def test_collector_embeds_weighting_from_config(tmp_path: Path) -> None:
    _write_config(tmp_path, {"pillar_weights": {"observability": 0}})
    collector = ReadinessCollector(repo_root=tmp_path)
    ctx = CollectionContext(repo_root=str(tmp_path), window_days=90, git_sha="0" * 40)
    data = collector.collect(ctx).data
    assert data["weighting_active"] is True
    assert data["pillar_weights"]["observability"] == 0.0
    assert "adjusted_pass_pct" in data
    assert "adjusted_level" in data
    obs = next(p for p in data["pillars"] if p["id"] == "observability")
    assert obs["excluded"] is True


def test_collector_without_config_is_unweighted(tmp_path: Path) -> None:
    collector = ReadinessCollector(repo_root=tmp_path)
    ctx = CollectionContext(repo_root=str(tmp_path), window_days=90, git_sha="0" * 40)
    data = collector.collect(ctx).data
    assert data["weighting_active"] is False
    assert data["adjusted_pass_pct"] == data["pass_pct"]
