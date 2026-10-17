"""The infrastructure stop: tails redact before they clip, masking merges only volatile tokens,
and the fold stops a role's arm on its Nth identical counting failure and on nothing else."""

from __future__ import annotations

import pytest

from praxion_evals.adherence.infra_stop import (
    COUNTING_KINDS,
    REDACTED,
    Continue,
    Decision,
    EvidenceTail,
    FoldState,
    Stop,
    StopReason,
    StopRule,
    mask,
    step,
)
from praxion_evals.adherence.model import (
    Arm,
    Errored,
    ErrorKind,
    Measured,
    NotMeasured,
    Passed,
    Role,
    SessionRecord,
    SessionSetup,
    SessionStatus,
)

CREDIT = EvidenceTail("", "Credit balance is too low")
RULE = StopRule.parse(3, COUNTING_KINDS, 2000)


def _record(
    arm: Arm,
    task: str,
    status: str = "credit",
    role: Role = "researcher",
    kind: ErrorKind = "result_error",
) -> SessionRecord:
    setup = SessionSetup(arm, "abc1234", role, task, "tmpl", 7)
    if status == "ran":
        outcome: SessionStatus = Measured({"C1": Passed()}, None, setup)
    elif status == "not-spawned":
        outcome = NotMeasured("never spawned", setup)
    else:
        outcome = Errored(kind, f"{kind} detail", setup)
    return SessionRecord(setup, outcome, 0.0, 1, "2026-10-17T00:00:00Z")


def _fold(
    sessions: list[tuple[SessionRecord, EvidenceTail | None]], rule: StopRule = RULE
) -> tuple[FoldState, list[Decision]]:
    state, decisions = FoldState(), []
    for record, tails in sessions:
        state, decision = step(rule, state, record, tails)
        decisions.append(decision)
    return state, decisions


def _reason(decisions: list[Decision], at: int) -> StopReason:
    stop = decisions[at]
    assert isinstance(stop, Stop), f"session {at} did not stop the run"
    return stop.reason


def _stops(decisions: list[Decision]) -> list[int]:
    return [i for i, d in enumerate(decisions) if isinstance(d, Stop)]


# --- evidence tails -------------------------------------------------------


def test_a_secret_is_redacted_before_the_clip_can_cut_it_in_half():
    secret = "super-secret-token-value"
    tail = EvidenceTail.capture("x" * 50 + secret, "ok " + secret, 8, [secret])

    assert secret not in tail.error_tail + tail.result_tail
    assert "secret" not in tail.error_tail + tail.result_tail
    assert tail.error_tail == REDACTED[-8:]


def test_an_api_key_shaped_token_is_redacted_without_being_named():
    tail = EvidenceTail.capture("bad key sk-ant-api03-AbC_dEf-123 rejected", "", 2000, [])

    assert "sk-ant" not in tail.error_tail
    assert tail.error_tail == f"bad key {REDACTED} rejected"


def test_a_secret_inside_another_secret_leaves_no_remnant():
    tail = EvidenceTail.capture("token=abcdef-long", "", 2000, ["abcdef", "abcdef-long"])

    assert tail.error_tail == f"token={REDACTED}"


def test_an_empty_stream_is_an_empty_string_and_a_long_one_keeps_its_end():
    tail = EvidenceTail.capture("", "0123456789", 4, [])

    assert tail == EvidenceTail("", "6789")


def test_a_blank_secret_redacts_nothing():
    assert EvidenceTail.capture("abc", "def", 10, [""]) == EvidenceTail("abc", "def")


def test_a_non_positive_bound_is_refused():
    with pytest.raises(ValueError, match="bound"):
        EvidenceTail.capture("a", "b", 0, [])


# --- the masking rule -----------------------------------------------------


@pytest.mark.parametrize(
    ("volatile", "placeholder"),
    [
        ("job 123e4567-e89b-12d3-a456-426614174000 failed", "job <uuid> failed"),
        ("commit 9fceb02d0ae598e95dc970b74767f19372d61af8 failed", "commit <hex-id> failed"),
        ("at 2026-10-17T12:30:05.123Z it failed", "at <timestamp> it failed"),
        ("at 2026-10-17 12:30:05+02:00 it failed", "at <timestamp> it failed"),
        ("request req_011CTx9Qp7aB failed", "request <request-id> failed"),
        ("failed after 4521ms", "failed after <duration>"),
        ("read 1048576 bytes then failed", "read <bytes> then failed"),
    ],
)
def test_every_volatile_token_kind_is_masked(volatile: str, placeholder: str):
    assert mask(volatile) == placeholder


