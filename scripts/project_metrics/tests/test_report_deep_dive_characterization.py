"""Characterization tests for ``_report_deep_dive.py`` ahead of the td-166 split.

Unlike the behavioral tests in ``test_report.py`` (written from the spec
before the renderer existed), these tests are written by **reading the
current, pre-extraction implementation** and pinning its exact rendered
output. That is the point: two structural seams are about to move ---
the five-way availability/status ladder in ``_render_collector_body``
into a ``_collector_marker`` helper, and the nine ``_summarize_*``
functions into a sibling ``_deep_dive_summaries.py`` module --- and this
file is the regression detector both extractions must keep green. A
failure here after the split means observable rendered output changed,
not merely that internal structure moved.

Golden strings are literal in every assertion (not computed by calling
the same marker-building helpers under test), so a change to marker
phrasing is caught here rather than laundered through a self-referential
comparison.

Fixtures for ``report`` are ``types.SimpleNamespace`` stand-ins rather
than full ``schema.Report`` instances: ``render_deep_dive`` and
``_render_collector_body`` read only ``.collectors`` and
``.tool_availability`` off their ``report`` argument, so a minimal
attribute holder is the smallest fixture that exercises the real
production code path.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from scripts.project_metrics import _report_deep_dive as deep_dive
from scripts.project_metrics.schema import CollectorResult, ToolAvailability


def _report(
    tool_availability: dict[str, ToolAvailability] | None = None,
    collectors: dict[str, CollectorResult] | None = None,
) -> Any:
    """Minimal report-shaped stand-in for ``render_deep_dive``/``_render_collector_body``."""

    return SimpleNamespace(
        tool_availability=tool_availability or {},
        collectors=collectors or {},
    )


# ---------------------------------------------------------------------------
# _render_collector_body — the five-way availability/status ladder.
# ---------------------------------------------------------------------------


class TestRenderCollectorBodyAvailabilityLadder:
    """Pin every arm of the ladder, in the order the current code checks it."""

    def test_unavailable_tool_short_circuits_to_the_install_marker(self) -> None:
        avail = ToolAvailability(
            status="unavailable", reason="not installed", hint="brew install foo"
        )
        result = CollectorResult(status="ok", data={"anything": 1})
        report = _report(tool_availability={"foo": avail})

        lines = deep_dive._render_collector_body("foo", result, report)

        assert lines == ["_not computed — install foo_"]

    def test_not_applicable_tool_short_circuits_to_the_not_applicable_marker(self) -> None:
        avail = ToolAvailability(status="not_applicable", reason="no python sources")
        result = CollectorResult(status="ok", data={})
        report = _report(tool_availability={"coverage": avail})

        lines = deep_dive._render_collector_body("coverage", result, report)

        assert lines == ["_not applicable for this repository_"]

    def test_error_with_skip_payload_and_no_availability_record_falls_back_to_install_marker(
        self,
    ) -> None:
        result = CollectorResult(
            status="error",
            data={"status": "skipped", "reason": "tool_unavailable", "tool": "pydeps"},
        )
        report = _report(tool_availability={})  # no "pydeps" entry -> avail is None

        lines = deep_dive._render_collector_body("pydeps", result, report)

        assert lines == ["_not computed — install pydeps_"]

    def test_error_with_skip_payload_and_unmatched_availability_status_falls_back_to_install_marker(
        self,
    ) -> None:
        """Pins the nested unavailable/not_applicable duplicate inside the error/skipped arm.

        ``avail.status`` here is neither ``unavailable`` nor ``not_applicable``, so both
        nested checks in the current code fall through to the same default the "no
        availability record" case above produces. Recorded so a future collapse of the
        duplicate into ``_collector_marker`` cannot silently change this arm's output.
        """
        avail = ToolAvailability(status="error", reason="crashed")
        result = CollectorResult(
            status="error",
            data={"status": "skipped", "reason": "tool_unavailable", "tool": "pydeps"},
        )
        report = _report(tool_availability={"pydeps": avail})

        lines = deep_dive._render_collector_body("pydeps", result, report)

        assert lines == ["_not computed — install pydeps_"]

    def test_error_without_skip_payload_renders_the_stated_reason(self) -> None:
        result = CollectorResult(status="error", data={"reason": "binary crashed"})
        report = _report()

        lines = deep_dive._render_collector_body("lizard", result, report)

        assert lines == ["_not computed — binary crashed_"]

    def test_error_with_empty_data_renders_the_generic_error_marker(self) -> None:
        result = CollectorResult(status="error", data={})
        report = _report()

        lines = deep_dive._render_collector_body("lizard", result, report)

        assert lines == ["_not computed — error_"]

    def test_timeout_renders_the_recorded_seconds(self) -> None:
        result = CollectorResult(status="timeout", data={"timeout_seconds": 45})
        report = _report()

        lines = deep_dive._render_collector_body("scc", result, report)

        assert lines == ["_not computed — timed out after 45s_"]

    def test_timeout_with_missing_seconds_defaults_to_zero(self) -> None:
        result = CollectorResult(status="timeout", data={})
        report = _report()

        lines = deep_dive._render_collector_body("scc", result, report)

        assert lines == ["_not computed — timed out after 0s_"]

    def test_ok_status_renders_layout_bullets_then_the_json_pointer_footer(self) -> None:
        result = CollectorResult(
            status="ok",
            data={"file_count": 42, "sloc_total": 1234, "language_count": 3},
        )
        avail = ToolAvailability(status="available", version="3.3.0")
        report = _report(tool_availability={"scc": avail})

        lines = deep_dive._render_collector_body("scc", result, report)

        assert lines == [
            "- Files counted: 42",
            "- SLOC total: 1234",
            "- Languages detected: 3",
            "",
            "_Full payload for `scc` lives in the sibling "
            "`METRICS_REPORT_<timestamp>.json` under the `scc` key._",
        ]

    def test_ok_status_with_no_layout_or_summarizer_match_falls_back_to_the_safe_dump(
        self,
    ) -> None:
        result = CollectorResult(status="ok", data={"foo": 1, "bar": [1, 2]})
        report = _report()

        lines = deep_dive._render_collector_body("unknown_tool", result, report)

        assert lines == [
            "- foo: 1",
            "- bar: 2 items (see JSON)",
            "",
            "_Full payload for `unknown_tool` lives in the sibling "
            "`METRICS_REPORT_<timestamp>.json` under the `unknown_tool` key._",
        ]

    def test_ok_status_with_empty_data_and_no_registration_renders_the_null_cell(self) -> None:
        result = CollectorResult(status="ok", data={})
        report = _report()

        lines = deep_dive._render_collector_body("unknown_tool", result, report)

        assert lines == [
            "—",
            "",
            "_Full payload for `unknown_tool` lives in the sibling "
            "`METRICS_REPORT_<timestamp>.json` under the `unknown_tool` key._",
        ]


# ---------------------------------------------------------------------------
# render_deep_dive — the public entry point, end-to-end over the ladder.
# ---------------------------------------------------------------------------


class TestRenderDeepDive:
    def test_emits_a_heading_then_one_subsection_per_collector_in_iteration_order(self) -> None:
        collectors = {
            "git": CollectorResult(
                status="ok",
                data={
                    "file_count": 1,
                    "churn_total_90d": 2,
                    "change_entropy_90d": 0.5,
                    "truck_factor": 1,
                    "churn_source": "numstat",
                },
            ),
            "complexipy": CollectorResult(
                status="error",
                data={"status": "skipped", "reason": "tool_unavailable", "tool": "complexipy"},
            ),
        }
        tool_availability = {
            "git": ToolAvailability(status="available", version="2.43.0"),
            "complexipy": ToolAvailability(
                status="unavailable", reason="not installed", hint="uv tool install complexipy"
            ),
        }
        report = _report(tool_availability=tool_availability, collectors=collectors)

        md = deep_dive.render_deep_dive(report)

        assert md == (
            "## Per-collector Deep Dive\n"
            "\n"
            "### git\n"
            "\n"
            "- Files touched in window: 1\n"
            "- Total churn (lines + or -): 2\n"
            "- Change entropy (bits): 0.50\n"
            "- Truck factor: 1\n"
            "- Churn source: numstat\n"
            "\n"
            "_Full payload for `git` lives in the sibling "
            "`METRICS_REPORT_<timestamp>.json` under the `git` key._\n"
            "\n"
            "### complexipy\n"
            "\n"
            "_not computed — install complexipy_\n"
        )


# ---------------------------------------------------------------------------
# The nine _summarize_* functions (plus the _pydeps_coverage_line helper) --
# one representative, exact-output test each, ahead of their move into
# _deep_dive_summaries.py.
# ---------------------------------------------------------------------------


class TestSummarizeGit:
    def test_ranks_churning_files_descending_by_lines_changed(self) -> None:
        data = {"churn_90d": {"a.py": 30, "b.py": 10}}

        lines = deep_dive._summarize_git(data)

        assert lines == [
            "- Top 2 churning files (of 2 touched):",
            "    - `a.py` — 30 lines",
            "    - `b.py` — 10 lines",
        ]


class TestSummarizeLizard:
    def test_renders_aggregate_bullets_then_top_files_by_p95_ccn(self) -> None:
        data = {
            "aggregate": {"total_function_count": 12, "ccn_p95": 5.678, "ccn_p75": 3.1},
            "files": {"a.py": {"p95_ccn": 9.5, "function_count": 4}},
        }

        lines = deep_dive._summarize_lizard(data)

        assert lines == [
            "- Functions analyzed: 12",
            "- CCN p95: 5.68",
            "- CCN p75: 3.10",
            "- Top 1 most complex files by p95 CCN (of 1):",
            "    - `a.py` — p95 CCN 9.5 (4 functions)",
        ]


class TestSummarizeComplexipy:
    def test_renders_aggregate_bullets_then_top_files_by_p95_cognitive(self) -> None:
        data = {
            "aggregate": {"total_function_count": 8, "cognitive_p95": 4.25, "cognitive_p75": 2.0},
            "files": {"b.py": {"p95_cognitive": 6.5, "function_count": 3}},
        }

        lines = deep_dive._summarize_complexipy(data)

        assert lines == [
            "- Functions analyzed: 8",
            "- Cognitive p95: 4.25",
            "- Cognitive p75: 2.00",
            "- Top 1 most cognitively complex files (p95 cognitive, of 1):",
            "    - `b.py` — p95 cognitive 6.5 (3 functions)",
        ]


class TestPydepsCoverageLine:
    def test_states_analyzed_of_total_with_percentage_and_root_count(self) -> None:
        aggregate = {
            "analyzed_python_files": 40,
            "repo_python_files": 50,
            "python_file_coverage_pct": 80.0,
            "package_roots": ["scripts", "hooks"],
        }

        line = deep_dive._pydeps_coverage_line(aggregate)

        assert line == (
            "- Import-graph coverage: 40 of 50 tracked Python files (80.0%) across 2 package roots"
        )


class TestSummarizePydeps:
    def test_renders_aggregate_bullets_coverage_line_then_package_roots(self) -> None:
        data = {
            "aggregate": {
                "total_modules": 10,
                "cyclic_deps": 1,
                "analyzed_python_files": 8,
                "repo_python_files": 10,
                "python_file_coverage_pct": 80.0,
                "package_roots": ["scripts"],
            },
        }

        lines = deep_dive._summarize_pydeps(data)

        assert lines == [
            "- Modules analyzed: 10",
            "- Non-trivial cyclic SCCs: 1",
            "- Import-graph coverage: 8 of 10 tracked Python files (80.0%) across 1 package root",
            "- Package roots analyzed: `scripts`",
        ]


class TestSummarizeScc:
    def test_ranks_languages_descending_by_sloc(self) -> None:
        data = {
            "language_breakdown": {
                "Python": {"sloc": 900, "file_count": 30},
                "YAML": {"sloc": 84, "file_count": 4},
            }
        }

        lines = deep_dive._summarize_scc(data)

        assert lines == [
            "- Top 2 languages by SLOC (of 2):",
            "    - Python — 30 files, 900 SLOC",
            "    - YAML — 4 files, 84 SLOC",
        ]


class TestSummarizeReadiness:
    def test_states_the_scoring_model_when_no_criteria_are_failing(self) -> None:
        data = {"llm": {"status": "scored", "model": "claude-x"}, "criteria": []}

        lines = deep_dive._summarize_readiness(data)

        assert lines == ["- LLM scoring: scored via `claude-x`"]


class TestSummarizeCoverageScope:
    def test_states_scope_and_withholds_the_percentage_when_partial(self) -> None:
        data = {
            "measured_files": 40,
            "source_files_total": 50,
            "artifact_scope_pct": 0.8,
            "status": "partial",
        }

        lines = deep_dive._summarize_coverage_scope(data)

        assert lines == [
            "- Artifact scope: 40 of 50 source files (80.00%)",
            "- Line coverage withheld: the artifact measures too small a share of "
            "the repository to trust a repo-wide percentage — regenerate from the "
            "full test suite; see the scope line above.",
        ]


class TestSummarizeCoverage:
    def test_lists_all_files_worst_first_when_under_the_display_cap(self) -> None:
        data = {
            "measured_files": 10,
            "source_files_total": 10,
            "artifact_scope_pct": 1.0,
            "per_file": {
                "a.py": {"line_pct": 0.5, "lines_covered": 5, "lines_total": 10},
                "b.py": {"line_pct": 0.25, "lines_covered": 1, "lines_total": 4},
            },
        }

        lines = deep_dive._summarize_coverage(data)

        assert lines == [
            "- Artifact scope: 10 of 10 source files (100.00%)",
            "- Lowest-covered files (all 2, worst first):",
            "    - `b.py` — 25.00% (1/4 lines)",
            "    - `a.py` — 50.00% (5/10 lines)",
        ]
