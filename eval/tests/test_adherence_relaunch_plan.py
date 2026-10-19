"""What a continuation launches again: only the tasks nobody finished, in the order the run planned
them, and a stop that does not match the sessions the run recorded is refused."""

from __future__ import annotations

from dataclasses import replace

import pytest

from praxion_evals.adherence import results
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    DEFAULT_STOP_COUNT,
    EvidenceTail,
    Launched,
    StopReason,
    StopRule,
)
from praxion_evals.adherence.lineage import (
    InfraStopped,
    Interrupted,
    RunEnding,
    SpendRefused,
    ending_to_json,
    never_launched,
    relaunch_tasks,
)
from praxion_evals.adherence.model import Errored
from tests.test_adherence_results import declared, pair_of_sessions, run_results, session

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
    settings = replace(
        declared(), stop_rule=StopRule.parse(DEFAULT_STOP_COUNT, COUNTING_KINDS, 2000)
    )
    return run_results(sessions, settings=settings, extra=extra)


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