def test_tails_that_differ_only_in_volatile_tokens_mask_equal():
    one = "req_aaa111 at 2026-01-01T00:00:00Z took 10ms (5 bytes) id 0123456789abcdef"
    two = "req_bbb222 at 2026-12-31T23:59:59Z took 9999ms (77 bytes) id fedcba9876543210"

    assert mask(one) == mask(two)


def test_tails_that_differ_in_anything_else_stay_apart():
    assert mask("exit code 1") != mask("exit code 2")
    assert mask("Credit balance is too low") != mask("Invalid API key")


# --- the declared rule ----------------------------------------------------


@pytest.mark.parametrize("count", [2, 0, -1, True])
def test_a_stop_count_below_three_is_refused(count: int):
    with pytest.raises(ValueError, match="at least 3"):
        StopRule.parse(count, COUNTING_KINDS, 2000)


@pytest.mark.parametrize("tail_chars", [0, -5])
def test_a_non_positive_tail_bound_is_refused(tail_chars: int):
    with pytest.raises(ValueError, match="positive"):
        StopRule.parse(3, COUNTING_KINDS, tail_chars)


@pytest.mark.parametrize(
    "kind",
    ["evaluation_exception", "isolation_breach", "launch_refused", "structured_output_missing"],
)
def test_a_kind_outside_the_counting_set_is_refused(kind: str):
    with pytest.raises(ValueError, match=kind):
        StopRule.parse(3, [*COUNTING_KINDS, kind], 2000)


def test_a_rule_that_counts_nothing_is_refused():
    with pytest.raises(ValueError, match="at least one"):
        StopRule.parse(3, [], 2000)


# --- the fold -------------------------------------------------------------


def test_the_third_identical_failure_of_one_arm_stops_the_run_and_no_earlier_one_does():
    sessions = [(_record("lean", f"t{i}"), CREDIT) for i in range(3)]

    _, decisions = _fold(sessions)

    assert _stops(decisions) == [2]
    assert isinstance(decisions[0], Continue)


def test_the_stop_names_the_kind_the_masked_tail_and_the_sessions_of_the_streak():
    _, decisions = _fold([(_record("lean", f"t{i}"), CREDIT) for i in range(3)])

    reason = _reason(decisions, 2)
    assert (reason.kind, reason.role, reason.arm) == (
        "result_error",
        "researcher",
        "lean",
    )
    assert reason.masked_tail == "\nCredit balance is too low"
    assert [(s.task_id, s.attempt) for s in reason.sessions] == [
        ("t0", 1),
        ("t1", 1),
        ("t2", 1),
    ]


def test_failures_differing_only_in_a_masked_token_count_as_identical():
    tails = [EvidenceTail("", f"timeout after {ms}ms (req_{ms}ab)") for ms in (100, 2500, 90)]

    _, decisions = _fold([(_record("full", f"t{i}"), t) for i, t in enumerate(tails)])

    assert _stops(decisions) == [2]


def test_two_different_errors_of_one_kind_never_merge_into_a_streak():
    tails = [EvidenceTail("", t) for t in ("Credit balance is too low", "Invalid API key") * 3]

    _, decisions = _fold([(_record("lean", f"t{i}"), t) for i, t in enumerate(tails)])

    assert _stops(decisions) == []


def test_the_same_tail_under_two_kinds_never_merges():
    sessions = [
        (_record("lean", f"t{i}", kind=kind), CREDIT)
        for i, kind in enumerate(["result_error", "exit_nonzero", "result_error"])
    ]

    assert _stops(_fold(sessions)[1]) == []


@pytest.mark.parametrize("breaker", ["ran", "not-spawned"])
def test_a_session_that_ran_breaks_the_streak(breaker: str):
    sessions = [
        (_record("lean", "t0"), CREDIT),
        (_record("lean", "t1"), CREDIT),
        (_record("lean", "t2", breaker), None),
        (_record("lean", "t3"), CREDIT),
        (_record("lean", "t4"), CREDIT),
    ]

    assert _stops(_fold(sessions)[1]) == []


@pytest.mark.parametrize("kind", ["isolation_breach", "evaluation_exception", "launch_refused"])
def test_an_error_outside_the_counting_kinds_resets_and_never_counts(kind: str):
    always_failing = [(_record("lean", f"t{i}", kind=kind), CREDIT) for i in range(5)]
    broken_by_it = [
        (_record("lean", "t0"), CREDIT),
        (_record("lean", "t1"), CREDIT),
        (_record("lean", "t2", kind=kind), CREDIT),
        (_record("lean", "t3"), CREDIT),
    ]

    assert _stops(_fold(always_failing)[1]) == []
    assert _stops(_fold(broken_by_it)[1]) == []


