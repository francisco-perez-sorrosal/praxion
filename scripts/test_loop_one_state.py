"""Tests for the one word a step's series state is shown and acted on by
(``scripts/_step_loop_state.py``, ``step_state_word``).

Every case passes plan text, ledger records and reconciler verdict dicts in and reads the word
out: no file is written, no process runs, nothing is mocked.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import get_args

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import GoalBudget  # noqa: E402
from _loop_state_testkit import (  # noqa: E402
    ACCEPT,
    FORCED_STEP,
    PARTIAL,
    PLAIN_STEP,
    PLAN,
    REVISE,
    one,
    read,
    rec,
    reviewed,
    revised,
    verdict,
    verified,
)
from _step_loop_action import Complete, Spawn, Stop, next_action  # noqa: E402
from _step_loop_state import (  # noqa: E402
    DoneOutside,
    Exhausted,
    Failed,
    Fresh,
    HumanVerdict,
    Marked,
    NotDriven,
    Running,
    Series,
    StateWord,
    Verified,
    is_done,
    step_series,
    step_state_word,
)


def action_cause(acted):
    """What `next` acts on: the kind of the request it issues, or the cause it stops on."""
    return acted.key.kind if isinstance(acted, Spawn) else acted.cause


STEP_ONE = PLAIN_STEP
FIRST, SECOND = rec(STEP_ONE, 1), rec(STEP_ONE, 2)
CLOSED_SET = {
    "pending",
    "in-flight",
    "verified-complete",
    "failed",
    "marked",
    "attempts-exhausted",
    "human-verdict",
}

STATES = {
    "fresh": (Fresh(1), "pending"),
    "not driven": (NotDriven("orchestrator"), "pending"),
    "running": (Running(1, "s1-a1-implement"), "in-flight"),
    "failed": (Failed(1, (FIRST,)), "failed"),
    "exhausted": (Exhausted((FIRST, SECOND)), "attempts-exhausted"),
    "marked": (Marked("CONFLICT", (FIRST,)), "marked"),
    "verified": (Verified(1, 1, None), "verified-complete"),
    "done outside": (DoneOutside(), "verified-complete"),
    "reconciler human word": (HumanVerdict("unknown", "no evidence"), "human-verdict"),
    "a line written without the loop": (
        HumanVerdict("attempts-exhausted", "the line says so"),
        "attempts-exhausted",
    ),
}


@pytest.mark.parametrize("name", sorted(STATES))
def test_a_series_state_reads_as_its_one_word(name):
    state, word = STATES[name]

    assert step_state_word(state) == word


def test_the_closed_set_of_words_is_the_one_the_type_declares():
    assert set(get_args(StateWord)) == CLOSED_SET


def test_every_state_kind_has_a_case_and_every_case_gives_a_word_of_the_closed_set():
    assert {type(state) for state, _ in STATES.values()} == set(get_args(Series))
    assert {word for _, word in STATES.values()} == CLOSED_SET


def test_a_stalled_goal_reads_as_attempts_exhausted_though_its_stop_names_the_stall():
    goal = one("**Assignee**: implementer", "**Iterations**: 6")
    stalled = Exhausted((rec(goal, 1), rec(goal, 2)), GoalBudget(6))

    assert step_state_word(stalled) == "attempts-exhausted"


def test_the_reconciler_word_never_reaches_the_series_word():
    """A marked return whose check passes is `verified-complete` to the reconciler."""
    marked = rec(STEP_ONE, 1, verdict="verified-complete", stop="conflict")
    inputs = read([STEP_ONE], records=[marked], verdicts=[verdict("1", "verified-complete")])

    state = step_series(STEP_ONE, inputs)

    assert (type(state), step_state_word(state)) == (Marked, "marked")


def test_a_verified_record_reads_as_verified_complete():
    inputs = read(
        [STEP_ONE], records=[verified(STEP_ONE)], verdicts=[verdict("1", "verified-complete")]
    )

    assert step_state_word(step_series(STEP_ONE, inputs)) == "verified-complete"


SECOND_REVIEW = rec(FORCED_STEP, 1, "review", verdict="verified-complete", round_=2)
VERIFIED_AND_REVIEWED = [verified(FORCED_STEP), reviewed(FORCED_STEP)]


@pytest.mark.parametrize(
    ("records", "reviews", "word", "acts"),
    [
        pytest.param([verified(FORCED_STEP)], {}, "pending", "review", id="review-due"),
        pytest.param([verified(FORCED_STEP)], {"1": PARTIAL}, "in-flight", "review", id="asked"),
        pytest.param(VERIFIED_AND_REVIEWED, {"1": REVISE}, "pending", "revise", id="revise-due"),
        pytest.param(VERIFIED_AND_REVIEWED, {}, "human-verdict", "review-unfinished", id="no-file"),
        pytest.param(
            [*VERIFIED_AND_REVIEWED, revised(FORCED_STEP, ok=False)],
            {"1": REVISE},
            "human-verdict",
            "revision-failed",
            id="revision-failed",
        ),
        pytest.param(
            [*VERIFIED_AND_REVIEWED, revised(FORCED_STEP), SECOND_REVIEW],
            {"1": REVISE},
            "human-verdict",
            "review-revised-twice",
            id="revised-twice",
        ),
    ],
)
def test_a_verified_step_whose_review_is_not_satisfied_is_not_shown_complete(
    records, reviews, word, acts
):
    inputs = read(PLAN, records=records, reviews=reviews)

    acted = next_action(inputs)

    assert step_state_word(step_series(FORCED_STEP, inputs)) == word
    assert action_cause(acted) == acts


@pytest.mark.parametrize(
    ("step", "records", "reviews"),
    [
        pytest.param(PLAIN_STEP, [verified(PLAIN_STEP)], {}, id="no-review-required"),
        pytest.param(FORCED_STEP, VERIFIED_AND_REVIEWED, {"1": ACCEPT}, id="review-accepted"),
    ],
)
def test_a_verified_step_with_its_review_satisfied_is_shown_complete(step, records, reviews):
    inputs = read([step], records=records, reviews=reviews)

    assert step_state_word(step_series(step, inputs)) == "verified-complete"


def test_a_done_marked_step_that_is_the_last_left_is_shown_complete_as_next_answers():
    """A marked return commits nothing; a verified record holding a commit completes the step."""
    committed = replace(verified(STEP_ONE), commit="abc1234")
    inputs = read([STEP_ONE], records=[committed, rec(STEP_ONE, 2, stop="blocked")])

    state = step_series(STEP_ONE, inputs)

    assert (type(state), is_done(state)) == (Marked, True)
    assert step_state_word(state) == "verified-complete"
    assert isinstance(next_action(inputs), Complete)


def test_a_marked_step_stops_the_loop_with_a_cause_that_names_the_marker_status_shows():
    inputs = read([STEP_ONE], records=[rec(STEP_ONE, 1, stop="blocked")])

    stopped = next_action(inputs)

    assert isinstance(stopped, Stop)
    assert step_state_word(step_series(STEP_ONE, inputs)) == "marked"
    assert stopped.cause == "blocked-marker"


def test_a_spent_ordinary_step_stops_with_the_cause_status_shows():
    inputs = read([STEP_ONE], records=[FIRST, SECOND])

    stopped = next_action(inputs)

    assert isinstance(stopped, Stop)
    assert step_state_word(step_series(STEP_ONE, inputs)) == stopped.cause


def test_a_conflicting_attempt_counts_as_one_attempt_of_a_marked_series():
    inputs = read([STEP_ONE], records=[rec(STEP_ONE, 1, stop="conflict")])

    state = step_series(STEP_ONE, inputs)

    assert isinstance(state, Marked)
    assert len(state.attempts) == 1
