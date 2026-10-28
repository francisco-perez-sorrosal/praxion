"""The move's stop folds a run's sessions per arm: the third identical counting failure of one arm
ends the run, the other arms' sessions between them neither break nor extend the streak, a paired
stop is continuable only when both arms failed alike, a floor stop on its own streak, and the fold
agrees with the role fold because both take the streak from `infra_stop.trailing_streak`."""

from __future__ import annotations

import pytest

from praxion_evals.adherence import infra_stop
from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    Continue,
    EvidenceTail,
    FoldState,
    StopRule,
)
from praxion_evals.adherence.model import (
    Errored,
    ErrorKind,
    Measured,
    Passed,
    SessionRecord,
    SessionSetup,
)
from praxion_evals.adherence.moves import stop
from praxion_evals.adherence.moves.model import MoveArm
from praxion_evals.adherence.moves.stop import Launched, MoveFold, MoveStop, MoveStopReason

RULE = StopRule.parse(3, COUNTING_KINDS, 2000)
CREDIT = EvidenceTail("", "Credit balance is too low")
ELSE = EvidenceTail("", "Request was rejected")


def _error(kind: ErrorKind = "result_error", tails: EvidenceTail | None = CREDIT, detail="x"):
    return Errored(kind, detail, tails=tails)


def _fold(sessions: list[tuple[str, MoveArm, Errored | None]], rule: StopRule = RULE):
    state, decisions = MoveFold(), []
    for task_id, arm, error in sessions:
        state, decision = stop.step(rule, state, task_id, arm, error)
        decisions.append(decision)
    return state, decisions


def _stops(decisions) -> list[int]:
    return [i for i, decision in enumerate(decisions) if isinstance(decision, MoveStop)]


def _reason(decisions, at: int) -> MoveStopReason:
    decision = decisions[at]
    assert isinstance(decision, MoveStop), f"session {at} did not stop the run"
    return decision.reason


def _failing(arm: MoveArm, count: int, first: int = 1) -> list[tuple[str, MoveArm, Errored]]:
    return [(f"t{n}", arm, _error()) for n in range(first, first + count)]


# --- the streak ---


def test_the_third_identical_failure_of_one_arm_stops_the_run_on_that_session():
    _, decisions = _fold(_failing("lean", 4))

    assert _stops(decisions) == [2, 3]
    assert [s.task_id for s in _reason(decisions, 2).sessions] == ["t1", "t2", "t3"]


def test_the_other_arms_sessions_between_the_failures_neither_break_nor_extend_the_streak():
    sessions = [
        ("t1", "lean", _error()),
        ("t1", "full", None),
        ("t2", "lean", _error()),
        ("t2", "full", _error(tails=ELSE)),
        ("t3", "lean", _error()),
    ]
    _, decisions = _fold(sessions)

    assert _stops(decisions) == [4]


def test_a_session_of_the_arm_that_ran_ends_its_streak():
    sessions = [*_failing("lean", 2), ("t3", "lean", None), *_failing("lean", 2, first=4)]
    _, decisions = _fold(sessions)

    assert _stops(decisions) == []


def test_a_retry_is_the_arms_next_session_and_counts_as_attempt_two():
    _, decisions = _fold([("t1", "lean", _error()), ("t1", "lean", _error()), *_failing("lean", 1)])

    assert _reason(decisions, 2).sessions[:2] == (
        Launched("t1", "lean", 1),
        Launched("t1", "lean", 2),
    )


def test_failures_that_differ_only_in_volatile_tokens_are_the_same_failure():
    first = EvidenceTail("", "request req_AAA failed after 120ms")
    second = EvidenceTail("", "request req_BBB failed after 87ms")
    sessions = [("t1", "full", _error(tails=first)), ("t2", "full", _error(tails=second))]
    _, decisions = _fold([*sessions, ("t3", "full", _error(tails=first))])

    assert _stops(decisions) == [2]


# --- continuability ---


def test_a_paired_stop_seen_in_one_arm_only_is_not_continuable():
    _, decisions = _fold(_failing("lean", 3))

    reason = _reason(decisions, 2)
    assert (reason.scope, reason.continuable) == ("one-arm", False)


