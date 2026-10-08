"""Tests for a step's bound and the `Iterations:` field (``scripts/_loop_fields.py``).

The bound is a sum type (an ordinary step's attempt cap, a goal step's iteration
budget); its invariants, the spent rule of each variant and the reading of the
field from a plan are tested here, plus `PlanStep.bound` end to end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _loop_fields as fields  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402

STEP = 7
LABEL = f"Step {STEP}"
OTHER = STEP + 1  # a neighbouring step, its label built from the constant
THIRD = STEP + 2
GOAL = fields.GoalBudget(5)
KEPT = "abc1234"
UNKEPT = None


def plan(*field_lines: str) -> str:
    """A one-step plan carrying the given field lines under its heading."""
    body = "\n".join(field_lines)
    return f"### {LABEL}: Do the thing\n\n**Assignee**: implementer\n{body}\n"


def records(*commits: str | None) -> list[tuple[int, str | None]]:
    """A series' implement records as `(attempt, commit)`, attempts counted from 1."""
    return list(enumerate(commits, start=1))


# --- the bound's invariants ---


@pytest.mark.parametrize("iterations", [0, -1, -10])
def test_a_goal_budget_below_one_is_refused(iterations: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        fields.GoalBudget(iterations)


def test_a_goal_budget_of_one_is_legal() -> None:
    assert fields.GoalBudget(1).iterations == 1


def test_the_attempt_cap_value_is_still_two() -> None:
    assert fields.ATTEMPT_CAP == 2


def test_an_ordinary_step_requests_up_to_the_attempt_cap() -> None:
    assert fields.request_cap(fields.AttemptCap()) == fields.ATTEMPT_CAP


@pytest.mark.parametrize("iterations", [1, 3, 12])
def test_a_goal_step_requests_up_to_its_budget(iterations: int) -> None:
    assert fields.request_cap(fields.GoalBudget(iterations)) == iterations


# --- the spent rule ---


@pytest.mark.parametrize(
    ("commits", "spent"),
    [
        ((), False),
        ((UNKEPT,), False),
        ((KEPT,), False),
        ((UNKEPT, UNKEPT), True),
        ((KEPT, KEPT), True),
        ((KEPT, UNKEPT, KEPT), True),
    ],
)
def test_an_ordinary_step_is_spent_at_the_attempt_cap(
    commits: tuple[str | None, ...], spent: bool
) -> None:
    assert fields.is_spent(fields.AttemptCap(), records(*commits)) is spent


def test_the_ordinary_rule_reads_the_highest_attempt_not_the_count() -> None:
    assert fields.is_spent(fields.AttemptCap(), [(2, KEPT)]) is True


@pytest.mark.parametrize(
    "commits",
    [(UNKEPT, UNKEPT), (KEPT, UNKEPT, UNKEPT), (UNKEPT, UNKEPT, UNKEPT, UNKEPT)],
)
def test_two_unkept_records_in_a_row_spend_a_goal_budget(commits: tuple[str | None, ...]) -> None:
    assert fields.is_spent(GOAL, records(*commits)) is True


@pytest.mark.parametrize(
    "commits",
    [(), (UNKEPT,), (UNKEPT, KEPT, UNKEPT), (UNKEPT, UNKEPT, KEPT), (KEPT, KEPT, KEPT)],
)
def test_a_kept_record_resets_the_stall_of_a_goal_step(commits: tuple[str | None, ...]) -> None:
    assert fields.is_spent(GOAL, records(*commits)) is False


def test_the_stall_run_is_two() -> None:
    assert fields.STALL_RUN == 2


# --- reading the field ---


@pytest.mark.parametrize(
    ("value", "count"),
    [("1", 1), ("5", 5), ("12", 12), (" 3 ", 3), ("007", 7), ("4**", 4)],
)
def test_a_whole_number_of_at_least_one_reads_as_its_count(value: str, count: int) -> None:
    assert fields.parse_iterations(value) == count


@pytest.mark.parametrize("value", ["0", "-2", "2.5", "three", "", "5 iterations", "1,2", "٣"])
def test_any_other_value_reads_as_unreadable_quoting_it(value: str) -> None:
    assert fields.parse_iterations(value) == fields.UnreadableIterations(value.strip())


@pytest.mark.parametrize(
    "line",
    [
        "**Iterations**: 4",
        "**Iterations:** 4",
        "Iterations: 4",
        "iterations: 4",
        "- Iterations: 4",
        "* **Iterations**: 4",
    ],
)
def test_the_label_may_be_bold_any_case_or_a_list_item(line: str) -> None:
    assert fields.parse_step_iterations(plan(line)) == {LABEL: 4}


def test_a_plan_without_the_field_has_no_entry() -> None:
    assert fields.parse_step_iterations(plan("**Files**: `a.py`")) == {}


def test_a_field_inside_a_code_fence_is_no_field() -> None:
    fenced = plan("```", "Iterations: 4", "```")
    assert fields.parse_step_iterations(fenced) == {}


def test_two_lines_for_one_step_read_as_unreadable() -> None:
    reading = fields.parse_step_iterations(plan("Iterations: 4", "Iterations: 6"))
    assert reading == {LABEL: fields.UnreadableIterations("4; 6")}


def test_each_step_of_a_plan_is_read_on_its_own() -> None:
    text = plan("Iterations: 3") + (
        f"\n### Step {OTHER}: Other\n\nIterations: nope\n\n### Step {THIRD}: Third\n"
    )
    assert fields.parse_step_iterations(text) == {
        LABEL: 3,
        f"Step {OTHER}": fields.UnreadableIterations("nope"),
    }


# --- PlanStep.bound ---


def test_a_step_without_the_field_is_bound_by_the_attempt_cap() -> None:
    (step,) = parse_plan_steps(plan("**Files**: `a.py`"))
    assert step.bound == fields.AttemptCap()


def test_a_step_with_the_field_is_a_goal_step_with_that_budget() -> None:
    (step,) = parse_plan_steps(plan("**Iterations**: 6"))
    assert step.bound == fields.GoalBudget(6)


def test_an_unreadable_value_stays_unreadable_on_the_step() -> None:
    (step,) = parse_plan_steps(plan("**Iterations**: many"))
    assert step.bound == fields.UnreadableIterations("many")


def test_the_field_of_one_step_does_not_bind_its_neighbour() -> None:
    text = plan("Iterations: 2") + f"\n### Step {OTHER}: Other\n\n**Assignee**: implementer\n"
    first, second = parse_plan_steps(text)
    assert (first.bound, second.bound) == (fields.GoalBudget(2), fields.AttemptCap())
