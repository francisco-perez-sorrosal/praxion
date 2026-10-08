"""Exact-value tests for the table renderer of the workflow run cost report."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def _cost():
    return importlib.import_module("workflow_run_cost")


COLUMN_HEADER = (
    "label" + " " * 12 + "phase" + " " * 6 + "model" + " " * 18 + "peak_ctx"
    + "  out_tok" + "  turns" + " wal_agreement" + " " * 3
)  # fmt: skip


def _orchestrator(launch=None, next_turn=None, delta=None) -> dict:
    return {
        "launch_turn_tokens": launch,
        "next_turn_tokens": next_turn,
        "delta": delta,
        "return_bytes": None,
    }


def _row(**overrides) -> dict:
    row = {
        "label": "alpha",
        "phase": "Collect",
        "model": "claude-x",
        "peak_context_tokens": 1200,
        "output_tokens": 300,
        "turns": 4,
        "wal_agreement": "agree",
    }
    return {**row, **overrides}


def test_render_table_prints_a_populated_row_at_fixed_column_widths():
    report = {
        "wf_id": "wf1",
        "agents": [_row()],
        "unobserved": [],
        "orchestrator": _orchestrator(100, 150, 50),
    }

    expected_row = (
        "alpha" + " " * 12 + "Collect" + " " * 4 + "claude-x" + " " * 19 + "1200"
        + " " * 6 + "300" + " " * 6 + "4" + " " + "agree" + " " * 11
    )  # fmt: skip
    assert _cost().render_table(report).split("\n") == [
        "wf_id=wf1  agents=1  unobserved=0",
        "",
        COLUMN_HEADER,
        expected_row,
        "",
        "orchestrator: launch=100 next=150 delta=50",
    ]


def test_render_table_marks_missing_row_fields_with_question_mark_and_dash():
    report = {
        "wf_id": "wf2",
        "agents": [
            _row(
                label=None,
                phase=None,
                model=None,
                peak_context_tokens=None,
                output_tokens=None,
                turns=None,
                wal_agreement="transcript-missing",
            )
        ],
        "unobserved": [],
        "orchestrator": _orchestrator(),
    }

    expected_row = (
        "?" + " " * 16 + "?" + " " * 10 + "?" + " " * 29 + "-" + " " * 8 + "-"
        + " " * 6 + "-" + " " + "transcript-missing"
    )  # fmt: skip
    lines = _cost().render_table(report).split("\n")
    assert lines[3] == expected_row
    assert lines[-1] == "orchestrator: launch=None next=None delta=None"


def test_render_table_with_no_agents_prints_only_header_and_orchestrator():
    report = {
        "wf_id": "wf3",
        "agents": [],
        "unobserved": [{"agent_id": "h1"}, {"agent_id": "h2"}],
        "orchestrator": _orchestrator(7, 9, 2),
    }

    assert _cost().render_table(report) == (
        "wf_id=wf3  agents=0  unobserved=2\n"
        "\n" + COLUMN_HEADER + "\n"
        "\n"
        "orchestrator: launch=7 next=9 delta=2"
    )


def test_disp_renders_none_as_a_dash():
    assert _cost()._disp(None) == "-"


def test_disp_renders_zero_as_a_digit_not_a_dash():
    assert _cost()._disp(0) == "0"


def test_disp_stringifies_numbers_and_passes_text_through():
    cost = _cost()
    assert (cost._disp(1200), cost._disp("agree")) == ("1200", "agree")