def test_a_task_and_its_retry_never_stop_a_run_at_the_smallest_count():
    task_and_retry = [(_record("lean", "t0"), CREDIT), (_record("lean", "t0"), CREDIT)]

    state, decisions = _fold(task_and_retry)
    state, after = step(RULE, state, _record("lean", "t1", "ran"), None)

    assert _stops(decisions) == []
    assert isinstance(after, Continue)
    assert [s.session.attempt for s in state.seen] == [1, 2, 1]


def test_a_retry_counts_as_the_arms_next_session():
    sessions = [(_record("lean", "t0"), CREDIT), (_record("lean", "t0"), CREDIT)]
    sessions.append((_record("lean", "t1"), CREDIT))

    reason = _reason(_fold(sessions)[1], 2)

    assert [(s.task_id, s.attempt) for s in reason.sessions] == [
        ("t0", 1),
        ("t0", 2),
        ("t1", 1),
    ]


def test_the_other_arms_sessions_do_not_break_a_streak():
    sessions = [
        (_record("lean", "t0"), CREDIT),
        (_record("full", "t0", "ran"), None),
        (_record("lean", "t1"), CREDIT),
        (_record("full", "t1", "ran"), None),
        (_record("lean", "t2"), CREDIT),
    ]

    assert _stops(_fold(sessions)[1]) == [4]


def test_a_streak_is_per_role():
    sessions = [
        (_record("lean", "t0", role="researcher"), CREDIT),
        (_record("lean", "t0", role="verifier"), CREDIT),
        (_record("lean", "t1", role="researcher"), CREDIT),
        (_record("lean", "t1", role="verifier"), CREDIT),
        (_record("lean", "t2", role="researcher"), CREDIT),
    ]

    reason = _reason(_fold(sessions)[1], 4)

    assert reason.role == "researcher"


def test_the_stop_is_both_arms_when_the_other_arm_failed_alike_inside_the_window():
    sessions = [
        (_record("full", "t0"), CREDIT),
        (_record("lean", "t0"), CREDIT),
        (_record("full", "t1"), CREDIT),
        (_record("lean", "t1"), CREDIT),
        (_record("full", "t2"), CREDIT),
        (_record("lean", "t2"), CREDIT),
    ]

    reason = _reason(_fold(sessions)[1], 4)

    assert reason.scope == "both-arms"


def test_the_stop_is_one_arm_when_the_other_arm_ran():
    sessions = [
        (_record("lean", "t0"), CREDIT),
        (_record("full", "t0", "ran"), None),
        (_record("lean", "t1"), CREDIT),
        (_record("full", "t1", "ran"), None),
        (_record("lean", "t2"), CREDIT),
    ]

    reason = _reason(_fold(sessions)[1], -1)

    assert reason.scope == "one-arm"


def test_the_stop_is_one_arm_when_the_other_arm_failed_differently():
    sessions = [
        (_record("lean", "t0"), CREDIT),
        (_record("full", "t0"), EvidenceTail("", "Invalid API key")),
        (_record("lean", "t1"), CREDIT),
        (_record("lean", "t2"), CREDIT),
    ]

    reason = _reason(_fold(sessions)[1], -1)

    assert reason.scope == "one-arm"


def test_an_alike_failure_of_the_other_arm_outside_the_window_does_not_widen_the_scope():
    sessions = [
        (_record("full", "t0"), CREDIT),
        (_record("full", "t1", "ran"), None),
        (_record("lean", "t0"), CREDIT),
        (_record("lean", "t1"), CREDIT),
        (_record("lean", "t2"), CREDIT),
    ]

    reason = _reason(_fold(sessions)[1], 4)

    assert reason.scope == "one-arm"


def test_a_failure_with_no_captured_tail_streaks_on_its_kind_alone():
    sessions = [(_record("lean", f"t{i}"), None) for i in range(3)]

    reason = _reason(_fold(sessions)[1], 2)

    assert reason.masked_tail == "\n"


def test_a_larger_declared_count_stops_exactly_at_that_count():
    rule = StopRule.parse(5, COUNTING_KINDS, 2000)

    _, decisions = _fold([(_record("lean", f"t{i}"), CREDIT) for i in range(5)], rule)

    assert _stops(decisions) == [4]
