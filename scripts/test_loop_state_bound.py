"""Tests for the step-loop driver's iteration budget, stop precedence and stops
(``scripts/_step_loop_action.py`` and the stop half of ``scripts/_step_loop_state.py``).

Every case passes plan text, WIP attempt readings, ledger records and reconciler verdict dicts
in and reads values out: no file is written, no process runs, nothing is mocked. The shared
builders live in ``_loop_state_testkit.py``; the review trigger and state are in
``test_loop_state_review.py``.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_fields import ATTEMPT_CAP, Attempt, OutstandingAttempt  # noqa: E402
from _loop_state_testkit import (  # noqa: E402
    ACCEPT,
    FILES,
    FORCED,
    FORCED_STEP,
    IMPL,
    OFF,
    OTHER,
    PARTIAL,
    PLAIN_STEP,
    PLAN,
    REVISE,
    RISKY,
    SECOND,
    STEP,
    act,
    block,
    done,
    one,
    read,
    rec,
    reviewed,
    revised,
    steps_of,
    verdict,
    verified,
)
from _step_loop_action import (  # noqa: E402
    BUDGET_CAUSE,
    HUMAN_CAUSES,
    Complete,
    Spawn,
    Stop,
    iteration_budget,
    iterations_used,
    next_action,
)
from _step_loop_render import _ACTIONS, RequestKey  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

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
    assert len(HUMAN_CAUSES) == len(set(HUMAN_CAUSES)) == 13


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
