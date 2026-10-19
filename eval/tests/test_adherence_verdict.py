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
from praxion_evals.adherence.model_verdict import Covered, NotCovered
from praxion_evals.adherence.transcript import EndedOnItsOwn, StoppedAtCap

PASS, FAIL = Passed(), Failed("the check failed")
WITHHELD = Withheld("no page to fetch")
ONE_SIDED_95 = NormalDist().inv_cdf(0.95)
MECHANICAL = {"C1": "mechanical"}
JUDGED = {"C3": "judged"}
BOTH = {"C1": "mechanical", "C3": "judged"}


def settings(
    required_pairs=20, margin_pp=10.0, allowances=None, confidence=0.95, allowance_method=None
):
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
        allowance_method=allowance_method,
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
# Mechanical checks sized by the run's own discordant count
# ---------------------------------------------------------------------------

OWN = "own-discordance-exact"
RUN_PAIRS = 24
# discordant pairs d -> the allowance. With no true difference the d discordant pairs split as a
# fair coin, so the net discordance b - c = 2 * Binomial(d, 1/2) - d. The allowance is the
# smallest k with P(b <= (d + k) // 2) >= 0.95: d = 4 gives 15/16 at k = 2 (short of 0.95) and
# 16/16 at k = 4; d = 5 gives 26/32 at k = 1 and 31/32 at k = 3.
EXACT_ALLOWANCE = {0: 0, 4: 4, 5: 3, 10: 6, 15: 7, 20: 8, 24: 8}


def discordant_run(check, discordant, net, total=RUN_PAIRS) -> list[Pair]:
    """``total`` pairs of which ``discordant`` split ``net`` more lean failures than lean passes."""
    lean_failed = (discordant + net) // 2
    ok, bad = measured(**{check: PASS}), measured(**{check: FAIL})
    return (
        pairs(lean_failed, ok, bad)
        + pairs(discordant - lean_failed, bad, ok)
        + pairs(total - discordant, ok, ok)
    )


def own_discordance_verdict(
    pairs_, checks=MECHANICAL, role: str | None = "researcher", **settings_kwargs
):
    declared = settings(required_pairs=RUN_PAIRS, allowance_method=OWN, **settings_kwargs)
    return verdict.role_verdict(checks, pairs_, declared, role)


@pytest.mark.parametrize(("discordant", "allowance"), EXACT_ALLOWANCE.items())
def test_a_net_discordance_at_the_exact_quantile_of_its_own_count_is_no_regression(
    discordant, allowance
):
    result = own_discordance_verdict(discordant_run("C1", discordant, allowance))

    check = result.check_verdicts["C1"]
    assert isinstance(check, NoRegression)
    assert check.allowance == allowance


@pytest.mark.parametrize("discordant", [5, 10, 15, 20, 24])
def test_a_net_discordance_one_step_past_the_exact_quantile_is_a_regression(discordant):
    past = EXACT_ALLOWANCE[discordant] + 2  # net discordance keeps the parity of the count

    result = own_discordance_verdict(discordant_run("C1", discordant, past))

    assert isinstance(result.check_verdicts["C1"], Regression)
    assert result.flip == "not clear"


def test_each_check_takes_the_allowance_of_its_own_discordant_count():
    c1_noise = pairs(5, measured(C1=PASS, C2=PASS), measured(C1=FAIL, C2=PASS))
    c2_noise = pairs(4, measured(C1=PASS, C2=PASS), measured(C1=PASS, C2=FAIL))
    quiet = pairs(15, measured(C1=PASS, C2=PASS), measured(C1=PASS, C2=PASS))
    both_checks = {"C1": "mechanical", "C2": "mechanical"}

    result = own_discordance_verdict(c1_noise + c2_noise + quiet, both_checks)

    assert result.check_verdicts["C1"].allowance == EXACT_ALLOWANCE[5]
    assert isinstance(result.check_verdicts["C1"], Regression)
    assert result.check_verdicts["C2"].allowance == EXACT_ALLOWANCE[4]
    assert isinstance(result.check_verdicts["C2"], NoRegression)


def test_a_lean_errored_pair_counts_in_the_discordant_count_the_allowance_is_sized_by():
    ok = measured(C1=PASS)

    result = own_discordance_verdict(pairs(RUN_PAIRS, ok, ok) + lean_errored(5, ok))

    assert result.check_verdicts["C1"].counts.b == 5
    assert result.check_verdicts["C1"].allowance == EXACT_ALLOWANCE[5]


def test_the_allowance_follows_the_declared_confidence():
    run = discordant_run("C1", 10, 6)

    strict = own_discordance_verdict(run, confidence=0.99)
    lenient = own_discordance_verdict(run, confidence=0.80)

    assert lenient.check_verdicts["C1"].allowance < strict.check_verdicts["C1"].allowance


