"""A move's verdict is the shared flip rule over its pairs; the sensitivity figure is exact."""

from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction
from math import comb

import pytest

from praxion_evals.adherence.model import Counts, Measured, Passed
from praxion_evals.adherence.moves.model import Arrived, NeverArrived, Unknown
from praxion_evals.adherence.moves.verdict import (
    FloorTally,
    Measurement,
    MovePair,
    Sensitivity,
    Side,
    move_verdict,
    sensitivity,
)

MESSAGE, STAGING = "commit-message-form", "staging-discipline"
TARGET = 20
OK = {MESSAGE: "passed", STAGING: "passed"}
LEAN_BREAKS_MESSAGE = {MESSAGE: "failed", STAGING: "passed"}


def wire_side(final, history=None, arrivals=None):
    side = {"final": dict(final)}
    if history is not None:
        side["history"] = history
    if arrivals is not None:
        side["arrivals"] = arrivals
    return side


def wire_pairs(count, full, lean, start=0, kind="managed"):
    return [
        {
            "task_id": f"{kind}-task-{start + i:03d}",
            "fixture_kind": kind,
            "full": wire_side(full),
            "lean": wire_side(lean),
        }
        for i in range(count)
    ]


def measurement(pairs, floor=(), target=TARGET, restriction=None):
    return Measurement.from_json(
        {
            "checks": [MESSAGE, STAGING],
            "margin_pp": 10.0,
            "target_pairs": target,
            "kind_restriction": restriction,
            "pairs": pairs,
            "floor": [None if s is None else wire_side(s) for s in floor],
        }
    )


# 7 discordant pairs on the message check (4 lean-only failures, 3 full-only), 2 on staging.
DISCORDANT = (
    wire_pairs(4, OK, LEAN_BREAKS_MESSAGE)
    + wire_pairs(3, LEAN_BREAKS_MESSAGE, OK, start=10, kind="unmanaged")
    + wire_pairs(1, OK, {MESSAGE: "passed", STAGING: "failed"}, start=20)
    + wire_pairs(1, {MESSAGE: "passed", STAGING: "failed"}, OK, start=30, kind="unmanaged")
    + wire_pairs(15, OK, OK, start=40)
)


def expected_allowance(discordant):
    """The smallest net discordance the exact one-sided test cannot call a regression, at 95%."""
    for allowance in range(discordant + 1):
        within = sum(comb(discordant, i) for i in range((discordant + allowance) // 2 + 1))
        if within >= 0.95 * 2**discordant:
            return allowance
    return discordant


# -- The wire form ------------------------------------------------------------------------------


def test_history_and_arrival_words_are_read_in_the_specifications_words():
    side = (
        Measurement.from_json(
            {
                "checks": [MESSAGE],
                "margin_pp": 10.0,
                "target_pairs": TARGET,
                "kind_restriction": None,
                "pairs": [
                    {
                        "task_id": "managed-task-000",
                        "fixture_kind": "managed",
                        "full": None,
                        "lean": wire_side(
                            {MESSAGE: "failed"},
                            history={MESSAGE: "right first time"},
                            arrivals={
                                MESSAGE: {
                                    "hook_context": "after execution",
                                    "gate_refusal": "never",
                                    "session_start": "unknown",
                                }
                            },
                        ),
                    }
                ],
                "floor": [],
            }
        )
        .pairs[0]
        .lean
    )

    assert side is not None
    assert side.history == {MESSAGE: "right_first_time"}
    assert side.arrivals[MESSAGE] == {
        "hook_context": Arrived("after execution"),
        "gate_refusal": NeverArrived(),
        "session_start": Unknown(),
    }


@pytest.mark.parametrize(
    ("spoken", "named"),
    [
        ("not repaired", "not_repaired"),
        ("action never taken", "never_taken"),
        ("never_taken", "never_taken"),
        ("repaired", "repaired"),
    ],
)
def test_a_history_word_means_the_same_spoken_or_named(spoken, named):
    pair = wire_pairs(1, OK, OK)[0]
    pair["lean"] = wire_side(OK, history={MESSAGE: spoken})

    parsed = measurement([pair]).pairs[0].lean

    assert parsed is not None
    assert parsed.history[MESSAGE] == named


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ({"final": {MESSAGE: "maybe"}}, "passed or failed"),
        ({"final": {MESSAGE: "passed"}, "history": {MESSAGE: "eventually"}}, "history outcome"),
        (
            {"final": {MESSAGE: "passed"}, "arrivals": {MESSAGE: {"carrier_pigeon": "never"}}},
            "delivery channel",
        ),
        (
            {"final": {MESSAGE: "passed"}, "arrivals": {MESSAGE: {"hook_context": "soon"}}},
            "arrival timing",
        ),
        ({"final": {}}, "at least one final state"),
    ],
)
def test_wire_values_outside_the_closed_sets_are_refused(bad, reason):
    pair = wire_pairs(1, OK, OK)[0]
    pair["lean"] = bad

    with pytest.raises(ValueError, match=reason):
        measurement([pair])


