"""Behavioral tests for ``hotspot.compose_hotspots`` — churn x complexity composer.

These tests encode the hotspot-composer behavioral contract derived from the
hotspot-formula and storage-schema ADRs under ``.ai-state/decisions/drafts/``.
They are written *from the behavioral spec, not from the implementation* — the
production module (``scripts/project_metrics/hotspot.py``) is a stub at author
time and is deliberately not read while authoring these tests.

**Import strategy**: every test imports ``compose_hotspots`` inside the test
body. At author time the symbol does not exist (the stub module has
``__all__: list[str] = []``), so top-of-module imports would break pytest
collection for every test in this file simultaneously. Deferred imports give
per-test RED/GREEN resolution and let individual tests surface a specific
``AttributeError`` / ``ImportError``.

**Mutation vs return**: the plan leaves open whether ``compose_hotspots``
mutates ``report`` or returns a new ``Report``. Tests bind
``result = compose_hotspots(report) or report`` so they pass under either
implementation choice. Assertions target the observable state on ``result``.

**Determinism**: the hotspot Top-N list MUST be byte-deterministic on
identical inputs (same SHA → same Top-N). Tests assert
this by calling the composer twice on equivalent inputs and comparing the
resulting Top-N list.

**Gini**: the formula is pinned in the test docstrings where used. Uniform
distributions collapse to Gini = 0; a one-hot distribution of ``n`` files
approaches Gini = ``(n-1)/n``. Small-N closed-form cases exercise both
endpoints.

**Soft contract on fallback dimension**: the hotspot ADR specifies "scc
branch-count per file" as the lizard fallback, but the existing
``SccCollector`` emits ``per_file_sloc`` (lines of code per file), not
branch counts. The fallback tests assume the implementer reads
``report.collectors["scc"].data["per_file_sloc"]`` as the complexity proxy
and marks ``complexity_source = "scc_fallback"``. This matches the behavior
the plan's "Done when" clause asserts ("Fallback path (scc branch-count)
labeled in output") while aligning with the only per-file dimension scc
actually produces.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.project_metrics.collectors.base import CollectorResult
from scripts.project_metrics.schema import (
    AggregateBlock,
    Report,
    RunMetadata,
    SCHEMA_VERSION,
    TrendBlock,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic Report builders. Tests use these rather than hand-rolling
# the full dataclass tree at each call site. Keeps "what" in the test body and
# "how" here.
# ---------------------------------------------------------------------------


def _zero_aggregate() -> AggregateBlock:
    """An AggregateBlock with placeholder zeros for fields the composer overwrites.

    The hotspot composer writes ``hotspot_top_score`` and ``hotspot_gini``; all
    other aggregate columns are incidental to these tests and can be any
    dataclass-valid placeholder. Using zeros (rather than ``None``) for the
    non-nullable columns keeps the dataclass well-formed under
    ``@dataclass(frozen=True)``.
    """

    return AggregateBlock(
        schema_version=SCHEMA_VERSION,
        timestamp="2026-04-24T00:00:00Z",
        commit_sha="0" * 40,
        window_days=90,
        sloc_total=0,
        file_count=0,
        language_count=0,
        ccn_p95=None,
        cognitive_p95=None,
        cyclic_deps=None,
        churn_total_90d=0,
        change_entropy_90d=0.0,
        truck_factor=0,
        hotspot_top_score=0.0,
        hotspot_gini=0.0,
        coverage_line_pct=None,
    )


def _make_report(
    *,
    churn: dict[str, int] | None = None,
    lizard_max_ccn: dict[str, int] | None = None,
    scc_per_file_sloc: dict[str, int] | None = None,
    top_n: int = 10,
) -> Report:
    """Build a minimal Report for hotspot-composition tests.

    Each keyword is optional:

    * ``churn=None`` omits the git namespace entirely (represents a hard
      failure upstream; should be an error before hotspot runs, but we want
      the composer to be robust).
    * ``lizard_max_ccn=None`` simulates lizard being skipped (namespace carries
      the uniform 3-key skip marker instead of usable data).
    * ``scc_per_file_sloc=None`` simulates scc being skipped.
    """

    collectors: dict[str, CollectorResult] = {}

    if churn is not None:
        collectors["git"] = CollectorResult(
            status="ok",
            data={"churn_90d": dict(churn)},
        )

    if lizard_max_ccn is not None:
        collectors["lizard"] = CollectorResult(
            status="ok",
            data={
                "files": {
                    path: {"max_ccn": value} for path, value in lizard_max_ccn.items()
                }
            },
        )
    else:
        collectors["lizard"] = CollectorResult(
            status="ok",
            data={
                "status": "skipped",
                "reason": "tool_unavailable",
                "tool": "lizard",
            },
        )

    if scc_per_file_sloc is not None:
        collectors["scc"] = CollectorResult(
            status="ok",
            data={"per_file_sloc": dict(scc_per_file_sloc)},
        )
    else:
        collectors["scc"] = CollectorResult(
            status="ok",
            data={
                "status": "skipped",
                "reason": "tool_unavailable",
                "tool": "scc",
            },
        )

    return Report(
        schema_version=SCHEMA_VERSION,
        aggregate=_zero_aggregate(),
        tool_availability={},
        collectors=collectors,
        hotspots={},
        trends=TrendBlock(status="first_run"),
        run_metadata=RunMetadata(
            command_version="0.0.0",
            python_version="3.13.0",
            wall_clock_seconds=0.0,
            window_days=90,
            top_n=top_n,
        ),
    )


def _extract_hotspots(result: Any, original: Report) -> dict[str, Any]:
    """Pull the hotspots dict from either a returned Report or a mutated one.

    ``compose_hotspots`` may either return an updated Report or mutate the
    input in place; tests bind ``result = compose_hotspots(report) or report``
    and delegate here to pull the ``hotspots`` block off whichever survives.
    """

    report = result if result is not None else original
    return dict(report.hotspots)


def _extract_aggregate(result: Any, original: Report) -> AggregateBlock:
    """Pull the aggregate block with hotspot fields updated, from mutated or returned Report."""

    report = result if result is not None else original
    return report.aggregate


# ---------------------------------------------------------------------------
# Happy-path: lizard available, churn available, three files with a clean
# ordering. Encodes the Top-N shape contract and the formula
# ``churn_lines_90d x max_ccn``.
# ---------------------------------------------------------------------------


class TestHotspotHappyPath:
    """Three files with distinct scores; the ranking is unambiguous."""

    def test_top_n_ranks_by_churn_times_max_ccn_descending(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50, "c.py": 10},
            lizard_max_ccn={"a.py": 20, "b.py": 5, "c.py": 2},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        top_n = hotspots["top_n"]
        assert [entry["path"] for entry in top_n] == ["a.py", "b.py", "c.py"]
        assert [entry["rank"] for entry in top_n] == [1, 2, 3]

    def test_top_n_entries_carry_five_keys_with_correct_types(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn={"a.py": 20, "b.py": 5},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        entry = hotspots["top_n"][0]
        # Schema: path, churn_90d, complexity, hotspot_score, rank — five keys.
        assert set(entry.keys()) == {
            "path",
            "churn_90d",
            "complexity",
            "hotspot_score",
            "rank",
        }
        assert isinstance(entry["path"], str)
        assert isinstance(entry["churn_90d"], int)
        assert isinstance(entry["complexity"], int)
        assert isinstance(entry["hotspot_score"], float)
        assert isinstance(entry["rank"], int)

    def test_top_n_score_equals_churn_times_max_ccn(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50, "c.py": 10},
            lizard_max_ccn={"a.py": 20, "b.py": 5, "c.py": 2},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        by_path = {entry["path"]: entry for entry in hotspots["top_n"]}
        assert by_path["a.py"]["hotspot_score"] == pytest.approx(2000.0)
        assert by_path["b.py"]["hotspot_score"] == pytest.approx(250.0)
        assert by_path["c.py"]["hotspot_score"] == pytest.approx(20.0)

    def test_aggregate_hotspot_top_score_equals_max_of_scores(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50, "c.py": 10},
            lizard_max_ccn={"a.py": 20, "b.py": 5, "c.py": 2},
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_top_score == pytest.approx(2000.0)

    def test_aggregate_hotspot_gini_is_populated_for_non_uniform_distribution(
        self,
    ) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50, "c.py": 10},
            lizard_max_ccn={"a.py": 20, "b.py": 5, "c.py": 2},
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        # Scores [20, 250, 2000] — distribution is highly concentrated on a.py.
        # Gini is strictly greater than 0 (non-uniform) and strictly less than
        # 1 (no zero scores).
        assert aggregate.hotspot_gini is not None
        assert 0.0 < aggregate.hotspot_gini < 1.0

    def test_complexity_source_defaults_to_lizard_when_lizard_available(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100},
            lizard_max_ccn={"a.py": 20},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        # When lizard is available it drives complexity; the "scc_fallback"
        # marker should NOT appear. Tests assert the negative (not the exact
        # lizard-marker spelling) so the implementer can choose whether to
        # emit an explicit "lizard" source marker or simply omit the marker
        # on the happy path.
        assert hotspots.get("complexity_source") != "scc_fallback"


# ---------------------------------------------------------------------------
# Fallback path: lizard is skipped but scc is available. The composer uses
# scc's per-file dimension and labels the output.
# ---------------------------------------------------------------------------


class TestHotspotFallback:
    """Lizard unavailable, scc available → scc_fallback complexity marker."""

    def test_falls_back_to_scc_per_file_dimension_when_lizard_skipped(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn=None,  # lizard namespace carries skip marker
            scc_per_file_sloc={"a.py": 30, "b.py": 10},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        # Ranking is still churn x complexity, using scc's per-file dimension
        # as the complexity proxy: a.py=100*30=3000, b.py=50*10=500.
        assert [entry["path"] for entry in hotspots["top_n"]] == ["a.py", "b.py"]
        assert hotspots["top_n"][0]["hotspot_score"] == pytest.approx(3000.0)

    def test_fallback_path_labels_complexity_source_as_scc_fallback(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn=None,
            scc_per_file_sloc={"a.py": 30, "b.py": 10},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert hotspots.get("complexity_source") == "scc_fallback"


# ---------------------------------------------------------------------------
# Both unavailable: hotspot composition is skipped entirely.
# ---------------------------------------------------------------------------


class TestHotspotBothUnavailable:
    """Lizard and scc both skipped → hotspots.status='skipped', aggregate nulls."""

    def test_hotspots_block_reports_skipped_status(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn=None,
            scc_per_file_sloc=None,
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert hotspots["status"] == "skipped"

    def test_aggregate_hotspot_top_score_is_none_when_skipped(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn=None,
            scc_per_file_sloc=None,
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_top_score is None

    def test_aggregate_hotspot_gini_is_none_when_skipped(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 100, "b.py": 50},
            lizard_max_ccn=None,
            scc_per_file_sloc=None,
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_gini is None


# ---------------------------------------------------------------------------
# Gini endpoints — uniform, concentrated, and a small closed-form case.
# ---------------------------------------------------------------------------


class TestHotspotGiniProperties:
    """Closed-form Gini cases for synthetic distributions.

    The pinned formula (sorted ascending scores ``s_1 <= ... <= s_n``, total
    ``S = sum(s)``):

        Gini = (2 * sum_{i=1..n}(i * s_i) - (n + 1) * S) / (n * S)

    When ``S == 0`` the distribution has no inequality to measure; by
    convention the composer returns ``0.0``.
    """

    def test_uniform_distribution_yields_gini_zero(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        # Equal churn, equal complexity → equal scores → uniform → Gini = 0.
        report = _make_report(
            churn={"a.py": 10, "b.py": 10, "c.py": 10},
            lizard_max_ccn={"a.py": 5, "b.py": 5, "c.py": 5},
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_gini == pytest.approx(0.0, abs=1e-9)

    def test_concentrated_distribution_approaches_n_minus_one_over_n(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        # One file carries all the hotspot mass, the rest score zero.
        # For n files with one non-zero score s and (n-1) zeros, the pinned
        # Gini formula yields (n-1)/n. Here n=4 → 0.75.
        report = _make_report(
            churn={"a.py": 100, "b.py": 50, "c.py": 10, "d.py": 5},
            lizard_max_ccn={"a.py": 20, "b.py": 0, "c.py": 0, "d.py": 0},
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_gini == pytest.approx(0.75, abs=1e-6)

    def test_small_closed_form_gini_three_files(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        # Scores: a=1*1=1, b=1*1=1, c=1*3=3 (sorted: [1, 1, 3], S=5).
        # Numerator = 2*(1*1 + 2*1 + 3*3) - (3+1)*5 = 2*12 - 20 = 4.
        # Denominator = 3*5 = 15 → Gini = 4/15 ≈ 0.266666...
        report = _make_report(
            churn={"a.py": 1, "b.py": 1, "c.py": 1},
            lizard_max_ccn={"a.py": 1, "b.py": 1, "c.py": 3},
        )

        result = compose_hotspots(report)
        aggregate = _extract_aggregate(result, report)

        assert aggregate.hotspot_gini == pytest.approx(4 / 15, abs=1e-6)


# ---------------------------------------------------------------------------
# Determinism: identical input produces byte-identical Top-N output.
# ---------------------------------------------------------------------------


class TestHotspotDeterminism:
    """Determinism: same synthetic Report → same Top-N list."""

    def test_compose_is_byte_deterministic_on_equivalent_inputs(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        churn = {"a.py": 100, "b.py": 50, "c.py": 10}
        max_ccn = {"a.py": 20, "b.py": 5, "c.py": 2}

        first_report = _make_report(churn=churn, lizard_max_ccn=max_ccn)
        second_report = _make_report(churn=churn, lizard_max_ccn=max_ccn)

        first = _extract_hotspots(compose_hotspots(first_report), first_report)
        second = _extract_hotspots(compose_hotspots(second_report), second_report)

        assert first["top_n"] == second["top_n"]

    def test_tie_break_orders_by_path_ascending(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        # z.py and a.py produce identical scores (100 * 1 == 100 * 1).
        # Deterministic ordering sorts ties lexicographically by path.
        report = _make_report(
            churn={"z.py": 100, "a.py": 100},
            lizard_max_ccn={"z.py": 1, "a.py": 1},
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert [entry["path"] for entry in hotspots["top_n"]] == ["a.py", "z.py"]


# ---------------------------------------------------------------------------
# Top-N limit: default 10, overridden by run_metadata.top_n; fewer files
# returns all.
# ---------------------------------------------------------------------------


class TestHotspotTopNLimit:
    """Top-N truncation honors run_metadata.top_n, falls through when short."""

    def test_returns_all_files_when_fewer_than_top_n(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        report = _make_report(
            churn={"a.py": 10, "b.py": 20},
            lizard_max_ccn={"a.py": 1, "b.py": 1},
            top_n=10,
        )

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert len(hotspots["top_n"]) == 2

    def test_truncates_to_top_n_when_more_files_than_limit(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        # Twelve files, all with distinct scores. Default top_n=10 should keep
        # the top 10 by score.
        churn = {f"file_{i:02d}.py": i + 1 for i in range(12)}
        max_ccn = {f"file_{i:02d}.py": 1 for i in range(12)}
        report = _make_report(churn=churn, lizard_max_ccn=max_ccn, top_n=10)

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert len(hotspots["top_n"]) == 10

    def test_honors_run_metadata_top_n_override(self) -> None:
        from scripts.project_metrics.hotspot import compose_hotspots

        churn = {f"file_{i:02d}.py": i + 1 for i in range(12)}
        max_ccn = {f"file_{i:02d}.py": 1 for i in range(12)}
        report = _make_report(churn=churn, lizard_max_ccn=max_ccn, top_n=5)

        result = compose_hotspots(report)
        hotspots = _extract_hotspots(result, report)

        assert len(hotspots["top_n"]) == 5
