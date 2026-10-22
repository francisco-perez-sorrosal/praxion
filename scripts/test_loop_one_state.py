"""Tests for the one word a step's series state is shown and acted on by
(``scripts/_step_loop_state.py``, ``step_state_word``).

Every case passes plan text, ledger records and reconciler verdict dicts in and reads the word
out: no file is written, no process runs, nothing is mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import GoalBudget  # noqa: E402
from _loop_state_testkit import PLAIN_STEP, one, read, rec, verdict, verified  # noqa: E402
from _step_loop_action import Stop, next_action  # noqa: E402
from _step_loop_state import (  # noqa: E402
    DoneOutside,
    Exhausted,
    Failed,
    Fresh,
    HumanVerdict,
    Marked,
    NotDriven,
    Running,
    Verified,
    step_series,
    step_state_word,
)

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


def test_every_word_a_state_gives_is_in_the_closed_set():
    assert {word for _, word in STATES.values()} == CLOSED_SET


def test_a_stalled_goal_reads_as_exhausted_like_the_reconciler_and_the_stop_say_it_ended():
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
