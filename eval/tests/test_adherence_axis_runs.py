"""The axis run record: what differs between axes when a run is conducted, with the default axis's
behaviour in every field, and the plan routed through it."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from praxion_evals.adherence import arms, axis, axis_runs, cli, results, tasks
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import EarlyStop, SessionSetup, Standard
from praxion_evals.adherence.session_loop import RunConfig

ROLES = ("implementer", "test-engineer")
DEFAULT = axis_runs.DEFAULT_RUN


def _config(*options: str) -> RunConfig:
    return cli.parse_config(["--role", "implementer", *options])


def test_the_record_is_total_over_the_closed_axis_set():
    assert [axis_runs.axis_run(name).axis for name in axis.AXES] == list(axis.AXES)


def test_the_default_axis_runs_the_default_record():
    assert axis_runs.axis_run(axis.DEFAULT_AXIS) is DEFAULT
    assert DEFAULT.positions == axis.POSITIONS[axis.DEFAULT_AXIS]


def test_the_record_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.axis = "refactoring-delivery"  # type: ignore[misc]


def test_the_default_record_holds_the_functions_that_run_today():
    assert DEFAULT.stage is tasks.build_scratch_repo
    assert DEFAULT.build is arms.build_arm
    assert DEFAULT.proof.prompt == arms.proof_prompt()
    assert DEFAULT.proof.observe is arms.observe_proof
    assert DEFAULT.proof.decide is arms.decide_proof


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("count", [0, 1, 3, 7])
def test_the_default_plan_is_what_the_generator_produces(role, count):
    assert DEFAULT.plan(role, 11, count) == tasks.generate(role, 11, count)


@pytest.mark.parametrize("role", ROLES)
def test_the_default_plan_never_holds_more_than_the_pool_produces(role):
    producible = tasks.producible_task_count(role, 11)

    planned = DEFAULT.plan(role, 11, producible + 50)

    assert planned == tasks.generate(role, 11, producible)


@pytest.mark.parametrize("role", ROLES)
def test_the_default_catalog_is_the_roles_checks(role):
    assert DEFAULT.catalog(role) == tuple(results.catalog_entry(c) for c in check_catalog(role))


def test_the_default_run_refuses_nothing():
    assert DEFAULT.refusals(_config()) == ()


def test_the_default_assessment_names_c3_only_for_a_task_that_can_plant_a_gap(monkeypatch):
    named: list[list[str]] = []
    monkeypatch.setattr(
        axis_runs.grade,
        "grade",
        lambda evidence, names, judge, setup, **_: named.append(list(names)),
    )
    task = tasks.generate("implementer", 11, 1)[0]
    plain = replace(task, variant=Standard())
    capped = replace(task, variant=EarlyStop(turn_cap=3))
    setup = SessionSetup("full", "abc1234", "implementer", plain.task_id, plain.template_id, 11)

    for task in (plain, capped):
        DEFAULT.assess(None, task, setup, None, None)  # type: ignore[arg-type]

    assert "C3" in named[0]
    assert "C3" not in named[1]


def test_the_new_axis_differs_from_the_default_in_its_name_positions_plan_staging_build_proof_and_refusals_only():
    other = axis_runs.axis_run("refactoring-delivery")

    changed = {
        field.name
        for field in dataclasses.fields(DEFAULT)
        if getattr(other, field.name) != getattr(DEFAULT, field.name)
    }

    assert changed == {"axis", "positions", "plan", "stage", "build", "proof", "refusals"}
    assert other.positions == axis.POSITIONS["refactoring-delivery"]


@pytest.mark.parametrize("role", ROLES)
def test_the_planned_tasks_of_the_default_axis_are_those_the_command_line_always_planned(role):
    config = replace(_config("--max-tasks", "3"), roles=(role,))

    wanted = min(config.required_pairs + config.pair_slack, 3)
    wanted = wanted if role in tasks.FULL_SET_ROLES else min(tasks.SMOKE_TASKS, 3)
    expected = tasks.generate(role, config.seed, min(wanted, tasks.producible_task_count(role, 11)))

    assert cli.plan_tasks(config)[role] == expected


@pytest.mark.parametrize(
    ("axis_name", "arms_named"),
    [
        ("inherited-context", ("full", "lean")),
        ("refactoring-delivery", ("preloaded", "delivered")),
    ],
)
def test_a_run_config_accepts_the_arms_of_its_own_axis(axis_name, arms_named):
    config = replace(_config(), axis=axis_name, arms=arms_named)

    assert config.arms == arms_named


@pytest.mark.parametrize(
    ("axis_name", "arms_named"),
    [
        ("refactoring-delivery", ("full", "lean")),
        ("inherited-context", ("preloaded", "delivered")),
        ("inherited-context", ("full", "delivered")),
    ],
)
def test_a_run_config_refuses_an_arm_of_the_other_axis(axis_name, arms_named):
    with pytest.raises(ValueError, match="arms"):
        replace(_config(), axis=axis_name, arms=arms_named)


def test_a_run_config_declares_the_default_axis_unless_told_otherwise():
    assert _config().axis == axis.DEFAULT_AXIS
