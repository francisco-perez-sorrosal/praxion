"""Behavioral tests for the cost collector's aggregate pass.

Covers the tier join, pipeline-bucket aggregation, the committed-summary
census, the dec-378 executable guard, and the Standard-vs-Lightweight cell
-- the aggregate-side seam that stays in
`scripts/project_metrics/collectors/cost_collector.py` (plus its
`cost_collector_tier`/`cost_collector_report` siblings) after the
read/aggregate split, reached through the `cost_collector` facade module
tests import from below.

**Import strategy**: every test imports from `cost_collector` inside the
test body (the "RED/GREEN deferred-import convention" this test suite
inherits from `test_git_collector.py`), preserved for consistency with the
read-pass and collector-wiring siblings this file was split from.

**Interface pinned by this test file** (the rationale behind each pinned
name was recorded in the pipeline's learnings):

- `TierResolved` / `TierAmbiguous` / `TierUnknown` -- frozen dataclasses,
  the three-variant tier-join result (`TierResolved(tier, rows)`,
  `TierAmbiguous(tiers, rows)`, `TierUnknown(reason)`).
- `parse_calibration_log(path: str) -> dict[str, list[str]]` -- slug (the
  Task cell's first whitespace-delimited token) to an ordered list of
  normalized `Actual Tier` tokens (the cell's leading alphabetic run), one
  per calibration-log row for that slug.
- `resolve_tier(slug: str, tier_index: dict[str, list[str]]) -> TierResolved | TierAmbiguous | TierUnknown`
- `PipelineBucket` -- frozen dataclass: `pipeline_slug, tier, tier_reason,
  attributed_rows, sessions, models, tokens, by_agent_type`.
- `build_pipeline_buckets(rows, tier_index) -> list[PipelineBucket]` -- the
  ONE fold every per-pipeline/per-tier/per-agent-type table projects from.
- `unresolved_agent_type_share(rows) -> dict` -- `{"unresolved_rows",
  "attributed_rows", "share"}` over a sequence of `AttributedRow`.
- `Coverage` -- frozen dataclass: `attributed_rows, total_agent_stop_rows,
  quarantine, duplicate_agent_ids, sessions_durable, sessions_with_slug,
  sessions_slug_unknown, sources`.
- `summary_row_slug(row: dict) -> str` -- `row.get("pipeline_slug",
  "unknown")`.
- `summary_row_is_rollup_unattributed(row: dict) -> bool` -- true when the
  row's `tokens_by_agent_type` carries any populated rollup.
- `_audit_totals(coverage: Coverage, buckets: list[PipelineBucket]) -> list[str]`
  -- the dec-378 executable guard; returns violated-invariant messages, empty
  when consistent.
- `compute_standard_vs_lightweight_cell(buckets: list[PipelineBucket]) -> dict` -- the two result
  shapes (`{"status": "n/a", "reason": ...}` /
  `{"status": "rendered", "basis": "tokens_total", "standard": {...},
  "lightweight": {...}, "ratio": ...}`), sharing no numeric key.

**Fixture provenance** (stated once here; restated per-use below):

- `calibration_log_excerpt.md` (loaded via the `calibration_log_excerpt_path`
  fixture in `conftest.py` -- shared cross-file with
  `test_cost_collector_collector.py`) -- **verbatim**, nine pipe-table rows
  (plus header and separator) copied byte-for-byte from
  `.ai-state/calibration_log.md`: the two agreeing Standard-tier rows for
  `process-economy-p3-2-adopt` and `process-economy-p3-6-adopt`, plus
  every row for the three slugs whose calibration rows disagree on tier
  (`sentinel-fanout-audit`: Full + Standard; `process-economy-phase1`:
  Direct + Lightweight + Full; `process-economy-p2-residual`: Direct +
  Standard).
- `summary_rollup_unattributed.jsonl` -- **verbatim**, one committed
  session-summary row copied byte-for-byte from this worktree's own
  `.ai-state/observations_summary.jsonl` (session `50ac9347...`),
  carrying the measured 14,666,970,597-token `tokens_by_agent_type`
  rollup. This row (like every row in that file today) also lacks
  `pipeline_slug` -- it doubles as the pre-change fixture for the
  `slug: unknown` census path, the same single-session reuse choice this
  test suite's own legacy-row fixture already made.
- Bucket/coverage fixtures below (`_make_attributed_row`, `_make_coverage`,
  `_make_pipeline_bucket`) are **hand-constructed** test data builders,
  per the aggregate pass's own fixture strategy (a mechanical rule over
  row shape, not a provenance claim, so hand construction is appropriate).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from scripts.project_metrics.tests.conftest import _load_single_row

# ---------------------------------------------------------------------------
# Tier join -- resolving a pipeline slug to a calibration-log tier.
# `calibration_log_excerpt_path` lives in conftest.py (see its docstring) --
# TestCostCollectorProductionWiring in test_cost_collector_collector.py also
# depends on it.
# ---------------------------------------------------------------------------


class TestParseCalibrationLog:
    """`parse_calibration_log` builds the slug -> tier-tokens index every
    tier-resolution test below reads from.
    """

    def test_normalizes_the_actual_tier_cells_leading_alphabetic_token(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import parse_calibration_log

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        assert index["process-economy-p3-2-adopt"] == ["Standard"]
        assert index["process-economy-p3-6-adopt"] == ["Standard"]
        assert set(index["sentinel-fanout-audit"]) == {"Full", "Standard"}, (
            "Both sentinel-fanout-audit rows must be indexed -- prose-decorated "
            "cells like 'Standard (batched, ...)' must normalize to 'Standard', "
            "not fail to parse or be indexed under the raw prose."
        )

    @pytest.mark.skipif(
        os.geteuid() == 0,
        reason="root ignores file modes; remove when the reader is injected",
    )
    def test_an_unreadable_calibration_log_is_a_named_issue_not_a_raise(
        self, tmp_path: Path, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import _load_tier_index

        log = tmp_path / ".ai-state" / "calibration_log.md"
        log.parent.mkdir()
        log.write_text(calibration_log_excerpt_path.read_text())
        log.chmod(0o000)
        issues: list[str] = []

        try:
            index = _load_tier_index(str(tmp_path), issues)
        finally:
            log.chmod(0o600)

        assert index == {}
        assert len(issues) == 1, issues
        assert "calibration log unreadable" in issues[0], issues

    def test_an_invalid_utf8_byte_in_the_log_degrades_that_cell_not_the_index(
        self, tmp_path: Path, calibration_log_excerpt_path: Path
    ) -> None:
        """The WAL reader and the producing hook both decode with
        `errors="replace"`; the calibration log gets the same treatment so
        one bad byte cannot raise a `UnicodeDecodeError` out of `collect()`."""

        from scripts.project_metrics.collectors.cost_collector import parse_calibration_log

        log = tmp_path / "calibration_log.md"
        log.write_bytes(
            calibration_log_excerpt_path.read_bytes()
            + b"| 2026-01-01 | bad\xff-row | x | x | Direct | x | x |\n"
        )

        index = parse_calibration_log(str(log))

        assert index["process-economy-p3-6-adopt"] == ["Standard"]


class TestResolveTier:
    """`resolve_tier` is the join itself -- slug -> tier is not a function,
    so it must expose three outcomes, never silently pick one.
    """

    @pytest.mark.parametrize("slug", ["process-economy-p3-2-adopt", "process-economy-p3-6-adopt"])
    def test_resolves_a_single_agreeing_slug_to_its_tier(
        self, calibration_log_excerpt_path: Path, slug: str
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierResolved,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier(slug, index)

        assert isinstance(result, TierResolved)
        assert result.tier == "Standard"

    @pytest.mark.parametrize(
        ("slug", "expected_tiers"),
        [
            ("sentinel-fanout-audit", {"Full", "Standard"}),
            ("process-economy-phase1", {"Direct", "Lightweight", "Full"}),
            ("process-economy-p2-residual", {"Direct", "Standard"}),
        ],
    )
    def test_resolves_a_disagreeing_slug_to_ambiguous_with_every_tier_listed(
        self, calibration_log_excerpt_path: Path, slug: str, expected_tiers: set[str]
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierAmbiguous,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier(slug, index)

        assert isinstance(result, TierAmbiguous)
        assert set(result.tiers) == expected_tiers, (
            "A silent first-wins pick would fabricate a tier -- every "
            "disagreeing tier must be listed, not just the first one seen."
        )

    def test_resolves_a_slug_absent_from_the_calibration_log_to_unknown(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            TierUnknown,
            parse_calibration_log,
            resolve_tier,
        )

        index = parse_calibration_log(str(calibration_log_excerpt_path))

        result = resolve_tier("no-such-pipeline-ever-ran", index)

        assert isinstance(result, TierUnknown)
        assert result.reason == "no-calibration-row"


# ---------------------------------------------------------------------------
# Pipeline bucket aggregation -- one bucket list, three projections.
# ---------------------------------------------------------------------------


def _make_attributed_row(**overrides: Any) -> Any:
    """Build an `AttributedRow` directly via its dataclass constructor --
    a test data builder with minimal, overridable defaults, per the
    aggregate pass's own fixture strategy (a mechanical rule over row
    shape, not a provenance claim, so hand construction is appropriate).
    """

    from scripts.project_metrics.collectors.cost_collector import AttributedRow

    defaults: dict[str, Any] = {
        "agent_id": "agent-default",
        "session_id": "session-default",
        "pipeline_slug": "process-economy-p3-2-adopt",
        "agent_type": "praxion:implementer",
        "agent_type_source": "payload",
        "model": "claude-sonnet-5",
        "tokens_in": 10,
        "tokens_out": 20,
        "cache_read": 30,
        "cache_create": 40,
        "duration_ms": 1000,
        "timestamp": "2026-09-21T00:00:00+00:00",
        "source_path": "fixtures/cost/synthetic.jsonl",
    }
    defaults.update(overrides)
    return AttributedRow(**defaults)


class TestBuildPipelineBuckets:
    """`build_pipeline_buckets` folds attributed rows into one bucket per
    `pipeline_slug`, joined to its tier -- the single population every
    per-pipeline/per-tier/per-agent-type table is a projection of.
    """

    def test_folds_same_slug_rows_into_one_bucket_carrying_the_resolved_tier(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        row_one = _make_attributed_row(
            agent_id="a1",
            pipeline_slug="process-economy-p3-2-adopt",
            agent_type="praxion:implementer",
            tokens_in=10,
            tokens_out=20,
            cache_read=30,
            cache_create=40,
        )
        row_two = _make_attributed_row(
            agent_id="a2",
            pipeline_slug="process-economy-p3-2-adopt",
            agent_type="praxion:test-engineer",
            tokens_in=1,
            tokens_out=2,
            cache_read=3,
            cache_create=4,
        )

        buckets = build_pipeline_buckets([row_one, row_two], tier_index)

        assert len(buckets) == 1, "Both rows share one pipeline_slug -- one bucket, not two."
        bucket = buckets[0]
        assert bucket.pipeline_slug == "process-economy-p3-2-adopt"
        assert bucket.tier == "Standard"
        assert bucket.attributed_rows == 2
        assert bucket.tokens["tokens_total"] == (10 + 20 + 30 + 40) + (1 + 2 + 3 + 4)
        assert set(bucket.by_agent_type) == {"praxion:implementer", "praxion:test-engineer"}

    def test_an_unjoinable_slug_still_gets_its_own_bucket_marked_unknown(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        row = _make_attributed_row(agent_id="a1", pipeline_slug="never-calibrated")

        buckets = build_pipeline_buckets([row], tier_index)

        assert len(buckets) == 1
        assert buckets[0].tier == "unknown", (
            "An unjoinable pipeline stays visible, never dropped -- the "
            "brief's core constraint for an uncalibrated slug."
        )

    def test_per_tier_and_per_agent_type_totals_never_disagree_with_the_grand_total(
        self, calibration_log_excerpt_path: Path
    ) -> None:
        """Three tables -- per-pipeline, per-tier, per-agent-type -- must be
        three projections of the SAME bucket list. Grouping the same
        buckets two different ways (by tier, by agent type) and comparing
        each grouped sum against the ungrouped grand total is the property
        that makes the tables structurally unable to disagree -- three
        independent scans over the raw rows could silently drift apart,
        one fold over one list cannot.
        """

        from scripts.project_metrics.collectors.cost_collector import (
            build_pipeline_buckets,
            parse_calibration_log,
        )

        tier_index = parse_calibration_log(str(calibration_log_excerpt_path))
        rows = [
            _make_attributed_row(
                agent_id="std-1",
                pipeline_slug="process-economy-p3-2-adopt",
                agent_type="praxion:implementer",
                tokens_in=10,
                tokens_out=20,
                cache_read=30,
                cache_create=40,
            ),
            _make_attributed_row(
                agent_id="std-2",
                pipeline_slug="process-economy-p3-6-adopt",
                agent_type="praxion:test-engineer",
                tokens_in=1,
                tokens_out=2,
                cache_read=3,
                cache_create=4,
            ),
        ]

        buckets = build_pipeline_buckets(rows, tier_index)
        grand_total = sum(bucket.tokens["tokens_total"] for bucket in buckets)

        tier_totals: dict[str, int] = {}
        for bucket in buckets:
            tier_totals[bucket.tier] = (
                tier_totals.get(bucket.tier, 0) + bucket.tokens["tokens_total"]
            )

        agent_type_totals: dict[str, int] = {}
        for bucket in buckets:
            for agent_type, agent_tokens in bucket.by_agent_type.items():
                agent_type_totals[agent_type] = (
                    agent_type_totals.get(agent_type, 0) + agent_tokens["tokens_total"]
                )

        assert sum(tier_totals.values()) == grand_total, (
            "Grouping the same buckets by tier must reproduce the grand "
            "total -- the per-tier table cannot show a different sum than "
            "the per-pipeline table."
        )
        assert sum(agent_type_totals.values()) == grand_total, (
            "Grouping the same buckets by agent type must also reproduce the grand total."
        )


class TestUnresolvedAgentTypeShare:
    """The unresolved `agent_type_source` share is its own figure, never
    folded into a named agent type's total.
    """

    def test_reports_the_unresolved_share_of_attributed_rows(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            unresolved_agent_type_share,
        )

        resolved_row = _make_attributed_row(agent_id="r1", agent_type_source="payload")
        unresolved_row_a = _make_attributed_row(agent_id="u1", agent_type_source="unresolved")
        unresolved_row_b = _make_attributed_row(agent_id="u2", agent_type_source="unresolved")

        result = unresolved_agent_type_share([resolved_row, unresolved_row_a, unresolved_row_b])

        assert result["unresolved_rows"] == 2
        assert result["attributed_rows"] == 3
        assert result["share"] == pytest.approx(2 / 3)

    def test_zero_attributed_rows_reports_a_zero_share_without_dividing_by_zero(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            unresolved_agent_type_share,
        )

        result = unresolved_agent_type_share([])

        assert result["unresolved_rows"] == 0
        assert result["attributed_rows"] == 0
        assert result["share"] == 0


# ---------------------------------------------------------------------------
# Committed-summary census -- read-only, never a token source.
# ---------------------------------------------------------------------------


class TestSummaryRowCensusHelpers:
    """The committed summary's pipeline-slug census, and the
    summary-rollup-unattributed quarantine population its
    `tokens_by_agent_type` rollup belongs to -- over the committed
    `observations_summary.jsonl` row shape.
    """

    def test_a_summary_row_without_pipeline_slug_reads_as_unknown(
        self, cost_fixtures_dir: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import summary_row_slug

        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        assert "pipeline_slug" not in row, "Fixture drift: every committed row lacks the key today."
        assert summary_row_slug(row) == "unknown"

    def test_a_summary_row_carrying_pipeline_slug_reads_its_real_slug(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import summary_row_slug

        row = {"session_id": "x", "pipeline_slug": "process-economy-p3-2-adopt"}

        assert summary_row_slug(row) == "process-economy-p3-2-adopt"

    def test_the_measured_14_billion_token_rollup_is_counted_as_quarantined(
        self, cost_fixtures_dir: Path
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            summary_row_is_rollup_unattributed,
        )

        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        assert summary_row_is_rollup_unattributed(row) is True

    def test_a_summary_row_with_no_token_rollup_is_not_quarantined(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            summary_row_is_rollup_unattributed,
        )

        row = {"session_id": "y", "tokens_by_agent_type": {}}

        assert summary_row_is_rollup_unattributed(row) is False


class TestAggregatePassFixtureIntegrity:
    """Guards the aggregate-pass fixtures themselves, not the collector."""

    def test_summary_rollup_fixture_carries_the_measured_token_total(
        self, cost_fixtures_dir: Path
    ) -> None:
        row = _load_single_row(cost_fixtures_dir / "summary_rollup_unattributed.jsonl")

        total = sum(sum(per_type.values()) for per_type in row["tokens_by_agent_type"].values())

        assert total == 14_666_970_597
        assert "pipeline_slug" not in row


# ---------------------------------------------------------------------------
# The dec-378 executable guard -- re-derivation, not assertion.
# ---------------------------------------------------------------------------


def _make_coverage(**overrides: Any) -> Any:
    from scripts.project_metrics.collectors.cost_collector import Coverage

    defaults: dict[str, Any] = {
        "attributed_rows": 2,
        "total_agent_stop_rows": 5,
        "quarantine": {
            "parent-sourced": 0,
            "pre-attribution": 1,
            "unparsed": 2,
            "summary-rollup-unattributed": 0,
        },
        "duplicate_agent_ids": [],
        "sessions_durable": 0,
        "sessions_with_slug": 0,
        "sessions_slug_unknown": 0,
        "sources": [],
    }
    defaults.update(overrides)
    return Coverage(**defaults)


def _make_pipeline_bucket(**overrides: Any) -> Any:
    from scripts.project_metrics.collectors.cost_collector import PipelineBucket

    defaults: dict[str, Any] = {
        "pipeline_slug": "process-economy-p3-2-adopt",
        "tier": "Standard",
        "tier_reason": None,
        "attributed_rows": 2,
        "sessions": 1,
        "models": frozenset({"claude-sonnet-5"}),
        "tokens": {
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_read": 0,
            "cache_create": 0,
            "tokens_total": 0,
        },
        "by_agent_type": {},
    }
    defaults.update(overrides)
    return PipelineBucket(**defaults)


class TestAuditTotals:
    """`_audit_totals` re-derives two counts from independent sources and
    compares them before any total is published -- proven here at the unit
    level; the fault-injection test (in `test_cost_collector_collector.py`)
    proves it fires through the full `collect()` path.
    """

    def test_consistent_counts_produce_no_issues(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage()
        bucket = _make_pipeline_bucket(attributed_rows=2)

        assert _audit_totals(coverage, [bucket]) == []

    def test_a_bucket_sum_mismatched_with_coverage_names_the_invariant(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage(attributed_rows=2)
        bucket = _make_pipeline_bucket(attributed_rows=99)  # deliberately wrong

        issues = _audit_totals(coverage, [bucket])

        assert issues, "A bucket-sum/coverage mismatch must be reported, never silently accepted."
        assert "attributed" in issues[0].lower()

    def test_a_quarantine_census_mismatched_with_the_total_names_the_invariant(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import _audit_totals

        coverage = _make_coverage(total_agent_stop_rows=999)  # no longer sums correctly
        bucket = _make_pipeline_bucket(attributed_rows=2)

        issues = _audit_totals(coverage, [bucket])

        assert issues, (
            "attributed + quarantine must equal total_agent_stop_rows, or the guard fires."
        )


# ---------------------------------------------------------------------------
# Standard-vs-Lightweight cell -- the withheld-verdict shape, and the rendered ratio.
# ---------------------------------------------------------------------------


class TestComputeStandardVsLightweightCell:
    """Two shapes sharing no numeric key -- a consumer cannot read a
    ratio out of an `n/a` cell.
    """

    def test_renders_na_when_the_lightweight_median_is_zero_tokens(self) -> None:
        """Attributed rows do not imply a non-zero total; a zero divisor is
        an `n/a` cell with a reason, never a raise."""

        from scripts.project_metrics.collectors.cost_collector import (
            compute_standard_vs_lightweight_cell,
        )

        zero_tokens = {
            "tokens_in": 0,
            "tokens_out": 0,
            "cache_read": 0,
            "cache_create": 0,
            "tokens_total": 0,
        }
        standard_bucket = _make_pipeline_bucket(
            pipeline_slug="standard-1",
            tier="Standard",
            attributed_rows=1,
            tokens={**zero_tokens, "tokens_total": 1000},
        )
        lightweight_bucket = _make_pipeline_bucket(
            pipeline_slug="lightweight-1",
            tier="Lightweight",
            attributed_rows=1,
            tokens=zero_tokens,
        )

        cell = compute_standard_vs_lightweight_cell([standard_bucket, lightweight_bucket])

        assert cell["status"] == "n/a"
        assert "zero" in cell["reason"].lower(), cell
        assert "ratio" not in cell

    def test_renders_na_with_a_reason_when_one_tier_has_zero_attributed_rows(self) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            compute_standard_vs_lightweight_cell,
        )

        standard_bucket = _make_pipeline_bucket(
            pipeline_slug="process-economy-p3-2-adopt",
            tier="Standard",
            attributed_rows=5,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 1000,
            },
        )

        cell = compute_standard_vs_lightweight_cell([standard_bucket])

        assert cell["status"] == "n/a"
        assert "lightweight" in cell["reason"].lower()
        assert "standard" not in cell
        assert "ratio" not in cell

    def test_renders_the_ratio_with_both_sample_sizes_and_basis_when_both_tiers_qualify(
        self,
    ) -> None:
        from scripts.project_metrics.collectors.cost_collector import (
            compute_standard_vs_lightweight_cell,
        )

        standard_bucket_one = _make_pipeline_bucket(
            pipeline_slug="standard-1",
            tier="Standard",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 1000,
            },
        )
        standard_bucket_two = _make_pipeline_bucket(
            pipeline_slug="standard-2",
            tier="Standard",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 3000,
            },
        )
        lightweight_bucket = _make_pipeline_bucket(
            pipeline_slug="lightweight-1",
            tier="Lightweight",
            attributed_rows=1,
            tokens={
                "tokens_in": 0,
                "tokens_out": 0,
                "cache_read": 0,
                "cache_create": 0,
                "tokens_total": 500,
            },
        )

        cell = compute_standard_vs_lightweight_cell(
            [standard_bucket_one, standard_bucket_two, lightweight_bucket]
        )

        assert cell["status"] == "rendered"
        assert cell["basis"] == "tokens_total"
        assert cell["standard"]["n"] == 2
        assert cell["lightweight"]["n"] == 1
        assert cell["ratio"] == pytest.approx(
            cell["standard"]["median"] / cell["lightweight"]["median"]
        )
