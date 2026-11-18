"""The axis run record: what differs between axes when a run is conducted, with the default axis's
behaviour in every field, and the plan routed through it."""

from __future__ import annotations

import dataclasses
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import arms, axis, axis_runs, cli, results, session_loop, tasks
from praxion_evals.adherence.catalog import check_catalog
from praxion_evals.adherence.model import EarlyStop, SessionSetup, Standard
from praxion_evals.adherence.session_loop import OUTPUT_DIR, RunConfig

ROLES = ("implementer", "test-engineer")
DEFAULT = axis_runs.DEFAULT_RUN
PAIRED = "refactoring-delivery"
PAIRED_ARMS = ("preloaded", "delivered")
RUN_ID = "2026-11-18T10-00-00Z"


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


def test_the_default_assessment_hands_the_evidence_judge_setup_and_real_home_to_the_grader(
    monkeypatch, tmp_path
):
    handed: list[tuple] = []

    def grade(evidence, names, judge, setup, *, real_home):
        handed.append((evidence, judge, setup, real_home))
        return "the grade"

    monkeypatch.setattr(axis_runs.grade, "grade", grade)
    task = tasks.generate("implementer", 11, 1)[0]
    setup = SessionSetup("full", "abc1234", "implementer", task.task_id, task.template_id, 11)
    evidence, judge = object(), object()

    graded = DEFAULT.assess(evidence, task, setup, judge, tmp_path)  # type: ignore[arg-type]

    assert graded == "the grade"
    assert handed == [(evidence, judge, setup, tmp_path)]


def test_the_new_axis_overrides_only_the_fields_that_differ_between_axes():
    other = axis_runs.axis_run("refactoring-delivery")

    changed = {
        field.name
        for field in dataclasses.fields(DEFAULT)
        if getattr(other, field.name) != getattr(DEFAULT, field.name)
    }

    assert changed == {
        "axis",
        "positions",
        "plan",
        "stage",
        "build",
        "proof",
        "assess",
        "catalog",
        "refusals",
        "results_subdir",
    }
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


# --- where an axis's runs are written and read ---


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository the run is started from: its results directories hang off its top level."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path.resolve()


def _paired_config(*options: str) -> RunConfig:
    return replace(_config(*options), axis=PAIRED, arms=PAIRED_ARMS)


def _hold_run(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{RUN_ID}.json"
    path.write_text("{}", encoding="utf-8")
    return directory


@pytest.mark.parametrize(("axis_name", "subdir"), [(axis.DEFAULT_AXIS, ""), (PAIRED, PAIRED)])
def test_each_axis_names_the_subdirectory_its_results_go_to(axis_name, subdir):
    assert axis_runs.axis_run(axis_name).results_subdir == subdir


def test_an_ordinary_run_without_output_writes_in_the_adherence_results_directory(repository):
    assert session_loop.results_dir(_config()) == repository / OUTPUT_DIR


def test_a_paired_run_without_output_writes_in_the_paired_results_directory(repository):
    assert session_loop.results_dir(_paired_config()) == repository / OUTPUT_DIR / PAIRED


@pytest.mark.parametrize("make_config", [_config, _paired_config])
def test_output_names_the_results_directory_of_a_run_of_any_axis(make_config, tmp_path):
    config = make_config("--output", str(tmp_path / "elsewhere" / "run.json"))

    assert session_loop.results_dir(config) == tmp_path / "elsewhere"


def test_a_run_is_read_from_the_parent_of_output_wherever_else_it_is_held(repository):
    _hold_run(repository / OUTPUT_DIR / PAIRED)
    config = _paired_config("--output", str(repository / "named" / "run.json"))

    assert session_loop.run_directory(config, RUN_ID) == repository / "named"


@pytest.mark.parametrize("make_config", [_config, _paired_config])
def test_a_paired_run_is_found_in_its_directory_whatever_axis_is_named(make_config, repository):
    held = _hold_run(repository / OUTPUT_DIR / PAIRED)

    assert session_loop.run_directory(make_config(), RUN_ID) == held


@pytest.mark.parametrize("make_config", [_config, _paired_config])
def test_an_ordinary_run_is_found_in_its_directory_whatever_axis_is_named(make_config, repository):
    held = _hold_run(repository / OUTPUT_DIR)

    assert session_loop.run_directory(make_config(), RUN_ID) == held


def test_a_run_held_in_two_axis_directories_is_read_from_the_named_axis_first(repository):
    _hold_run(repository / OUTPUT_DIR)
    paired = _hold_run(repository / OUTPUT_DIR / PAIRED)

    assert session_loop.run_directory(_paired_config(), RUN_ID) == paired


@pytest.mark.parametrize(("make_config", "subdir"), [(_config, ""), (_paired_config, PAIRED)])
def test_a_run_held_nowhere_is_looked_for_in_the_named_axis_directory(
    make_config, subdir, repository
):
    assert session_loop.run_directory(make_config(), RUN_ID) == repository / OUTPUT_DIR / subdir
