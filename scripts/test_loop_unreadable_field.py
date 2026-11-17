"""An `Iterations:` or `Change type:` value the plan grammar cannot read stops under a cause of
its own (``scripts/_step_loop_state.py`` and ``scripts/_step_loop_action.py``, printed by
``scripts/_step_loop_render.py``).

The stop names the step and the field, the reconciler's own words never decide it, and no other
cause is chosen by matching another module's wording.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import HUMAN_CAUSES, Stop, next_action  # noqa: E402
from _step_loop_render import StopView, stop_next_action, stop_stderr  # noqa: E402
from _step_loop_state import LoopInputs, UnreadableField, step_series  # noqa: E402

CAUSE = "unreadable-plan-field"
SLUG = "demo"
INVOKE = "python3 scripts/step_loop.py"
FIELDS = {
    "iterations": ("**Iterations**: several, give or take", "Iterations"),
    "change-type": ("**Change type**: a sort of feature, mostly", "Change type"),
}
STEP_ONE = "Step 1"  # id-citation-discipline:ignore (plan heading format)
PLAN = f"# Plan\n\n## Steps\n\n### {STEP_ONE}: Do it\n\n**Assignee**: implementer\n"


def inputs_for(line, verdicts=()):
    return LoopInputs.read(parse_plan_steps(f"{PLAN}{line}\n\n"), {}, (), verdicts)


def stopped_on(line, verdicts=()):
    action = next_action(inputs_for(line, verdicts))
    assert type(action) is Stop, action
    return action


def view_of(stop):
    return StopView(stop.cause, stop.step, stop.evidence, (), SLUG, INVOKE)


def next_line(view):
    (line,) = [row for row in stop_stderr(view).splitlines() if row.startswith("  Next:")]
    return line


@pytest.mark.parametrize("case", list(FIELDS))
def test_an_unreadable_field_stops_under_its_own_cause_naming_step_and_field(case):
    line, field = FIELDS[case]

    stop = stopped_on(line)

    assert (stop.cause, stop.step) == (CAUSE, "1")
    assert f"{STEP_ONE}: the {field}: value cannot be read" in stop.evidence


@pytest.mark.parametrize("case", list(FIELDS))
def test_an_unreadable_field_is_stopped_on_whatever_the_reconciler_says(case):
    line, _ = FIELDS[case]
    verdict = {"step": STEP_ONE, "verdict": "unknown", "evidence": "the reconciler's words"}

    stop = stopped_on(line, [verdict])

    assert stop.cause == CAUSE
    assert "the reconciler's words" not in stop.evidence


@pytest.mark.parametrize("case", list(FIELDS))
def test_the_state_of_an_unreadable_field_holds_the_field_and_the_fix(case):
    line, field = FIELDS[case]
    loop_inputs = inputs_for(line)

    state = step_series(loop_inputs.steps[0], loop_inputs)

    assert type(state) is UnreadableField
    assert state.field == field
    assert "IMPLEMENTATION_PLAN.md" in state.fix


@pytest.mark.parametrize("case", list(FIELDS))
def test_the_handoff_names_the_field_and_the_command_that_resumes(case):
    line, field = FIELDS[case]

    paragraph = stop_next_action(view_of(stopped_on(line)))

    assert field in paragraph
    assert "step_loop.py next" in paragraph


def test_the_stderr_block_says_to_correct_the_line_the_evidence_names():
    line = next_line(view_of(stopped_on(FIELDS["iterations"][0])))

    assert "correct the plan line the evidence names in IMPLEMENTATION_PLAN.md" in line


def test_a_human_verdict_whose_evidence_names_a_field_keeps_its_own_action():
    view = StopView("human-verdict", "1", "the Iterations: value cannot be read", (), SLUG, INVOKE)

    assert "verify the step by hand and correct WIP.md" in next_line(view)


def test_the_cause_is_one_of_the_human_stops():
    assert CAUSE in HUMAN_CAUSES
