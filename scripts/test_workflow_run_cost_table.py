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


def _build_row_kwargs(**overrides) -> dict:
    kwargs = {
        "label": "alpha",
        "phase": "Collect",
        "journal_result": "done",
        "transcript_stats": None,
        "meta": None,
        "wal_row": None,
        "kind": "workflow-agent",
    }
    return {**kwargs, **overrides}


def _transcript_stats(**overrides) -> dict:
    stats = {
        "path": Path("/t/agent-a1.jsonl"),
        "model": "claude-x",
        "peak_context_tokens": 1200,
        "output_tokens": 300,
        "turns": 4,
        "tool_uses": 9,
    }
    return {**stats, **overrides}


def test_build_row_joins_transcript_wal_and_meta_into_one_row():
    wal = {"tokens_out": 300, "duration_ms": 5000}

    row = _cost()._build_row(
        "a1",
        **_build_row_kwargs(
            transcript_stats=_transcript_stats(),
            meta={"agentType": "researcher"},
            wal_row=wal,
        ),
    )

    assert row == {
        "agent_id": "a1",
        "kind": "workflow-agent",
        "label": "alpha",
        "phase": "Collect",
        "agent_type": "researcher",
        "model": "claude-x",
        "peak_context_tokens": 1200,
        "output_tokens": 300,
        "turns": 4,
        "tool_uses": 9,
        "duration_ms": 5000,
        "transcript": "/t/agent-a1.jsonl",
        "journal_result": "done",
        "wal": {"tokens_out": 300, "duration_ms": 5000},
        "wal_agreement": "agree",
    }


def test_build_row_without_transcript_wal_or_meta_nulls_every_derived_field():
    row = _cost()._build_row(
        "a2", **_build_row_kwargs(label=None, phase=None, kind="unobserved-helper")
    )

    assert row == {
        "agent_id": "a2",
        "kind": "unobserved-helper",
        "label": None,
        "phase": None,
        "agent_type": None,
        "model": None,
        "peak_context_tokens": None,
        "output_tokens": None,
        "turns": None,
        "tool_uses": None,
        "duration_ms": None,
        "transcript": None,
        "journal_result": "done",
        "wal": None,
        "wal_agreement": "transcript-missing",
    }


def test_build_row_copies_the_wal_row_rather_than_aliasing_it():
    wal = {"tokens_out": 300, "duration_ms": 2}

    row = _cost()._build_row(
        "a3",
        **_build_row_kwargs(transcript_stats=_transcript_stats(), wal_row=wal),
    )

    assert (row["wal"] == wal, row["wal"] is wal) == (True, False)
