"""Tests for the step-loop driver's review state, iteration budget and stop precedence
(``scripts/_step_loop_review.py``, ``scripts/_step_loop_action.py`` and the review half of
``scripts/_step_loop_state.py``).

Every case passes plan text, WIP attempt readings, ledger records, reconciler verdict dicts and
review-file text in and reads values out: no file is written, no process runs, nothing is mocked.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import ATTEMPT_CAP, Attempt, OutstandingAttempt  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import (  # noqa: E402
    BUDGET_CAUSE,
    HUMAN_CAUSES,
    Complete,
    Spawn,
    Stop,
    issuable_action,
    iteration_budget,
    iterations_used,
    next_action,
)
from _step_loop_render import _ACTIONS, RequestKey  # noqa: E402
from _step_loop_review import (  # noqa: E402
    Accepted,
    Due,
    NotRequired,
    Requested,
    RevisedTwice,
    ReviseDue,
    RevisionFailed,
    Unfinished,
    file_verdict,
    needs_review,
    review_state,
    satisfied,
)
from _step_loop_state import (  # noqa: E402
    LoopInputs,
    Marked,
    Next,
    Verified,
    is_done,
    review_range,
    select_step,
    series_work,
    step_series,
)
from iteration_ledger import IterationRecord  # noqa: E402

STEP = "Step "
IMPL = "**Assignee**: implementer"
OTHER = "**Assignee**: test-engineer"
FILES = "**Files**: `scripts/a.py`"
FORCED = "**review**: force"
RISKY = "tier: H"
OFF = "**review**: off"
ACCEPT = "verdict: accept"
REVISE = "verdict: revise"
PARTIAL = "verdict: [PARTIAL]"


def block(number, *lines, annotations=""):
    body = "".join(f"{line}\n" for line in lines)
    return f"### {STEP}{number}: Do it{annotations}\n\n{body}\n"


def steps_of(*blocks):
    return parse_plan_steps("## Steps\n\n" + "".join(blocks))


def one(*lines, number="1"):
    return steps_of(block(number, *lines))[0]


def rec(step, attempt=1, kind="implement", *, verdict="mismatch", stop="completed", round_=1):
    """A ledger record for `step`, its request id built the way the driver builds it."""
    key = RequestKey(step.id, attempt, kind, 1, None if kind == "implement" else round_)
    return IterationRecord(
        step=STEP + step.id,
        attempt=attempt,
        agent_id=f"agent-{attempt}",
        verdict=verdict,
        decided_by="check",
        test_result="Result: none",
        commit=None,
        stop_reason=stop,
        request=key.id,
        step_digest=step.digest,
    )


def verdict(step_id, word, claim="PENDING", evidence=""):
    return {"step": STEP + step_id, "verdict": word, "wip_claim": claim, "evidence": evidence}


def read(steps, attempts=None, records=(), verdicts=(), reviews=None, unnamed=()):
    return LoopInputs.read(steps, attempts or {}, records, verdicts, reviews, unnamed)


def act(steps, **given):
    return next_action(read(steps, **given))


def verified(step, attempt=1):
    return rec(step, attempt, verdict="verified-complete")


def reviewed(step):
    return rec(step, 1, "review", verdict="verified-complete", stop="completed")


def revised(step, *, ok=True):
    return rec(step, 1, "revise", verdict="verified-complete" if ok else "mismatch")


FORCED_STEP = one(IMPL, FILES, FORCED)
PLAIN_STEP = one(IMPL, FILES)
SECOND = one(IMPL, FILES, number="2")
PLAN = [FORCED_STEP, SECOND]  # step 2 keeps the budget wide enough for a review loop


def done(*ids):
    return [verdict(i, "verified-complete", "COMPLETE") for i in ids]


# --- the trigger and the review file -----------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "marked"),
    [
        pytest.param([IMPL], False, id="no-signal"),
        pytest.param([IMPL, RISKY], True, id="tier-h"),
        pytest.param([IMPL, FORCED], True, id="forced"),
        pytest.param([IMPL, RISKY, OFF], False, id="off-beats-tier-h"),
        pytest.param([IMPL, OFF], False, id="off-alone"),
    ],
)
def test_the_plan_local_trigger_marks_tier_h_and_forced_steps_unless_off(lines, marked):
    assert needs_review(one(*lines)) is marked


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(None, None, id="absent-file"),
        pytest.param("", None, id="empty-file"),
        pytest.param("findings: none\n", None, id="no-verdict-line"),
        pytest.param("verdict: accept\n", "accept", id="accept"),
        pytest.param("verdict: revise\nfindings:\n  - id: F1\n", "revise", id="revise"),
        pytest.param("verdict: [PARTIAL]\n", "partial", id="partial"),
        pytest.param("verdict: [PARTIAL]\nfindings:\nverdict: accept\n", "accept", id="last-wins"),
        pytest.param("verdict: accept\nverdict: [PARTIAL]\n", "partial", id="rewritten-partial"),
        pytest.param("verdict: maybe\n", "partial", id="unknown-word-is-unfinished"),
        pytest.param("  verdict: accept\n", None, id="indented-line-is-no-verdict"),
        pytest.param("the verdict: accept was close\n", None, id="mid-line-mention"),
    ],
)
def test_the_review_files_last_verdict_line_decides(text, expected):
    assert file_verdict(text) == expected


# --- the review state --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("required", "reviews", "revises", "failed", "text", "expected"),
    [
        pytest.param(False, 0, 0, False, None, NotRequired(), id="off"),
        pytest.param(False, 1, 0, False, ACCEPT, NotRequired(), id="off-ignores-the-file"),
        pytest.param(True, 0, 0, False, None, Due(1), id="due"),
        pytest.param(True, 0, 0, False, PARTIAL, Requested(1), id="requested"),
        pytest.param(True, 0, 0, False, ACCEPT, Due(1), id="a-stale-accept-with-no-review"),
        pytest.param(True, 1, 0, False, ACCEPT, Accepted(), id="accepted-first-round"),
        pytest.param(True, 2, 1, False, ACCEPT, Accepted(), id="accepted-second-round"),
        pytest.param(True, 1, 0, False, REVISE, ReviseDue(1), id="revise-due"),
        pytest.param(True, 1, 1, False, REVISE, Due(2), id="second-review-due"),
        pytest.param(True, 1, 1, False, PARTIAL, Requested(2), id="second-review-requested"),
        pytest.param(True, 2, 1, False, REVISE, RevisedTwice(), id="revised-twice"),
        pytest.param(True, 1, 0, False, PARTIAL, Unfinished(), id="unfinished-partial"),
        pytest.param(True, 1, 0, False, None, Unfinished(), id="unfinished-no-file"),
        pytest.param(True, 2, 1, False, None, Unfinished(), id="unfinished-second-round"),
        pytest.param(True, 1, 1, True, REVISE, RevisionFailed(), id="revision-failed"),
        pytest.param(True, 1, 1, True, ACCEPT, Accepted(), id="accept-clears-a-failed-revision"),
    ],
)
def test_the_review_state_reads_the_trigger_the_returns_and_the_file(
    required, reviews, revises, failed, text, expected
):
    assert review_state(required, reviews, revises, failed, text) == expected


@pytest.mark.parametrize(
    ("state", "is_satisfied"),
    [
        (NotRequired(), True),
        (Accepted(), True),
        (Due(1), False),
        (Requested(1), False),
        (ReviseDue(1), False),
        (RevisedTwice(), False),
        (Unfinished(), False),
        (RevisionFailed(), False),
    ],
    ids=lambda value: type(value).__name__ if not isinstance(value, bool) else str(value),
)
def test_only_an_absent_or_accepted_review_is_satisfied(state, is_satisfied):
    assert satisfied(state) is is_satisfied


@pytest.mark.parametrize(
    ("step", "records", "reviews", "expected"),
    [
        pytest.param(PLAIN_STEP, [verified(PLAIN_STEP)], {}, NotRequired(), id="not-marked"),
        pytest.param(FORCED_STEP, [verified(FORCED_STEP)], {}, Due(1), id="due"),
        pytest.param(
            FORCED_STEP, [verified(FORCED_STEP)], {"1": PARTIAL}, Requested(1), id="requested"
        ),
        pytest.param(
            FORCED_STEP,
            [verified(FORCED_STEP), reviewed(FORCED_STEP)],
            {"1": ACCEPT},
            Accepted(),
            id="accepted",
        ),
        pytest.param(
            FORCED_STEP,
            [verified(FORCED_STEP), reviewed(FORCED_STEP)],
            {"1": REVISE},
            ReviseDue(1),
            id="revise-due",
        ),
        pytest.param(
            FORCED_STEP,
            [verified(FORCED_STEP), reviewed(FORCED_STEP), revised(FORCED_STEP)],
            {"1": REVISE},
            Due(2),
            id="second-review-due-after-a-passing-revision",
        ),
        pytest.param(
            FORCED_STEP,
            [verified(FORCED_STEP), reviewed(FORCED_STEP), revised(FORCED_STEP, ok=False)],
            {"1": REVISE},
            RevisionFailed(),
            id="revision-failed",
        ),
        pytest.param(
            FORCED_STEP,
            [verified(FORCED_STEP), reviewed(FORCED_STEP)],
            {},
            Unfinished(),
            id="reviewer-left-no-file",
        ),
    ],
)
def test_a_verified_step_carries_the_review_state_of_its_series(step, records, reviews, expected):
    state = step_series(step, read([step], records=records, reviews=reviews))

    assert state == Verified(1, 1, None, expected)


def test_a_review_file_left_by_an_earlier_series_cannot_accept_a_new_one():
    original = one(IMPL, FILES, FORCED, "Original wording.")
    revised_step = one(IMPL, FILES, FORCED, "Revised wording.")
    records = [verified(original), reviewed(original), verified(revised_step)]

    state = step_series(revised_step, read([revised_step], records=records, reviews={"1": ACCEPT}))

    assert state == Verified(1, 2, None, Due(1))


@pytest.mark.parametrize(
    ("records", "reviews", "finished"),
    [
        pytest.param([verified(PLAIN_STEP)], {}, True, id="not-marked"),
        pytest.param([verified(FORCED_STEP)], {}, False, id="review-due"),
        pytest.param([verified(FORCED_STEP), reviewed(FORCED_STEP)], {"1": ACCEPT}, True, id="ok"),
    ],
)
def test_a_verified_step_is_done_only_once_its_review_is_satisfied(records, reviews, finished):
    step = PLAIN_STEP if records[0].step_digest == PLAIN_STEP.digest else FORCED_STEP
    state = step_series(step, read([step], records=records, reviews=reviews))

    assert is_done(state) is finished


def test_a_step_waiting_for_its_review_holds_back_the_steps_after_it():
    plan = steps_of(
        block("1", IMPL, FILES, FORCED), block("2", IMPL, annotations=" [depends-on: 1]")
    )

    chosen = select_step(read(plan, records=[verified(plan[0])]))

    assert (type(chosen), chosen.step.id) == (Next, "1")


# --- the iteration budget ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("steps", "budget"),
    [
        pytest.param([], 0, id="no-steps"),
        pytest.param([PLAIN_STEP, SECOND], 2 * ATTEMPT_CAP, id="the-cap-for-each-driven-step"),
        pytest.param([FORCED_STEP], ATTEMPT_CAP + 1, id="plus-one-for-a-forced-review"),
        pytest.param([one(IMPL, RISKY)], ATTEMPT_CAP + 1, id="plus-one-for-tier-h"),
        pytest.param([one(IMPL, RISKY, OFF)], ATTEMPT_CAP, id="off-takes-the-review-back"),
        pytest.param([one(OTHER, FORCED)], 0, id="a-step-outside-the-loop-adds-nothing"),
    ],
)
def test_the_budget_is_the_cap_per_driven_step_plus_a_review_for_each_marked_one(steps, budget):
    assert iteration_budget(steps) == budget


def test_the_iterations_used_are_the_ledger_records_that_carry_a_request():
    legacy = IterationRecord(
        STEP + "1", 1, "a", "mismatch", "check", "Result: none", None, "completed"
    )

    assert iterations_used(read([PLAIN_STEP], records=[legacy, rec(PLAIN_STEP, 1)])) == 1


def test_a_plan_revision_opens_a_new_series_without_growing_the_budget():
    old = [one(IMPL, FILES, "Original wording.", number=n) for n in "12"]
    new = [one(IMPL, FILES, "Revised wording.", number=n) for n in "12"]

    assert iteration_budget(old) == iteration_budget(new) == 2 * ATTEMPT_CAP


def test_the_budget_stop_is_reachable_once_revised_series_have_used_it_up():
    old = [one(IMPL, FILES, "Original wording.", number=n) for n in "12"]
    new = [one(IMPL, FILES, "Revised wording.", number=n) for n in "12"]
    spent_records = [rec(step, n) for step in old for n in (1, 2)]

    stopped = act(new, records=spent_records)
    fresh = act(new, records=spent_records[:2])

    assert stopped == Stop(BUDGET_CAUSE, None, "4 of 4 iterations used")
    assert fresh == Spawn(new[0], RequestKey("1", 1, "implement", 2))


# --- precedence: Complete > human stop > budget stop > Spawn ----------------------------------

SPENT_PLAN = [PLAIN_STEP]
SPENT = [rec(PLAIN_STEP, 1), rec(PLAIN_STEP, 2)]  # the whole budget of the one-step plan


def test_complete_outranks_a_human_stop():
    verified_plan = [PLAIN_STEP]
    records = [rec(PLAIN_STEP, 1), verified(PLAIN_STEP, 2)]

    action = act(verified_plan, records=records, unnamed=("count=2 names no step",))

    assert action == Complete()


def test_complete_outranks_the_budget_stop():
    records = [rec(PLAIN_STEP, 1), verified(PLAIN_STEP, 2)]

    assert iterations_used(read([PLAIN_STEP], records=records)) == iteration_budget([PLAIN_STEP])
    assert act([PLAIN_STEP], records=records) == Complete()


def test_a_plan_with_no_steps_is_complete():
    assert act([]) == Complete()


def test_a_human_stop_outranks_the_budget_stop():
    action = act(SPENT_PLAN, records=SPENT)

    assert (action.cause, action.step) == ("attempts-exhausted", "1")


def test_the_budget_stop_outranks_a_spawn():
    old = [one(IMPL, FILES, "Original wording.", number=n) for n in "12"]
    new = [one(IMPL, FILES, "Revised wording.", number=n) for n in "12"]
    records = [rec(step, n) for step in old for n in (1, 2)]

    assert isinstance(act(new, records=records), Stop)
    assert isinstance(act(new, records=records[1:]), Spawn)


def test_a_spawn_is_the_last_resort():
    assert act([PLAIN_STEP]) == Spawn(PLAIN_STEP, RequestKey("1", 1, "implement", 1))


OUTSTANDING = {
    STEP + "1": OutstandingAttempt(1, "s1-a1-implement"),
    STEP + "2": OutstandingAttempt(1, "s2-a1-implement"),
}


def test_a_loop_state_defect_outranks_an_unnamed_attempts_line():
    action = act([PLAIN_STEP, SECOND], attempts=OUTSTANDING, unnamed=("count=2",))

    assert (action.cause, action.step) == ("loop-state-defect", None)


def test_an_unnamed_attempts_line_outranks_a_dependency_defect():
    plan = steps_of(block("1", IMPL, annotations=" [depends-on: 9]"))

    action = act(plan, unnamed=("count=2",))

    assert (action.cause, action.step) == ("unnamed-attempts", None)


def test_a_dependency_defect_outranks_the_budget_and_a_spawn():
    plan = steps_of(block("1", IMPL, annotations=" [depends-on: 9]"))

    action = act(plan)

    assert (action.cause, action.step) == ("dependency-defect", "1")
    assert "9" in action.evidence


def test_the_stop_of_the_selected_step_comes_before_a_stuck_step_behind_it():
    plan = steps_of(block("1", IMPL, FILES), block("2", IMPL, annotations=" [depends-on: 9]"))

    action = act(plan, records=[rec(plan[0], 1), rec(plan[0], 2)])

    assert (action.cause, action.step) == ("attempts-exhausted", "1")


# --- what is spawned ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("records", "reviews", "attempts", "key", "reissued"),
    [
        pytest.param([], {}, None, RequestKey("1", 1, "implement"), False, id="fresh"),
        pytest.param(
            [rec(FORCED_STEP, 1)], {}, None, RequestKey("1", 2, "implement"), False, id="failed"
        ),
        pytest.param(
            [],
            {},
            {STEP + "1": OutstandingAttempt(1, "s1-a1-implement")},
            RequestKey("1", 1, "implement"),
            True,
            id="running-reissues-the-wip-request",
        ),
        pytest.param(
            [verified(FORCED_STEP)],
            {},
            None,
            RequestKey("1", 1, "review", 1, 1),
            False,
            id="review",
        ),
        pytest.param(
            [verified(FORCED_STEP)],
            {"1": PARTIAL},
            None,
            RequestKey("1", 1, "review", 1, 1),
            True,
            id="requested-review-reissues",
        ),
        pytest.param(
            [verified(FORCED_STEP), reviewed(FORCED_STEP)],
            {"1": REVISE},
            None,
            RequestKey("1", 1, "revise", 1, 1),
            False,
            id="revision",
        ),
        pytest.param(
            [verified(FORCED_STEP), reviewed(FORCED_STEP), revised(FORCED_STEP)],
            {"1": REVISE},
            None,
            RequestKey("1", 1, "review", 1, 2),
            False,
            id="second-review",
        ),
        pytest.param(
            [rec(FORCED_STEP, 1), verified(FORCED_STEP, 2)],
            {},
            None,
            RequestKey("1", 2, "review", 1, 1),
            False,
            id="a-review-carries-the-attempt-that-verified",
        ),
    ],
)
def test_the_selected_step_is_spawned_with_the_request_its_state_calls_for(
    records, reviews, attempts, key, reissued
):
    action = act(PLAN, attempts=attempts, records=records, reviews=reviews)

    assert action == Spawn(FORCED_STEP, key, reissued)


def test_a_revised_step_is_spawned_in_a_fresh_series_whose_request_id_says_so():
    original = one(IMPL, FILES, "Original wording.")
    revised_step = one(IMPL, FILES, "Revised wording.")
    records = [rec(original, 1), rec(original, 2)]

    action = act([revised_step, SECOND], records=records)

    assert action.key.id == "s1-p2-a1-implement"


# --- the stops, that they persist while their evidence holds and how each clears ---------------

REVISED_PLAN_STEP = one(IMPL, FILES, "Revised wording.")
EXHAUSTED_RECORDS = [rec(PLAIN_STEP, 1), rec(PLAIN_STEP, 2)]
TWO_STEPS = [PLAIN_STEP, SECOND]
PLAN_WITH_OTHER = steps_of(block("1", OTHER, FILES), block("2", IMPL))
REVIEWED_ONCE = [verified(FORCED_STEP), reviewed(FORCED_STEP)]
REVISED_TWICE = [*REVIEWED_ONCE, revised(FORCED_STEP), reviewed(FORCED_STEP)]
REVISION_FAILED = [*REVIEWED_ONCE, revised(FORCED_STEP, ok=False)]
NEXT_IMPLEMENT = Spawn(PLAIN_STEP, RequestKey("1", 1, "implement", 1))
SECOND_IMPLEMENT = Spawn(SECOND, RequestKey("2", 1, "implement", 1))
FRESH_SERIES = Spawn(REVISED_PLAN_STEP, RequestKey("1", 1, "implement", 2))
ONE_OUTSTANDING = {STEP + "1": OutstandingAttempt(1, "s1-a1-implement")}


@pytest.mark.parametrize(
    ("plan", "given", "cause", "step"),
    [
        pytest.param(
            TWO_STEPS, {"records": EXHAUSTED_RECORDS}, "attempts-exhausted", "1", id="exhausted"
        ),
        pytest.param(
            TWO_STEPS,
            {"records": [rec(PLAIN_STEP, 1, stop="blocked")]},
            "blocked-marker",
            "1",
            id="blocked",
        ),
        pytest.param(
            TWO_STEPS,
            {"records": [rec(PLAIN_STEP, 1, stop="conflict")]},
            "conflict-marker",
            "1",
            id="conflict",
        ),
        pytest.param(
            TWO_STEPS,
            {"verdicts": [verdict("1", "unknown", evidence="ambiguous")]},
            "human-verdict",
            "1",
            id="human-verdict",
        ),
        pytest.param(PLAN_WITH_OTHER, {}, "not-driven", "1", id="not-driven"),
        pytest.param(
            PLAN,
            {"records": REVISED_TWICE, "reviews": {"1": REVISE}},
            "review-revised-twice",
            "1",
            id="revised-twice",
        ),
        pytest.param(
            PLAN,
            {"records": REVIEWED_ONCE, "reviews": {"1": PARTIAL}},
            "review-unfinished",
            "1",
            id="unfinished",
        ),
        pytest.param(
            PLAN,
            {"records": REVISION_FAILED, "reviews": {"1": REVISE}},
            "revision-failed",
            "1",
            id="revision-failed",
        ),
        pytest.param(TWO_STEPS, {"unnamed": ("count=2",)}, "unnamed-attempts", None, id="unnamed"),
        pytest.param(
            TWO_STEPS, {"attempts": OUTSTANDING}, "loop-state-defect", None, id="two-outstanding"
        ),
        pytest.param(
            [PLAIN_STEP],
            {"attempts": {STEP + "1": OutstandingAttempt(1, "s9-a1-implement")}},
            "loop-state-defect",
            None,
            id="a-wip-request-the-series-does-not-derive",
        ),
    ],
)
def test_each_stop_names_its_cause_and_step_and_holds_while_its_evidence_holds(
    plan, given, cause, step
):
    first = act(plan, **given)

    assert (first.cause, first.step) == (cause, step)
    assert act(plan, **given) == first


@pytest.mark.parametrize(
    ("plan", "given", "cleared"),
    [
        pytest.param(
            [REVISED_PLAN_STEP, SECOND],
            {"records": EXHAUSTED_RECORDS},
            FRESH_SERIES,
            id="exhausted-clears-on-a-plan-revision",
        ),
        pytest.param(
            [REVISED_PLAN_STEP, SECOND],
            {"records": [rec(PLAIN_STEP, 1, stop="blocked")]},
            FRESH_SERIES,
            id="marked-clears-on-a-plan-revision",
        ),
        pytest.param(
            TWO_STEPS,
            {"verdicts": [verdict("1", "pending")]},
            NEXT_IMPLEMENT,
            id="a-human-verdict-clears-when-ground-truth-changes",
        ),
        pytest.param(
            PLAN_WITH_OTHER,
            {"verdicts": done("1")},
            Spawn(PLAN_WITH_OTHER[1], RequestKey("2", 1, "implement", 1)),
            id="not-driven-clears-when-the-step-is-done-outside",
        ),
        pytest.param(
            PLAN,
            {"records": REVISED_TWICE, "reviews": {"1": ACCEPT}},
            SECOND_IMPLEMENT,
            id="revised-twice-clears-when-the-file-reads-accept",
        ),
        pytest.param(
            PLAN,
            {"records": REVIEWED_ONCE, "reviews": {"1": ACCEPT}},
            SECOND_IMPLEMENT,
            id="unfinished-clears-when-the-file-reads-accept",
        ),
        pytest.param(
            PLAN,
            {"records": REVIEWED_ONCE, "reviews": {"1": REVISE}},
            Spawn(FORCED_STEP, RequestKey("1", 1, "revise", 1, 1)),
            id="unfinished-clears-when-the-file-carries-a-revise",
        ),
        pytest.param(
            PLAN,
            {"records": REVISION_FAILED, "reviews": {"1": ACCEPT}},
            SECOND_IMPLEMENT,
            id="revision-failed-clears-when-the-file-reads-accept",
        ),
        pytest.param(
            TWO_STEPS,
            {"attempts": ONE_OUTSTANDING},
            Spawn(PLAIN_STEP, RequestKey("1", 1, "implement", 1), True),
            id="two-outstanding-clears-when-one-line-is-removed",
        ),
        pytest.param(TWO_STEPS, {}, NEXT_IMPLEMENT, id="unnamed-clears-when-the-line-is-removed"),
    ],
)
def test_each_stop_clears_when_the_evidence_that_holds_it_changes(plan, given, cleared):
    assert act(plan, **given) == cleared


def test_a_dependency_defect_names_each_stuck_step_and_clears_when_the_plan_is_corrected():
    stuck = steps_of(block("1", IMPL, annotations=" [depends-on: 9]"))
    fixed = steps_of(block("1", IMPL))

    assert act(stuck).cause == "dependency-defect"
    assert isinstance(act(fixed), Spawn)


def test_an_exhausted_stop_carries_its_attempts_and_the_replan_text_from_wip():
    attempts = {STEP + "1": Attempt(2, replan="split the step")}

    stop = act(TWO_STEPS, records=EXHAUSTED_RECORDS, attempts=attempts)

    assert (stop.attempts, stop.replan_request) == (tuple(EXHAUSTED_RECORDS), "split the step")


def test_an_exhausted_stop_without_a_replan_text_falls_back_to_its_own_evidence():
    stop = act(TWO_STEPS, records=EXHAUSTED_RECORDS)

    assert stop.replan_request == stop.evidence


def test_an_exhausted_line_written_without_the_loop_hands_the_reconcilers_evidence_back():
    given = {"verdicts": [verdict("1", "attempts-exhausted", evidence="2 of 2 used")]}

    stop = act(TWO_STEPS, **given)

    assert (stop.cause, stop.evidence, stop.replan_request) == (
        "attempts-exhausted",
        "2 of 2 used",
        "2 of 2 used",
    )


def test_the_budget_stop_belongs_to_no_step():
    old = [one(IMPL, FILES, "Original wording.", number=n) for n in "12"]
    new = [one(IMPL, FILES, "Revised wording.", number=n) for n in "12"]
    records = [rec(step, n) for step in old for n in (1, 2)]

    stop = act(new, records=records)

    assert (stop.cause, stop.step) == (BUDGET_CAUSE, None)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        pytest.param(lambda: Stop("nope", "1", "x"), "not a stop cause", id="unknown-cause"),
        pytest.param(
            lambda: Stop("attempts-exhausted", None, "x", (), "r"), "disagree", id="step-missing"
        ),
        pytest.param(lambda: Stop(BUDGET_CAUSE, "1", "x"), "disagree", id="budget-names-a-step"),
        pytest.param(
            lambda: Stop("human-verdict", "1", "x", (), "r"), "replan request", id="stray-replan"
        ),
        pytest.param(
            lambda: Stop("attempts-exhausted", "1", "x"), "replan request", id="missing-replan"
        ),
    ],
)
def test_a_stop_cannot_be_built_against_its_invariants(build, message):
    with pytest.raises(ValueError, match=message):
        build()


def test_the_causes_are_the_closed_set_the_stop_texts_cover():
    assert set(HUMAN_CAUSES) | {BUDGET_CAUSE} == set(_ACTIONS)
    assert len(HUMAN_CAUSES) == len(set(HUMAN_CAUSES)) == 12


# --- A marked series is done only when its review is satisfied -------------------------------

BLOCKED_REVISION = [
    verified(FORCED_STEP),
    reviewed(FORCED_STEP),
    rec(FORCED_STEP, 1, "revise", stop="blocked"),
]


def test_a_revision_that_returned_blocked_after_a_verified_implement_is_not_done():
    state = step_series(FORCED_STEP, read(PLAN, records=BLOCKED_REVISION))

    assert (type(state), type(state.review), is_done(state)) == (Marked, RevisionFailed, False)


def test_the_marker_stops_the_loop_apart_from_the_done_reading():
    stop = act(PLAN, records=BLOCKED_REVISION)

    assert (stop.cause, stop.step) == ("blocked-marker", "1")


@pytest.mark.parametrize(
    ("steps", "reviews", "done"),
    [
        pytest.param([FORCED_STEP], {"1": ACCEPT}, True, id="review-accepted"),
        pytest.param([PLAIN_STEP], {}, True, id="no-review-required"),
        pytest.param([FORCED_STEP], {"1": REVISE}, False, id="review-asked-for-revision"),
    ],
)
def test_a_marked_series_with_verified_work_is_done_exactly_when_its_review_is_satisfied(
    steps, reviews, done
):
    step = steps[0]
    returned = rec(step, 1, "implement", stop="blocked", verdict="verified-complete")
    asked = [reviewed(step)] if step is FORCED_STEP else []

    state = step_series(step, read(steps, records=[returned, *asked], reviews=reviews))

    assert (isinstance(state, Marked), is_done(state)) == (True, done)


# --- A disturbed tree keeps the loop stopped while its snapshot file stays -------------------


def disturbed(*records, snapshots):
    return replace(read(PLAN, records=records), snapshots=tuple(snapshots))


def test_the_snapshot_of_the_latest_request_of_a_step_stops_the_loop_with_its_evidence():
    first = rec(FORCED_STEP)

    stop = next_action(disturbed(first, snapshots=[first.request]))

    assert (stop.cause, stop.step, stop.attempts) == ("commit-disturbed-tree", "1", (first,))
    assert first.request in stop.evidence
    assert f"TREE_SNAPSHOT_{first.request}.patch" in stop.evidence


@pytest.mark.parametrize(
    "held",
    [
        pytest.param(lambda first, second: [], id="no-snapshot"),
        pytest.param(lambda first, second: [first.request], id="an-earlier-request"),
        pytest.param(lambda first, second: ["s9-a1-implement"], id="an-unknown-request"),
    ],
)
def test_a_snapshot_of_an_earlier_request_or_none_stops_nothing(held):
    first, second = rec(FORCED_STEP, 1), verified(FORCED_STEP, 2)

    action = next_action(disturbed(first, second, snapshots=held(first, second)))

    assert isinstance(action, Spawn)


def test_the_snapshot_stop_comes_before_a_marker():
    marked = rec(FORCED_STEP, 1, stop="blocked")

    stop = next_action(disturbed(marked, snapshots=[marked.request]))

    assert stop.cause == "commit-disturbed-tree"


# --- the range a review reads, and the requests a review leaves outstanding --------------------

FIRST_SHA, SECOND_SHA, THIRD_SHA = "a" * 40, "b" * 40, "c" * 40


def committed(record, sha):
    return replace(record, commit=sha)


def ranged(*records, step=FORCED_STEP):
    return review_range(read([step], records=records), step)


def test_a_review_reads_from_before_the_first_commit_of_the_work_to_the_last():
    work = [committed(verified(FORCED_STEP), FIRST_SHA)]

    assert ranged(*work) == (f"{FIRST_SHA}^", FIRST_SHA)


def test_the_range_spans_the_commits_of_the_implement_and_the_revisions_of_the_series():
    work = [
        committed(verified(FORCED_STEP), FIRST_SHA),
        reviewed(FORCED_STEP),
        committed(revised(FORCED_STEP), SECOND_SHA),
    ]

    assert ranged(*work) == (f"{FIRST_SHA}^", SECOND_SHA)


def test_a_failed_attempt_and_a_review_add_no_commit_to_the_range():
    work = [rec(FORCED_STEP, 1), committed(verified(FORCED_STEP, 2), FIRST_SHA)]
    work.append(committed(reviewed(FORCED_STEP), THIRD_SHA))

    assert ranged(*work) == (f"{FIRST_SHA}^", FIRST_SHA)


def test_work_that_holds_no_commit_leaves_the_review_no_range():
    assert ranged(verified(FORCED_STEP)) is None


def test_the_work_of_an_earlier_series_is_not_in_the_range():
    original = one(IMPL, FILES, FORCED, "Original wording.")
    revised_step = one(IMPL, FILES, FORCED, "Revised wording.")
    records = [
        committed(verified(original), FIRST_SHA),
        committed(verified(revised_step), SECOND_SHA),
    ]

    assert ranged(*records, step=revised_step) == (f"{SECOND_SHA}^", SECOND_SHA)
    assert series_work(read([revised_step], records=records), revised_step) == (records[1],)


def test_a_review_that_is_due_over_work_with_a_commit_is_issued():
    inputs = read(PLAN, records=[committed(verified(FORCED_STEP), FIRST_SHA)])

    assert issuable_action(inputs) == Spawn(FORCED_STEP, RequestKey("1", 1, "review", 1, 1))


def test_a_review_that_is_due_over_work_with_no_commit_is_a_stop_not_a_spawn():
    inputs = read(PLAN, records=[verified(FORCED_STEP)])

    stop = issuable_action(inputs)

    assert (stop.cause, stop.step) == ("loop-state-defect", None)
    assert "no commit holds its work" in stop.evidence


def test_an_action_that_is_not_a_review_is_the_next_action_whatever_the_commits():
    inputs = read(PLAN)

    assert issuable_action(inputs) == next_action(inputs)
    assert next_action(inputs) == Spawn(FORCED_STEP, RequestKey("1", 1, "implement", 1))


@pytest.mark.parametrize("request_id", ["s1-a1-review-r1", "s1-a1-revise-r1", "s1-a1-implement"])
def test_an_outstanding_request_of_any_kind_naming_the_step_is_reissued(request_id):
    records = [committed(verified(FORCED_STEP), FIRST_SHA)]
    waiting = {STEP + "1": OutstandingAttempt(1, request_id)}

    action = act(PLAN, records=records, attempts=waiting)

    assert (action.key.id, action.reissued) == (request_id, True)


@pytest.mark.parametrize(
    "request_id", ["s2-a1-review-r1", "s1-p2-a1-review-r1", "s1-a1-review", "review"]
)
def test_an_outstanding_request_naming_another_step_or_series_or_nothing_is_a_defect(request_id):
    records = [committed(verified(FORCED_STEP), FIRST_SHA)]
    waiting = {STEP + "1": OutstandingAttempt(1, request_id)}

    action = act(PLAN, records=records, attempts=waiting)

    assert (action.cause, action.step) == ("loop-state-defect", None)