@pytest.mark.parametrize("calibrated", [0, 3, 12])
def test_an_allowance_a_calibration_run_declared_is_never_taken_under_the_own_method(calibrated):
    run = discordant_run("C1", 10, 8)  # past the exact quantile of 6

    result = own_discordance_verdict(
        run, allowances={"researcher/C1": calibrated, "C1": calibrated}
    )

    assert isinstance(result.check_verdicts["C1"], Regression)
    assert result.check_verdicts["C1"].allowance == EXACT_ALLOWANCE[10]


def test_the_allowance_is_the_same_whatever_role_asks_for_it():
    run = discordant_run("C1", 10, 6)

    as_researcher = own_discordance_verdict(run, role="researcher")
    as_verifier = own_discordance_verdict(run, role="verifier")
    bare = own_discordance_verdict(run, role=None)

    assert as_researcher.check_verdicts == as_verifier.check_verdicts == bare.check_verdicts


def test_a_settings_without_the_method_keeps_reading_the_declared_allowance():
    run = discordant_run("C1", 10, 8)

    narrow = verdict.role_verdict(
        MECHANICAL, run, settings(required_pairs=RUN_PAIRS, allowances={"C1": 7})
    )
    wide = verdict.role_verdict(
        MECHANICAL, run, settings(required_pairs=RUN_PAIRS, allowances={"C1": 8})
    )

    assert isinstance(narrow.check_verdicts["C1"], Regression)
    assert isinstance(wide.check_verdicts["C1"], NoRegression)


def test_a_settings_without_the_method_and_without_allowances_reads_zero():
    result = verdict.role_verdict(
        MECHANICAL, discordant_run("C1", 10, 2), settings(required_pairs=RUN_PAIRS)
    )

    assert isinstance(result.check_verdicts["C1"], Regression)
    assert result.check_verdicts["C1"].allowance == 0


# ---------------------------------------------------------------------------
# A check whose allowance is wider than the margin is not covered
# ---------------------------------------------------------------------------


def test_fifteen_discordant_pairs_of_twenty_four_are_not_covered_at_the_margin():
    result = own_discordance_verdict(discordant_run("C1", 15, 7))

    assert result.not_covered == {"C1": verdict.OVER_MARGIN}
    assert result.coverage("C1") == NotCovered(verdict.OVER_MARGIN)
    assert result.flip == "not clear"


def test_two_discordant_pairs_of_twenty_four_are_covered():
    result = own_discordance_verdict(discordant_run("C1", 2, 2))

    assert result.not_covered == {}
    assert result.coverage("C1") == Covered()
    assert result.flip == "clear"


@pytest.mark.parametrize(
    ("margin_pp", "covered"),
    [pytest.param(12.5, True, id="allowance equals margin times pairs"), (12.4, False)],
)
def test_an_allowance_equal_to_the_margin_times_the_usable_pairs_is_still_covered(
    margin_pp, covered
):
    # three discordant pairs of 24 give an allowance of 3, which is 12.5 points of 24
    result = own_discordance_verdict(discordant_run("C1", 3, 3), margin_pp=margin_pp)

    assert (result.coverage("C1") == Covered()) is covered


def test_a_covered_check_clears_beside_one_the_flip_claim_is_silent_on():
    ok, c1_down = measured(C1=PASS, C2=PASS), measured(C1=FAIL, C2=PASS)
    run = pairs(11, ok, c1_down) + pairs(4, c1_down, ok) + pairs(9, ok, ok)  # C1: 15 discordant

    result = own_discordance_verdict(run, {"C1": "mechanical", "C2": "mechanical"})

    assert (result.flip, list(result.not_covered)) == ("clear", ["C1"])


def test_a_regression_beyond_a_wide_allowance_is_never_withheld():
    result = own_discordance_verdict(discordant_run("C1", 15, 9))

    assert isinstance(result.check_verdicts["C1"], Regression)
    assert (result.not_covered, result.flip) == ({}, "not clear")


def test_a_judged_check_is_never_held_to_the_allowance_rule():
    ok = measured(C3=PASS)

    result = own_discordance_verdict(pairs(RUN_PAIRS, ok, ok), JUDGED)

    assert result.not_covered == {}


# ---------------------------------------------------------------------------
# The forced-stop check needs five pairs that ran out of turns on both sides
# ---------------------------------------------------------------------------

FORCED_STOP = {"C5": "mechanical"}
CAP = 6
NOT_RUN_OUT = NotApplicable("the role ended before its cap")


