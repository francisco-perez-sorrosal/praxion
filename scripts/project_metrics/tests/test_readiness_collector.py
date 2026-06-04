"""Behavioral tests for :class:`ReadinessCollector` — the deterministic
mechanical half of agent-readiness.

The collector reads only the filesystem, so ``resolve()`` always returns
``Available`` and ``collect(ctx)`` must be byte-identical across two calls on
the same :class:`CollectionContext`. The LLM enrichment runs out-of-band in
``cli.py``; after ``collect()`` the ``llm`` sub-block is the ``pending``
placeholder. These tests pin the resolution outcome, the determinism contract,
and the ``data`` shape the dashboard and the enrichment step depend on.

Import strategy: symbols are imported inside each test body (deferred import)
so the BDD/TDD RED handshake yields per-test resolution rather than a
collection-time ImportError that masks every test at once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers.
# ---------------------------------------------------------------------------


def _make_context(repo_root: Path) -> object:
    """Build a CollectionContext pointing at ``repo_root``."""

    from scripts.project_metrics.collectors.base import CollectionContext

    return CollectionContext(
        repo_root=str(repo_root),
        window_days=90,
        git_sha="0" * 40,
    )


def _make_env() -> object:
    """Build the default resolution environment (ambient PATH)."""

    from scripts.project_metrics.collectors.base import ResolutionEnv

    return ResolutionEnv()


@pytest.fixture
def populated_repo(tmp_path: Path) -> Path:
    """A small repo with a spread of readiness signals across pillars.

    Enough mechanical signals are present that the scorer produces a non-zero
    level and a mix of passing/failing criteria — exercising the real
    pillar-and-level machinery rather than an all-empty edge.
    """

    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'x'\n[tool.ruff]\n", encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# resolve() — always available (filesystem-only collector).
# ---------------------------------------------------------------------------


class TestResolveAlwaysAvailable:
    """The collector reads only the filesystem, so its tool is always present."""

    def test_resolve_returns_available(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=tmp_path)
        result = collector.resolve(_make_env())

        assert isinstance(result, Available)

    def test_resolve_available_carries_a_version_string(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=tmp_path)
        result = collector.resolve(_make_env())

        assert isinstance(result, Available)
        assert isinstance(result.version, str)
        assert result.version != ""

    def test_resolve_available_even_on_empty_repo(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.base import Available
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        # No files at all — still available; the collector never needs a tool.
        collector = ReadinessCollector(repo_root=tmp_path)
        assert isinstance(collector.resolve(_make_env()), Available)


# ---------------------------------------------------------------------------
# collect() — determinism (byte-identical across two calls on same ctx).
# ---------------------------------------------------------------------------


class TestCollectDeterminism:
    """collect() must be byte-identical across repeat calls on one context.

    Wall-clock duration is excluded by the collector (left at the dataclass
    default 0.0), so two serializations of the ``data`` payload compare equal.
    """

    def test_collect_data_is_byte_identical_across_two_calls(
        self, populated_repo: Path
    ) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        ctx = _make_context(populated_repo)

        first = collector.collect(ctx)
        second = collector.collect(ctx)

        first_bytes = json.dumps(first.data, sort_keys=True).encode("utf-8")
        second_bytes = json.dumps(second.data, sort_keys=True).encode("utf-8")
        assert first_bytes == second_bytes, (
            "collect() must be byte-deterministic on the same CollectionContext "
            "— any clock/random/ordering leakage breaks the determinism contract."
        )

    def test_collect_duration_is_zero_for_determinism(
        self, populated_repo: Path
    ) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        result = collector.collect(_make_context(populated_repo))

        assert result.duration_seconds == 0.0, (
            "duration_seconds must stay at 0.0 — wall-clock would make the "
            "record non-deterministic across runs."
        )

    def test_collect_status_is_ok(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        result = collector.collect(_make_context(populated_repo))

        assert result.status == "ok"


# ---------------------------------------------------------------------------
# collect() — the LLM block is the pending placeholder (enrichment fills it).
# ---------------------------------------------------------------------------


class TestCollectLlmPending:
    """After the mechanical collect pass, the LLM block is ``pending``.

    The non-deterministic LLM enrichment runs later in ``cli.py``; the
    collector itself never touches the network, so it leaves a placeholder.
    """

    def test_llm_status_is_pending_after_collect(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        result = collector.collect(_make_context(populated_repo))

        assert result.data["llm"]["status"] == "pending"

    def test_llm_block_has_null_model_and_grounded_on(
        self, populated_repo: Path
    ) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        llm = collector.collect(_make_context(populated_repo)).data["llm"]

        assert llm["model"] is None
        assert llm["grounded_on"] is None

    def test_llm_criteria_are_left_unscored_after_collect(
        self, populated_repo: Path
    ) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        criteria = collector.collect(_make_context(populated_repo)).data["criteria"]

        llm_criteria = [c for c in criteria if c["llm"]]
        assert llm_criteria, "the rubric carries LLM-judged criteria"
        for crit in llm_criteria:
            assert crit["passed"] is None, (
                f"LLM criterion {crit['id']} must be left unscored "
                "(passed=None) for the enrichment step"
            )


# ---------------------------------------------------------------------------
# collect() — the data shape the dashboard + enrichment depend on.
# ---------------------------------------------------------------------------


class TestCollectDataShape:
    """The ``data`` payload carries the required top-level fields and the
    per-criterion / per-pillar structure the downstream layers read."""

    def test_data_has_required_top_level_keys(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        data = collector.collect(_make_context(populated_repo)).data

        for key in (
            "level",
            "pass_pct",
            "note",
            "pillars",
            "manageability",
            "criteria",
            "llm",
        ):
            assert key in data, f"data block must carry the '{key}' field"

    def test_level_is_int_in_one_to_five(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        level = collector.collect(_make_context(populated_repo)).data["level"]

        assert isinstance(level, int)
        assert 1 <= level <= 5

    def test_pillars_lists_eight_factory_pillars(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness.criteria import (
            FACTORY_PILLARS,
        )
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        pillars = collector.collect(_make_context(populated_repo)).data["pillars"]

        assert len(pillars) == len(FACTORY_PILLARS)
        pillar_ids = {p["id"] for p in pillars}
        assert pillar_ids == set(FACTORY_PILLARS)

    def test_each_pillar_carries_breakdown_fields(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        pillars = collector.collect(_make_context(populated_repo)).data["pillars"]

        for pillar in pillars:
            for key in (
                "id",
                "name",
                "pass_pct",
                "numerator",
                "denominator",
                "level_pass",
            ):
                assert key in pillar, f"pillar must carry '{key}'"
            assert len(pillar["level_pass"]) == 5

    def test_manageability_is_separate_sub_score(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        manage = collector.collect(_make_context(populated_repo)).data["manageability"]

        for key in ("pass_pct", "numerator", "denominator", "note"):
            assert key in manage, f"manageability must carry '{key}'"

    def test_each_criterion_carries_required_fields(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        criteria = collector.collect(_make_context(populated_repo)).data["criteria"]

        assert criteria, "the rubric must produce at least one criterion verdict"
        for crit in criteria:
            for key in (
                "id",
                "pillar",
                "level",
                "scope",
                "applicable",
                "passed",
                "llm",
                "rationale",
            ):
                assert key in crit, f"criterion {crit.get('id')} must carry '{key}'"

    def test_one_verdict_per_rubric_criterion(self, populated_repo: Path) -> None:
        from scripts.project_metrics.collectors.readiness.criteria import CRITERIA
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=populated_repo)
        criteria = collector.collect(_make_context(populated_repo)).data["criteria"]

        assert len(criteria) == len(CRITERIA)


# ---------------------------------------------------------------------------
# Collector metadata — registration contract.
# ---------------------------------------------------------------------------


class TestCollectorMetadata:
    """The runner reads class-level metadata for registration and filtering."""

    def test_name_is_readiness(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        assert ReadinessCollector(repo_root=tmp_path).name == "readiness"

    def test_collector_is_tier_zero_and_not_required(self, tmp_path: Path) -> None:
        from scripts.project_metrics.collectors.readiness_collector import (
            ReadinessCollector,
        )

        collector = ReadinessCollector(repo_root=tmp_path)
        assert collector.tier == 0
        assert collector.required is False
