"""The launch, the arm copies, the proof, the loop and the plan read the run's record.

Each test hands the code under test a record whose functions note that they were called, and shows
the call reached them and not the default axis's functions. The default record's behaviour is
pinned by the paid-loop and arm tests that run through it unedited.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from praxion_evals.adherence import cli, session_arms, session_launch, session_loop, tasks
from praxion_evals.adherence.axis_runs import DEFAULT_RUN, ArmProof, AxisRun
from praxion_evals.adherence.model import ArmBuild, Errored, NotBuilt, Role
from praxion_evals.adherence.session_launch import Launch
from praxion_evals.live.spend import SpendLedger
from tests.adherence_run_support import ROLE, Script, run_small, sessions_of

pytestmark = pytest.mark.usefixtures("unswitched_checkout")

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 7
STARTING_COMMIT = "starting-commit"
SETTLED = Errored("evaluation_exception", "the record's assessment")
Calls = list[tuple[str, tuple[Any, ...]]]


def _noting(calls: Calls, name: str, answer: Any):
    def noted(*args: Any) -> Any:
        calls.append((name, args))
        return answer

    return noted


def _record(calls: Calls) -> AxisRun:
    """A record whose every function notes its call and answers without doing the default's work."""
    return replace(
        DEFAULT_RUN,
        plan=_noting(calls, "plan", []),
        stage=_noting(calls, "stage", STARTING_COMMIT),
        build=_noting(calls, "build", NotBuilt("noted")),
        proof=ArmProof(
            prompt="the record's proof prompt",
            prepare=_noting(calls, "prepare", "the-nonce"),
            observe=_noting(calls, "observe", NotBuilt("nothing observed")),
            decide=_noting(calls, "decide", {}),
        ),
        assess=_noting(calls, "assess", SETTLED),
        catalog=_noting(calls, "catalog", ()),
    )


def _called(calls: Calls, name: str) -> list[tuple[Any, ...]]:
    return [args for noted, args in calls if noted == name]


def _launch(tmp_path: Path, **overrides: Any) -> Launch:
    fields: dict[str, Any] = {
        "run_root": tmp_path / "run",
        "checkout_commit": "abc",
        "page_url": "",
        "judge": None,
        "seed": SEED,
        "model": "m",
        "effort": "low",
        "session_budget_usd": 1.0,
        "keep_sandbox": True,
        "env_for": lambda root, path_first: {},
        "real_home": tmp_path / "home",
        "ambient": {"PATH": "/usr/bin"},
    }
    return Launch(**{**fields, **overrides})


def _task(role: Role = ROLE):
    return tasks.generate(role, SEED, 1)[0]


def _build(root: Path, role: Role = ROLE) -> ArmBuild:
    """A copy holding the role's definition, which is all the session's spec reads of it."""
    (root / "agents").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "agents" / f"{role}.md", root / "agents" / f"{role}.md")
    return ArmBuild(role, "full", root, None, "digest", ())


# --- the launch ---


def test_a_launch_carries_the_default_record_unless_given_another(tmp_path):
    assert _launch(tmp_path).axis_run is DEFAULT_RUN


def test_the_loop_launches_with_the_record_of_the_runs_axis(tmp_path):
    config = replace(cli.parse_config(["--role", ROLE]), axis="refactoring-delivery", arms=())
    context = SimpleNamespace(
        config=config,
        checkout=SimpleNamespace(commit="abc"),
        run_root=tmp_path,
        page_url="",
        judge=None,
    )

    launched = session_loop._launch_of(context)  # type: ignore[arg-type]

    assert launched.axis_run.axis == "refactoring-delivery"
    assert launched.axis_run == session_loop.axis_run("refactoring-delivery")


def test_a_session_is_staged_by_the_records_stage_in_its_scratch_directory(tmp_path):
    calls: Calls = []

    def stage(task, dest, url):
        calls.append(("stage", (task, dest, url)))
        dest.mkdir(parents=True)
        return STARTING_COMMIT

    record = replace(_record(calls), stage=stage)
    task, sandbox = _task(), tmp_path / "sandbox"

    _, commit, _ = session_launch._prepare(
        _launch(tmp_path, axis_run=record),
        task,
        _build(tmp_path / "copy"),
        lambda root: None,
        "http://page",
        sandbox,
    )

    assert commit == STARTING_COMMIT
    assert _called(calls, "stage") == [
        (task, tasks.scratch_dir(session_launch.SandboxPaths(sandbox)), "http://page")
    ]