def ran_out() -> Measured:
    return Measured({"C5": PASS}, None, role_ending=StoppedAtCap(CAP, CAP))


def ended_before_cap() -> Measured:
    return Measured({"C5": NOT_RUN_OUT}, None, role_ending=EndedOnItsOwn(CAP - 3))


def clean() -> Measured:
    return Measured({"C5": NotApplicable("the task did not stop the role early")}, None)


def forced_stop_run(both_ran_out: int, ended_early: int = 0) -> list[Pair]:
    """24 pairs: `both_ran_out` stopped at the cap in both arms, `ended_early` stopped in the full
    arm only, the rest not forced-stop tasks."""
    idle = RUN_PAIRS - both_ran_out - ended_early
    return (
        pairs(both_ran_out, ran_out(), ran_out())
        + pairs(ended_early, ran_out(), ended_before_cap())
        + pairs(idle, clean(), clean())
    )


@pytest.mark.parametrize(("both_ran_out", "covered"), [(4, False), (5, True)])
def test_the_forced_stop_check_is_covered_from_five_pairs_that_ran_out_on_both_sides(
    both_ran_out, covered
):
    result = own_discordance_verdict(forced_stop_run(both_ran_out), FORCED_STOP)

    assert (result.coverage("C5") == Covered()) is covered


def test_the_reason_the_forced_stop_check_is_not_covered_counts_the_pairs_that_ran_out():
    result = own_discordance_verdict(forced_stop_run(4), FORCED_STOP)

    assert result.not_covered == {
        "C5": "4 pairs ran out of turns on both sides, fewer than the 5 it needs to be scored"
    }
    assert result.flip == "not clear"


def test_a_pair_that_ran_out_on_one_side_only_is_not_counted():
    assert verdict.ran_out_on_both_sides(forced_stop_run(4, ended_early=3)) == 4


def test_the_floor_binds_the_forced_stop_check_alone():
    both = {"C1": "mechanical", "C5": "mechanical"}
    ok_and_ran_out = Measured({"C1": PASS, "C5": PASS}, None, role_ending=StoppedAtCap(CAP, CAP))
    idle = Measured({"C1": PASS, "C5": NotApplicable("not a forced stop")}, None)
    run = pairs(4, ok_and_ran_out, ok_and_ran_out) + pairs(RUN_PAIRS - 4, idle, idle)

    result = own_discordance_verdict(run, both)

    assert list(result.not_covered) == ["C5"]


def test_a_settings_without_the_method_keeps_the_forced_stop_verdict_it_showed():
    result = verdict.role_verdict(
        FORCED_STOP, forced_stop_run(4), settings(required_pairs=RUN_PAIRS)
    )

    assert (result.not_covered, result.flip) == ({}, "clear")


def test_a_forced_stop_regression_is_never_withheld_for_want_of_pairs():
    lean_crashed = lean_errored(8, ran_out())  # counted as lean failures on the full side's check

    result = own_discordance_verdict(forced_stop_run(3) + lean_crashed, FORCED_STOP)

    assert isinstance(result.check_verdicts["C5"], Regression)
    assert (result.not_covered, result.flip) == ({}, "not clear")


def test_a_settings_without_the_method_keeps_a_wide_declared_allowance_covered():
    result = verdict.role_verdict(
        MECHANICAL,
        discordant_run("C1", 15, 7),
        settings(required_pairs=RUN_PAIRS, allowances={"C1": 8}),
    )

    assert (result.not_covered, result.flip) == ({}, "clear")


def test_an_allowance_method_nobody_defined_is_refused():
    with pytest.raises(ValueError, match="allowance method"):
        settings(allowance_method="widest-calibration")


def test_the_allowance_method_round_trips_through_the_settings_codec():
    declared = settings(allowance_method=OWN)

    assert model.settings_from_json(model.settings_to_json(declared)) == declared


def test_a_settings_record_without_the_method_loads_as_none_and_writes_none_back():
    written = model.settings_to_json(settings())

    assert "allowance_method" not in written
    assert model.settings_from_json(written).allowance_method is None


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


def test_the_verdict_codec_carries_what_the_core_computes():
    ok, bad = measured(C1=PASS, C3=PASS), measured(C1=FAIL, C3=PASS)

    encoded = model.verdict_to_json(
        verdict.role_verdict(BOTH, pairs(19, ok, ok) + pairs(1, ok, bad), settings())
    )

    assert encoded["check_verdicts"] == {"C1": "regression", "C3": "non-inferior"}
    assert encoded["worst_case_lean_failures"] == {"C1": 1, "C3": 0}
    assert set(encoded["judged_intervals"]) == {"C3"}
