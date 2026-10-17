"""How a run ended: the ending's wire form round-trips, only a both-arms stop or a spend refusal
is continuable, a file without an ending is legacy, and the runner records the ending it had.
A run's lineage is parsed from its results directory, a continuation relaunches only the tasks
nobody finished, and is refused with every reason, while a stopped run left neither continued nor
closed is found by its role and closing one records why. What a run was measured on is tested in
`test_adherence_run_identity.py`."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import tests.test_adherence_cli as cli_tests
from praxion_evals.adherence import report, results
from praxion_evals.adherence.infra_stop import EvidenceTail, Launched, StopReason
from praxion_evals.adherence.lineage import (
    CONTINUATION_OPTIONS,
    Closed,
    Finished,
    InfraStopped,
    Interrupted,
    Legacy,
    Lineage,
    PartRef,
    ReadTip,
    RunEnding,
    SpendRefused,
    UnreadableTip,
    close,
    continuable,
    continuation_refusals,
    ending_from_json,
    ending_of,
    ending_to_json,
    never_launched,
    pending_stop,
    relaunch_tasks,
)
from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.run_identity import MeasuredIdentity
from praxion_evals.live.session import SessionRun, SessionSpec
from tests.test_adherence_report import results_of
from tests.test_adherence_results import declared, pair_of_sessions, run_results, session

# The fixtures that stand a scripted `claude` in for the paid sessions and keep the live checkout's
# role unswitched, shared with the paid-loop tests of the command line.
paid = cli_tests.paid
full_first = cli_tests.full_first  # every task launches full first, as these runs end mid-task
unswitched_checkout = cli_tests.unswitched_checkout

pytestmark = pytest.mark.usefixtures("full_first")

CREDIT_TAIL = "\nCredit balance is too low"


def _stop(scope: str = "both-arms") -> InfraStopped:
    sessions = tuple(Launched(f"task-{n}", "lean", 1) for n in range(3))
    reason = StopReason("result_error", CREDIT_TAIL, "researcher", "lean", sessions, scope)  # type: ignore[arg-type]
    return InfraStopped(reason)


def _closed(stopped: Any = None) -> Closed:
    return Closed("no credit left", "2026-10-17T09:00:00Z", {"C1": "clear"}, stopped or _stop())


ROUND_TRIPPING: dict[str, RunEnding] = {
    "finished": Finished(),
    "infrastructure stop": _stop(),
    "one-arm infrastructure stop": _stop("one-arm"),
    "spend refusal": SpendRefused(("task-001", "task-002")),
    "interrupt": Interrupted(),
    "closed run": _closed(),
}


@pytest.mark.parametrize("ending", ROUND_TRIPPING.values(), ids=ROUND_TRIPPING.keys())
def test_every_ending_survives_its_wire_form(ending: RunEnding) -> None:
    assert ending_from_json(ending_to_json(ending)) == ending


def test_an_infrastructure_stop_is_written_with_the_pinned_field_names() -> None:
    assert ending_to_json(_stop()) == {
        "kind": "infra_stopped",
        "error_kind": "result_error",
        "masked_tail": CREDIT_TAIL,
        "role": "researcher",
        "arm": "lean",
        "sessions": [{"task_id": f"task-{n}", "arm": "lean", "attempt": 1} for n in range(3)],
        "scope": "both-arms",
    }


def test_a_closed_ending_keeps_the_stop_it_closed() -> None:
    wire = ending_to_json(_closed(SpendRefused(("task-001",))))

    assert wire["stopped"] == {"kind": "spend_refused", "tasks": ["task-001"]}


def test_a_spend_refusal_written_without_tasks_reads_as_naming_none() -> None:
    assert ending_from_json({"kind": "spend_refused"}) == SpendRefused()


@pytest.mark.parametrize(
    ("ending", "expected"),
    [
        (_stop("both-arms"), True),
        (SpendRefused(), True),
        (_stop("one-arm"), False),
        (Finished(), False),
        (Interrupted(), False),
        (_closed(), False),
        (Legacy(), False),
    ],
    ids=[
        "both-arms stop",
        "spend refusal",
        "one-arm stop",
        "finished",
        "interrupt",
        "closed",
        "legacy",
    ],
)
def test_only_a_both_arms_stop_or_a_spend_refusal_can_be_continued(
    ending: RunEnding, expected: bool
) -> None:
    assert continuable(ending) is expected


def test_a_file_with_no_ending_is_legacy_and_legacy_has_no_wire_form() -> None:
    legacy = results_of([])

    assert ending_of(legacy) == Legacy()
    with pytest.raises(ValueError, match="never written"):
        ending_to_json(Legacy())


def test_the_ending_is_read_from_the_run_record() -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(_stop())})

    assert ending_of(replace(loaded, run=recorded)) == _stop()


@pytest.mark.parametrize(
    ("wire", "complaint"),
    [
        ({"kind": "exploded"}, "unknown run ending"),
        ({}, "lacks 'kind'"),
        ({**ending_to_json(_stop()), "arm": "middle"}, "unknown arm"),
        ({**ending_to_json(_stop()), "scope": "some-arms"}, "unknown scope"),
        ({"kind": "infra_stopped"}, "lacks 'error_kind'"),
        ({**ending_to_json(_closed()), "stopped": {"kind": "finished"}}, "closes a stopped run"),
    ],
    ids=[
        "unknown kind",
        "no kind",
        "unknown arm",
        "unknown scope",
        "missing field",
        "closed finish",
    ],
)
def test_a_malformed_ending_is_refused_with_what_was_wrong(
    wire: dict[str, Any], complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        ending_from_json(wire)


def test_a_run_cannot_be_closed_without_a_reason() -> None:
    with pytest.raises(ValueError, match="needs a reason"):
        Closed("  ", "2026-10-17T09:00:00Z", {}, Interrupted())


# ---------------------------------------------------------------------------
# What the runner records
# ---------------------------------------------------------------------------


class Interrupts(cli_tests.Script):
    """Answers like the stand-in until its Nth launch, where the operator presses Ctrl-C."""

    def __init__(self, at_launch: int) -> None:
        super().__init__()
        self.at_launch = at_launch

    def __call__(self, spec: SessionSpec, env: dict[str, str]) -> SessionRun:
        run = super().__call__(spec, env)
        if len(self.specs) == self.at_launch:
            raise KeyboardInterrupt
        return run


def test_a_run_that_reaches_the_end_of_its_plan_records_that_it_finished(
    paid: Any, tmp_path: Path
) -> None:
    paid(cli_tests.Script())

    code, loaded = cli_tests._run(tmp_path)

    assert (code, ending_of(loaded)) == (0, Finished())


def test_a_launch_refused_by_the_spend_cap_is_recorded_as_a_continuable_spend_refusal(
    paid: Any, tmp_path: Path
) -> None:
    paid(cli_tests.Script(cost=None))

    code, loaded = cli_tests._run(tmp_path, "--max-total-usd", "2")

    ending = ending_of(loaded)
    assert (code, loaded.run.complete) == (1, False)
    assert ending == SpendRefused((loaded.sessions[0].setup.task_id,))
    assert continuable(ending)


def test_an_interrupt_still_writes_the_file_with_every_session_that_had_ended(
    paid: Any, tmp_path: Path
) -> None:
    paid(Interrupts(at_launch=4))  # the proofs, then the full arm's session, then Ctrl-C

    code, loaded = cli_tests._run(tmp_path)

    assert (code, loaded.run.complete) == (1, False)
    assert ending_of(loaded) == Interrupted()
    assert [(r.setup.arm, type(r.status).__name__) for r in loaded.sessions] == [
        ("full", "Measured")
    ]
    assert not continuable(ending_of(loaded))


def test_an_interrupt_keeps_the_spend_the_run_had_settled(paid: Any, tmp_path: Path) -> None:
    paid(Interrupts(at_launch=4))

    loaded = cli_tests._run(tmp_path)[1]

    assert loaded.run.extra["spend"]["spent_usd"] == pytest.approx(3 * 0.01)


# ---------------------------------------------------------------------------
# What the report says
# ---------------------------------------------------------------------------


def _rendered(ending: RunEnding | None) -> str:
    loaded = results_of([])
    extra = {} if ending is None else {"ending": ending_to_json(ending)}
    return report.render(replace(loaded, run=replace(loaded.run, extra=extra)))


@pytest.mark.parametrize("ending", [Finished(), None], ids=["finished", "recorded before endings"])
def test_a_run_that_finished_or_predates_endings_renders_without_an_ending_line(
    ending: RunEnding | None,
) -> None:
    assert _rendered(ending) == _rendered(None)
    assert "stopped" not in _rendered(ending).split("Declared at")[0]


def test_an_infrastructure_stop_is_reported_with_its_count_kind_evidence_and_continuability() -> (
    None
):
    assert (
        "The run stopped itself: 3 lean sessions in a row ended in result_error with the same"
        " evidence Credit balance is too low; continuable."
    ) in _rendered(_stop())


def test_a_one_arm_stop_is_reported_as_not_continuable() -> None:
    assert "; not continuable." in _rendered(_stop("one-arm"))


def test_an_interrupt_and_a_closed_run_are_reported_on_their_own_line() -> None:
    assert "The operator interrupted the run; not continuable." in _rendered(Interrupted())
    assert (
        "The run was closed on 2026-10-17T09:00:00Z without being continued: no credit left."
        in (_rendered(_closed()))
    )


def test_a_spend_refusal_is_reported_with_the_tasks_it_refused() -> None:
    assert "The spend cap refused launches (tasks task-001); continuable." in _rendered(
        SpendRefused(("task-001",))
    )


def test_the_results_loader_keeps_the_ending_it_was_given(tmp_path: Path) -> None:
    loaded = results_of([])
    recorded = replace(loaded.run, extra={"ending": ending_to_json(Interrupted())})
    path = tmp_path / "out.json"
    results.write_atomic(path, replace(loaded, run=recorded))

    assert ending_of(results.load(path)) == Interrupted()


# ---------------------------------------------------------------------------
# A run's lineage: the parts of one declared run
# ---------------------------------------------------------------------------


def _write_part(
    directory: Path, run_id: str, continues: str | None = None, ending: RunEnding | None = None
) -> None:
    extra: dict[str, Any] = {} if continues is None else {"continues": continues}
    if ending is not None:
        extra["ending"] = ending_to_json(ending)
    results.write_atomic(directory / f"{run_id}.json", run_results([], run_id=run_id, extra=extra))


def _ids(chain: Lineage) -> list[str]:
    return [part.run_id for part in chain.parts]


def test_a_run_nothing_continues_is_a_lineage_of_one_part(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")

    chain = Lineage.parse(tmp_path, "run-a")

    assert (_ids(chain), chain.tip.run_id) == (["run-a"], "run-a")


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_any_part_names_the_whole_lineage_oldest_first(tmp_path: Path, named: str) -> None:
    _write_part(tmp_path, "run-c", continues="run-b")
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    assert _ids(Lineage.parse(tmp_path, named)) == ["run-a", "run-b", "run-c"]


def test_only_the_latest_part_is_the_tip(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    assert Lineage.parse(tmp_path, "run-a").tip.run_id == "run-b"


def test_a_part_remembers_its_file_and_the_run_it_continues(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")

    first, second = Lineage.parse(tmp_path, "run-b").parts

    assert (first, second) == (
        PartRef("run-a", tmp_path / "run-a.json", None),
        PartRef("run-b", tmp_path / "run-b.json", "run-a"),
    )


def test_runs_that_are_not_in_the_lineage_are_left_out(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")
    _write_part(tmp_path, "run-elsewhere")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a", "run-b"]


def test_a_json_file_that_is_not_a_results_file_does_not_break_a_lineage(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    (tmp_path / "stray.json").write_text("[1, 2]", encoding="utf-8")

    assert _ids(Lineage.parse(tmp_path, "run-a")) == ["run-a"]


@pytest.mark.parametrize("named", ["run-a", "run-b", "run-c"])
def test_a_lineage_where_two_parts_continue_one_is_refused_whichever_part_is_named(
    tmp_path: Path, named: str
) -> None:
    _write_part(tmp_path, "run-a")
    _write_part(tmp_path, "run-b", continues="run-a")
    _write_part(tmp_path, "run-c", continues="run-a")

    with pytest.raises(ValueError, match=r"forks: run-b, run-c all continue run-a"):
        Lineage.parse(tmp_path, named)


def test_a_part_continuing_a_run_no_file_holds_is_a_gap(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-b", continues="run-lost")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-lost"):
        Lineage.parse(tmp_path, "run-b")


def test_a_predecessor_that_cannot_be_read_is_a_gap(tmp_path: Path) -> None:
    (tmp_path / "run-a.json").write_text("{not json", encoding="utf-8")
    _write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"gap: run run-b continues run-a"):
        Lineage.parse(tmp_path, "run-b")


def test_parts_that_continue_each_other_are_refused_as_a_loop(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a", continues="run-b")
    _write_part(tmp_path, "run-b", continues="run-a")

    with pytest.raises(ValueError, match=r"loops"):
        Lineage.parse(tmp_path, "run-a")


def test_a_run_no_file_holds_has_no_lineage(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")

    with pytest.raises(ValueError, match=r"holds run run-missing"):
        Lineage.parse(tmp_path, "run-missing")


def test_two_files_holding_one_run_are_refused(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a")
    (tmp_path / "copy.json").write_text((tmp_path / "run-a.json").read_text(), encoding="utf-8")

    with pytest.raises(ValueError, match=r"copy.json and run-a.json both hold run run-a"):
        Lineage.parse(tmp_path, "run-a")


def test_a_lineage_has_a_part() -> None:
    with pytest.raises(ValueError, match=r"at least one part"):
        Lineage(())


def test_a_lineage_built_out_of_order_is_refused() -> None:
    first = PartRef("run-a", Path("run-a.json"), None)
    second = PartRef("run-b", Path("run-b.json"), "run-a")

    with pytest.raises(ValueError, match=r"run run-b continues 'run-a', not its predecessor None"):
        Lineage((second, first))


# ---------------------------------------------------------------------------
# What a continuation launches again
# ---------------------------------------------------------------------------

STOPPING_TAIL = "fatal: the session channel closed unexpectedly"
STOPPING_KIND = "exit_nonzero"
COMPLETE_PAIR, LEAN_BEFORE_STREAK, LEAN_ONLY, FULL_ONLY = "task-1", "task-2", "task-3", "task-4"
LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NOT_REACHED = "task-5", "task-6", "task-7", "task-8"
PLANNED = (
    COMPLETE_PAIR,
    LEAN_BEFORE_STREAK,
    LEAN_ONLY,
    FULL_ONLY,
    LEAN_IN_STREAK,
    BOTH_IN_STREAK,
    REFUSED,
    NOT_REACHED,
)
EIGHT_SHAPES = {
    "a complete pair": COMPLETE_PAIR,
    "a lean session of the stopping kind and tail before the streak": LEAN_BEFORE_STREAK,
    "a lean-only error of another kind": LEAN_ONLY,
    "a full-only error of another kind": FULL_ONLY,
    "a full session complete and its lean session inside the streak": LEAN_IN_STREAK,
    "both sessions inside the streak": BOTH_IN_STREAK,
    "a launch the spend cap refused": REFUSED,
    "a task never launched": NOT_REACHED,
}
LAUNCHED_AGAIN = {LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NOT_REACHED}


def failed(task: str, arm: str, kind: str = STOPPING_KIND, tail: str = STOPPING_TAIL):
    status = Errored(kind, "the session failed", tails=EvidenceTail(tail, ""))  # type: ignore[arg-type]
    return session(task, arm, status)


def stopped_at(*streak: tuple[str, int], arm: str = "lean", tail: str = STOPPING_TAIL):
    sessions = tuple(Launched(task, arm, attempt) for task, attempt in streak)  # type: ignore[arg-type]
    masked = EvidenceTail(tail, "").masked()
    return InfraStopped(
        StopReason(STOPPING_KIND, masked, "researcher", arm, sessions, "both-arms")  # type: ignore[arg-type]
    )


def stopped_run(sessions, ending: RunEnding, planned=PLANNED) -> results.RunResults:
    extra = {"tasks": {"researcher": list(planned)}, "ending": ending_to_json(ending)}
    return run_results(sessions, extra=extra)


def eight_shapes_run() -> results.RunResults:
    """The streak is the last three lean sessions: the lean retry pair of one task, then one
    more; the full arm of the last streak task failed the same way inside the window."""
    sessions = [
        *pair_of_sessions(COMPLETE_PAIR),
        session(LEAN_BEFORE_STREAK, "full"),
        *[failed(LEAN_BEFORE_STREAK, "lean")] * 2,
        session(LEAN_ONLY, "full"),
        *[failed(LEAN_ONLY, "lean", "no_result_event", "")] * 2,
        *[failed(FULL_ONLY, "full", "envelope_unparseable", "")] * 2,
        session(FULL_ONLY, "lean"),
        failed(REFUSED, "full", "launch_refused", ""),
        failed(REFUSED, "lean", "launch_refused", ""),
        session(LEAN_IN_STREAK, "full"),
        *[failed(LEAN_IN_STREAK, "lean")] * 2,
        *[failed(BOTH_IN_STREAK, "full")] * 2,
        failed(BOTH_IN_STREAK, "lean"),
    ]
    streak = ((LEAN_IN_STREAK, 1), (LEAN_IN_STREAK, 2), (BOTH_IN_STREAK, 1))
    return stopped_run(sessions, stopped_at(*streak))


@pytest.mark.parametrize("task", EIGHT_SHAPES.values(), ids=EIGHT_SHAPES.keys())
def test_a_task_is_launched_again_only_when_nothing_finished_it(task: str) -> None:
    relaunched = relaunch_tasks(eight_shapes_run(), "researcher")

    assert (task in relaunched) == (task in LAUNCHED_AGAIN)


def test_the_tasks_launched_again_keep_the_order_the_run_planned_them_in() -> None:
    assert relaunch_tasks(eight_shapes_run(), "researcher") == (
        LEAN_IN_STREAK,
        BOTH_IN_STREAK,
        REFUSED,
        NOT_REACHED,
    )


def test_the_sessions_never_launched_are_the_refused_ones_and_those_in_the_streak() -> None:
    run = eight_shapes_run()

    ignored = [
        (r.setup.task_id, r.setup.arm)
        for i, r in enumerate(run.sessions)
        if i in never_launched(run)
    ]

    assert ignored == [
        (REFUSED, "full"),
        (REFUSED, "lean"),
        (LEAN_IN_STREAK, "lean"),
        (LEAN_IN_STREAK, "lean"),
        (BOTH_IN_STREAK, "full"),
        (BOTH_IN_STREAK, "full"),
        (BOTH_IN_STREAK, "lean"),
    ]


def test_a_full_session_of_the_stopping_kind_and_tail_before_the_streak_keeps_its_outcome() -> None:
    sessions = [
        *[failed("early", "full")] * 2,
        session("early", "lean"),
        session("late", "full"),
        *[failed("late", "lean")] * 3,
    ]
    streak = (("late", 1), ("late", 2), ("late", 3))
    run = stopped_run(sessions, stopped_at(*streak), ("early", "late"))

    assert relaunch_tasks(run, "researcher") == ("late",)


def test_a_full_session_of_another_tail_inside_the_streaks_window_keeps_its_outcome() -> None:
    other = "fatal: another channel failed"
    sessions = [
        session("b", "lean"),
        session("a", "full"),
        failed("a", "lean"),
        *[failed("b", "full", tail=other)] * 2,
        session("c", "full"),
        *[failed("c", "lean")] * 2,
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), ("c", 2)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "c")


def test_a_full_session_of_another_kind_inside_the_streaks_window_keeps_its_outcome() -> None:
    sessions = [
        session("b", "lean"),
        session("a", "full"),
        failed("a", "lean"),
        *[failed("b", "full", "no_result_event", STOPPING_TAIL)] * 2,
        session("c", "full"),
        *[failed("c", "lean")] * 2,
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), ("c", 2)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "c")


def test_a_lean_session_that_retried_into_a_measured_one_with_a_full_session_is_a_pair() -> None:
    sessions = [
        session("a", "full"),
        failed("a", "lean", "no_result_event", ""),
        session("a", "lean"),
    ]
    run = stopped_run(sessions, Interrupted(), ("a",))

    assert relaunch_tasks(run, "researcher") == ()


def test_an_interrupted_run_launches_again_the_tasks_it_never_finished() -> None:
    sessions = [*pair_of_sessions("a"), session("b", "full")]
    run = stopped_run(sessions, Interrupted(), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("b", "c")


def test_a_spend_refusal_launches_again_the_refused_tasks_and_the_unreached_ones() -> None:
    sessions = [
        *pair_of_sessions("a"),
        failed("b", "full", "launch_refused", ""),
        failed("b", "lean", "launch_refused", ""),
    ]
    run = stopped_run(sessions, SpendRefused(("b",)), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("b", "c")


def test_a_run_that_recorded_no_session_launches_every_planned_task() -> None:
    assert relaunch_tasks(stopped_run([], Interrupted(), ("a", "b")), "researcher") == ("a", "b")


def test_a_session_recorded_before_tails_were_kept_counts_as_one_with_an_empty_tail() -> None:
    old = session("b", "full", Errored(STOPPING_KIND, "the session failed"))  # type: ignore[arg-type]
    sessions = [
        session("b", "lean"),
        failed("a", "lean", tail=""),
        old,
        failed("c", "lean", tail=""),
    ]
    run = stopped_run(sessions, stopped_at(("a", 1), ("c", 1), tail=""), ("a", "b", "c"))

    assert relaunch_tasks(run, "researcher") == ("a", "b", "c")


def test_a_stop_naming_sessions_the_arm_did_not_end_on_is_refused() -> None:
    sessions = [failed("a", "lean"), session("b", "lean")]
    run = stopped_run(sessions, stopped_at(("a", 1)), ("a", "b"))

    with pytest.raises(ValueError, match=r"the stop names sessions that the researcher lean arm"):
        relaunch_tasks(run, "researcher")


def test_a_stop_naming_no_session_is_refused() -> None:
    run = stopped_run([failed("a", "lean")], stopped_at(), ("a",))

    with pytest.raises(ValueError, match=r"the stop names sessions"):
        relaunch_tasks(run, "researcher")


def test_a_run_that_planned_no_tasks_for_the_role_is_refused() -> None:
    run = run_results([], extra={"tasks": {}, "ending": ending_to_json(Interrupted())})

    with pytest.raises(ValueError, match=r"a run's planned tasks lacks 'researcher'"):
        relaunch_tasks(run, "researcher")


# ---------------------------------------------------------------------------
# Whether a stopped run may be continued
# ---------------------------------------------------------------------------

SEED = 7


def _identity(tree: str = "tree-a", **changes: Any) -> MeasuredIdentity:
    held: dict[str, Any] = {
        "tree": tree,
        "model": "claude-opus-5-5",
        "seed": SEED,
        "tasks": {"researcher": ("task-0", "task-1")},
        "launch_orders": {},
        "declared": declared(),
        "roles": {},
    }
    return MeasuredIdentity(**{**held, **changes})


def _tip(ending: RunEnding | None = None, continued_by: str | None = None) -> ReadTip:
    extra = {} if ending is None else {"ending": ending_to_json(ending)}
    return ReadTip(run_results([], run_id="run-a", extra=extra), _identity(), continued_by)


def _refusals(
    tip: ReadTip, now: MeasuredIdentity | None = None, options: Any = ()
) -> tuple[str, ...]:
    return continuation_refusals(tip, now or _identity(), options)


@pytest.mark.parametrize(
    "ending",
    [_stop("both-arms"), SpendRefused(("task-1",))],
    ids=["both-arms stop", "spend refusal"],
)
def test_a_run_that_stopped_continuably_and_still_measures_the_same_is_not_refused(
    ending: RunEnding,
) -> None:
    assert _refusals(_tip(ending)) == ()


def test_a_results_file_that_cannot_be_read_is_refused_naming_it() -> None:
    unreadable = UnreadableTip(Path("out/20261020T000000Z-0badf1.json"), "it is not JSON")

    refused = continuation_refusals(unreadable, _identity(), ())

    assert refused == (
        "20261020T000000Z-0badf1.json cannot be read as a results file: it is not JSON",
    )


@pytest.mark.parametrize(
    ("ending", "said"),
    [
        (Finished(), "finished its plan"),
        (_stop("one-arm"), "lean arm alone"),
        (Interrupted(), "interrupted"),
        (_closed(), "was closed on 2026-10-17T09:00:00Z: no credit left"),
        (Legacy(), "before runs recorded how they ended"),
    ],
    ids=["complete run", "one-arm stop", "interrupt or crash", "closed run", "recorded before"],
)
def test_a_run_that_did_not_stop_continuably_is_refused_with_the_reason_and_its_name(
    ending: RunEnding, said: str
) -> None:
    (refused,) = _refusals(_tip(None if isinstance(ending, Legacy) else ending))

    assert refused.startswith("run run-a ")
    assert said in refused


def test_a_run_that_already_has_a_continuation_is_refused_naming_it() -> None:
    (refused,) = _refusals(_tip(_stop(), continued_by="run-b"))

    assert "already has a continuation, run-b" in refused


@pytest.mark.parametrize("option", sorted(CONTINUATION_OPTIONS))
def test_an_option_that_only_bounds_spend_or_output_may_accompany_a_continuation(
    option: str,
) -> None:
    assert _refusals(_tip(_stop()), options=[option]) == ()


@pytest.mark.parametrize("option", ["--margin-pp", "--seed", "--role"])
def test_an_option_that_could_change_what_is_measured_is_refused_naming_it(option: str) -> None:
    (refused,) = _refusals(_tip(_stop()), options=["--output", option])

    assert refused.startswith(f"{option} would change what the run measures")


@pytest.mark.parametrize(
    ("now", "named"),
    [
        (_identity(tree="tree-b"), "tree"),
        (_identity(model="claude-opus-5-6"), "model"),
        (_identity(seed=8), "seed"),
        (_identity(tasks={"researcher": ("task-1",)}), "tasks.researcher"),
        (_identity(declared=replace(declared(), margin_pp=12.0)), "declared.margin_pp"),
    ],
    ids=["tree", "model", "seed", "tasks", "a declared setting"],
)
def test_a_difference_in_what_is_measured_is_refused_naming_it(
    now: MeasuredIdentity, named: str
) -> None:
    (refused,) = _refusals(_tip(_stop()), now)

    assert refused.startswith(f"changed since the stop: {named}")


def test_every_reason_is_named_not_only_the_first() -> None:
    refused = _refusals(_tip(Interrupted(), continued_by="run-b"), _identity(seed=9), ["--seed"])

    assert [line.split(" ")[0] for line in refused] == ["run", "run", "--seed", "changed"]


def test_how_well_the_run_did_never_decides_whether_it_is_continued() -> None:
    errored = Errored("result_error", "boom")
    outcomes = {
        "none": [],
        "all passed": [*pair_of_sessions("task-0")],
        "lean errored": [session("task-0", "full"), session("task-0", "lean", errored)],
    }
    ending = {"ending": ending_to_json(_stop())}

    refusals = {
        name: continuation_refusals(
            ReadTip(run_results(sessions, extra=ending), _identity()), _identity(), ()
        )
        for name, sessions in outcomes.items()
    }

    assert refusals == dict.fromkeys(outcomes, ())


# ---------------------------------------------------------------------------
# A stopped run left neither continued nor closed
# ---------------------------------------------------------------------------


def test_the_stopped_run_of_a_role_that_nothing_resolved_is_pending(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a", ending=Finished())
    _write_part(tmp_path, "run-b", ending=_stop())

    pending = pending_stop(tmp_path, "researcher")

    assert pending == PartRef("run-b", tmp_path / "run-b.json", None)


def test_a_stop_of_another_role_is_not_pending_for_this_one(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a", ending=_stop())

    assert pending_stop(tmp_path, "verifier") is None


def test_nothing_is_pending_in_a_directory_with_no_stopped_run(tmp_path: Path) -> None:
    _write_part(tmp_path, "run-a", ending=Finished())
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")

    assert pending_stop(tmp_path, "researcher") is None


@pytest.mark.parametrize(
    "ending",
    [_stop("one-arm"), Interrupted(), _closed(), None],
    ids=["one-arm stop", "interrupt", "closed", "recorded before endings"],
)
def test_a_run_that_was_not_continuable_when_it_stopped_blocks_nothing(
    tmp_path: Path, ending: RunEnding | None
) -> None:
    _write_part(tmp_path, "run-a", ending=ending)

    assert pending_stop(tmp_path, "researcher") is None


def test_a_stop_that_was_continued_is_resolved_and_a_continuation_that_stopped_is_pending(
    tmp_path: Path,
) -> None:
    _write_part(tmp_path, "run-a", ending=_stop())
    _write_part(tmp_path, "run-b", continues="run-a", ending=SpendRefused(("task-1",)))

    assert pending_stop(tmp_path, "researcher") == PartRef(
        "run-b", tmp_path / "run-b.json", "run-a"
    )

    _write_part(tmp_path, "run-c", continues="run-b", ending=Finished())

    assert pending_stop(tmp_path, "researcher") is None


# ---------------------------------------------------------------------------
# Closing a stopped run
# ---------------------------------------------------------------------------

CLOSED_AT = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


def test_closing_a_stopped_run_records_the_reason_the_time_and_the_ending_it_closes() -> None:
    stopped = _stop()

    closed = close(_tip(stopped), "the credential is gone for good", CLOSED_AT)

    assert (closed.reason, closed.at, closed.stopped) == (
        "the credential is gone for good",
        "2026-10-17T09:00:00+00:00",
        stopped,
    )
    assert not continuable(closed)


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_close_without_a_reason_is_refused(reason: str) -> None:
    with pytest.raises(ValueError, match="closing a run needs a reason"):
        close(_tip(_stop()), reason, CLOSED_AT)


def test_a_close_at_a_time_that_names_no_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="must carry a UTC offset"):
        close(_tip(_stop()), "gone", datetime(2026, 10, 17, 9, 0))


@pytest.mark.parametrize(
    "ending", [Finished(), _closed(), None], ids=["finished", "closed", "recorded before"]
)
def test_a_run_that_did_not_stop_cannot_be_closed(ending: RunEnding | None) -> None:
    with pytest.raises(ValueError, match="did not stop"):
        close(_tip(ending), "gone", CLOSED_AT)


def test_only_the_latest_part_of_a_lineage_can_be_closed() -> None:
    with pytest.raises(ValueError, match="continued by run-b"):
        close(_tip(_stop(), continued_by="run-b"), "gone", CLOSED_AT)


def test_the_closed_ending_carries_the_per_check_result_the_run_had_reached() -> None:
    pairs = [s for task in ("task-0", "task-1") for s in pair_of_sessions(task)]
    ending = {"ending": ending_to_json(_stop())}
    tip = ReadTip(results_of(pairs, required_pairs=2, extra=ending), _identity())

    interim = close(tip, "gone", CLOSED_AT).interim

    assert interim == {"researcher.C1": "clear", "researcher.C3": "clear"}


def test_a_role_short_of_pairs_is_carried_as_underpowered() -> None:
    ending = {"ending": ending_to_json(_stop())}
    tip = ReadTip(results_of([], required_pairs=2, extra=ending), _identity())

    assert close(tip, "gone", CLOSED_AT).interim == {"researcher": "underpowered"}


def test_a_closed_ending_survives_the_results_file(tmp_path: Path) -> None:
    closed = close(_tip(_stop()), "gone", CLOSED_AT)
    _write_part(tmp_path, "run-a", ending=closed)

    assert ending_of(results.load(tmp_path / "run-a.json")) == closed
