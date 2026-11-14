"""Tests for the change type a plan declares for a step (``scripts/_plan_steps.py``).

A step's type is the first that applies of: its own ``Change type`` field, a ``[Phase:
Refactoring]`` heading tag (``refactor``), a plan-level ``Change type`` line outside every step
block, else none. A value outside the closed set, or lines that disagree, is kept as an
unreadable reading that quotes what was written. The reader is pure: every case passes text.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import (  # noqa: E402
    CHANGE_TYPES,
    ChangeType,
    UnreadableChangeType,
    parse_plan_steps,
)

IMPLEMENTER = "**Assignee**: implementer"
PLAN_LINE = "**Change type**: feat"


def step(number, *lines, heading="Do it"):
    body = "".join(f"{line}\n" for line in lines)
    return f"### Step {number}: {heading}\n\n{IMPLEMENTER}\n{body}\n"


def plan(*steps, head=""):
    return f"# Plan\n\n{head}## Steps\n\n" + "".join(steps)


def type_of(*lines, heading="Do it", head=""):
    return parse_plan_steps(plan(step("1", *lines, heading=heading), head=head))[0].change_type


# -- The closed set ---------------------------------------------------------------------------


def test_the_closed_set_is_the_conventional_commit_types_the_driver_may_write():
    assert CHANGE_TYPES == ("feat", "fix", "refactor", "perf", "docs", "test", "chore")
    assert CHANGE_TYPES == get_args(ChangeType)


# -- A step's own field -----------------------------------------------------------------------


@pytest.mark.parametrize("value", CHANGE_TYPES)
def test_a_step_field_reads_each_type_of_the_set(value):
    assert type_of(f"**Change type**: {value}") == value


@pytest.mark.parametrize(
    "line",
    [
        "**Change type**: fix",
        "Change type: fix",
        "**change type**: fix",
        "CHANGE TYPE: fix",
        "- **Change type**: fix",
        "**Change type:** fix",
    ],
)
def test_the_field_label_is_optionally_bold_and_case_insensitive(line):
    assert type_of(line) == "fix"


def test_a_step_with_no_field_and_no_tag_declares_no_type():
    assert type_of() is None


def test_a_field_line_inside_a_code_fence_declares_nothing():
    assert type_of("```", "**Change type**: fix", "```") is None


# -- The refactoring tag ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "[Phase: Refactoring] Extract the parser",
        "Extract the parser [Phase: Refactoring]",
        "[phase: refactoring] Extract the parser",
        "[Phase:  REFACTORING ] Extract the parser",
    ],
)
def test_the_refactoring_phase_tag_means_refactor_whatever_its_case_or_place(heading):
    assert type_of(heading=heading) == "refactor"


def test_another_phase_name_maps_to_no_type():
    assert type_of(heading="[Phase: Migration] Move the data") is None


def test_a_step_field_beats_the_refactoring_tag():
    assert type_of("**Change type**: fix", heading="[Phase: Refactoring] Tidy") == "fix"


# -- The plan-level line ----------------------------------------------------------------------


def test_a_plan_level_line_gives_every_step_without_its_own_type_that_type():
    text = plan(step("1"), step("2", "**Change type**: fix"), head=f"{PLAN_LINE}\n\n")

    assert [s.change_type for s in parse_plan_steps(text)] == ["feat", "fix"]


def test_the_refactoring_tag_beats_the_plan_level_line():
    assert type_of(heading="[Phase: Refactoring] Tidy", head=f"{PLAN_LINE}\n\n") == "refactor"


def test_a_plan_level_line_after_the_last_step_under_its_own_heading_counts():
    text = plan(step("1")) + f"## Notes\n\n{PLAN_LINE}\n"

    assert parse_plan_steps(text)[0].change_type == "feat"


def test_a_plan_level_line_in_a_code_fence_declares_nothing():
    assert type_of(head="```\n**Change type**: feat\n```\n\n") is None


def test_a_line_inside_a_step_block_is_that_steps_and_never_the_plans():
    text = plan(step("1", "**Change type**: fix"), step("2"))

    assert [s.change_type for s in parse_plan_steps(text)] == ["fix", None]


def test_a_plan_level_line_changes_no_step_block_or_digest():
    bare = plan(step("1", "**Files**: `a.py`"), step("2"))
    typed = plan(step("1", "**Files**: `a.py`"), step("2"), head=f"{PLAN_LINE}\n\n")
    typed += f"## Notes\n\n{PLAN_LINE}\n"

    before, after = parse_plan_steps(bare), parse_plan_steps(typed)

    assert [(s.block, s.digest) for s in after] == [(s.block, s.digest) for s in before]
    assert [s.change_type for s in after] == ["feat", "feat"]


# -- The unreadable readings ------------------------------------------------------------------


@pytest.mark.parametrize("value", ["feature", "Feat", "feat!", "", "feat fix", "build"])
def test_a_step_value_outside_the_set_is_kept_as_written(value):
    reading = type_of(f"**Change type**: {value}")

    assert reading == UnreadableChangeType(value, "step")


def test_two_step_lines_that_disagree_are_one_unreadable_reading_quoting_both():
    reading = type_of("**Change type**: feat", "**Change type**: fix")

    assert reading == UnreadableChangeType("feat; fix", "step")


def test_two_step_lines_that_agree_read_as_that_type():
    assert type_of("**Change type**: fix", "Change type: fix") == "fix"


def test_a_value_outside_the_set_in_the_plan_level_line_is_kept_as_written():
    reading = type_of(head="**Change type**: feature\n\n")

    assert reading == UnreadableChangeType("feature", "plan")


def test_two_plan_level_lines_that_disagree_are_unreadable():
    reading = type_of(head="**Change type**: feat\n**Change type**: docs\n\n")

    assert reading == UnreadableChangeType("feat; docs", "plan")


def test_two_plan_level_lines_that_agree_read_as_that_type():
    assert type_of(head="**Change type**: docs\n**Change type**: docs\n\n") == "docs"


def test_an_unreadable_plan_level_line_reaches_only_the_steps_that_would_use_it():
    text = plan(
        step("1"),
        step("2", "**Change type**: fix"),
        step("3", heading="[Phase: Refactoring] Tidy"),
        head="**Change type**: nonsense\n\n",
    )

    assert [s.change_type for s in parse_plan_steps(text)] == [
        UnreadableChangeType("nonsense", "plan"),
        "fix",
        "refactor",
    ]


def test_an_unreadable_step_field_beats_the_tag_and_the_plan_line():
    reading = type_of("**Change type**: nope", heading="[Phase: Refactoring] Tidy", head=PLAN_LINE)

    assert reading == UnreadableChangeType("nope", "step")
