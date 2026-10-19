"""The seeded launch order: which arm a task launches first, drawn from the run's seed and the
task, recorded before the task's first session, and printed by the dry run in the same order."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from praxion_evals.adherence import cli, session_loop
from tests.adherence_run_support import (
    ROLE,
    Script,
    dry_run,
    run_small,
)

pytestmark = pytest.mark.usefixtures("unswitched_checkout")


TWENTY_FOUR_TASKS = [f"task-{number}" for number in range(24)]


def _orders(seed: int) -> list[tuple[str, str]]:
    return [session_loop.launch_order(seed, task_id) for task_id in TWENTY_FOUR_TASKS]


def test_the_same_seed_gives_each_task_the_same_launch_order() -> None:
    assert _orders(7) == _orders(7)


def test_two_seeds_differ_in_some_task_launch_order() -> None:
    assert _orders(7) != _orders(8)


def test_twenty_four_tasks_hold_both_launch_orders_and_each_names_both_arms() -> None:
    orders = _orders(7)

    assert set(orders) == {("full", "lean"), ("lean", "full")}


def test_an_order_names_only_the_arms_a_run_launches() -> None:
    for task_id in TWENTY_FOUR_TASKS:
        assert session_loop.ordered_arms(["lean"], 7, task_id) == ["lean"]
        assert sorted(session_loop.ordered_arms(["full", "lean"], 7, task_id)) == ["full", "lean"]


def test_a_run_records_each_task_order_and_launches_in_it(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())

    _, loaded = run_small(tmp_path)

    (task_id,) = {r.setup.task_id for r in loaded.sessions}
    order = session_loop.launch_order(cli.DEFAULT_SEED, task_id)
    assert loaded.run.extra["launch_order"] == {ROLE: {task_id: list(order)}}
    assert [r.setup.arm for r in loaded.sessions] == list(order)


def test_a_calibration_run_records_its_fixed_slot_order(
    paid: Callable[[Script], None], tmp_path: Path
) -> None:
    paid(Script())

    _, loaded = run_small(tmp_path, "--calibration")

    (task_id,) = {r.setup.task_id for r in loaded.sessions}
    assert loaded.run.extra["launch_order"] == {ROLE: {task_id: ["full", "lean"]}}
    assert [r.setup.arm for r in loaded.sessions] == ["full", "lean"]


@pytest.mark.usefixtures("no_launch")
def test_a_dry_run_prints_each_task_arms_in_its_launch_order(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    lines = dry_run(capsys, tmp_path, "--role", ROLE)

    printed: dict[str, list[str]] = {}
    for line in lines:
        printed.setdefault(line["task_id"], []).append(line["arm"])
    assert printed
    assert {task: tuple(arms) for task, arms in printed.items()} == {
        task: session_loop.launch_order(cli.DEFAULT_SEED, task) for task in printed
    }
