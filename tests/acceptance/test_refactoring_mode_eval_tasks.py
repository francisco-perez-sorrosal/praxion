"""The adherence eval holds refactoring-mode tasks for the implementer and the test-engineer,
grades them from what they left behind, and can dry-run a paired run of the move at no cost.

A stand-in `claude` sits first on every run's `PATH`, so any launch is recorded by it and never
reaches a paying session.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import refactoring_delivery as rd
from tests.acceptance.drivers import refactoring_mode_eval as ev
from tests.acceptance.drivers.refactoring_delivery import MARKER, ROLES, Installation

MARKED_STEP = (
    "Task slug: widget-pricing\n\n"
    f"### Step 4: {MARKER} Extract the pricing rules into their own module\n\n"  # id-citation-discipline:ignore
    "Move the rules out of `orders.py`; keep every caller working."
)


def _checklist_cases() -> list[tuple[str, str]]:
    return [(role, item) for role, items in ev.CHECKLIST.items() for item in items]


@pytest.fixture(scope="module", params=ROLES)
def dry_run(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    role = request.param
    return role, ev.dry_run(role, tmp_path_factory.mktemp(f"dry-run-{role}"))


# -- Refactoring-mode tasks in the dry run ---------------------------------------------------------


def test_a_dry_run_lists_refactoring_mode_tasks_delegated_with_the_marker(dry_run) -> None:
    role, run = dry_run

    assert run.exit_code == 0, f"the dry run failed: {run.stderr[-2000:]}"
    marked = [s.task_id for s in run.sessions if s.role == role and rd.mentions_marker(s.prompt)]
    assert marked, f"the {role} dry run lists no task delegated with {MARKER}"


def test_a_dry_run_for_the_role_launches_no_session(dry_run) -> None:
    role, run = dry_run

    assert run.exit_code == 0, f"the dry run failed: {run.stderr[-2000:]}"
    assert run.launches == 0, f"the {role} dry run started {run.launches} sessions"


# -- Graded from the end state ---------------------------------------------------------------------


@pytest.mark.parametrize(("role", "item"), _checklist_cases())
def test_an_end_state_that_breaks_one_checklist_item_fails_its_grade(
    tmp_path: Path, role: str, item: str
) -> None:
    grade = ev.grade_refactoring_task(
        role, tmp_path, broken=item, account="Done: every checklist item holds."
    )

    assert not grade.passed, f"a {role} end state where not '{item}' still passed"


@pytest.mark.parametrize("role", ROLES)
def test_a_clean_end_state_passes_even_when_the_agent_reports_a_problem(
    tmp_path: Path, role: str
) -> None:
    grade = ev.grade_refactoring_task(
        role, tmp_path, broken=None, account="I left a compatibility shim and some dead code."
    )

    assert grade.passed, f"a clean {role} end state failed on the agent's own account"


# -- A paired run of the move, dry-run ---------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_a_dry_run_of_the_paired_move_names_the_same_refactoring_tasks_in_both_arms(
    tmp_path: Path, role: str
) -> None:
    run = ev.dry_run_paired_move(role, tmp_path)

    preloaded = sorted(s.task_id for s in run.sessions if s.arm == "preloaded")
    delivered = sorted(s.task_id for s in run.sessions if s.arm == "delivered")
    assert preloaded, f"the paired dry run names no {role} session"
    assert preloaded == delivered
    assert all(rd.mentions_marker(s.prompt) for s in run.sessions), "an arm task is unmarked"


@pytest.mark.parametrize("role", ROLES)
def test_a_dry_run_of_the_paired_move_launches_no_session(tmp_path: Path, role: str) -> None:
    run = ev.dry_run_paired_move(role, tmp_path)

    assert run.launches == 0


@pytest.mark.parametrize("role", ROLES)
def test_each_arm_of_the_paired_move_gives_a_marked_spawn_the_skill_its_own_way(
    tmp_path: Path, role: str
) -> None:
    arms = ev.build_paired_move_arms(role, tmp_path / "arms")
    project = rd.project_checkout(tmp_path / "project")

    preloaded = rd.spawn(Installation(arms["preloaded"]), project, f"praxion:{role}", MARKED_STEP)
    delivered = rd.spawn(Installation(arms["delivered"]), project, f"praxion:{role}", MARKED_STEP)

    assert rd.SKILL_NAME in preloaded.preloaded
    assert rd.copies_held(preloaded) == rd.Copies(whole=1, most=1)
    assert rd.SKILL_NAME not in delivered.preloaded
    assert rd.copies_held(delivered) == rd.Copies(whole=1, most=1)
