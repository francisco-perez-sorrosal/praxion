"""Paired verdicts follow the ratified flip rule, and the reported interval is Tango's."""

from __future__ import annotations

from itertools import product
from statistics import NormalDist

import pytest

from praxion_evals.adherence import model, verdict
from praxion_evals.adherence.model import (
    Assessed,
    CheckErrored,
    Counts,
    DeclaredSettings,
    Errored,
    Failed,
    Inferior,
    Measured,
    NonInferior,
    NoRegression,
    NotApplicable,
    NotMeasured,
    Pair,
    Passed,
    Regression,
    Underpowered,
    Withheld,
)

PASS, FAIL = Passed(), Failed("the check failed")
WITHHELD = Withheld("no page to fetch")
ONE_SIDED_95 = NormalDist().inv_cdf(0.95)
MECHANICAL = {"C1": "mechanical"}
JUDGED = {"C3": "judged"}
BOTH = {"C1": "mechanical", "C3": "judged"}


def settings(required_pairs=20, margin_pp=10.0, allowances=None, confidence=0.95):
    allowances = allowances or {}
    return DeclaredSettings(
        margin_pp=margin_pp,
        method="tango-score",
        confidence=confidence,
        sidedness="one-sided",
        required_pairs=required_pairs,
        pair_slack=0,
        retry_policy="one retry for infrastructure errors",
        allowance_source="calibration-run" if allowances else None,
        allowances=allowances,
    )


def measured(**outcomes) -> Measured:
    return Measured(outcomes, None)


def pairs(count, full, lean) -> list[Pair]:
    return [Pair(f"task-{i}", "tmpl", full, lean) for i in range(count)]


def lean_errored(count, full) -> list[Pair]:
    return pairs(count, full, Errored("timeout", "lean crashed"))


def both_errored(count) -> list[Pair]:
    return pairs(count, Errored("timeout", "x"), Errored("timeout", "x"))


def counts(b, c, n):
    return Counts(n - b - c, b, c, 0)


def lower_bound(b, c, n, confidence=0.95) -> float:
    return verdict.tango_interval(counts(b, c, n), confidence).lower


# ---------------------------------------------------------------------------
# Mechanical checks
# ---------------------------------------------------------------------------


def test_a_mechanical_check_the_lean_arm_fails_on_one_more_pair_regresses():
    ok, bad = measured(C1=PASS), measured(C1=FAIL)

    result = verdict.role_verdict(MECHANICAL, pairs(19, ok, ok) + pairs(1, ok, bad), settings())

    assert isinstance(result, Assessed)
    assert isinstance(result.check_verdicts["C1"], Regression)
    assert result.flip == "not clear"


@pytest.mark.parametrize(
    ("full", "lean"),
    [
        pytest.param(measured(C1=FAIL), measured(C1=FAIL), id="both arms fail the same pairs"),
        pytest.param(measured(C1=FAIL), measured(C1=PASS), id="lean passes what full fails"),
    ],
)
def test_a_mechanical_check_the_lean_arm_passes_at_least_as_often_shows_no_regression(full, lean):
    ok = measured(C1=PASS)

    result = verdict.role_verdict(MECHANICAL, pairs(18, ok, ok) + pairs(2, full, lean), settings())

    assert isinstance(result.check_verdicts["C1"], NoRegression)


@pytest.mark.parametrize(("allowance", "expected"), [(1, Regression), (2, NoRegression)])
def test_a_mechanical_check_regresses_only_beyond_its_declared_noise_allowance(allowance, expected):
    ok, bad = measured(C1=PASS), measured(C1=FAIL)

    result = verdict.role_verdict(
        MECHANICAL, pairs(18, ok, ok) + pairs(2, ok, bad), settings(allowances={"C1": allowance})
    )

    assert isinstance(result.check_verdicts["C1"], expected)


@pytest.mark.parametrize(
    ("role", "expected"), [("researcher", NoRegression), ("verifier", Regression)]
)
def test_a_role_reads_its_own_allowance_of_a_shared_check_and_no_other_roles(role, expected):
    ok, bad = measured(C1=PASS), measured(C1=FAIL)

    result = verdict.role_verdict(
        MECHANICAL,
        pairs(18, ok, ok) + pairs(2, ok, bad),
        settings(allowances={"researcher/C1": 2}),
        role,
    )

    assert isinstance(result.check_verdicts["C1"], expected)


