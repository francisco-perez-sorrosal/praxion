"""A role's paired verdicts follow the ratified flip rule.

A mechanical check shows no regression only when the lean arm passes it on at
least as many complete pairs as the full arm. A judged check is non-inferior only
when the paired comparison bounds the lean arm's pass rate within the declared
margin below the full arm's. The role's flip verdict is clear only when every
scored check holds, and it never covers a withheld check. A role that achieved
fewer complete pairs than the declared target, or whose achieved pairs could not
show non-inferiority even if both arms agreed on every pair, is underpowered and
gets no flip verdict.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.adherence_eval import (
    CheckSpec,
    FlipSettings,
    errored_pairs,
    repeated,
    role_verdict,
)

DURABLE_OUTPUT = CheckSpec("C1", "mechanical")
SURFACED_ASSUMPTION = CheckSpec("C3", "judged")
FETCHED_CONTENT = CheckSpec("C6", "mechanical")
PASS, FAIL = "passed", "failed"


def test_a_mechanical_check_the_lean_arm_passes_on_one_fewer_pair_regresses():
    pairs = repeated(19, {"C1": PASS}, {"C1": PASS}) + repeated(1, {"C1": PASS}, {"C1": FAIL})

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
    assert (verdict.underpowered, verdict.flip) == (False, "clear")


def test_a_judged_check_the_lean_arm_fails_twenty_points_more_often_is_not_non_inferior():
    pairs = repeated(160, {"C1": PASS, "C3": PASS}, {"C1": PASS, "C3": PASS}) + repeated(
        40, {"C1": PASS, "C3": PASS}, {"C1": PASS, "C3": FAIL}
    )

    verdict = role_verdict(
        [DURABLE_OUTPUT, SURFACED_ASSUMPTION], pairs, FlipSettings(required_pairs=200)
    )

    assert verdict.check_verdicts["C3"] == "not non-inferior"
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


def test_achieved_pairs_too_few_to_show_non_inferiority_even_with_full_agreement_are_underpowered():
    pairs = repeated(3, {"C3": PASS}, {"C3": PASS})

    verdict = role_verdict(
        [SURFACED_ASSUMPTION], pairs, FlipSettings(margin_pp=10, required_pairs=3)
    )

    assert verdict.underpowered
    assert verdict.flip is None
