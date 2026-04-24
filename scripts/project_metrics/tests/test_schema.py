"""Behavioral tests for the canonical JSON schema module.

These tests encode the architect's frozen-on-first-release aggregate-column
contract plus the schema-version + timestamp presence guarantees the
downstream UI depends on. They are written *from the behavioral spec*, not
the implementation -- production code (`scripts/project_metrics/schema.py`)
is not read while authoring these tests.

Golden column ordering is lifted verbatim from the Metrics storage schema
ADR (section "Frozen aggregate-block columns (v1.0.0)") -- the canonical
source of truth. If the implementation re-orders the columns, that is a
freeze violation and this test fails loudly.

Import strategy: each test imports symbols from `scripts.project_metrics.schema`
at test-body time (deferred import). This is deliberate -- during the
BDD/TDD RED handshake, the module stub does not yet export these symbols,
and top-of-module imports would break pytest collection for every test in
this file simultaneously. Deferred imports give per-test RED/GREEN resolution.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# Golden data -- mirrors dec-draft-b068ad8e "Frozen aggregate-block columns
# (v1.0.0)" in exact declaration order. Any drift in the ADR OR in the
# production code triggers the freeze-violation test below.
# ---------------------------------------------------------------------------

GOLDEN_AGGREGATE_COLUMNS: tuple[str, ...] = (
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

# ---------------------------------------------------------------------------
# Sample-data helpers -- construct a minimal but complete Report that can be
# fed through to_json(). Values are literal; no clock, no random, no env.
# ---------------------------------------------------------------------------


def _sample_aggregate_kwargs() -> dict[str, Any]:
    """16 aggregate-block fields with deterministic literal values.

    Types chosen to match the ADR's "Type" column (string/int/number/null).
    Null-eligible fields (`ccn_p95`, `cognitive_p95`, `cyclic_deps`,
    `coverage_line_pct`) are populated with numeric values here to avoid
    confusing the "schema_version + timestamp present" assertion with a
    null-handling assertion.
    """
    return {
        "schema_version": "1.0.0",
        "timestamp": "2026-04-23T12:00:00Z",
        "commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
        "window_days": 90,
        "sloc_total": 1234,
        "file_count": 42,
        "language_count": 3,
        "ccn_p95": 7.5,
        "cognitive_p95": 9.0,
        "cyclic_deps": 0,
        "churn_total_90d": 567,
        "change_entropy_90d": 2.1,
        "truck_factor": 2,
        "hotspot_top_score": 123.4,
        "hotspot_gini": 0.75,
        "coverage_line_pct": 81.3,
    }


def _build_sample_report() -> Any:
    """Build a minimal `Report` instance suitable for `to_json()`.

    Shape is derived from the storage-schema ADR's example root JSON:
    `schema_version`, `aggregate`, `tool_availability`, plus per-collector
    namespace entries. The collectors/hotspots/trends/run_metadata content
    is illustrative rather than prescriptive -- the tests that use this
    helper only depend on `schema_version` (root) and `aggregate.timestamp`
    (nested) being present in the serialized output.

    If the implementer chooses a differently-shaped `Report` signature
    (different required args), the `TypeError` surfaced here is actionable
    feedback rather than a test-design flaw.
    """
    from scripts.project_metrics.schema import AggregateBlock, Report

    aggregate = AggregateBlock(**_sample_aggregate_kwargs())
    # Construct via keyword-only args that match the ADR's root-JSON shape.
    # Any extra required fields added by the implementer will surface as
    # a TypeError here and become an actionable Register-Objection signal.
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability={},
        collectors={},
    )


# ---------------------------------------------------------------------------
# Tests -- named after the behavior under verification; no REQ/AC/step IDs
# per rules/swe/id-citation-discipline.md. Traceability lives in
# .ai-work/<slug>/traceability.yml.
# ---------------------------------------------------------------------------


class TestSchemaVersionConstant:
    """The SCHEMA_VERSION constant is the pinned release identifier consumed
    by METRICS_LOG.md rows and the schema-mismatch delta policy."""

    def test_schema_version_constant_is_1_0_0(self) -> None:
        from scripts.project_metrics.schema import SCHEMA_VERSION

        assert SCHEMA_VERSION == "1.0.0"

    def test_schema_version_is_string(self) -> None:
        from scripts.project_metrics.schema import SCHEMA_VERSION

        assert isinstance(SCHEMA_VERSION, str)


class TestAggregateColumnsFreeze:
    """AGGREGATE_COLUMNS is the frozen 16-column contract for METRICS_LOG.md
    and the aggregate JSON block. The tuple is compared verbatim against
    the golden order lifted from the storage-schema ADR."""

    def test_aggregate_columns_is_a_tuple(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        assert isinstance(AGGREGATE_COLUMNS, tuple), (
            "AGGREGATE_COLUMNS must be a tuple (immutable) -- a list would "
            "silently permit reorder/append mutations at import time."
        )

    def test_aggregate_columns_has_sixteen_entries(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        assert len(AGGREGATE_COLUMNS) == 16

    def test_aggregate_columns_matches_frozen_golden_order(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        assert AGGREGATE_COLUMNS == GOLDEN_AGGREGATE_COLUMNS

    def test_aggregate_columns_all_entries_are_strings(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        assert all(isinstance(col, str) for col in AGGREGATE_COLUMNS)

    def test_aggregate_columns_has_no_duplicates(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        assert len(set(AGGREGATE_COLUMNS)) == len(AGGREGATE_COLUMNS)


class TestToJsonContract:
    """to_json() serializes a Report to deterministic bytes carrying the
    schema_version at root and aggregate.timestamp nested. These two
    JSON paths are the downstream-UI handshake -- any absence is a
    contract break."""

    def test_to_json_returns_bytes(self) -> None:
        from scripts.project_metrics.schema import to_json

        result = to_json(_build_sample_report())
        assert isinstance(result, bytes)

    def test_to_json_payload_contains_schema_version_at_root(self) -> None:
        from scripts.project_metrics.schema import to_json

        payload = json.loads(to_json(_build_sample_report()).decode("utf-8"))

        assert "schema_version" in payload, (
            "Serialized payload must expose schema_version at the top "
            "level -- downstream UI reads it without descending into blocks."
        )
        assert payload["schema_version"] == "1.0.0"

    def test_to_json_payload_contains_aggregate_timestamp(self) -> None:
        from scripts.project_metrics.schema import to_json

        payload = json.loads(to_json(_build_sample_report()).decode("utf-8"))

        assert "aggregate" in payload
        assert isinstance(payload["aggregate"], dict)
        assert "timestamp" in payload["aggregate"], (
            "aggregate.timestamp is the time-axis the METRICS_LOG.md chart "
            "reads; absence would silently break any charting consumer."
        )
        assert payload["aggregate"]["timestamp"] == "2026-04-23T12:00:00Z"

    def test_to_json_is_deterministic_across_repeat_calls(self) -> None:
        from scripts.project_metrics.schema import to_json

        report = _build_sample_report()
        first = to_json(report)
        second = to_json(report)

        assert first == second, (
            "to_json() must be byte-deterministic on the same input -- "
            "dict-ordering leakage would desynchronize test fixtures and "
            "cross-run comparisons."
        )

    def test_to_json_payload_exposes_all_sixteen_aggregate_columns(self) -> None:
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS, to_json

        payload = json.loads(to_json(_build_sample_report()).decode("utf-8"))
        aggregate = payload["aggregate"]

        missing = [col for col in AGGREGATE_COLUMNS if col not in aggregate]
        assert missing == [], (
            f"aggregate block missing columns: {missing}. Every frozen "
            "column must appear in the serialized JSON; nullable columns "
            "appear as JSON null, not as absent keys."
        )


class TestAggregateHeaderForLog:
    """aggregate_header_for_log() returns the markdown table header whose
    cells must be byte-identical to AGGREGATE_COLUMNS. Any drift between
    the schema and the log header causes ragged columns in METRICS_LOG.md."""

    def test_aggregate_header_is_a_string(self) -> None:
        from scripts.project_metrics.schema import aggregate_header_for_log

        assert isinstance(aggregate_header_for_log(), str)

    def test_aggregate_header_cells_match_aggregate_columns(self) -> None:
        from scripts.project_metrics.schema import (
            AGGREGATE_COLUMNS,
            aggregate_header_for_log,
        )

        header = aggregate_header_for_log()

        # Parse the FIRST line of the markdown header (subsequent lines may
        # contain a `| --- | --- | ... |` separator row). Strip outer pipes,
        # split on `|`, trim whitespace from each cell.
        first_line = header.strip().splitlines()[0]
        cells = [c.strip() for c in first_line.strip("|").split("|")]

        # Drop a trailing `report_file` column if present -- the ADR permits
        # (and the plan requires) the log header to end with a link column
        # that is NOT part of the frozen aggregate set.
        if cells and cells[-1] == "report_file":
            cells = cells[:-1]

        assert tuple(cells) == AGGREGATE_COLUMNS, (
            "Log header cells must match AGGREGATE_COLUMNS verbatim. "
            "Header drift is the class of bug the freeze contract exists "
            "to prevent."
        )