def test_an_unknown_fixture_kind_is_refused():
    with pytest.raises(ValueError, match="fixture kind"):
        measurement(wire_pairs(1, OK, OK, kind="exotic"))


# -- The verdict ---------------------------------------------------------------------------------


def test_a_lean_arm_that_fails_more_pairs_than_its_allowance_regresses():
    verdict = move_verdict(
        measurement(wire_pairs(12, OK, LEAN_BREAKS_MESSAGE) + wire_pairs(12, OK, OK, start=20))
    )

    assert verdict.check_verdicts == {MESSAGE: "regression", STAGING: "no regression"}


def test_a_lean_arm_within_its_allowance_does_not_regress():
    verdict = move_verdict(measurement(DISCORDANT))

    assert verdict.check_verdicts == {MESSAGE: "no regression", STAGING: "no regression"}


@pytest.mark.parametrize("history", ["right first time", "repaired", "not repaired"])
def test_history_never_changes_the_verdict(history):
    pairs = wire_pairs(12, OK, LEAN_BREAKS_MESSAGE) + wire_pairs(12, OK, OK, start=20)
    for pair in pairs:
        pair["lean"]["history"] = {MESSAGE: history, STAGING: history}

    assert move_verdict(measurement(pairs)).check_verdicts[MESSAGE] == "regression"


def test_each_allowance_is_the_exact_quantile_at_its_own_checks_discordant_count():
    verdict = move_verdict(measurement(DISCORDANT))

    assert verdict.discordant == {MESSAGE: 7, STAGING: 2}
    assert verdict.allowances == {MESSAGE: expected_allowance(7), STAGING: expected_allowance(2)}
    assert (expected_allowance(7), expected_allowance(2)) == (5, 2)


def test_floor_sessions_move_no_allowance_and_enter_no_pair():
    floor = [{MESSAGE: "failed", STAGING: "failed"}] * 8

    with_floor = move_verdict(measurement(DISCORDANT, floor=floor))
    without = move_verdict(measurement(DISCORDANT))

    assert with_floor == without


def test_a_pair_whose_lean_session_errored_is_counted_as_a_lean_failure_and_is_not_complete():
    pairs = [*DISCORDANT, {**wire_pairs(1, OK, OK, start=90)[0], "lean": None}]

    verdict = move_verdict(measurement(pairs))

    assert verdict.complete_pairs == 24
    assert verdict.discordant[MESSAGE] == 8


def test_a_pair_whose_full_session_errored_enters_no_count():
    pairs = [*DISCORDANT, {**wire_pairs(1, OK, OK, start=90)[0], "full": None}]

    verdict = move_verdict(measurement(pairs))

    assert verdict.complete_pairs == 24
    assert verdict.discordant == {MESSAGE: 7, STAGING: 2}


def test_clearance_waits_for_the_target_number_of_complete_pairs():
    short = move_verdict(measurement(DISCORDANT, target=25))
    reached = move_verdict(measurement(DISCORDANT, target=24))

    assert (short.cleared, reached.cleared) == (None, True)


def test_a_regression_never_clears():
    regressing = wire_pairs(12, OK, LEAN_BREAKS_MESSAGE) + wire_pairs(12, OK, OK, start=20)

    assert move_verdict(measurement(regressing)).cleared is False


def test_an_allowance_wider_than_the_margin_leaves_the_check_not_covered():
    wide = wire_pairs(8, OK, LEAN_BREAKS_MESSAGE) + wire_pairs(7, LEAN_BREAKS_MESSAGE, OK, start=10)
    wide += wire_pairs(9, OK, OK, start=30)

    verdict = move_verdict(measurement(wide))

    assert verdict.check_verdicts[MESSAGE] == "no regression"
    assert MESSAGE in verdict.not_covered


