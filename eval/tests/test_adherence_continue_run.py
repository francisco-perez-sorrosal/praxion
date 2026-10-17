"""Continuing a stopped run over a scripted `claude`: the later part declares what the run
declared, launches again only the tasks no part finished (whole, in both arms, in the planned
order, each with its own retry), records the harness version it ran under and names the run it
continues, while a run that did not stop continuably, or an option that changes a declaration,
is refused before anything launches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

import tests.test_adherence_cli as cli_tests
from praxion_evals.adherence import cli, results, session_loop
from praxion_evals.adherence.arms import PROOF_LABEL
from praxion_evals.adherence.infra_stop import EvidenceTail, Launched, StopReason
from praxion_evals.adherence.lineage import (
    Finished,
    InfraStopped,
    RunEnding,
    SpendRefused,
    ending_of,
    ending_to_json,
)
from praxion_evals.adherence.model import Errored, Measured, SessionRecord
from praxion_evals.live.session import SessionSpec

# The fixtures that stand a scripted `claude` in for the paid sessions and keep the live checkout's
# role unswitched, shared with the paid-loop tests of the command line.
paid = cli_tests.paid
full_first = cli_tests.full_first  # every task launches full first, as the shapes below read
unswitched_checkout = cli_tests.unswitched_checkout
Script = cli_tests.Script
ROLE = cli_tests.ROLE

pytestmark = pytest.mark.usefixtures("full_first")

EIGHT_TASKS = ["--required-pairs", "8"]  # with the small run's zero slack: eight planned tasks
STOPPING_KIND, STOPPING_TAIL = "exit_nonzero", "fatal: the session channel closed unexpectedly"
STOPPED = "stopped.json"
# The planned position of each task shape, as the planner reads them.
(COMPLETE, LEAN_BEFORE_STREAK, LEAN_ONLY, FULL_ONLY) = (0, 1, 2, 3)
(LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED) = (4, 5, 6, 7)
LAUNCHED_AGAIN = (LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED)


# ---------------------------------------------------------------------------
# A stopped run in eight shapes, and its continuation
# ---------------------------------------------------------------------------


def _failed(record: SessionRecord, kind: str = STOPPING_KIND, tail: str = STOPPING_TAIL):
    status = Errored(kind, "the session failed", tails=EvidenceTail(tail, ""))  # type: ignore[arg-type]
    return replace(record, status=status)


def _shaped(ran: dict[tuple[int, str], SessionRecord]) -> list[SessionRecord]:
    """The eight task shapes in planned order; ``ran`` is each (position, arm)'s measured record."""
    return [
        ran[(COMPLETE, "full")],
        ran[(COMPLETE, "lean")],
        ran[(LEAN_BEFORE_STREAK, "full")],
        *[_failed(ran[(LEAN_BEFORE_STREAK, "lean")])] * 2,
        ran[(LEAN_ONLY, "full")],
        *[_failed(ran[(LEAN_ONLY, "lean")], "no_result_event", "")] * 2,
        *[_failed(ran[(FULL_ONLY, "full")], "envelope_unparseable", "")] * 2,
        ran[(FULL_ONLY, "lean")],
        _failed(ran[(REFUSED, "full")], "launch_refused", ""),
        _failed(ran[(REFUSED, "lean")], "launch_refused", ""),
        ran[(LEAN_IN_STREAK, "full")],
        *[_failed(ran[(LEAN_IN_STREAK, "lean")])] * 2,
        *[_failed(ran[(BOTH_IN_STREAK, "full")])] * 2,
        _failed(ran[(BOTH_IN_STREAK, "lean")]),
    ]


def _rewritten(tmp_path: Path, run: results.RunResults, ending: RunEnding, sessions=None):
    extra = {**run.run.extra, "ending": ending_to_json(ending)}
    rewritten = replace(run, run=replace(run.run, extra=extra), sessions=sessions or run.sessions)
    results.write_atomic(tmp_path / STOPPED, rewritten)
    return rewritten


