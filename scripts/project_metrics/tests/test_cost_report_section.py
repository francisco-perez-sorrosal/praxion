"""Behavioral tests for the ``## Cost`` Markdown report section.

These tests are written from the behavioral spec the systems-architect
produced for the cost collector's report-rendering surface, not from the
renderer's implementation -- ``render_cost`` does not exist yet, so every
test in this file is expected to fail with ``ImportError`` on first run.
The tests exercise ``render_cost(report) -> str`` directly (the same
``render_*(report) -> str`` shape every other renderer in this package
follows), rather than the full ``render_markdown`` document, so a fixture
here only needs the one namespace the function reads.

Fixture provenance: ``_grounded_cost_data`` below encodes the measured
figures from a real scan of this worktree's own observability
write-ahead log, dated to when this file was authored (the corpus is
live and append-only, so re-measure before trusting these numbers
again): 44 honestly-attributed ``agent_stop`` rows, 286 rows whose usage
predates the honesty marker, 4,768 rows carrying no usage data at all,
and 0 rows sourced from a parent session's cumulative usage -- 5,098
distinct row identities recovered from 5,170 raw rows (72 within-file
duplicates collapsed). The four attributed-token components: 6,420 input
tokens, 1,781,859 output tokens, 510,242,396 cache-read tokens, and
21,593,470 cache-create tokens, summing to 533,624,145. The per-pipeline
split behind the 44 attributed rows is itself measured (the main
checkout contributed 7, one worktree pipeline 15, a second worktree
pipeline 22), but no equivalent per-pipeline split of the four token
components was captured at measurement time -- only the corpus-wide
total was. The fixture therefore collapses the three real pipelines
into one illustrative bucket (labelled with one of the two real
worktree-pipeline slugs) carrying the corpus-wide token totals, so the
renderer's per-table shape can be exercised without inventing a
per-pipeline token split the corpus does not evidence. Every other
fixture field not named above (session counts, model names, source
lists) is illustrative only and carries no measurement claim.

``_two_tier_cost_data`` is deliberately synthetic in full: no live
Lightweight-tier attributed row exists in the corpus at measurement
time (today's live report reads the withheld-verdict shape the first
fixture exercises), so exercising the rendered-ratio shape needs a
fabricated tier mix.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

from scripts.project_metrics.schema import CollectorResult

# ---------------------------------------------------------------------------
# Grounded fixture -- see the module docstring for what is measured and what
# is illustrative.
# ---------------------------------------------------------------------------

_PIPELINE_SLUG = "process-economy-p3-6-adopt"
_TIER = "Standard"
_AGENT_TYPE = "implementer"

_TOKEN_TOTALS: dict[str, int] = {
    "tokens_in": 6420,
    "tokens_out": 1781859,
    "cache_read": 510242396,
    "cache_create": 21593470,
    "tokens_total": 533624145,
}

_ATTRIBUTED_ROWS = 44
_PRE_ATTRIBUTION_ROWS = 286
_UNPARSED_ROWS = 4768
_PARENT_SOURCED_ROWS = 0
_TOTAL_AGENT_STOP_ROWS = 5170  # 5,170 raw rows scanned; 5,098 survive dedup.
_DUPLICATES_DROPPED = _TOTAL_AGENT_STOP_ROWS - (
    _ATTRIBUTED_ROWS + _PARENT_SOURCED_ROWS + _PRE_ATTRIBUTION_ROWS + _UNPARSED_ROWS
)  # = 72, derived from the two measured row counts above, not itself measured.

# Illustrative only -- no corpus-wide unresolved-source count was captured at
# measurement time. Kept internally consistent with the attributed total
# above (4 of 44), never presented as itself a measured corpus figure.
_UNRESOLVED_ROWS = 4


def _grounded_cost_data() -> dict[str, Any]:
    """The ``cost`` collector's ``data`` envelope, corpus-grounded.

    One pipeline bucket, one tier, one agent type -- deliberately, so the
    per-pipeline/per-tier/per-agent-type tables fold the same underlying
    numbers (the three tables are three projections of one bucket list per
    the architecture, so agreement between them is the expected shape, not
    a coincidence a test should be surprised by).
    """

    bucket = {
        "pipeline_slug": _PIPELINE_SLUG,
        "tier": _TIER,
        "tier_reason": None,
        "attributed_rows": _ATTRIBUTED_ROWS,
        "sessions": 3,
        "models": ["claude-sonnet-5"],
        "tokens": dict(_TOKEN_TOTALS),
        "by_agent_type": {_AGENT_TYPE: dict(_TOKEN_TOTALS)},
    }
    return {
        "pipelines": [bucket],
        "tiers": {
            _TIER: {
                "attributed_rows": _ATTRIBUTED_ROWS,
                "tokens": dict(_TOKEN_TOTALS),
                "pipelines": [_PIPELINE_SLUG],
            }
        },
        "agent_types": {_AGENT_TYPE: dict(_TOKEN_TOTALS)},
        "unresolved_agent_type_share": {
            "unresolved_rows": _UNRESOLVED_ROWS,
            "attributed_rows": _ATTRIBUTED_ROWS,
            "share": _UNRESOLVED_ROWS / _ATTRIBUTED_ROWS,
        },
        "coverage": {
            "attributed_rows": _ATTRIBUTED_ROWS,
            "total_agent_stop_rows": _TOTAL_AGENT_STOP_ROWS,
            "quarantine": {
                "parent-sourced": _PARENT_SOURCED_ROWS,
                "pre-attribution": _PRE_ATTRIBUTION_ROWS,
                "unparsed": _UNPARSED_ROWS,
                "summary-rollup-unattributed": 0,
            },
            "duplicate_agent_ids": [],
            "sessions_durable": 13,
            "sessions_with_slug": 2,
            "sessions_slug_unknown": 11,
            "duplicates_dropped": _DUPLICATES_DROPPED,
            "sources": [],
        },
        # The live corpus carries zero attributed Lightweight-tier rows
        # today, so the withheld-verdict shape -- not a ratio -- is what a
        # live run actually produces; this fixture mirrors that.
        "standard_vs_lightweight": {
            "status": "n/a",
            "reason": "no attributed rows at tier Lightweight",
        },
    }


def _two_tier_cost_data() -> dict[str, Any]:
    """A synthetic two-tier fixture exercising the rendered-ratio shape.

    Every count below is fixture-local, not a corpus measurement -- see
    the module docstring.
    """

    standard_a = {
        "pipeline_slug": "fixture-standard-a",
        "tier": "Standard",
        "tier_reason": None,
        "attributed_rows": 2,
        "sessions": 1,
        "models": ["claude-sonnet-5"],
        "tokens": {
            "tokens_in": 100,
            "tokens_out": 200,
            "cache_read": 300,
            "cache_create": 400,
            "tokens_total": 1000,
        },
        "by_agent_type": {},
    }
    standard_b = {
        "pipeline_slug": "fixture-standard-b",
        "tier": "Standard",
        "tier_reason": None,
        "attributed_rows": 3,
        "sessions": 1,
        "models": ["claude-sonnet-5"],
        "tokens": {
            "tokens_in": 150,
            "tokens_out": 250,
            "cache_read": 350,
            "cache_create": 450,
            "tokens_total": 2000,
        },
        "by_agent_type": {},
    }
    lightweight_a = {
        "pipeline_slug": "fixture-lightweight-a",
        "tier": "Lightweight",
        "tier_reason": None,
        "attributed_rows": 1,
        "sessions": 1,
        "models": ["claude-sonnet-5"],
        "tokens": {
            "tokens_in": 10,
            "tokens_out": 20,
            "cache_read": 30,
            "cache_create": 40,
            "tokens_total": 100,
        },
        "by_agent_type": {},
    }
    return {
        "pipelines": [standard_a, standard_b, lightweight_a],
        "tiers": {},
        "agent_types": {},
        "unresolved_agent_type_share": {
            "unresolved_rows": 0,
            "attributed_rows": 6,
            "share": 0.0,
        },
        "coverage": {
            "attributed_rows": 6,
            "total_agent_stop_rows": 6,
            "quarantine": {
                "parent-sourced": 0,
                "pre-attribution": 0,
                "unparsed": 0,
                "summary-rollup-unattributed": 0,
            },
            "duplicate_agent_ids": [],
            "sessions_durable": 0,
            "sessions_with_slug": 0,
            "sessions_slug_unknown": 0,
            "duplicates_dropped": 0,
            "sources": [],
        },
        "standard_vs_lightweight": {
            "status": "rendered",
            "basis": "tokens_total",
            "standard": {"n": 2, "median": 1500.0},
            "lightweight": {"n": 1, "median": 100.0},
            "ratio": 15.0,
        },
    }


def _report(cost_data: dict[str, Any]) -> Any:
    """Minimal report-shaped stand-in exercising only what ``render_cost`` needs.

    Every sibling renderer in this package reads its own namespace off
    ``report.collectors`` through the shared namespace accessor, so a bare
    ``SimpleNamespace`` carrying just ``.collectors`` is the smallest
    fixture that exercises the real render function against
    production-shaped input, matching the convention the deep-dive
    renderer's own characterization tests already use.
    """

    return SimpleNamespace(collectors={"cost": CollectorResult(status="ok", data=cost_data)})


def _find_row_starting_with(markdown: str, key: str) -> str | None:
    """Return the first Markdown table row whose leading cell equals ``key``.

    Anchoring on the row's *leading* cell, rather than a bare substring
    search over the whole document, is what makes the per-pipeline,
    per-tier and per-agent-type table assertions distinguishable from one
    another when -- as the grounded fixture above does, deliberately --
    all three tables fold the same single bucket and so carry identical
    token figures: only the leading cell differs between a pipeline's row,
    a tier's row, and an agent type's row.
    """

    prefix = f"| {key} |"
    for line in markdown.splitlines():
        if line.startswith(prefix):
            return line
    return None


# ---------------------------------------------------------------------------
# Heading.
# ---------------------------------------------------------------------------


class TestCostHeading:
    def test_renders_a_cost_markdown_heading(self) -> None:
        # Grepped every renderer module in this package (the document
        # orchestrator and its two section-composition siblings) for the
        # literal string "## Cost" before writing this test: zero matches
        # anywhere, so a section using this exact heading collides with
        # nothing already rendered.
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        assert "## Cost" in markdown


# ---------------------------------------------------------------------------
# Token-component tables -- one test per table, each anchored on that
# table's own leading-cell marker so the three assertions stay
# distinguishable even though the grounded fixture makes all three tables
# carry identical numbers by construction.
# ---------------------------------------------------------------------------


class TestTokenComponentTables:
    def test_per_pipeline_table_row_carries_all_four_token_components_beside_the_total(
        self,
    ) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        row = _find_row_starting_with(markdown, _PIPELINE_SLUG)
        assert row is not None, "no table row starts with the fixture's pipeline slug"
        for value in _TOKEN_TOTALS.values():
            assert str(value) in row

    def test_per_tier_table_row_carries_all_four_token_components_beside_the_total(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        row = _find_row_starting_with(markdown, _TIER)
        assert row is not None, "no table row starts with the fixture's tier name"
        for value in _TOKEN_TOTALS.values():
            assert str(value) in row

    def test_per_agent_type_table_row_carries_all_four_token_components_beside_the_total(
        self,
    ) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        row = _find_row_starting_with(markdown, _AGENT_TYPE)
        assert row is not None, "no table row starts with the fixture's agent type"
        for value in _TOKEN_TOTALS.values():
            assert str(value) in row


# ---------------------------------------------------------------------------
# The Standard-vs-Lightweight cell -- two shapes, tested to render
# distinctly.
# ---------------------------------------------------------------------------


class TestStandardVsLightweightCell:
    def test_withheld_shape_names_the_reason_naming_the_missing_tier(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        assert "no attributed rows at tier Lightweight" in markdown

    def test_rendered_shape_prints_both_sample_sizes_and_the_basis(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_two_tier_cost_data()))

        assert "n=2 Standard vs n=1 Lightweight" in markdown
        assert "tokens_total" in markdown


# ---------------------------------------------------------------------------
# Unresolved agent-type-source share.
# ---------------------------------------------------------------------------


class TestUnresolvedAgentTypeShare:
    def test_per_agent_type_section_states_the_unresolved_share(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        unresolved_line = next(
            (line for line in markdown.splitlines() if "unresolved" in line), None
        )
        assert unresolved_line is not None, "no line mentions the unresolved agent-type share"
        assert str(_UNRESOLVED_ROWS) in unresolved_line
        assert str(_ATTRIBUTED_ROWS) in unresolved_line


# ---------------------------------------------------------------------------
# The coverage line.
# ---------------------------------------------------------------------------


class TestCoverageLine:
    def test_renders_the_attributed_over_total_coverage_line(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_grounded_cost_data()))

        expected = f"coverage: {_ATTRIBUTED_ROWS} attributed / {_TOTAL_AGENT_STOP_ROWS} total"
        assert expected in markdown


# ---------------------------------------------------------------------------
# Regression: adding the section must not touch the frozen aggregate
# contract or the append-only log writer.
# ---------------------------------------------------------------------------


class TestNoRegressionToSiblingContracts:
    def test_aggregate_columns_stay_the_frozen_sixteen_column_golden_tuple(self) -> None:
        from scripts.project_metrics._report_sections import render_cost
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        _ = render_cost(_report(_grounded_cost_data()))

        assert AGGREGATE_COLUMNS == (
            "schema_version",
            "timestamp",
            "commit_sha",
            "window_days",
            "sloc_total",
            "file_count",
            "language_count",
            "ccn_p95",
            "cognitive_p95",
            "cyclic_deps",
            "churn_total_90d",
            "change_entropy_90d",
            "truck_factor",
            "hotspot_top_score",
            "hotspot_gini",
            "coverage_line_pct",
        )

    def test_no_metrics_log_writer_references_a_cost_key(self) -> None:
        from scripts.project_metrics import logappend
        from scripts.project_metrics._report_sections import render_cost

        _ = render_cost(_report(_grounded_cost_data()))

        source = inspect.getsource(logappend)
        assert '"cost"' not in source
        assert "'cost'" not in source


# ---------------------------------------------------------------------------
# Degraded states -- each renders one skip marker naming its reason, never
# the empty-table shape a real payload would produce.
# ---------------------------------------------------------------------------


def _degraded_report(entry: Any, availability: Any = None) -> Any:
    return SimpleNamespace(
        collectors={"cost": entry},
        tool_availability={} if availability is None else {"cost": availability},
    )


def _zero_attributed_data(source_kinds: list[str]) -> dict[str, Any]:
    data = _grounded_cost_data()
    data["pipelines"], data["tiers"], data["agent_types"] = [], {}, {}
    data["coverage"] = {
        **data["coverage"],
        "attributed_rows": 0,
        "sources": [{"path": f"/repo/.ai-state/{kind}", "kind": kind} for kind in source_kinds],
    }
    return data


class TestDegradedStates:
    def test_skipped_collector_names_the_resolution_reason_instead_of_tables(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        reason = "no observability artifacts under .ai-state/"
        markdown = render_cost(
            _degraded_report(
                {"status": "skipped", "reason": "tool_unavailable", "tool": "cost"},
                SimpleNamespace(status="not_applicable", reason=reason),
            )
        )

        assert reason in markdown
        assert "### Per-pipeline" not in markdown

    def test_error_status_names_the_collector_issue_instead_of_tables(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        issue = "provenance guard: attributed totals disagree with the audit census"
        markdown = render_cost(
            _degraded_report(CollectorResult(status="error", data={}, issues=[issue]))
        )

        assert issue in markdown
        assert "### Per-pipeline" not in markdown

    def test_zero_attributed_rows_without_a_wal_source_names_the_unreachable_wal(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_zero_attributed_data(["summary"])))

        assert "no reachable WAL (machine-local since dec-377)" in markdown
        assert "### Per-pipeline" not in markdown

    def test_zero_attributed_rows_beside_a_reachable_wal_still_render_the_tables(self) -> None:
        from scripts.project_metrics._report_sections import render_cost

        markdown = render_cost(_report(_zero_attributed_data(["wal", "summary"])))

        assert "### Per-pipeline" in markdown
        assert "no reachable WAL" not in markdown
