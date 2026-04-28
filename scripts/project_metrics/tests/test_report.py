"""Behavioral tests for the JSON->MD report renderer and JSON flattener.

These tests encode the human-facing and machine-facing contracts of the
report layer. They are written from the behavioral spec in
``.ai-work/project-metrics/SYSTEMS_PLAN.md`` (sections on deterministic
section order, skip-marker language, Top-N table shape, delta table shape,
and flat-JSON root). Production code
(``scripts/project_metrics/report.py``) is not read while authoring.

Two public functions are contract-tested:

* ``render_markdown(report) -> str`` — produces a human-readable MD string
  with a deterministic nine-section order. Validated byte-identically
  against ``fixtures/golden_report.md`` modulo the single "Generated at
  <timestamp>" line, which is replaced with a sentinel in both sides
  before comparison.
* ``render_json(report) -> bytes`` — produces the deterministic JSON bytes
  whose root is the **flat** shape the downstream UI consumes:
  ``{"git": {...}, "scc": {...}, ...}`` at root rather than nested under
  ``{"collectors": {...}}``. The flattening is a render-layer concern the
  runner intentionally does not do (see ``WIP.md`` Policy clarified note).

Import strategy: symbols are imported inside each test body (deferred
import) so pytest collection succeeds before the renderer module is
implemented. Top-of-module imports would break collection for every
test at once during the RED handshake, whereas deferred imports give
per-test RED/GREEN resolution.

Traceability for the REQ IDs this file validates lives in
``.ai-work/project-metrics/traceability_13b_test-engineer.yml``
per ``rules/swe/id-citation-discipline.md`` — code is ID-free.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Golden fixture location + the exact timestamp line that must be masked
# out before byte-comparing the renderer output against the golden MD.
# The fixture file captures the timestamp as a literal string so the
# golden is human-readable; tests mask the line at comparison time.
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_report.md"
_TIMESTAMP_LINE_PREFIX = "Generated at "
_TIMESTAMP_SENTINEL = "Generated at __TIMESTAMP__"


def _mask_timestamp_line(markdown: str) -> str:
    """Replace the single "Generated at <...>" line with a fixed sentinel.

    The header embeds the report's wall-clock timestamp, which cannot
    match across runs. Masking is a one-line substitution: any line that
    starts with "Generated at " becomes ``_TIMESTAMP_SENTINEL``. All
    other lines pass through unchanged so every other byte of the report
    (tables, skip markers, section order, trailing newline) participates
    in the comparison.
    """
    lines = markdown.splitlines(keepends=True)
    masked = []
    for line in lines:
        if line.startswith(_TIMESTAMP_LINE_PREFIX):
            # Preserve the trailing newline byte so the total byte length
            # of the masked file matches what splitlines(keepends=True)
            # would produce on a pure-text re-render.
            trailing = "\n" if line.endswith("\n") else ""
            masked.append(_TIMESTAMP_SENTINEL + trailing)
        else:
            masked.append(line)
    return "".join(masked)


# ---------------------------------------------------------------------------
# Reference Report builder. The returned Report object is the exact input
# that MUST reproduce ``golden_report.md`` byte-identically (modulo the
# masked timestamp line). If the implementer's renderer disagrees, either
# the renderer or the golden is wrong — test failures must name which.
#
# Values chosen:
#   - 3 Available collectors (git, scc, lizard) + 1 Unavailable (complexipy)
#     + 1 Available (pydeps) + 1 NotApplicable (coverage)  = 6 collectors.
#   - Tool availability mix: 4 available, 1 unavailable, 1 not_applicable,
#     0 error, 0 timeout (exercises every status in the tool_availability
#     union that is resolver-produced, not runner-produced).
#   - hotspots: Top-5 with distinct descending scores (aids determinism
#     assertions + rank-order assertions).
#   - trends: TrendBlock with status="computed" and 3 non-null deltas +
#     1 null delta (coverage_line_pct).
#   - aggregate: all 16 frozen columns populated; two are null-rendered
#     (cognitive_p95 -> skip marker because complexipy unavailable;
#      coverage_line_pct -> skip marker because coverage not_applicable).
# ---------------------------------------------------------------------------


def _reference_aggregate_kwargs() -> dict[str, Any]:
    """16 aggregate-block fields matching the values in the golden MD."""
    return {
        "schema_version": "1.0.0",
        "timestamp": "2026-04-23T12:00:00Z",
        "commit_sha": "abcdef1234567890abcdef1234567890abcdef12",
        "window_days": 90,
        "sloc_total": 1234,
        "file_count": 42,
        "language_count": 3,
        "ccn_p95": 7.5,
        # cognitive_p95 is None because complexipy is unavailable in the
        # reference scenario; the renderer must emit a skip marker, not
        # a literal "None" or "null".
        "cognitive_p95": None,
        "cyclic_deps": 0,
        "churn_total_90d": 567,
        "change_entropy_90d": 2.1,
        "truck_factor": 2,
        "hotspot_top_score": 123.4,
        "hotspot_gini": 0.75,
        # coverage_line_pct is None because coverage is not_applicable
        # (no Python sources); the renderer must emit the NotApplicable
        # skip marker, not the Unavailable one.
        "coverage_line_pct": None,
    }


def _reference_tool_availability() -> dict[str, Any]:
    """Six-entry tool_availability mapping (4 available / 1 unavailable / 1 NA)."""
    from scripts.project_metrics.schema import ToolAvailability

    return {
        "git": ToolAvailability(status="available", version="2.43.0"),
        "scc": ToolAvailability(status="available", version="3.3.0"),
        "lizard": ToolAvailability(status="available", version="1.17.10"),
        "complexipy": ToolAvailability(
            status="unavailable",
            reason="not installed",
            hint="uv tool install complexipy",
        ),
        "pydeps": ToolAvailability(status="available", version="1.12.20"),
        "coverage": ToolAvailability(
            status="not_applicable",
            reason="no Python sources",
        ),
    }


def _reference_collectors() -> dict[str, Any]:
    """Per-collector namespace payloads matching the golden deep-dive section.

    Available collectors carry tool-specific data dicts. Unavailable and
    NotApplicable collectors carry the uniform 3-key skip marker returned
    by ``skip_marker_for_namespace`` — the renderer reads these and emits
    the "_not computed — install <tool>_" and "_not applicable_" MD lines
    respectively. The renderer distinguishes the two cases by consulting
    ``tool_availability[name].status`` (unavailable vs not_applicable),
    not the skip marker itself, because the marker shape is uniform.
    """
    from scripts.project_metrics.collectors.base import (
        CollectorResult,
        skip_marker_for_namespace,
    )

    return {
        "git": CollectorResult(
            status="ok",
            data={
                "file_count": 42,
                "churn_total_90d": 567,
                "change_entropy_90d": 2.10,
                "truck_factor": 2,
                "churn_source": "numstat",
                "churn_90d": {
                    "src/core/engine.py": 120,
                    "src/core/parser.py": 80,
                    "src/api/routes.py": 60,
                },
                "change_coupling": {
                    "pairs": [
                        {
                            "files": ["src/core/engine.py", "src/core/parser.py"],
                            "count": 5,
                        },
                    ],
                    "threshold": 3,
                },
                "ownership": {
                    "src/core/engine.py": {
                        "top_author": "Alice",
                        "top_author_pct": 0.8,
                        "major": [["Alice", 0.8], ["Bob", 0.2]],
                        "minor": [],
                    },
                    "src/api/routes.py": {
                        "top_author": "Alice",
                        "top_author_pct": 1.0,
                        "major": [["Alice", 1.0]],
                        "minor": [],
                    },
                },
                "age_days": {
                    "src/core/engine.py": 45,
                    "src/util/log.py": 12,
                },
            },
        ),
        "scc": CollectorResult(
            status="ok",
            data={
                "file_count": 42,
                "sloc_total": 1234,
                "language_count": 3,
                "language_breakdown": {
                    "Python": {"sloc": 900, "file_count": 30},
                    "Markdown": {"sloc": 250, "file_count": 8},
                    "YAML": {"sloc": 84, "file_count": 4},
                },
            },
        ),
        "lizard": CollectorResult(
            status="ok",
            data={
                "aggregate": {
                    "ccn_p95": 7.5,
                    "ccn_p75": 3.0,
                    "total_function_count": 210,
                },
                "files": {
                    "src/core/engine.py": {
                        "p95_ccn": 18.0,
                        "max_ccn": 22,
                        "p75_ccn": 10.0,
                        "function_count": 12,
                        "ccns": [22, 18, 10, 5, 3],
                    },
                    "src/core/parser.py": {
                        "p95_ccn": 14.0,
                        "max_ccn": 16,
                        "p75_ccn": 8.0,
                        "function_count": 8,
                        "ccns": [16, 14, 8, 4],
                    },
                },
                "per_language_ccn_p95": {"Python": 7.5},
            },
        ),
        "complexipy": CollectorResult(
            status="error",
            data=skip_marker_for_namespace("complexipy"),
        ),
        "pydeps": CollectorResult(
            status="ok",
            data={"modules": 48, "cyclic_sccs": 0},
        ),
        "coverage": CollectorResult(
            status="error",
            data=skip_marker_for_namespace("coverage"),
        ),
    }


def _reference_hotspots() -> dict[str, Any]:
    """Top-5 hotspots matching the golden four-column table."""
    return {
        "top_n": [
            {
                "path": "src/core/engine.py",
                "churn_90d": 120,
                "complexity": 18.0,
                "hotspot_score": 2160.0,
                "rank": 1,
            },
            {
                "path": "src/core/parser.py",
                "churn_90d": 80,
                "complexity": 14.0,
                "hotspot_score": 1120.0,
                "rank": 2,
            },
            {
                "path": "src/api/routes.py",
                "churn_90d": 60,
                "complexity": 12.0,
                "hotspot_score": 720.0,
                "rank": 3,
            },
            {
                "path": "src/util/cache.py",
                "churn_90d": 30,
                "complexity": 9.0,
                "hotspot_score": 270.0,
                "rank": 4,
            },
            {
                "path": "src/util/log.py",
                "churn_90d": 20,
                "complexity": 6.0,
                "hotspot_score": 120.0,
                "rank": 5,
            },
        ],
        "gini": 0.75,
    }


def _reference_trends() -> Any:
    """TrendBlock with status="computed" and a mixed-null delta payload."""
    from scripts.project_metrics.schema import TrendBlock

    return TrendBlock(
        status="computed",
        prior_report="METRICS_REPORT_2026-04-22_12-00-00.json",
        prior_schema="1.0.0",
        current_schema="1.0.0",
        deltas={
            "sloc_total": {
                "current": 1234,
                "prior": 1200,
                "delta": 34,
                "delta_pct": 2.83,
            },
            "file_count": {"current": 42, "prior": 40, "delta": 2, "delta_pct": 5.00},
            "churn_total_90d": {
                "current": 567,
                "prior": 500,
                "delta": 67,
                "delta_pct": 13.40,
            },
            # Null-input delta: current and prior both None, so the row
            # renders em-dashes in every numeric column.
            "coverage_line_pct": {
                "current": None,
                "prior": None,
                "delta": None,
                "delta_pct": None,
                "reason": "null_input",
            },
        },
    )


def _reference_run_metadata() -> Any:
    """Run metadata matching the golden "Run Metadata" section."""
    from scripts.project_metrics.schema import RunMetadata

    return RunMetadata(
        command_version="0.2.1.dev0",
        python_version="3.11.7",
        wall_clock_seconds=4.2,
        window_days=90,
        top_n=5,
    )


def _build_reference_report() -> Any:
    """Assemble the full reference Report object that feeds the golden MD."""
    from scripts.project_metrics.schema import AggregateBlock, Report

    aggregate = AggregateBlock(**_reference_aggregate_kwargs())
    return Report(
        schema_version="1.0.0",
        aggregate=aggregate,
        tool_availability=_reference_tool_availability(),
        collectors=_reference_collectors(),
        hotspots=_reference_hotspots(),
        trends=_reference_trends(),
        run_metadata=_reference_run_metadata(),
    )


# ---------------------------------------------------------------------------
# Golden-byte comparison — the strongest single assertion in this file.
# ---------------------------------------------------------------------------


class TestGoldenMarkdownByteComparison:
    """render_markdown(reference_report) must reproduce the golden MD
    byte-identically, modulo the single "Generated at <timestamp>" line."""

    def test_render_markdown_matches_golden_fixture_modulo_timestamp(self) -> None:
        from scripts.project_metrics.report import render_markdown

        actual = render_markdown(_build_reference_report())
        expected = _GOLDEN_PATH.read_text(encoding="utf-8")

        masked_actual = _mask_timestamp_line(actual)
        masked_expected = _mask_timestamp_line(expected)

        assert masked_actual == masked_expected, (
            "render_markdown output diverged from golden_report.md. "
            "Either the renderer changed or the golden is stale. Diff "
            "the two files (masking the 'Generated at' line) to locate "
            "the divergence."
        )


# ---------------------------------------------------------------------------
# Section-order contract — plan line 416 prescribes a deterministic
# nine-section order. The renderer MUST emit these `##` headings in order
# regardless of which collectors are Available or skipped.
# ---------------------------------------------------------------------------


class TestReportSectionOrder:
    """Sections appear in the plan-prescribed order in every run."""

    _EXPECTED_ORDER: tuple[str, ...] = (
        "Tool Availability",
        "Install to improve",
        "Aggregate Summary",
        "Top-",  # Top-5 / Top-10 / ... — prefix-match to allow N variance
        "Trends",
        "Per-collector Deep Dive",
        "Per-language Breakdown",
        "Run Metadata",
    )

    def test_eight_secondary_sections_appear_in_declared_order(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())

        # Locate each expected heading by its '##' prefix to avoid
        # accidental matches inside table cells or body prose.
        positions = []
        for name in self._EXPECTED_ORDER:
            # The heading line always starts with '## '; prefix-matching
            # on the name avoids brittleness around "Top-5" vs "Top-10".
            pattern = re.compile(rf"^##\s+{re.escape(name)}", re.MULTILINE)
            match = pattern.search(md)
            assert match is not None, (
                f"Expected '## {name}...' heading missing from rendered "
                f"MD. Plan line 416 requires this section. Got:\n{md[:500]}"
            )
            positions.append(match.start())

        assert positions == sorted(positions), (
            "Section headings did not appear in declared order. "
            f"Observed positions: {positions}; expected monotonic "
            f"non-decreasing."
        )

    def test_header_precedes_every_other_section(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())

        # The report title is an H1 heading; it must appear before any H2.
        h1_match = re.search(r"^#\s+", md, re.MULTILINE)
        h2_match = re.search(r"^##\s+", md, re.MULTILINE)
        assert h1_match is not None, "Missing H1 header at top of report."
        assert h2_match is not None, "Missing H2 sections."
        assert h1_match.start() < h2_match.start()


# ---------------------------------------------------------------------------
# Header content — timestamp, commit SHA, schema version.
# ---------------------------------------------------------------------------


class TestReportHeader:
    """The top-of-report header carries timestamp, commit SHA, and schema
    version in a shape stable enough for downstream UI consumption."""

    def test_header_contains_commit_sha(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        assert "abcdef1234567890abcdef1234567890abcdef12" in md

    def test_header_contains_schema_version(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        assert "1.0.0" in md

    def test_header_contains_generated_at_line(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        # Presence of the Generated-at line is what makes timestamp
        # masking possible in the golden comparison.
        assert _TIMESTAMP_LINE_PREFIX in md, (
            "Report header must include a 'Generated at <timestamp>' "
            "line so byte-comparison can mask it. Absence makes byte-"
            "compare-modulo-timestamp infeasible."
        )


# ---------------------------------------------------------------------------
# Install-to-improve enumeration — Unavailable only; NotApplicable omitted.
# Uses the ToolAvailability.hint as the install command text.
# ---------------------------------------------------------------------------


class TestReportInstallToImprove:
    """The Install to improve section enumerates ONLY collectors whose
    tool_availability.status == 'unavailable'. NotApplicable collectors
    are silently omitted — there is no user action for them."""

    def test_lists_unavailable_tool_name(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        install_section = _extract_section(md, "Install to improve")
        assert "complexipy" in install_section, (
            "Unavailable tool 'complexipy' must appear in Install to "
            "improve. This is how users learn what to install."
        )

    def test_includes_install_hint_for_unavailable(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        install_section = _extract_section(md, "Install to improve")
        # The reference fixture's complexipy entry carries the hint
        # "uv tool install complexipy".
        assert "uv tool install complexipy" in install_section

    def test_omits_not_applicable_collector(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        install_section = _extract_section(md, "Install to improve")
        # coverage is NotApplicable and must NOT appear under "Install to
        # improve" — there is nothing to install to make it apply.
        assert "coverage" not in install_section, (
            "NotApplicable collector 'coverage' leaked into Install to "
            "improve. Only Unavailable collectors belong there."
        )

    def test_omits_available_collectors(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        install_section = _extract_section(md, "Install to improve")
        # Sanity: every Available collector must be absent from the
        # install section.
        for available_name in ("git", "scc", "lizard", "pydeps"):
            assert available_name not in install_section, (
                f"Available collector '{available_name}' leaked into "
                "Install to improve."
            )


# ---------------------------------------------------------------------------
# Top-N hot-spot table — four-column data + rank column.
# ---------------------------------------------------------------------------


class TestReportTopNTable:
    """Top-N table exposes the per-row path/churn/complexity/score with a
    rank column. Rows are descending by score; header matches the plan."""

    def test_table_header_names_four_data_columns(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Top-")
        # Accept any casing / separator the renderer picks, as long as
        # the four data dimensions plus the rank column are all named.
        normalized = section.lower()
        for col in ("path", "churn", "complexity", "score"):
            assert col in normalized, (
                f"Top-N table missing '{col}' column. Plan line 417 "
                "requires four-column shape."
            )

    def test_all_five_reference_rows_appear(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Top-")
        for path in (
            "src/core/engine.py",
            "src/core/parser.py",
            "src/api/routes.py",
            "src/util/cache.py",
            "src/util/log.py",
        ):
            assert path in section, f"Hot-spot path '{path}' missing from Top-N table."

    def test_rows_appear_in_descending_score_order(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Top-")

        paths_in_order = (
            "src/core/engine.py",
            "src/core/parser.py",
            "src/api/routes.py",
            "src/util/cache.py",
            "src/util/log.py",
        )
        positions = [section.index(path) for path in paths_in_order]
        assert positions == sorted(positions), (
            "Top-N rows not rendered in descending score order. "
            f"Observed position order: {positions}."
        )


# ---------------------------------------------------------------------------
# Trends block — three rendering modes (first-run / schema-mismatch /
# computed). The reference report exercises the "computed" path; the
# other two paths are exercised with locally-built minimal reports.
# ---------------------------------------------------------------------------


class TestReportTrendsBlock:
    """Trends rendering has three discriminated modes driven by
    TrendBlock.status: first_run / schema_mismatch / computed."""

    def test_computed_mode_produces_delta_table_with_expected_columns(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Trends")
        normalized = section.lower()
        for col in ("metric", "current", "prior", "delta"):
            assert col in normalized, (
                f"Trends delta table missing '{col}' column. Plan "
                "requires these five columns on the computed path."
            )

    def test_computed_mode_renders_each_non_null_delta_row(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Trends")
        # All three numeric-delta rows from the reference fixture must
        # appear in the section.
        for metric in ("sloc_total", "file_count", "churn_total_90d"):
            assert metric in section, (
                f"Delta row for '{metric}' missing from trends section."
            )

    def test_first_run_mode_emits_first_run_sentinel_string(self) -> None:
        from scripts.project_metrics.report import render_markdown
        from scripts.project_metrics.schema import TrendBlock

        report = _build_reference_report()
        # Rebuild with a first-run trends block to exercise the first-run path.
        first_run_report = _replace_trends(report, TrendBlock(status="first_run"))

        md = render_markdown(first_run_report)
        section = _extract_section(md, "Trends")
        assert "first run" in section.lower(), (
            "first_run mode must surface a 'first run' marker string so "
            "users understand why the delta table is absent."
        )

    def test_schema_mismatch_mode_emits_warning_naming_both_schemas(self) -> None:
        from scripts.project_metrics.report import render_markdown
        from scripts.project_metrics.schema import TrendBlock

        report = _build_reference_report()
        mismatch_block = TrendBlock(
            status="schema_mismatch",
            prior_schema="1.0.0",
            current_schema="2.0.0",
            prior_report="METRICS_REPORT_OLD.json",
        )
        mismatch_report = _replace_trends(report, mismatch_block)

        md = render_markdown(mismatch_report)
        section = _extract_section(md, "Trends")
        assert "1.0.0" in section and "2.0.0" in section, (
            "schema_mismatch rendering must name both the prior and "
            "current schema versions so users understand why deltas "
            "are deferred."
        )

    def test_computed_mode_handles_null_delta_without_raising(self) -> None:
        from scripts.project_metrics.report import render_markdown

        # The reference report's trends block includes a null-input
        # coverage_line_pct delta. The renderer must not raise or emit
        # bare "None" strings — it must render a uniform dash/NA cell.
        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Trends")
        # No bare Python-literal "None" should leak into user-facing MD.
        assert "None" not in section, (
            "Bare 'None' leaked into trends MD. Null-input deltas must "
            "render as '—' or 'N/A', not as Python literals."
        )


# ---------------------------------------------------------------------------
# Per-collector Deep Dive — Available collectors produce '### <name>'
# subsections with their data; skipped collectors produce only the
# italic skip marker.
# ---------------------------------------------------------------------------


class TestReportPerCollectorDeepDive:
    """The Deep Dive section emits a subsection per collector, with skip
    markers for Unavailable and NotApplicable collectors."""

    def test_every_collector_has_its_own_subsection_heading(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Per-collector Deep Dive")
        for name in ("git", "scc", "lizard", "complexipy", "pydeps", "coverage"):
            # Match either '### <name>' or '### <Name>' — the renderer's
            # casing choice is intentionally not locked here because the
            # plan does not specify it.
            pattern = re.compile(
                rf"^###\s+{re.escape(name)}", re.IGNORECASE | re.MULTILINE
            )
            assert pattern.search(section), (
                f"Deep Dive missing '### {name}' subsection. Every "
                "registered collector must be named in the deep dive."
            )

    def test_scc_subsection_emits_top_n_languages_by_sloc_descending(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Per-collector Deep Dive")
        scc_start = section.lower().index("### scc")
        next_heading = section.find("### ", scc_start + 1)
        scc_body = (
            section[scc_start:next_heading]
            if next_heading != -1
            else section[scc_start:]
        )

        assert "Top 3 languages by SLOC (of 3):" in scc_body, (
            "scc subsection must surface a 'Top N languages by SLOC' bullet "
            "so readers see the language breakdown inline next to "
            "'Languages detected'."
        )
        python_pos = scc_body.find("Python — 30 files, 900 SLOC")
        markdown_pos = scc_body.find("Markdown — 8 files, 250 SLOC")
        yaml_pos = scc_body.find("YAML — 4 files, 84 SLOC")
        assert python_pos != -1 and markdown_pos != -1 and yaml_pos != -1, (
            "scc subsection must list each language with '<Name> — "
            "<files> files, <sloc> SLOC'."
        )
        assert python_pos < markdown_pos < yaml_pos, (
            "Languages in the scc summary must be sorted by SLOC "
            "descending (Python 900 > Markdown 250 > YAML 84)."
        )

    def test_skipped_collectors_emit_skip_marker_in_deep_dive(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Per-collector Deep Dive")
        # complexipy (Unavailable) and coverage (NotApplicable) both
        # contribute skip markers in their subsection — the exact
        # marker-text contract is exercised by TestReportSkipMarkerLanguage.
        # Here we only assert that both names are reachable via an
        # italic marker within the deep dive section.
        assert "_not computed" in section.lower(), (
            "Deep Dive must contain at least one '_not computed_' skip "
            "marker (complexipy is Unavailable in the reference fixture)."
        )
        assert "_not applicable" in section.lower(), (
            "Deep Dive must contain at least one '_not applicable_' "
            "skip marker (coverage is NotApplicable in the reference)."
        )


# ---------------------------------------------------------------------------
# Skip-marker language contract — the exact phrasing of the two italic
# markers used whenever a collector contributed no data.
# ---------------------------------------------------------------------------


class TestReportSkipMarkerLanguage:
    """Skip-marker phrasing is part of the public UX contract — these
    exact strings appear anywhere a skipped collector would otherwise
    contribute data."""

    def test_unavailable_collector_uses_install_phrasing(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        # Form: "_not computed — install <tool>_" where <tool> is the
        # collector's tool name.
        assert "_not computed — install complexipy_" in md, (
            "Unavailable skip marker must read exactly "
            "'_not computed — install <tool>_' to match the plan's "
            "UX contract."
        )

    def test_not_applicable_collector_uses_not_applicable_phrasing(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        # Form: "_not applicable for this repository_" — no tool name
        # because there is no user action.
        assert "_not applicable for this repository_" in md, (
            "NotApplicable skip marker must read exactly "
            "'_not applicable for this repository_'."
        )

    def test_unavailable_skip_marker_never_used_for_not_applicable(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        # Coverage is NotApplicable. The MD must not say "install coverage"
        # anywhere — that would mislead users into installing a package
        # that cannot apply to their repo.
        assert "install coverage" not in md, (
            "Install hint for NotApplicable collector leaked into MD. "
            "NotApplicable collectors must use the neutral "
            "'_not applicable for this repository_' marker only."
        )


# ---------------------------------------------------------------------------
# Aggregate summary — the 16-column table plus the narrative paragraph.
# ---------------------------------------------------------------------------


class TestReportAggregateSummary:
    """The Aggregate Summary section surfaces all 16 frozen columns with
    human-readable labels and values; null columns carry skip markers."""

    def test_section_names_every_frozen_aggregate_column(self) -> None:
        from scripts.project_metrics.report import render_markdown
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Aggregate Summary")
        missing = [c for c in AGGREGATE_COLUMNS if c not in section]
        assert missing == [], (
            f"Aggregate summary missing frozen columns: {missing}. "
            "Every column in AGGREGATE_COLUMNS must appear in the user-"
            "facing MD, even if the value is null."
        )

    def test_null_aggregate_columns_render_as_skip_markers_not_literal_none(
        self,
    ) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Aggregate Summary")
        # cognitive_p95 and coverage_line_pct are None in the reference.
        # They must NOT render as literal 'None' — they must render as
        # skip markers.
        # Extract the two relevant lines to scope the assertion.
        cognitive_line = _line_containing(section, "cognitive_p95")
        coverage_line = _line_containing(section, "coverage_line_pct")
        assert "None" not in cognitive_line, (
            f"Literal 'None' leaked into cognitive_p95 cell: {cognitive_line!r}"
        )
        assert "None" not in coverage_line, (
            f"Literal 'None' leaked into coverage_line_pct cell: {coverage_line!r}"
        )


# ---------------------------------------------------------------------------
# Tool Availability table — one row per collector with status + detail.
# ---------------------------------------------------------------------------


class TestReportToolAvailabilityTable:
    """The Tool Availability table surfaces every registered collector
    and its resolve-pass status."""

    def test_table_contains_row_for_every_collector(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Tool Availability")
        for name in ("git", "scc", "lizard", "complexipy", "pydeps", "coverage"):
            assert name in section, f"Tool Availability table missing row for '{name}'."

    def test_table_statuses_match_tool_availability_input(self) -> None:
        from scripts.project_metrics.report import render_markdown

        md = render_markdown(_build_reference_report())
        section = _extract_section(md, "Tool Availability")
        # Each of the five ADR-canonical statuses present in the
        # reference fixture must appear literally in the rendered table
        # row so downstream readers can cite the status without guessing.
        assert "available" in section
        assert "unavailable" in section
        assert "not_applicable" in section


# ---------------------------------------------------------------------------
# JSON flattening contract — render_json(report) -> bytes emits the flat
# root shape the UI consumes: {"git": {...}, "scc": {...}, ...} at root
# rather than nested under {"collectors": {...}}.
# ---------------------------------------------------------------------------


class TestRenderJsonFlattening:
    """render_json flattens Report.collectors[name] to top-level JSON keys
    so the downstream UI reads collector data without descending through
    an extra 'collectors' wrapper."""

    def test_render_json_returns_bytes(self) -> None:
        from scripts.project_metrics.report import render_json

        result = render_json(_build_reference_report())
        assert isinstance(result, bytes)

    def test_collectors_appear_at_json_root_not_nested(self) -> None:
        from scripts.project_metrics.report import render_json

        payload = json.loads(render_json(_build_reference_report()).decode("utf-8"))
        # Flat contract: every collector namespace is a key at JSON root.
        for name in ("git", "scc", "lizard", "complexipy", "pydeps", "coverage"):
            assert name in payload, (
                f"Collector '{name}' missing from JSON root. Storage-"
                "schema ADR requires flat root shape, not nested under "
                "'collectors'."
            )

    def test_json_root_has_no_nested_collectors_wrapper(self) -> None:
        from scripts.project_metrics.report import render_json

        payload = json.loads(render_json(_build_reference_report()).decode("utf-8"))
        assert "collectors" not in payload, (
            "'collectors' wrapper leaked into JSON root. The runner "
            "emits a nested shape; render_json MUST flatten it."
        )

    def test_json_root_still_exposes_schema_version_and_aggregate(self) -> None:
        from scripts.project_metrics.report import render_json

        payload = json.loads(render_json(_build_reference_report()).decode("utf-8"))
        # Flattening collectors must NOT erase the other root keys.
        assert "schema_version" in payload
        assert "aggregate" in payload
        assert "tool_availability" in payload

    def test_json_is_deterministic_across_repeat_calls(self) -> None:
        from scripts.project_metrics.report import render_json

        report = _build_reference_report()
        first = render_json(report)
        second = render_json(report)
        assert first == second, (
            "render_json must be byte-deterministic on the same input; "
            "dict-ordering leakage would desynchronize fixtures."
        )

    def test_collector_namespace_keys_do_not_collide_with_root_keys(self) -> None:
        from scripts.project_metrics.report import render_json
        from scripts.project_metrics.schema import AGGREGATE_COLUMNS

        payload = json.loads(render_json(_build_reference_report()).decode("utf-8"))
        # Safety: no collector name may shadow a root-level key like
        # 'aggregate' or 'schema_version'. If it did, the flatten step
        # would silently clobber the root key. The reference fixture
        # uses collector names that are safe (git, scc, lizard, ...).
        collector_names = {"git", "scc", "lizard", "complexipy", "pydeps", "coverage"}
        reserved = {
            "schema_version",
            "aggregate",
            "tool_availability",
            "hotspots",
            "trends",
            "run_metadata",
        }
        assert collector_names.isdisjoint(reserved), (
            "Test fixture error: a reference collector name shadows a "
            "reserved root key. Rename the collector in the fixture."
        )
        # And those aggregate columns still sit nested under 'aggregate'.
        for col in AGGREGATE_COLUMNS:
            assert col in payload["aggregate"], (
                f"Aggregate column '{col}' missing after flattening; "
                "flattening must not disturb the aggregate block."
            )


# ---------------------------------------------------------------------------
# Module-level public API — __all__ is the readable contract.
# ---------------------------------------------------------------------------


class TestReportModuleApi:
    """The report module exposes exactly two public entry points."""

    def test_public_api_lists_both_renderers(self) -> None:
        import scripts.project_metrics.report as report_module

        public_api = getattr(report_module, "__all__", None)
        assert public_api is not None, (
            "report module must declare __all__ so the two-entry-point "
            "contract is explicit to importers."
        )
        assert set(public_api) >= {"render_markdown", "render_json"}, (
            f"__all__ missing required entry points. Got: {public_api}; "
            "expected at least render_markdown and render_json."
        )


# ---------------------------------------------------------------------------
# Helpers — kept private (underscore-prefixed). These are DAMP support for
# the tests above; inlining them in every test would dilute readability.
# ---------------------------------------------------------------------------


def _extract_section(markdown: str, heading_prefix: str) -> str:
    """Return the body of the first '## <heading_prefix>...' section.

    Used to scope assertions to one section at a time so a failing
    assertion points at the offending renderer output directly rather
    than forcing the reader to scan the whole document.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading_prefix)}.*?(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    if match is None:
        pytest.fail(
            f"Section starting with '## {heading_prefix}' not found in "
            f"rendered MD. Searched document of length {len(markdown)}."
        )
    return match.group(0)


def _line_containing(text: str, needle: str) -> str:
    """Return the first line in ``text`` that contains ``needle``.

    Used to scope cell-level assertions to the single table row whose
    label matches a particular aggregate column.
    """
    for line in text.splitlines():
        if needle in line:
            return line
    pytest.fail(f"No line containing {needle!r} in text.")
    return ""  # unreachable; satisfies type checker


def _replace_trends(report: Any, new_trends: Any) -> Any:
    """Return a new Report with ``trends`` replaced by ``new_trends``.

    ``Report`` is a frozen dataclass, so mutation is not an option. This
    helper uses ``dataclasses.replace`` to produce a substituted clone
    without re-deriving every other field. Kept here rather than
    inline so each trends test reads as a single intent.
    """
    from dataclasses import replace

    return replace(report, trends=new_trends)