def _stopped_in_eight_shapes(tmp_path: Path) -> results.RunResults:
    """A run of eight tasks that stopped on three lean failures in a row, seen in both arms."""
    run = cli_tests._run(tmp_path, *EIGHT_TASKS, name=STOPPED)[1]
    planned = run.run.extra["tasks"][ROLE]
    ran = {(planned.index(r.setup.task_id), r.setup.arm): r for r in run.sessions}
    streak = [(LEAN_IN_STREAK, 1), (LEAN_IN_STREAK, 2), (BOTH_IN_STREAK, 1)]
    stop = StopReason(
        STOPPING_KIND,
        EvidenceTail(STOPPING_TAIL, "").masked(),
        ROLE,
        "lean",
        tuple(Launched(planned[at], "lean", attempt) for at, attempt in streak),
        "both-arms",
    )
    return _rewritten(tmp_path, run, InfraStopped(stop), _shaped(ran))


def _continue(tmp_path: Path, run_id: str, *options: str, name: str = "part.json") -> int:
    where = ["--output", str(tmp_path / name)]  # its directory is where the stopped run is
    return cli.main([str(cli_tests.REPO_ROOT), "--continue", run_id, *where, *options])


def _task_sessions(script: Script) -> list[SessionSpec]:
    """The task sessions the script launched since it was installed; the arm proofs are not."""
    return [spec for spec in script.specs if PROOF_LABEL not in spec.prompt]


@pytest.fixture
def stopped(paid: Callable[[Script], None], tmp_path: Path) -> results.RunResults:
    paid(Script())
    return _stopped_in_eight_shapes(tmp_path)


def _planned(run: results.RunResults, *positions: int) -> list[str]:
    planned = run.run.extra["tasks"][ROLE]
    return [planned[at] for at in positions]


def _relaunched(part: results.RunResults) -> list[tuple[str, str]]:
    return [(r.setup.task_id, r.setup.arm) for r in part.sessions]


# ---------------------------------------------------------------------------
# What a continuation launches
# ---------------------------------------------------------------------------


def test_a_continuation_launches_again_exactly_the_tasks_no_part_finished_in_both_arms(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())

    code = _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert code == 0
    assert {task for task, _ in _relaunched(part)} == set(_planned(stopped, *LAUNCHED_AGAIN))
    assert len(_relaunched(part)) == 2 * len(LAUNCHED_AGAIN)


def test_the_tasks_launched_again_run_in_their_planned_and_seeded_order(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())

    _continue(tmp_path, stopped.run.id)

    expected = [
        (task, arm) for task in _planned(stopped, *LAUNCHED_AGAIN) for arm in ("full", "lean")
    ]
    assert _relaunched(results.load(tmp_path / "part.json")) == expected


def test_lean_failures_recorded_before_the_stop_stand_in_the_stopped_part(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())
    recorded = (tmp_path / STOPPED).read_text(encoding="utf-8")

    _continue(tmp_path, stopped.run.id)

    kept = set(_planned(stopped, LEAN_BEFORE_STREAK, LEAN_ONLY))
    part = results.load(tmp_path / "part.json")
    assert not kept & {task for task, _ in _relaunched(part)}
    assert (tmp_path / STOPPED).read_text(encoding="utf-8") == recorded, "the stop is rewritten"


