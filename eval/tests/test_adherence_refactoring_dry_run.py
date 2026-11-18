"""The paired move planned and dry-run: the refactoring pool's tasks, both arms of the axis, in the
axis's launch order, and the other axis's arms and the calibration refused at the command line."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import cli, session_arms, session_loop, tasks
from praxion_evals.adherence import refactoring_tasks as pool
from praxion_evals.adherence.axis import ARMS_BY_AXIS, patched_paths
from praxion_evals.adherence.axis_runs import DEFAULT_RUN, axis_run
from praxion_evals.adherence.dry_run import planned_copy
from tests.adherence_run_support import dry_run, scripted_checkout

AXIS = "refactoring-delivery"
PAIRED = ["--axis", AXIS]
POOL_ROLES = ("implementer", "test-engineer")
ARMS = ARMS_BY_AXIS[AXIS]
SEED = cli.DEFAULT_SEED

pytestmark = pytest.mark.usefixtures("no_launch")


def _paired_lines(capsys, tmp_path, role: str, *options: str) -> list[dict]:
    return dry_run(capsys, tmp_path, "--role", role, *PAIRED, *options)


def _refused(capsys, tmp_path, *options: str) -> str:
    output = tmp_path / "out.json"
    with pytest.raises(SystemExit) as stopped:
        cli.parse_config(["--role", "implementer", "--output", str(output), *options])
    assert stopped.value.code == cli.EXIT_USAGE
    assert not output.exists()
    return capsys.readouterr().err


@pytest.mark.parametrize("role", POOL_ROLES)
def test_both_arms_name_the_same_tasks(capsys, tmp_path, role):
    lines = _paired_lines(capsys, tmp_path, role)

    by_arm = {arm: sorted(line["task_id"] for line in lines if line["arm"] == arm) for arm in ARMS}
    assert by_arm["preloaded"]
    assert by_arm["preloaded"] == by_arm["delivered"]
    assert {line["arm"] for line in lines} == set(ARMS)


@pytest.mark.parametrize("role", POOL_ROLES)
def test_every_planned_prompt_carries_the_marker(capsys, tmp_path, role):
    lines = _paired_lines(capsys, tmp_path, role)

    assert lines
    assert all(pool.MARKER in " ".join(line["argv"]) for line in lines)


@pytest.mark.parametrize("role", POOL_ROLES)
def test_a_run_capped_at_two_tasks_still_holds_two_templates(capsys, tmp_path, role):
    lines = _paired_lines(capsys, tmp_path, role, "--max-tasks", "2")

    task_ids = {line["task_id"] for line in lines}
    templates = {task_id.split(".")[1] for task_id in task_ids}
    assert len(task_ids) == 2
    assert len(templates) == 2
    assert len(lines) == 4


def _paired_stderr(capsys, tmp_path, role: str, *options: str) -> str:
    argv = [str(scripted_checkout()), "--output", str(tmp_path / "out.json"), "--dry-run"]
    argv += ["--role", role, *PAIRED, "--session-budget-usd", "1.25", *options]
    assert cli.main(argv) == 0
    return capsys.readouterr().err


@pytest.mark.parametrize("role", POOL_ROLES)
def test_a_paired_dry_run_states_its_sessions_and_the_cap_that_admits_them(capsys, tmp_path, role):
    err = _paired_stderr(capsys, tmp_path, role, "--max-tasks", "2")

    # two tasks on two arms, plus one proof per arm
    assert "6 sessions reserve against the run cap, 2 of them proofs" in err
    assert "6 x 1.25 = 7.5 USD admits every one launched once" in err
    assert "a launch tried again reserves its budget again" in err


@pytest.mark.parametrize("role", POOL_ROLES)
def test_a_paired_cap_below_the_smallest_warns_of_refusals_and_names_the_cap(
    capsys, tmp_path, role
):
    err = _paired_stderr(capsys, tmp_path, role, "--max-tasks", "2", "--max-total-usd", "7")

    assert "later launches may then be refused" in err
    assert "--max-total-usd 7.5 admits them all" in err


@pytest.mark.parametrize("role", POOL_ROLES)
def test_a_paired_cap_that_admits_every_session_draws_no_refusal_warning(capsys, tmp_path, role):
    err = _paired_stderr(capsys, tmp_path, role, "--max-tasks", "2", "--max-total-usd", "7.5")

    assert "refus" not in err


@pytest.mark.parametrize("role", POOL_ROLES)
def test_the_arms_of_a_task_follow_the_axis_launch_order(capsys, tmp_path, role):
    lines = _paired_lines(capsys, tmp_path, role)

    for first, second in zip(lines[::2], lines[1::2], strict=True):
        assert first["task_id"] == second["task_id"]
        expected = session_loop.launch_order(SEED, first["task_id"], AXIS)
        assert (first["arm"], second["arm"]) == expected


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("variant", ["ambiguity", "early-stop"])
def test_the_dry_run_names_the_plugin_copy_a_real_run_builds_for_each_arm(tmp_path, arm, variant):
    built: list[Path] = []
    record = replace(axis_run(AXIS), build=lambda original, dest, *_, **__: built.append(dest))
    task = next(
        t for t in pool.planned_pool("implementer", SEED, 100) if t.task_id.endswith(f".{variant}")
    )

    session_arms.build_copy(
        tmp_path / task.role,
        None,
        task.role,
        arm,
        tasks.turn_cap_of(task),
        record,  # type: ignore[arg-type]
    )

    assert planned_copy(tmp_path, task, arm) == built[0]


def test_the_delivered_arm_patches_the_two_move_sites_and_the_preloaded_none():
    assert patched_paths("implementer", "preloaded", None) == ()
    assert patched_paths("implementer", "delivered", None) == (
        "agents/implementer.md",
        "agents/test-engineer.md",
    )


@pytest.mark.parametrize("role", POOL_ROLES)
def test_the_planned_pool_holds_each_task_once_and_never_a_default_task(role):
    planned = pool.planned_pool(role, SEED, 100)

    ids = [t.task_id for t in planned]
    assert len(ids) == len(set(ids)) == len(pool.pool_tasks(role, SEED))
    default_ids = {
        t.task_id for t in tasks.generate(role, SEED, tasks.producible_task_count(role, SEED))
    }
    assert not default_ids & set(ids)
    assert all(pool.MARKER in t.main_prompt for t in planned)


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_the_planned_pool_is_capped_at_the_count_in_the_same_order(count):
    whole = pool.planned_pool("implementer", SEED, 100)

    assert pool.planned_pool("implementer", SEED, count) == whole[:count]


def test_the_planned_pool_takes_one_task_of_each_template_before_any_repeats():
    planned = pool.planned_pool("implementer", SEED, 100)
    templates = len(pool.pool_templates("implementer"))

    assert len({t.template_id for t in planned[:templates]}) == templates


def test_the_planned_pool_is_the_same_for_the_same_seed():
    assert pool.planned_pool("implementer", 3, 100) == pool.planned_pool("implementer", 3, 100)


def test_the_new_axis_plans_the_pool_and_refuses_a_calibration():
    record = axis_run(AXIS)

    assert record.plan is pool.planned_pool
    assert record.refusals(cli.parse_config(["--role", "implementer", *PAIRED])) == ()
    assert DEFAULT_RUN.plan is not pool.planned_pool


def test_the_new_axis_defaults_to_both_of_its_arms_in_positions_order():
    config = cli.parse_config(["--role", "implementer", *PAIRED])

    assert (config.axis, config.arms) == (AXIS, ("preloaded", "delivered"))


@pytest.mark.parametrize("arm", ["full", "lean"])
def test_an_arm_of_the_default_axis_is_refused_with_the_new_axis(capsys, tmp_path, arm):
    err = _refused(capsys, tmp_path, *PAIRED, "--arm", arm)

    assert (
        f"--arm {arm} is an arm of the inherited-context axis;"
        " the refactoring-delivery axis has arms preloaded and delivered"
    ) in err


@pytest.mark.parametrize("arm", ["preloaded", "delivered"])
def test_an_arm_of_the_new_axis_is_refused_with_the_default_axis(capsys, tmp_path, arm):
    err = _refused(capsys, tmp_path, "--arm", arm)

    assert (
        f"--arm {arm} is an arm of the refactoring-delivery axis;"
        " the inherited-context axis has arms full and lean"
    ) in err


def test_a_calibration_is_refused_with_the_new_axis(capsys, tmp_path):
    err = _refused(capsys, tmp_path, *PAIRED, "--calibration")

    assert (
        "--calibration measures the full arm of the inherited-context axis against itself;"
        " it takes no --axis refactoring-delivery"
    ) in err


def test_a_calibration_is_still_legal_on_the_default_axis():
    config = cli.parse_config(["--role", "implementer", "--calibration"])

    assert (config.calibration, config.arms) == (True, ("full",))


@pytest.mark.parametrize("role", POOL_ROLES)
def test_the_default_axis_lines_do_not_change_when_it_is_named(capsys, tmp_path, role):
    implicit = dry_run(capsys, tmp_path, "--role", role, "--max-tasks", "4")
    explicit = dry_run(
        capsys, tmp_path, "--role", role, "--max-tasks", "4", "--axis", "inherited-context"
    )

    assert implicit == explicit
    assert {line["arm"] for line in implicit} == {"full", "lean"}
    assert all(pool.MARKER not in json.dumps(line) for line in implicit)