def test_a_check_with_no_allowance_declared_gets_zero():
    ok, bad = measured(C1=PASS, C2=PASS), measured(C1=PASS, C2=FAIL)

    result = verdict.role_verdict(
        {"C1": "mechanical", "C2": "mechanical"},
        pairs(20, ok, bad),
        settings(allowances={"C1": 5}),
    )

    assert isinstance(result.check_verdicts["C1"], NoRegression)
    assert isinstance(result.check_verdicts["C2"], Regression)


# ---------------------------------------------------------------------------
# Judged checks
# ---------------------------------------------------------------------------


def test_a_judged_check_both_arms_pass_on_two_hundred_pairs_is_non_inferior_and_the_flip_clear():
    ok = measured(C1=PASS, C3=PASS)

    result = verdict.role_verdict(BOTH, pairs(200, ok, ok), settings())

    assert isinstance(result.check_verdicts["C3"], NonInferior)
    assert result.flip == "clear"


def test_a_judged_check_the_lean_arm_fails_twenty_points_more_often_is_inferior():
    ok, lean_fails = measured(C1=PASS, C3=PASS), measured(C1=PASS, C3=FAIL)

    result = verdict.role_verdict(
        BOTH, pairs(160, ok, ok) + pairs(40, ok, lean_fails), settings(required_pairs=200)
    )

    assert isinstance(result.check_verdicts["C3"], Inferior)
    assert result.flip == "not clear"


def test_a_judged_check_within_the_margin_on_its_point_estimate_is_non_inferior_whatever_its_interval():
    ok, lean_fails = measured(C3=PASS), measured(C3=FAIL)

    result = verdict.role_verdict(
        JUDGED, pairs(19, ok, ok) + pairs(1, ok, lean_fails), settings(margin_pp=10)
    )

    scored_check = result.check_verdicts["C3"]
    assert isinstance(scored_check, NonInferior)
    assert scored_check.interval.lower < -0.10, "twenty pairs cannot bound the difference"


def test_a_judged_check_exactly_at_the_margin_is_non_inferior():
    ok, lean_fails = measured(C3=PASS), measured(C3=FAIL)

    result = verdict.role_verdict(
        JUDGED, pairs(9, ok, ok) + pairs(1, ok, lean_fails), settings(required_pairs=10)
    )

    assert isinstance(result.check_verdicts["C3"], NonInferior)


def test_a_judged_check_just_past_the_margin_is_inferior():
    ok, lean_fails = measured(C3=PASS), measured(C3=FAIL)

    result = verdict.role_verdict(
        JUDGED, pairs(8, ok, ok) + pairs(2, ok, lean_fails), settings(required_pairs=10)
    )

    assert isinstance(result.check_verdicts["C3"], Inferior)


# ---------------------------------------------------------------------------
# Coverage, power, and the worst-case recount
# ---------------------------------------------------------------------------


def test_a_withheld_check_is_listed_as_not_covered_with_its_reason_and_never_scored():
    both = measured(C1=PASS, C6=WITHHELD)

    result = verdict.role_verdict(
        {"C1": "mechanical", "C6": "mechanical"}, pairs(20, both, both), settings()
    )

    assert result.not_covered == {"C6": "no page to fetch"}
    assert "C6" not in result.check_verdicts
    assert result.flip == "clear"


def test_a_not_applicable_check_is_not_covered_either():
    both = measured(C1=PASS, C5=NotApplicable("no forced stop"))

    result = verdict.role_verdict(
        {"C1": "mechanical", "C5": "mechanical"}, pairs(20, both, both), settings()
    )

    assert result.not_covered == {"C5": "no forced stop"}


def test_a_check_errored_on_every_pair_is_not_covered():
    both = measured(C1=PASS, C3=CheckErrored("judge crashed"))

    result = verdict.role_verdict(BOTH, pairs(20, both, both), settings())

    assert "C3" in result.not_covered
    assert result.flip == "clear"


def test_a_role_whose_every_check_is_not_covered_is_never_clear():
    both = measured(C6=WITHHELD)

    result = verdict.role_verdict({"C6": "mechanical"}, pairs(20, both, both), settings())

    assert result.flip == "not clear"


def test_errored_pairs_are_neither_complete_nor_counted_against_the_role():
    ok = measured(C1=PASS)

    result = verdict.role_verdict(MECHANICAL, pairs(20, ok, ok) + both_errored(5), settings())

    assert result.complete_pairs == 20
    assert result.flip == "clear"


def test_a_pair_whose_full_side_alone_errored_is_incomplete_and_not_recounted():
    ok = measured(C1=PASS)
    full_errored = pairs(1, Errored("timeout", "x"), ok)

    result = verdict.role_verdict(MECHANICAL, pairs(20, ok, ok) + full_errored, settings())

    assert result.complete_pairs == 20
    assert result.worst_case_lean_failures["C1"] == 0
    assert result.flip == "clear"