def test_a_relaunched_session_has_its_own_retry_whatever_the_stopped_run_retried(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    proofs = 2  # one per arm, launched before any task
    paid(Script(fail_launch=lambda number: number == proofs + 1))

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    first = _planned(stopped, LEAN_IN_STREAK)[0]
    statuses = [
        type(r.status) for r in part.sessions if (r.setup.task_id, r.setup.arm) == (first, "full")
    ]
    assert statuses == [Errored, Measured]
    assert part.run.extra["retries"] == [
        {"role": ROLE, "arm": "full", "task_id": first, "after": "exit_nonzero"}
    ]


def test_a_continuation_of_a_continuation_launches_only_what_neither_part_finished(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script(cost=None))  # each session is charged its whole budget: room for two proofs, a pair
    _continue(tmp_path, stopped.run.id, "--session-budget-usd", "1", "--max-total-usd", "4")
    second = results.load(tmp_path / "part.json")
    paid(Script())

    _continue(tmp_path, second.run.id, name="third.json")

    third = results.load(tmp_path / "third.json")
    assert isinstance(ending_of(second), SpendRefused)
    assert {task for task, _ in _relaunched(third)} == set(
        _planned(stopped, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED)
    )
    assert [part["run_id"] for part in third.run.extra["lineage"]] == [
        stopped.run.id,
        second.run.id,
        third.run.id,
    ]


# ---------------------------------------------------------------------------
# What the later part records
# ---------------------------------------------------------------------------


def test_the_later_part_names_the_run_it_continues_and_declares_what_it_declared(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    paid(Script())

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert part.run.extra["continues"] == stopped.run.id
    assert part.run.extra["lineage"] == [
        {
            "run_id": stopped.run.id,
            "stop": f"3 lean sessions in a row ended in {STOPPING_KIND} with the same evidence",
        },
        {"run_id": part.run.id, "stop": None},
    ]
    assert part.settings == stopped.settings
    assert part.run.extra["tasks"] == stopped.run.extra["tasks"], "the whole plan, not the relaunch"
    assert ending_of(part) == Finished()
    assert {arm: part.arms[ROLE][arm]["built"] for arm in ("full", "lean")} == {
        "full": True,
        "lean": True,
    }, "each part builds and proves its own arms"


def test_the_later_part_records_the_harness_version_it_ran_under(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_loop, "query_claude_version", lambda: "9.9.10-later")

    _continue(tmp_path, stopped.run.id)

    part = results.load(tmp_path / "part.json")
    assert (stopped.run.claude_code_version, part.run.claude_code_version) == (
        "9.9.9-test",
        "9.9.10-later",
    )


# ---------------------------------------------------------------------------
# Refused before anything launches
# ---------------------------------------------------------------------------


def test_a_continuation_of_a_run_that_finished_its_plan_is_refused_before_any_launch(
    paid: Callable[[Script], None], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    paid(Script())
    run = cli_tests._run(tmp_path, name=STOPPED)[1]
    finished = _rewritten(tmp_path, run, Finished())
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, finished.run.id)

    assert code == 2
    assert f"run {finished.run.id} finished its plan" in capsys.readouterr().err
    assert script.specs == []
    assert not (tmp_path / "part.json").exists()


@pytest.mark.parametrize(
    ("options", "named"),
    [
        (["--margin-pp", "5"], "--margin-pp"),
        (["--seed", "8"], "--seed"),
        (["--max-tasks", "2"], "--max-tasks"),
    ],
    ids=["margin", "seed", "task cap"],
)
def test_an_option_that_changes_a_declaration_is_refused_naming_it(
    paid: Callable[[Script], None],
    stopped: results.RunResults,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    options: list[str],
    named: str,
) -> None:
    script = Script()
    paid(script)
    capsys.readouterr()

    code = _continue(tmp_path, stopped.run.id, *options)

    assert code == 2
    assert named in capsys.readouterr().err
    assert script.specs == []


def test_options_that_restate_the_declarations_are_accepted(
    paid: Callable[[Script], None], stopped: results.RunResults, tmp_path: Path
) -> None:
    script = Script()
    paid(script)
    restated = ["--role", ROLE, "--no-judge", "--max-tasks", "8", "--seed", "7"]

    code = _continue(tmp_path, stopped.run.id, *restated, "--session-budget-usd", "2")

    assert code == 0
    assert _task_sessions(script), "the continuation launched its tasks"
