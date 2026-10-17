"""A stopped run is continued or closed, never abandoned for a fresh draw.

A continuation of a run stopped by a streak holding both arms launches again, whole and in
the seeded order, only the tasks with no complete pair and no session ending otherwise;
every other outcome stands as recorded. It is refused before any launch, naming the
difference, unless it measures the same thing under the same declarations; committing a
results file never invalidates it. A fresh run of a role beside an unresolved stopped run
is refused until that run is continued or closed with a reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers.adherence_runs import (
    EIGHT_SHAPES,
    KEPT_LEAN_FAILURE_SHAPES,
    RELAUNCHED_SHAPES,
    Plan,
    Script,
)

PLAN = Plan(max_tasks=len(EIGHT_SHAPES))
REASON = "the trial's credit was cut off for an unrelated audit; no continuation planned"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return runs.new_checkout(tmp_path)


@pytest.fixture
def stopped(tmp_path: Path, checkout: Path) -> runs.PlantedRun:
    return runs.plant_stopped_run(tmp_path, checkout, PLAN)


def tasks_of(planted: runs.PlantedRun, shapes: frozenset[str]) -> set[str]:
    return {task for task, shape in planted.shapes.items() if shape in shapes}


def assert_refused_before_launch(result: runs.StandInRun, *named: str) -> None:
    printed = result.stdout + result.stderr
    assert result.exit_code != 0, "the continuation was accepted"
    assert result.launches == (), "a session launched before the refusal"
    assert all(word in printed for word in named), f"the refusal does not name {named}: {printed}"


def test_a_continuation_launches_exactly_the_unfinished_tasks_whole_in_every_arm(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    result = runs.continue_run(tmp_path, checkout, stopped.path, PLAN)

    relaunched = tasks_of(stopped, RELAUNCHED_SHAPES)

    assert result.launched_tasks() == relaunched
    assert {(s.task_id, s.arm) for s in result.launches} == {
        (task, arm) for task in relaunched for arm in ("full", "lean")
    }


def test_a_continuation_launches_its_tasks_in_the_order_its_seed_gave_them(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    orders = runs.launch_orders(runs.dry_run(tmp_path / "dry", checkout))

    result = runs.continue_run(tmp_path, checkout, stopped.path, PLAN)
    task_order = [t for t in stopped.task_ids if t in result.launched_tasks()]

    assert [s.task_id for s in result.launches if s.attempt == 1][::2] == task_order
    assert {
        s.task_id: tuple(x.arm for x in result.launches if x.task_id == s.task_id)
        for s in result.launches
    } == {task: orders[task] for task in task_order}


def test_lean_failures_recorded_before_the_streak_still_count_after_a_continuation(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    result = runs.continue_run(tmp_path, checkout, stopped.path, PLAN)

    counted = runs.lean_failure_tasks(result.results_path, PLAN.role)

    assert tasks_of(stopped, KEPT_LEAN_FAILURE_SHAPES) <= counted


def test_committing_a_results_file_between_the_stop_and_the_continuation_does_not_refuse_it(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    relpath = str(stopped.path.relative_to(checkout))
    runs.commit_in_checkout(checkout, relpath, "record the stopped run")

    result = runs.continue_run(tmp_path, checkout, stopped.path, PLAN)

    assert result.launched_tasks() == tasks_of(stopped, RELAUNCHED_SHAPES)


def test_a_change_to_the_adoption_ledger_since_the_stop_refuses_the_continuation(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    runs.change_in_checkout(checkout, ".ai-state/kernel_adoption.yaml")

    result = runs.continue_run(tmp_path, checkout, stopped.path, PLAN)

    assert_refused_before_launch(result, "kernel_adoption.yaml")


DIFFERENT_DECLARATIONS = {
    "model": (Plan(max_tasks=len(EIGHT_SHAPES), model="sonnet"), "model"),
    "seed": (Plan(max_tasks=len(EIGHT_SHAPES), seed=99), "seed"),
    "task list": (Plan(max_tasks=len(EIGHT_SHAPES) - 1), "task"),
    "margin": (Plan(max_tasks=len(EIGHT_SHAPES), margin_pp=5), "margin"),
    "stop count": (Plan(max_tasks=len(EIGHT_SHAPES), stop_count=5), "stop"),
}


@pytest.mark.parametrize(
    ("plan", "named"), DIFFERENT_DECLARATIONS.values(), ids=DIFFERENT_DECLARATIONS.keys()
)
def test_a_continuation_differing_in_a_declaration_is_refused_naming_it(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun, plan: Plan, named: str
) -> None:
    result = runs.continue_run(tmp_path, checkout, stopped.path, plan)

    assert_refused_before_launch(result, named)


def test_a_continuation_of_a_run_whose_recorded_launch_order_differs_from_its_seed_is_refused(
    tmp_path: Path, checkout: Path
) -> None:
    tampered = runs.plant_stopped_run(tmp_path, checkout, PLAN, recorded_launch_order_swapped=True)

    result = runs.continue_run(tmp_path, checkout, tampered.path, PLAN)

    assert_refused_before_launch(result, "order")


NOT_CONTINUABLE = ("complete", "confined to one arm", "operator interrupt", "already continued")


@pytest.mark.parametrize("variant", NOT_CONTINUABLE)
def test_a_run_that_did_not_stop_continuably_is_refused_a_continuation(
    tmp_path: Path, checkout: Path, variant: runs.StopVariant
) -> None:
    planted = runs.plant_stopped_run(tmp_path, checkout, PLAN, variant=variant)

    result = runs.continue_run(tmp_path, checkout, planted.path, PLAN)

    assert_refused_before_launch(result, planted.run_id)


def test_a_continuation_of_an_unreadable_results_file_is_refused(
    tmp_path: Path, checkout: Path
) -> None:
    broken = runs.results_dir(checkout) / "20261020T000000Z-0badf1.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text('{"schema_version": "adherence/1", "run": ', encoding="utf-8")

    result = runs.continue_run(tmp_path, checkout, broken, PLAN)

    assert_refused_before_launch(result, broken.name)


def test_a_continuation_of_a_run_recorded_before_this_change_is_refused(
    tmp_path: Path, checkout: Path
) -> None:
    recorded = runs.results_dir(checkout) / "20261014T045733Z-7050ca.json"

    result = runs.continue_run(tmp_path, checkout, recorded, Plan())

    assert_refused_before_launch(result, "20261014T045733Z-7050ca")


def test_a_fresh_run_beside_an_unresolved_continuable_stopped_run_is_refused_naming_it(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    result = runs.run_with_stand_in(tmp_path, checkout, PLAN, Script())

    assert_refused_before_launch(result, stopped.run_id)


def test_after_an_explicit_close_with_a_reason_a_fresh_run_starts(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    closed = runs.close_run(tmp_path, checkout, stopped.path, REASON)

    fresh = runs.run_with_stand_in(tmp_path, checkout, PLAN, Script())

    assert closed.exit_code == 0, closed.stdout + closed.stderr
    assert fresh.launches, "no session launched after the stopped run was closed"


def test_a_close_without_a_reason_is_refused(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    closed = runs.close_run(tmp_path, checkout, stopped.path, None)

    fresh = runs.run_with_stand_in(tmp_path, checkout, PLAN, Script())

    assert closed.exit_code != 0, "a stopped run was closed with no recorded reason"
    assert fresh.launches == ()


def test_a_closed_run_is_listed_as_a_not_clear_draw_with_its_interim_result(
    tmp_path: Path, checkout: Path, stopped: runs.PlantedRun
) -> None:
    runs.close_run(tmp_path, checkout, stopped.path, REASON)

    fresh = runs.run_with_stand_in(tmp_path, checkout, PLAN, Script())
    listed = runs.earlier_runs(fresh.results_path, PLAN.role)

    assert [(d.run_ids, d.flip, d.interim) for d in listed.draws] == [
        ((stopped.run_id,), "not clear", True)
    ]