def test_a_role_short_of_the_declared_complete_pairs_is_underpowered_and_still_gives_counts():
    ok = measured(C1=PASS)

    result = verdict.role_verdict(MECHANICAL, pairs(19, ok, ok) + both_errored(3), settings())

    assert isinstance(result, Underpowered)
    assert (result.complete_pairs, result.required_pairs) == (19, 20)


def test_a_pair_with_an_unmeasured_side_is_incomplete():
    ok = measured(C1=PASS)

    result = verdict.role_verdict(
        MECHANICAL, pairs(20, ok, ok) + pairs(1, NotMeasured("never spawned"), ok), settings()
    )

    assert result.complete_pairs == 20


def test_a_pair_whose_lean_side_alone_errored_counts_as_a_lean_failure():
    ok = measured(C1=PASS)

    result = verdict.role_verdict(MECHANICAL, pairs(20, ok, ok) + lean_errored(1, ok), settings())

    assert result.complete_pairs == 20
    assert result.worst_case_lean_failures["C1"] == 1
    assert isinstance(result.check_verdicts["C1"], Regression)


def test_a_lean_errored_pair_counts_only_on_the_checks_the_full_side_scored():
    full = measured(C1=PASS, C6=WITHHELD)
    ok = measured(C1=PASS, C6=PASS)

    result = verdict.role_verdict(
        {"C1": "mechanical", "C6": "mechanical"},
        pairs(20, ok, ok) + lean_errored(1, full),
        settings(),
    )

    assert result.worst_case_lean_failures["C6"] == 0
    assert isinstance(result.check_verdicts["C6"], NoRegression)


def test_the_recount_reaches_a_judged_check_through_its_point_estimate():
    ok = measured(C3=PASS)

    result = verdict.role_verdict(
        JUDGED, pairs(20, ok, ok) + lean_errored(5, ok), settings(margin_pp=10)
    )

    assert isinstance(result.check_verdicts["C3"], Inferior)


def test_the_tally_counts_the_four_cells_after_the_recount():
    ok, bad = measured(C1=PASS), measured(C1=FAIL)
    sessions = pairs(3, ok, ok) + pairs(2, ok, bad) + pairs(1, bad, ok) + pairs(4, bad, bad)
    sessions += lean_errored(2, ok) + lean_errored(1, bad)

    result = verdict.tally("C1", sessions)

    assert result == Counts(both_passed=3, lean_failed_only=4, lean_passed_only=1, both_failed=5)


# ---------------------------------------------------------------------------
# The interval: Tango's score bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [5, 20, 25, 80, 400])
def test_the_bound_at_perfect_agreement_has_the_closed_form(n):
    z2 = ONE_SIDED_95**2

    assert lower_bound(0, 0, n) == pytest.approx(-z2 / (n + z2), abs=1e-9)


def test_twenty_pairs_in_perfect_agreement_cannot_clear_ten_points():
    assert lower_bound(0, 0, 20) == pytest.approx(-0.119, abs=5e-4)


def test_thirty_five_pairs_in_perfect_agreement_clear_ten_points_at_the_stricter_confidence():
    assert lower_bound(0, 0, 35, confidence=0.975) > -0.10 > lower_bound(0, 0, 34, 0.975)


# At n = 25 the bound clears -10 pp for exactly these tables (the consult's figures).
CLEARING_AT_25 = [(0, c) for c in range(8)] + [(1, c) for c in range(2, 8)]
CLEARING_AT_25 += [(2, c) for c in range(4, 8)] + [(3, c) for c in range(6, 8)]
BLOCKED_AT_25 = [(1, 0), (1, 1), (2, 3), (3, 5), (4, 7)]


@pytest.mark.parametrize(("b", "c"), CLEARING_AT_25)
def test_the_bound_at_twenty_five_pairs_clears_the_tables_the_consult_lists(b, c):
    assert lower_bound(b, c, 25) > -0.10


@pytest.mark.parametrize(("b", "c"), BLOCKED_AT_25)
def test_the_bound_at_twenty_five_pairs_blocks_the_tables_the_consult_rejects(b, c):
    assert lower_bound(b, c, 25) <= -0.10


def test_the_bound_stays_wide_where_wald_would_collapse():
    assert lower_bound(0, 0, 20) < -0.05


GRID = [(n, b, c) for n, b, c in product((10, 25, 60), range(0, 6), range(0, 6)) if b + c <= n]