def test_a_paired_stop_whose_other_arm_failed_alike_inside_the_window_is_continuable():
    sessions = [
        ("t1", "lean", _error()),
        ("t1", "full", _error()),
        ("t2", "lean", _error()),
        ("t3", "lean", _error()),
    ]
    _, decisions = _fold(sessions)

    reason = _reason(decisions, 3)
    assert (reason.scope, reason.continuable) == ("both-arms", True)


def test_a_floor_stop_is_continuable_on_its_own_streak():
    _, decisions = _fold(_failing("floor", 3))

    reason = _reason(decisions, 2)
    assert (reason.arm, reason.scope, reason.continuable) == ("floor", "one-arm", True)


# --- what counts as a failure ---


def test_an_errored_floor_session_outside_the_counting_kinds_is_no_failure_and_ends_the_streak():
    refused = _error("launch_refused", detail="spend cap")
    sessions = [*_failing("floor", 2), ("t3", "floor", refused), *_failing("floor", 2, first=4)]
    state, decisions = _fold(sessions)

    assert _stops(decisions) == []
    assert state.seen[2].failure is None


def test_a_floor_session_its_own_budget_stopped_is_no_failure():
    spent = _error(detail="exit_code=1 result_subtype=error_max_budget_usd")
    sessions = [*_failing("floor", 2), ("t3", "floor", spent)]
    state, decisions = _fold(sessions)

    assert (_stops(decisions), state.seen[2].failure) == ([], None)


def test_a_session_that_ran_counts_for_no_failure():
    assert stop.failure_of(RULE, None) is None


# --- parity with the role fold ---


def _role_record(task_id: str, error: Errored | None) -> SessionRecord:
    setup = SessionSetup("lean", "abc1234", "researcher", task_id, "tmpl", 7)
    status = Measured({"C1": Passed()}, None, setup) if error is None else error
    if error is not None:
        status = Errored(error.kind, error.detail, setup, error.tails)
    return SessionRecord(setup, status, 0.0, 1, "2026-10-17T00:00:00Z")


def test_the_move_fold_stops_where_the_role_fold_stops_over_the_same_failures():
    errors = [_error(), _error(tails=ELSE), None, _error(), _error(), _error(), _error()]
    ids = [f"t{n}" for n in range(len(errors))]
    _, moves = _fold([(i, "lean", e) for i, e in zip(ids, errors, strict=True)])
    role_state, role_stops = FoldState(), []
    for task_id, error in zip(ids, errors, strict=True):
        role_state, decision = infra_stop.step(RULE, role_state, _role_record(task_id, error))
        role_stops.append(not isinstance(decision, Continue))

    assert [i in _stops(moves) for i in range(len(errors))] == role_stops


def test_the_move_fold_names_the_same_sessions_as_the_role_fold_for_the_same_streak():
    errors = [_error(), _error(), _error()]
    ids = ["t1", "t2", "t3"]
    _, moves = _fold([(i, "lean", e) for i, e in zip(ids, errors, strict=True)])
    state = FoldState()
    for task_id, error in zip(ids, errors, strict=True):
        state, decision = infra_stop.step(RULE, state, _role_record(task_id, error))

    assert isinstance(decision, infra_stop.Stop)
    role_sessions = [(s.task_id, s.arm, s.attempt) for s in decision.reason.sessions]
    move_sessions = [(s.task_id, s.arm, s.attempt) for s in _reason(moves, 2).sessions]
    assert move_sessions == role_sessions


def test_both_folds_take_their_streak_from_trailing_streak(monkeypatch: pytest.MonkeyPatch):
    calls: list[int] = []
    real = infra_stop.trailing_streak

    def spy(failures, failure):
        calls.append(len(failures))
        return real(failures, failure)

    monkeypatch.setattr(infra_stop, "trailing_streak", spy)

    _fold(_failing("lean", 1))
    after_move = len(calls)
    infra_stop.step(RULE, FoldState(), _role_record("t1", _error()))

    assert (after_move, len(calls) - after_move) == (1, 1)