def test_a_session_is_assessed_by_the_records_assess(tmp_path, monkeypatch):
    calls: Calls = []
    judge = object()
    seen: dict[str, Any] = {}

    def attempt(launch, ledger, task, build, populate, page_url, assess):
        seen["assessed"] = assess("the-evidence")
        return ledger, SimpleNamespace(
            result=seen["assessed"], charged_usd=0.0, duration_ms=0, started_at="t",
            refused_commands=(), model=None,
        )  # fmt: skip

    monkeypatch.setattr(session_launch, "attempt", attempt)
    launch = _launch(tmp_path, axis_run=_record(calls), judge=judge)
    task = _task()

    session_launch.task_session(
        launch, SpendLedger(cap_usd=10.0), task, "full", _build(tmp_path / "copy"), None
    )

    assert seen["assessed"] is SETTLED
    [(evidence, assessed_task, setup, passed_judge, real_home)] = _called(calls, "assess")
    assert (evidence, assessed_task, passed_judge, real_home) == (
        "the-evidence",
        task,
        judge,
        tmp_path / "home",
    )
    assert (setup.arm, setup.task_id) == ("full", task.task_id)


# --- the arm copies and the proof ---


def test_a_copy_is_built_by_the_records_build(tmp_path):
    calls: Calls = []
    original = SimpleNamespace(name="the-original")

    built = session_arms.build_copy(
        tmp_path / ROLE,
        original,
        ROLE,
        "lean",
        3,
        _record(calls),  # type: ignore[arg-type]
    )

    assert built == NotBuilt("noted")
    assert _called(calls, "build") == [(original, tmp_path / ROLE / "lean-cap3", ROLE, "lean", 3)]


def test_the_proof_runs_the_records_prompt_preparation_observer_and_decision(tmp_path, monkeypatch):
    calls: Calls = []
    sessions: list[Any] = []

    def attempt(launch, ledger, task, build, populate, page_url, assess):
        sessions.append(task.main_prompt)
        observed = assess("the-evidence")
        return ledger, SimpleNamespace(result=observed, model="m-1")

    monkeypatch.setattr(session_arms, "attempt", attempt)
    launch = _launch(tmp_path, axis_run=_record(calls))
    original = SimpleNamespace(name="the-original")
    builds = {("full", None): _build(tmp_path / "copy")}

    proof = session_arms.prove(
        launch,
        SpendLedger(cap_usd=10.0),
        ROLE,
        original,
        builds,
        _task(),  # type: ignore[arg-type]
    )

    assert _called(calls, "prepare") == [(original, tmp_path / "run" / ROLE / "proof-home")]
    assert sessions == ["the record's proof prompt"]
    assert _called(calls, "observe") == [("the-evidence", session_launch.REAL_HOME)]
    assert _called(calls, "decide") == [("the-nonce", {})]
    assert proof.models == ("m-1",)
    assert isinstance(proof.verdicts["full"], NotBuilt)


# --- the loop and the plan ---


def test_a_run_reaches_every_function_of_the_record(tmp_path, monkeypatch, paid, full_first):
    calls: Calls = []

    def noting_default(name: str, function):
        def noted(*args: Any) -> Any:
            calls.append((name, args))
            return function(*args)

        return noted

    record = replace(
        DEFAULT_RUN,
        plan=noting_default("plan", DEFAULT_RUN.plan),
        stage=noting_default("stage", DEFAULT_RUN.stage),
        build=noting_default("build", DEFAULT_RUN.build),
        proof=ArmProof(
            DEFAULT_RUN.proof.prompt,
            noting_default("prepare", DEFAULT_RUN.proof.prepare),
            noting_default("observe", DEFAULT_RUN.proof.observe),
            noting_default("decide", DEFAULT_RUN.proof.decide),
        ),
        assess=noting_default("assess", DEFAULT_RUN.assess),
        catalog=noting_default("catalog", DEFAULT_RUN.catalog),
    )
    monkeypatch.setattr(cli, "axis_run", lambda axis: record)
    monkeypatch.setattr(session_loop, "axis_run", lambda axis: record)
    paid(Script())

    code, loaded = run_small(tmp_path)

    assert code == 0
    assert sessions_of(loaded) == [("full", "Measured"), ("lean", "Measured")]
    reached = {name for name, _ in calls}
    assert reached == {
        "plan",
        "stage",
        "build",
        "prepare",
        "observe",
        "decide",
        "assess",
        "catalog",
    }


def test_the_plan_is_made_by_the_records_plan(monkeypatch):
    calls: Calls = []
    monkeypatch.setattr(cli, "axis_run", lambda axis: _record(calls))
    config = cli.parse_config(["--role", ROLE, "--required-pairs", "2", "--pair-slack", "1"])

    planned = cli.plan_tasks(config)

    assert planned == {ROLE: []}
    assert _called(calls, "plan") == [
        (ROLE, config.seed, config.required_pairs + config.pair_slack)
    ]
