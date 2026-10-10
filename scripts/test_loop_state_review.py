"""Tests for the step-loop driver's review trigger and review state
(``scripts/_step_loop_review.py`` and the review half of ``scripts/_step_loop_state.py``).

Every case passes plan text, WIP attempt readings, ledger records, reconciler verdict dicts and
review-file text in and reads values out: no file is written, no process runs, nothing is mocked.
The iteration budget, the stop precedence and the stops are in ``test_loop_state_bound.py``.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import OutstandingAttempt  # noqa: E402
from _loop_state_testkit import (  # noqa: E402
    ACCEPT,
    FILES,
    FORCED,
    FORCED_STEP,
    IMPL,
    OFF,
    PARTIAL,
    PLAIN_STEP,
    PLAN,
    REVISE,
    RISKY,
    STEP,
    act,
    block,
    one,
    read,
    rec,
    reviewed,
    revised,
    steps_of,
    verified,
)
from _step_loop_action import Spawn, issuable_action, next_action  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
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
    Marked,
    Next,
    Verified,
    is_done,
    review_range,
    select_step,
    series_work,
    step_series,
)

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