def test_no_complete_pair_leaves_nothing_to_show():
    verdict = move_verdict(measurement([]))

    assert (verdict.check_verdicts, verdict.complete_pairs, verdict.cleared) == ({}, 0, None)


def test_the_verdict_serialises_as_plain_values():
    plain = asdict(move_verdict(measurement(DISCORDANT)))

    assert plain["counts"][MESSAGE]["lean_failed_only"] == 4


# -- Floor tallies and the sensitivity figure ---------------------------------------------------


def test_an_errored_floor_session_and_one_without_the_check_score_nothing():
    floor = [{MESSAGE: "failed"}, {MESSAGE: "passed"}, None, {STAGING: "failed"}]

    tally = measurement(DISCORDANT, floor=floor).floor_tally(MESSAGE)

    assert (tally.failures, tally.scored) == (1, 2)


def full_failing_once_in_24():
    return Counts(both_passed=23, lean_failed_only=0, lean_passed_only=1, both_failed=0)


def test_the_figure_is_the_target_times_the_floor_rate_less_the_full_rate():
    result = sensitivity(full_failing_once_in_24(), FloorTally(1, 8), TARGET, allowance=2)

    assert result is not None
    assert result.figure == TARGET * (Fraction(1, 8) - Fraction(1, 24)) == Fraction(5, 3)
    assert result.shown == "1.7"


def test_a_figure_that_shows_as_the_allowance_but_exceeds_it_is_read_as_exceeding():
    result = sensitivity(full_failing_once_in_24(), FloorTally(1, 7), TARGET, allowance=2)

    assert result is not None
    assert (result.shown, result.exceeds_allowance) == ("2.0", True)


def test_a_figure_below_the_allowance_does_not_exceed_it():
    result = sensitivity(full_failing_once_in_24(), FloorTally(1, 8), TARGET, allowance=2)

    assert result is not None
    assert result.exceeds_allowance is False


def test_a_figure_below_zero_is_shown_signed_and_exceeds_nothing():
    result = sensitivity(full_failing_once_in_24(), FloorTally(0, 8), TARGET, allowance=0)

    assert result is not None
    assert (result.shown, result.exceeds_allowance) == ("-0.8", False)


def test_a_figure_of_exactly_zero_exceeds_a_zero_allowance_by_nothing():
    result = sensitivity(full_failing_once_in_24(), FloorTally(3, 72), TARGET, allowance=0)

    assert result is not None
    assert (result.figure, result.shown, result.exceeds_allowance) == (0, "0.0", False)


def test_a_figure_that_rounds_to_zero_from_below_shows_unsigned():
    counts = Counts(both_passed=99, lean_failed_only=0, lean_passed_only=1, both_failed=0)

    result = sensitivity(counts, FloorTally(0, 100), target_pairs=1, allowance=0)

    assert result is not None
    assert result.shown == "0.0"


@pytest.mark.parametrize(("figure", "shown"), [(Fraction(1, 4), "0.3"), (Fraction(-1, 4), "-0.3")])
def test_a_half_rounds_away_from_zero(figure, shown):
    assert Sensitivity(figure, allowance=0).shown == shown


def test_no_figure_exists_without_a_scored_floor_session_or_a_usable_pair():
    counts = full_failing_once_in_24()

    assert sensitivity(counts, FloorTally(0, 0), TARGET, allowance=2) is None
    assert sensitivity(Counts(0, 0, 0, 0), FloorTally(1, 8), TARGET, allowance=2) is None


def test_the_figure_changes_no_verdict():
    blind = [{MESSAGE: "passed", STAGING: "passed"}] * 8
    seeing = [{MESSAGE: "failed", STAGING: "failed"}] * 8

    assert move_verdict(measurement(DISCORDANT, floor=blind)) == move_verdict(
        measurement(DISCORDANT, floor=seeing)
    )


def test_a_pair_reads_its_checks_as_final_state_outcomes():
    pair = MovePair("t", "managed", Side({MESSAGE: Passed()}, {}, {}), None)

    status = pair.as_pair().full

    assert isinstance(status, Measured)
    assert status.outcomes == {MESSAGE: Passed()}
