"""Tests that an unreadable change type stops the step-loop driver before any spawn
(``scripts/_step_loop_state.py``, read through ``scripts/_step_loop_action.py``).

A step's own unreadable line stops that step only; an unreadable plan-level line stops every
step that would have used it, so a step with its own readable field or the refactoring tag still
runs. The stop is an unreadable field naming the value, the legal values and the line to fix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import CHANGE_TYPES, parse_plan_steps  # noqa: E402
from _step_loop_action import Spawn, Stop, next_action  # noqa: E402
from _step_loop_state import Fresh, LoopInputs, UnreadableField, step_series  # noqa: E402

IMPLEMENTER = "**Assignee**: implementer"


def step(number, *lines, heading="Do it"):
    body = "".join(f"{line}\n" for line in lines)
    return f"### Step {number}: {heading}\n\n{IMPLEMENTER}\n{body}\n"


def plan(*steps, head=""):
    return f"# Plan\n\n{head}## Steps\n\n" + "".join(steps)


def inputs_for(text):
    return LoopInputs.read(parse_plan_steps(text), {}, (), ())


def series_of(text, index=0):
    loop_inputs = inputs_for(text)
    return step_series(loop_inputs.steps[index], loop_inputs)


# -- The stop ---------------------------------------------------------------------------------


def test_an_unreadable_step_line_is_an_unreadable_field_naming_value_legal_values_and_line():
    state = series_of(plan(step("1", "**Change type**: feature")))

    assert type(state) is UnreadableField
    assert (state.field, state.text) == ("Change type", "feature")
    assert all(legal in state.fix for legal in CHANGE_TYPES)
    assert "step's block" in state.fix


def test_an_unreadable_plan_level_line_names_the_plan_level_line_to_fix():
    state = series_of(plan(step("1"), head="**Change type**: feature\n\n"))

    assert type(state) is UnreadableField
    assert state.text == "feature"
    assert all(legal in state.fix for legal in CHANGE_TYPES)
    assert "plan-level" in state.fix


def test_two_plan_level_lines_that_disagree_stop_with_both_values_quoted():
    state = series_of(plan(step("1"), head="**Change type**: feat\n**Change type**: fix\n\n"))

    assert type(state) is UnreadableField
    assert state.text == "feat; fix"


def test_next_stops_before_any_spawn_on_an_unreadable_step_line():
    action = next_action(inputs_for(plan(step("1", "**Change type**: feature"))))

    assert (type(action), action.cause, action.step) == (Stop, "unreadable-plan-field", "1")
    assert "feature" in action.evidence


# -- What is not stopped ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "block",
    [
        step("1", "**Change type**: fix"),
        step("1", heading="[Phase: Refactoring] Tidy"),
    ],
    ids=["own-readable-field", "refactoring-tag"],
)
def test_an_unreadable_plan_level_line_does_not_stop_a_step_that_does_not_use_it(block):
    text = plan(block, head="**Change type**: feature\n\n")

    assert series_of(text) == Fresh(1)
    assert type(next_action(inputs_for(text))) is Spawn


def test_an_unreadable_step_line_stops_that_step_only():
    text = plan(step("1"), step("2", "**Change type**: nope"))

    assert (series_of(text, 0), type(series_of(text, 1))) == (Fresh(1), UnreadableField)
    assert type(next_action(inputs_for(text))) is Spawn


def test_a_plan_with_no_change_type_anywhere_is_not_stopped():
    assert series_of(plan(step("1"))) == Fresh(1)
