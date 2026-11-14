"""Tests for the trailing-segment slot of the prompt-rewrite emitter in
``hooks/inject_subagent_context.py``.

The rewritten prompt is the leading segments, then the delegation verbatim, then the trailing
segments, still one updatedInput. An empty trailing list leaves the output byte-identical to the
leading-only form, and a spawn with nothing to add still prints nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))

import inject_subagent_context as hook  # noqa: E402

TOOL_INPUT = {"subagent_type": "Explore", "description": "probe", "model": "sonnet"}
DELEGATION = "Line one of the delegation.\n\n  Indented line two.\n"


def _emit(capsys, *args) -> str:
    hook._emit_updated_input(*args)
    return capsys.readouterr().out


def _prompt_of(output: str) -> str:
    return json.loads(output)["hookSpecificOutput"]["updatedInput"]["prompt"]


def test_a_trailing_segment_lands_after_the_delegation(capsys):
    output = _emit(capsys, TOOL_INPUT, "ORIGINAL", ["LEAD"], ["TAIL"])
    assert _prompt_of(output) == "LEAD\n\nORIGINAL\n\nTAIL"


def test_trailing_segments_keep_their_order_each_on_its_own_paragraph(capsys):
    output = _emit(capsys, TOOL_INPUT, "ORIGINAL", [], ["T1", "T2"])
    assert _prompt_of(output) == "ORIGINAL\n\nT1\n\nT2"


def test_the_delegation_is_carried_verbatim_between_the_segments(capsys):
    output = _emit(capsys, TOOL_INPUT, DELEGATION, ["LEAD"], ["TAIL"])
    assert DELEGATION in _prompt_of(output)
    assert _prompt_of(output) == f"LEAD\n\n{DELEGATION}\n\nTAIL"


def test_an_empty_trailing_list_is_byte_identical_to_the_leading_only_form(capsys):
    leading_only = _emit(capsys, TOOL_INPUT, "ORIGINAL", ["A", "B"])
    with_empty_trailing = _emit(capsys, TOOL_INPUT, "ORIGINAL", ["A", "B"], [])
    assert with_empty_trailing == leading_only
    assert _prompt_of(leading_only) == "A\n\nB\n\nORIGINAL"


def test_other_tool_input_fields_survive_a_trailing_segment(capsys):
    output = _emit(capsys, TOOL_INPUT, "ORIGINAL", [], ["TAIL"])
    updated = json.loads(output)["hookSpecificOutput"]["updatedInput"]
    assert {k: v for k, v in updated.items() if k != "prompt"} == TOOL_INPUT


def test_a_spawn_with_nothing_to_add_still_prints_nothing(capsys, tmp_path):
    hook._process(
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "praxion:implementer", "prompt": "plain"},
            "cwd": str(tmp_path),
            "session_id": "trailing-slot-nothing-to-add",
        }
    )
    assert capsys.readouterr().out == ""
