"""A role's paired verdicts follow the ratified flip rule.

A pair whose lean side errored while its full side did not counts as a lean
failure (the worst-case recount). A mechanical check regresses only when the lean
arm fails it on more pairs than the full arm plus that check's noise allowance:
the exact one-sided quantile of the net discordance at the check's own discordant
count in the run (a results file written before that method declares its allowance
instead). A judged check is non-inferior when the lean arm's pass rate over the
recounted pairs is no more than the declared margin below the full arm's -- a
point estimate -- with the one-sided interval on the paired difference reported
beside it and never deciding. The role's flip verdict is clear only when every
scored check holds, and it never covers a withheld check. A role that achieved
fewer complete pairs than the declared target is underpowered and gets no flip
verdict.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.adherence_eval import (
    CheckSpec,
    FlipSettings,
    errored_pairs,
    lean_errored_pairs,
    repeated,
    role_verdict,
)

DURABLE_OUTPUT = CheckSpec("C1", "mechanical")
SURFACED_ASSUMPTION = CheckSpec("C3", "judged")
FETCHED_CONTENT = CheckSpec("C6", "mechanical")
PASS, FAIL = "passed", "failed"


def test_a_mechanical_check_the_lean_arm_fails_on_more_pairs_than_its_own_discordance_allows_regresses():
    # Five discordant pairs, all lean-only: the exact allowance at five is three pairs.
    pairs = repeated(15, {"C1": PASS}, {"C1": PASS}) + repeated(5, {"C1": PASS}, {"C1": FAIL})

    verdict = role_verdict([DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20))

    assert verdict.check_verdicts["C1"] == "regression"
    assert verdict.flip == "not clear"


@pytest.mark.parametrize(
    "discordant",
    [
        pytest.param(({"C1": FAIL}, {"C1": FAIL}), id="both arms fail the same pairs"),
        pytest.param(({"C1": FAIL}, {"C1": PASS}), id="lean passes pairs full fails"),
    ],
)
def test_a_mechanical_check_the_lean_arm_passes_at_least_as_often_shows_no_regression(discordant):
    full, lean = discordant
    pairs = repeated(18, {"C1": PASS}, {"C1": PASS}) + repeated(2, full, lean)

    verdict = role_verdict([DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20))

    assert verdict.check_verdicts["C1"] == "no regression"


def test_a_judged_check_both_arms_pass_on_two_hundred_achieved_pairs_is_non_inferior_and_the_flip_clear():
    pairs = repeated(200, {"C1": PASS, "C3": PASS}, {"C1": PASS, "C3": PASS})

    verdict = role_verdict(
        [DURABLE_OUTPUT, SURFACED_ASSUMPTION], pairs, FlipSettings(required_pairs=20)
    )

    assert verdict.check_verdicts["C3"] == "non-inferior"
    assert "C3" in verdict.judged_intervals, "the judged check's interval is not reported"
    assert (verdict.underpowered, verdict.flip) == (False, "clear")


def test_a_judged_check_the_lean_arm_fails_twenty_points_more_often_is_inferior():
    pairs = repeated(160, {"C1": PASS, "C3": PASS}, {"C1": PASS, "C3": PASS}) + repeated(
        40, {"C1": PASS, "C3": PASS}, {"C1": PASS, "C3": FAIL}
    )

    verdict = role_verdict(
        [DURABLE_OUTPUT, SURFACED_ASSUMPTION], pairs, FlipSettings(required_pairs=200)
    )

    assert verdict.check_verdicts["C3"] == "inferior"
    assert verdict.flip == "not clear"


def test_a_withheld_check_is_listed_as_not_covered_and_never_scored():
    withheld = {"C1": PASS, "C6": "withheld"}
    pairs = repeated(20, withheld, withheld)

    verdict = role_verdict(
        [DURABLE_OUTPUT, FETCHED_CONTENT], pairs, FlipSettings(required_pairs=20)
    )

    assert verdict.not_covered == frozenset({"C6"})
    assert "C6" not in verdict.check_verdicts
    assert verdict.flip == "clear"


def test_errored_pairs_neither_count_as_complete_nor_against_the_role():
    pairs = repeated(20, {"C1": PASS}, {"C1": PASS}) + errored_pairs(5)

    verdict = role_verdict([DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20))

    assert verdict.complete_pairs == 20
    assert (verdict.underpowered, verdict.flip) == (False, "clear")


def test_a_role_short_of_the_declared_target_of_complete_pairs_is_underpowered_with_no_flip_verdict():
    pairs = repeated(19, {"C1": PASS}, {"C1": PASS}) + errored_pairs(3)

    verdict = role_verdict([DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20))

    assert verdict.underpowered
    assert verdict.flip is None
    assert verdict.complete_pairs == 19, "an underpowered role still reports its counts"


def test_a_judged_check_within_the_margin_on_its_point_estimate_is_non_inferior_whatever_its_interval():
    pairs = repeated(19, {"C3": PASS}, {"C3": PASS}) + repeated(1, {"C3": PASS}, {"C3": FAIL})

    verdict = role_verdict(
        [SURFACED_ASSUMPTION], pairs, FlipSettings(margin_pp=10, required_pairs=20)
    )

    interval = verdict.judged_intervals["C3"]
    assert verdict.check_verdicts["C3"] == "non-inferior", (
        "a 5-point shortfall is within a 10-point margin"
    )
    assert interval.lower < -0.10, (
        "twenty pairs cannot bound the paired difference within 10 points"
    )
    assert (verdict.underpowered, verdict.flip) == (False, "clear")


@pytest.mark.parametrize(("allowance", "expected"), [(1, "regression"), (2, "no regression")])
def test_a_mechanical_check_regresses_only_beyond_its_declared_noise_allowance(allowance, expected):
    # A declared table of allowances and no method: the reading of a file written before the
    # own-discordance method existed, which a recorded results file keeps.
    pairs = repeated(18, {"C1": PASS}, {"C1": PASS}) + repeated(2, {"C1": PASS}, {"C1": FAIL})

    verdict = role_verdict(
        [DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20, allowances={"C1": allowance})
    )

    assert verdict.check_verdicts["C1"] == expected


def test_a_pair_whose_lean_side_alone_errored_counts_as_a_lean_failure():
    pairs = repeated(20, {"C1": PASS}, {"C1": PASS}) + lean_errored_pairs(5, {"C1": PASS})

    verdict = role_verdict([DURABLE_OUTPUT], pairs, FlipSettings(required_pairs=20))

    assert verdict.complete_pairs == 20
    assert verdict.worst_case_lean_failures["C1"] == 5
    assert verdict.check_verdicts["C1"] == "regression", "an errored lean session hid a failure"