@pytest.mark.parametrize(("n", "b", "c"), GRID)
def test_the_reported_bound_is_below_the_point_estimate_and_inside_the_parameter_space(n, b, c):
    interval = verdict.tango_interval(counts(b, c, n), 0.95)

    assert -1.0 <= interval.lower <= (c - b) / n + 1e-12
    assert interval.upper == 1.0


@pytest.mark.parametrize(("n", "b", "c"), [t for t in GRID if t[1] + t[2] < t[0]])
def test_the_bound_never_falls_when_the_lean_arm_wins_one_more_pair(n, b, c):
    assert lower_bound(b, c + 1, n) >= lower_bound(b, c, n)


@pytest.mark.parametrize(("n", "b", "c"), [t for t in GRID if t[1] + t[2] < t[0]])
def test_the_bound_never_rises_when_the_lean_arm_loses_one_more_pair(n, b, c):
    assert lower_bound(b + 1, c, n) <= lower_bound(b, c, n)


@pytest.mark.parametrize("confidence", [0.8, 0.9, 0.975])
def test_a_higher_confidence_gives_a_lower_bound(confidence):
    assert lower_bound(1, 2, 30, confidence) > lower_bound(1, 2, 30, confidence + 0.02)


def test_a_role_where_the_lean_arm_loses_every_pair_has_the_floor_as_its_bound():
    assert lower_bound(5, 0, 5) == -1.0


# ---------------------------------------------------------------------------
# Calibration: the allowance a same-arm run earns each check
# ---------------------------------------------------------------------------


def calibration(discordant_against_second: int, discordant_for_second: int) -> list[Pair]:
    ok, bad = measured(C1=PASS), measured(C1=FAIL)
    return (
        pairs(10, ok, ok)
        + pairs(discordant_against_second, ok, bad)
        + pairs(discordant_for_second, bad, ok)
    )


@pytest.mark.parametrize(
    ("b", "c", "expected"),
    [
        pytest.param(0, 0, 0, id="no discordance, no noise"),
        pytest.param(1, 0, 1, id="one discordant pair needs one pair of slack"),
        pytest.param(2, 2, 4, id="four discordant pairs"),
        pytest.param(5, 5, 6, id="ten discordant pairs"),
    ],
)
def test_the_allowance_is_the_smallest_noise_the_same_arm_run_stays_under(b, c, expected):
    allowances = verdict.allowances_from_calibration(calibration(b, c), 0.95)

    assert allowances == {"C1": expected}


def test_a_higher_confidence_never_earns_a_smaller_allowance():
    pairs_ = calibration(4, 3)

    low = verdict.allowances_from_calibration(pairs_, 0.80)["C1"]
    high = verdict.allowances_from_calibration(pairs_, 0.99)["C1"]

    assert low <= high


def test_the_allowance_is_the_exact_binomial_quantile_of_the_net_discordance():
    # Six discordant pairs: b - c = 2 * Bin(6, 1/2) - 6, and Bin(6, 1/2) <= 4 holds with
    # probability 57/64 = 0.89 while <= 5 holds with 63/64, so 0.95 first holds at k = 4.
    assert verdict.allowances_from_calibration(calibration(3, 3), 0.95) == {"C1": 4}
    assert verdict.allowances_from_calibration(calibration(3, 3), 0.85) == {"C1": 2}


def test_a_pair_with_an_errored_side_adds_no_noise_to_the_allowance():
    pairs_ = calibration(0, 0) + both_errored(4) + lean_errored(3, measured(C1=PASS))

    assert verdict.allowances_from_calibration(pairs_, 0.95) == {"C1": 0}


def test_every_check_the_run_scored_gets_its_own_allowance():
    ok = measured(C1=PASS, C2=PASS)
    drifted = measured(C1=PASS, C2=FAIL)

    allowances = verdict.allowances_from_calibration(
        pairs(10, ok, ok) + pairs(1, ok, drifted), 0.95
    )

    assert allowances == {"C1": 0, "C2": 1}


def test_the_verdict_codec_carries_what_the_core_computes():
    ok, bad = measured(C1=PASS, C3=PASS), measured(C1=FAIL, C3=PASS)

    encoded = model.verdict_to_json(
        verdict.role_verdict(BOTH, pairs(19, ok, ok) + pairs(1, ok, bad), settings())
    )

    assert encoded["check_verdicts"] == {"C1": "regression", "C3": "non-inferior"}
    assert encoded["worst_case_lean_failures"] == {"C1": 1, "C3": 0}
    assert set(encoded["judged_intervals"]) == {"C3"}
