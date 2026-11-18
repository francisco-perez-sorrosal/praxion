"""What a run of the paired move records: the setup's axis, the kernel owed to both arms, the axis
in the run's file, and the earlier-run listing kept per axis."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from praxion_evals.adherence import (
    arms,
    cli,
    results,
    session_arms,
    session_launch,
    session_loop,
    tasks,
)
from praxion_evals.adherence.axis import KERNEL_OWED, patched_paths
from praxion_evals.adherence.axis_runs import ArmProof, axis_run
from praxion_evals.adherence.model import ArmBuild, Measured, Passed, SessionRecord, SessionSetup
from praxion_evals.adherence.session_launch import Launch
from praxion_evals.live.spend import SpendLedger
from tests.adherence_run_support import scripted_checkout
from tests.test_adherence_results import run_results

pytestmark = pytest.mark.usefixtures("unswitched_checkout")

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = "implementer"  # the paired axis authors a pool for the implementer and the test-engineer
SEED = 7
PAIRED = "refactoring-delivery"
PAIRED_ARMS = ("preloaded", "delivered")
STARTED_AT = "2026-10-12T09:00:00Z"
PAIRED_OPTIONS = ["--axis", PAIRED, "--arm", "preloaded", "--arm", "delivered"]


def _launch(tmp_path: Path, axis: str) -> Launch:
    return Launch(
        run_root=tmp_path / "run",
        checkout_commit="abc",
        page_url="",
        judge=None,
        seed=SEED,
        model="m",
        effort="low",
        session_budget_usd=1.0,
        keep_sandbox=True,
        env_for=lambda root, path_first: {},
        real_home=tmp_path / "home",
        ambient={"PATH": "/usr/bin"},
        axis_run=axis_run(axis),  # type: ignore[arg-type]
    )


def _build(root: Path, arm: str) -> ArmBuild:
    (root / "agents").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "agents" / f"{ROLE}.md", root / "agents" / f"{ROLE}.md")
    return ArmBuild(ROLE, arm, root, None, "digest", patched_paths(ROLE, arm, None))  # type: ignore[arg-type]


def _session(task: str, arm: str, axis: str) -> SessionRecord:
    setup = SessionSetup(arm, "c" * 40, ROLE, task, "template", SEED, axis)  # type: ignore[arg-type]
    return SessionRecord(setup, Measured({"C1": Passed()}, 1), 0.01, 1000, STARTED_AT)


def _run_of(axis: str, run_id: str, arms: tuple[str, str]) -> results.RunResults:
    extra = {} if axis == "inherited-context" else {"axis": axis}
    sessions = [_session("t1", arm, axis) for arm in arms]
    run = run_results(sessions, run_id=run_id, roles=(ROLE,), extra=extra)
    return replace(run, arms={ROLE: {arm: {"built": True} for arm in arms}})


def _write(directory: Path, run: results.RunResults) -> None:
    results.write_atomic(directory / f"{run.run.id}.json", run)


def _listed(directory: Path, axis: str = "inherited-context") -> results.EarlierRuns:
    listing = results.earlier_runs(directory, (ROLE,), lambda earlier, role: (), axis=axis)
    return listing.by_role[ROLE]


# --- the setup's axis and the kernel owed ---


@pytest.mark.parametrize("axis", ["inherited-context", PAIRED])
def test_a_task_session_records_a_setup_of_the_runs_axis(tmp_path, monkeypatch, axis):

    def attempt(launch, ledger, task, build, populate, page_url, assess):
        return ledger, SimpleNamespace(
            result=Measured({"C1": Passed()}, 1), charged_usd=0.0, duration_ms=0,
            started_at="t", refused_commands=(), model=None,
        )  # fmt: skip

    monkeypatch.setattr(session_launch, "attempt", attempt)
    arm = "lean" if axis == "inherited-context" else "delivered"

    _, record, _ = session_launch.task_session(
        _launch(tmp_path, axis),
        SpendLedger(cap_usd=10.0),
        tasks.generate(ROLE, SEED, 1)[0],
        arm,  # type: ignore[arg-type]
        _build(tmp_path / "copy", arm),
        None,
    )

    assert record.setup.axis == axis


def test_the_kernel_is_owed_to_lean_on_the_default_axis_and_to_both_arms_of_the_new_one():
    assert KERNEL_OWED["inherited-context"] == ("lean",)
    assert KERNEL_OWED[PAIRED] == PAIRED_ARMS


@pytest.mark.parametrize(
    ("axis", "arm", "owed"),
    [
        ("inherited-context", "full", False),
        ("inherited-context", "lean", True),
        (PAIRED, "preloaded", True),
        (PAIRED, "delivered", True),
    ],
)
def test_an_arm_is_graded_as_owed_its_kernel_by_the_table_of_its_axis(
    tmp_path, monkeypatch, axis, arm, owed
):
    taken: dict[str, Any] = {}
    monkeypatch.setattr(session_launch.grade, "kernel_adopted", lambda copy, role: True)
    monkeypatch.setattr(
        session_launch.grade, "evidence_from_recording", lambda **kwargs: taken.update(kwargs)
    )
    run = SimpleNamespace(stdout="", exit_code=0, timed_out=False)

    session_launch._evidence(
        _launch(tmp_path, axis),
        tasks.generate(ROLE, SEED, 1)[0],
        _build(tmp_path / "copy", arm),
        None,
        tmp_path / "root",
        run,  # type: ignore[arg-type]
        "commit",
    )

    assert taken["kernel_expected"] is owed


def test_a_role_that_adopts_no_kernel_is_owed_none_on_either_axis(tmp_path, monkeypatch):
    taken: dict[str, Any] = {}
    monkeypatch.setattr(session_launch.grade, "kernel_adopted", lambda copy, role: False)
    monkeypatch.setattr(
        session_launch.grade, "evidence_from_recording", lambda **kwargs: taken.update(kwargs)
    )
    run = SimpleNamespace(stdout="", exit_code=0, timed_out=False)

    session_launch._evidence(
        _launch(tmp_path, PAIRED),
        tasks.generate(ROLE, SEED, 1)[0],
        _build(tmp_path / "copy", "delivered"),
        None,
        tmp_path / "root",
        run,  # type: ignore[arg-type]
        "commit",
    )

    assert taken["kernel_expected"] is False


# --- the run's axis in its file ---


def _provisional(tmp_path: Path, *options: str) -> results.RunResults:
    config = cli.parse_config(["--role", ROLE, "--output", str(tmp_path / "o.json"), *options])
    checkout = session_loop.Checkout(scripted_checkout(), "0" * 40, False)
    planned = {ROLE: config_plan(config)}
    started = session_loop.datetime.now(session_loop.UTC)
    return session_loop._provisional(
        config,
        checkout,
        planned,
        cli.declared_settings(config),
        "run",
        "1",
        started,
        tmp_path / "o.json",
    )


def config_plan(config: session_loop.RunConfig) -> list[Any]:
    return axis_run(config.axis).plan(ROLE, SEED, 1)


def test_a_provisional_file_of_the_new_axis_holds_the_axis(tmp_path):
    provisional = _provisional(tmp_path, *PAIRED_OPTIONS)

    assert provisional.run.extra["axis"] == PAIRED


def test_a_provisional_file_of_the_default_axis_holds_no_axis_key(tmp_path):
    provisional = _provisional(tmp_path)

    assert "axis" not in provisional.run.extra
    assert "axis" not in json.loads(json.dumps(results.to_json(provisional)))["run"]


# --- the arms in the axis's launch order ---


@pytest.mark.parametrize("task", ["t1", "t2", "t3", "t4"])
def test_the_planned_order_of_the_new_axis_is_the_default_draw_on_its_arms(task):
    onto_paired = {"full": "preloaded", "lean": "delivered"}
    first, second = session_loop.planned_order(cli.parse_config(["--role", ROLE]), task)

    planned = session_loop.planned_order(cli.parse_config(["--role", ROLE, *PAIRED_OPTIONS]), task)

    assert planned == (onto_paired[first], onto_paired[second])


def test_the_slots_of_the_new_axis_run_its_arms_in_the_planned_order():
    config = cli.parse_config(["--role", ROLE, *PAIRED_OPTIONS])
    task = SimpleNamespace(task_id="t1")

    slots = session_loop.session_slots(config, list(PAIRED_ARMS), task)  # type: ignore[arg-type]

    assert [slot for slot, _ in slots] == list(session_loop.planned_order(config, "t1"))
    assert all(slot == copy for slot, copy in slots)


# --- a session names the axis its run compares along ---


def test_a_session_of_another_axis_than_its_runs_is_refused_on_construction():
    run = _run_of(PAIRED, "paired", PAIRED_ARMS)

    with pytest.raises(ValueError, match="refactoring-delivery axis"):
        replace(run, run=replace(run.run, extra={}))


def test_a_default_run_holding_a_paired_session_is_refused_on_construction():
    with pytest.raises(ValueError, match="inherited-context axis"):
        run_results([_session("t1", "delivered", PAIRED)], roles=(ROLE,))


def test_a_file_whose_session_names_another_axis_than_its_run_is_refused_on_decode(tmp_path):
    path = tmp_path / "paired.json"
    results.write_atomic(path, _run_of(PAIRED, "paired", PAIRED_ARMS))
    document = json.loads(path.read_text())
    del document["run"]["axis"]

    with pytest.raises(ValueError, match="refactoring-delivery axis"):
        results.from_json(document)


def _unknown_axis_file(tmp_path: Path) -> Path:
    path = tmp_path / "unknown.json"
    document = results.to_json(run_results([], roles=(ROLE,)))
    document["run"]["axis"] = "no-such-axis"  # the writer cannot make this file; a hand edit can
    path.write_text(json.dumps(document))
    return path


def test_a_file_with_no_session_and_an_unknown_axis_is_refused_on_load_naming_the_axis(tmp_path):
    with pytest.raises(ValueError, match="inherited-context.*refactoring-delivery.*'no-such-axis'"):
        results.load(_unknown_axis_file(tmp_path))


def test_the_report_of_a_file_naming_an_unknown_axis_ends_with_the_usage_error(tmp_path, capsys):
    code = cli.main(["--report", str(_unknown_axis_file(tmp_path))])

    assert (code, capsys.readouterr().err.count("Traceback")) == (cli.EXIT_USAGE, 0)


@pytest.mark.parametrize("run", [[], "run", None, 7])
def test_a_file_whose_run_is_not_an_object_is_refused_on_load_with_a_value_error(tmp_path, run):
    document = results.to_json(run_results([], roles=(ROLE,)))
    document["run"] = run
    path = tmp_path / "shaped.json"
    path.write_text(json.dumps(document))

    with pytest.raises(ValueError, match="the run is a JSON object"):
        results.load(path)


def test_a_default_file_with_no_axis_key_and_a_paired_file_still_load(tmp_path):
    for run in (
        _run_of("inherited-context", "default-1", ("full", "lean")),
        _run_of(PAIRED, "paired-1", PAIRED_ARMS),
    ):
        _write(tmp_path, run)
        assert results.load(tmp_path / f"{run.run.id}.json") == run


def test_a_run_and_its_sessions_of_one_axis_round_trip(tmp_path):
    run = _run_of(PAIRED, "paired", PAIRED_ARMS)
    results.write_atomic(tmp_path / "paired.json", run)

    assert results.load(tmp_path / "paired.json") == run


# --- earlier runs are listed per axis ---


def test_a_paired_run_is_not_listed_among_the_default_runs_earlier_runs(tmp_path):
    _write(tmp_path, _run_of("inherited-context", "default-1", ("full", "lean")))
    _write(tmp_path, _run_of(PAIRED, "paired-1", PAIRED_ARMS))

    listed = _listed(tmp_path)

    assert [draw.run_ids for draw in listed.draws] == [("default-1",)]
    assert (dict(listed.apart), listed.calibration) == ({}, ())


def test_a_default_run_is_not_listed_among_the_paired_runs_earlier_runs(tmp_path):
    _write(tmp_path, _run_of("inherited-context", "default-1", ("full", "lean")))
    _write(tmp_path, _run_of(PAIRED, "paired-1", PAIRED_ARMS))

    listed = _listed(tmp_path, PAIRED)

    assert [draw.run_ids for draw in listed.draws] == [("paired-1",)]


def test_the_default_listing_equals_the_listing_with_the_paired_file_absent(tmp_path):
    beside, alone = tmp_path / "beside", tmp_path / "alone"
    beside.mkdir()
    alone.mkdir()
    for directory in (beside, alone):
        _write(directory, _run_of("inherited-context", "default-1", ("full", "lean")))
    _write(beside, _run_of(PAIRED, "paired-1", PAIRED_ARMS))

    default = results.earlier_runs(beside, (ROLE,), lambda earlier, role: ())
    absent = results.earlier_runs(alone, (ROLE,), lambda earlier, role: ())

    assert default == absent


def test_a_paired_file_is_a_run_not_a_stray_json_file(tmp_path):
    _write(tmp_path, _run_of(PAIRED, "paired-1", PAIRED_ARMS))

    listing = results.earlier_runs(tmp_path, (ROLE,), lambda earlier, role: ())

    assert listing.skipped_files == ()


def test_the_loop_lists_earlier_runs_of_the_runs_own_axis(tmp_path):
    _write(tmp_path, _run_of("inherited-context", "default-1", ("full", "lean")))
    _write(tmp_path, _run_of(PAIRED, "paired-1", PAIRED_ARMS))

    provisional = _provisional(tmp_path, *PAIRED_OPTIONS)

    listed = results.earlier_listed(provisional.run, ROLE)
    assert listed is not None
    # the fixture runs recorded no identity, so a run of the loop's axis is listed apart
    assert (listed.draws, set(listed.apart)) == ((), {"paired-1"})


# --- the proof carries the new axis's own observation to its own decision ---


def test_a_run_of_the_new_axis_proves_both_arms_through_prove(tmp_path, monkeypatch):
    seen = {
        "preloaded": arms.DeliveryObservation(0, 0, 1, 900),
        "delivered": arms.DeliveryObservation(1, 0, 0, 800),
    }
    served = iter(seen.values())

    def attempt(launch, ledger, task, build, populate, page_url, assess):
        return ledger, SimpleNamespace(result=next(served), model="m-1")

    monkeypatch.setattr(session_arms, "attempt", attempt)
    launch = _launch(tmp_path, PAIRED)
    launch = replace(
        launch, axis_run=replace(launch.axis_run, proof=_without_home(launch.axis_run.proof))
    )
    builds = {(arm, None): _build(tmp_path / arm, arm) for arm in PAIRED_ARMS}

    proof = session_arms.prove(
        launch,
        SpendLedger(cap_usd=10.0),
        ROLE,
        SimpleNamespace(),  # type: ignore[arg-type]
        builds,  # type: ignore[arg-type]
        tasks.generate(ROLE, SEED, 1)[0],
    )

    assert proof.verdicts == {
        "preloaded": arms.ArmProven("preloaded", 900, cross_checked=False),
        "delivered": arms.ArmProven("delivered", 800, cross_checked=False),
    }


def _without_home(proof: ArmProof) -> ArmProof:
    """The axis's proof with its home preparation left out: the home is no part of this reading."""
    return replace(proof, prepare=lambda original, template: "")
