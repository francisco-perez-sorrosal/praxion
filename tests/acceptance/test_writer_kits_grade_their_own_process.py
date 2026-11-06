"""Each writer role is graded on its own process in every covered mode, and on its convention.

For each covered mode of the test-engineer and the systems-architect, a habit record (the task's
work done as a session does it with no rule present, every form only the role's definition
states left out) fails at least one of the role's own checks, on a planned task of that mode the
role is not stopped early on. Every task either role can draw states the project convention only
in its fixture's `CLAUDE.md`; the role scores the convention check, which passes when a file the
session wrote holds the house-rules line, fails when none does, and is not applicable on a task
that stopped the role early.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import implementer_kit
from tests.acceptance.drivers import writer_kits as kits
from tests.acceptance.drivers.flip_evidence import convention_check
from tests.acceptance.drivers.writer_kits import (
    COVERED_MODES,
    INSTRUCTION_FILE,
    OBSERVANCE_LINE,
    WRITER_ROLES,
    TaskId,
)

MODES = [(role, mode) for role in WRITER_ROLES for mode in COVERED_MODES[role]]


@pytest.fixture(scope="module")
def plans(tmp_path_factory) -> dict[str, kits.Plan]:
    return {
        role: kits.plan(tmp_path_factory.mktemp(f"{role}-plan"), role, arms=("full",))
        for role in WRITER_ROLES
    }


def a_task_that_runs_to_its_end(plan: kits.Plan, mode: str) -> str:
    """The first planned task of `mode` whose variant does not stop the role early."""
    tasks = [t for t in plan.tasks_in(mode) if TaskId.parse(t).variant != "early-stop"]
    assert tasks, f"the {plan.role} plans no {mode} task that runs to its end"
    return tasks[0]


# -- The role's own process ------------------------------------------------------------------------


@pytest.mark.parametrize(("role", "mode"), MODES)
def test_a_habit_record_of_a_covered_mode_fails_one_of_the_roles_own_checks(
    plans, tmp_path, role, mode
):
    task = a_task_that_runs_to_its_end(plans[role], mode)

    outcomes = kits.habit_outcomes(tmp_path, role, mode, task)

    failed = sorted(name for name, kind in outcomes.items() if kind == "failed")
    assert failed, (
        f"a {mode} habit record of the {role} on {task} passes every own check: {outcomes}"
    )


# -- The project convention -----------------------------------------------------------------------


@pytest.fixture(scope="module", params=WRITER_ROLES)
def conventions(request) -> tuple[str, list[kits.StatedConvention]]:
    return request.param, kits.stated_conventions(request.param)


def test_every_task_states_the_convention_with_the_roles_convention_check(conventions):
    role, stated = conventions

    unstated = [c.task_id for c in stated if c.text is None]
    checks = {c.check for c in stated}

    assert stated, f"the {role} has no task"
    assert unstated == [], f"{len(unstated)} {role} tasks state no convention: {unstated[:3]}"
    assert checks == {convention_check(role)}, checks


def test_the_convention_is_stated_only_in_the_fixtures_instruction_file(conventions):
    role, stated = conventions

    missing = [c.task_id for c in stated if not c.text or c.text not in c.instructions]
    elsewhere = [(c.task_id, c.elsewhere) for c in stated if c.elsewhere]

    assert missing == [], (
        f"{role} tasks whose {INSTRUCTION_FILE} states no convention: {missing[:3]}"
    )
    assert elsewhere == [], (
        f"the convention also appears outside {INSTRUCTION_FILE}: {elsewhere[:3]}"
    )


def test_the_conventions_observance_is_the_house_rules_line(conventions):
    role, stated = conventions

    lacking = [c.task_id for c in stated if not c.text or OBSERVANCE_LINE not in c.text]

    assert stated, f"the {role} has no task"
    assert lacking == [], f"{role} conventions not observed by the house-rules line: {lacking[:3]}"


@pytest.mark.parametrize("role", WRITER_ROLES)
def test_the_convention_check_is_among_the_roles_scored_checks(role):
    assert convention_check(role) in kits.scored_checks(role)


@pytest.mark.parametrize("role", WRITER_ROLES)
@pytest.mark.parametrize(
    ("wrote_line", "forced_stop", "expected"),
    [
        (True, False, "passed"),
        (False, False, "failed"),
        (False, True, "not applicable"),
    ],
    ids=["wrote the line", "wrote no such line", "stopped early"],
)
def test_a_writer_session_is_scored_on_the_convention(role, wrote_line, forced_stop, expected):
    outcome = implementer_kit.convention_outcome(
        wrote_line=wrote_line, forced_stop=forced_stop, role=role
    )

    assert outcome == expected
