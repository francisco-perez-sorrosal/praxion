"""The forced-stop check binds only on a role that ran out of turns; allowances come from the trial.

C5 is scored only on a session the harness stopped at its cap; one that ended before its
cap is not applicable on C5 and scored on C2; one whose record cannot tell is withheld.
Run-out counts and the differential rate are reported and never gate; C5 is not covered
under five pairs that ran out on both sides. A mechanical check's allowance is the exact
one-sided quantile at its own discordant count, never a calibration run's; a check whose
allowance exceeds the margin is listed as not covered. Recorded verdicts never move.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers import adherence_scoring as scoring
from tests.acceptance.drivers.adherence_scoring import exact_allowance, mechanical_verdict

ROLE = "verifier"
FORCED_STOP_CHECKS = ["C2", "C5"]


def graded_forced_stop(tmp_path: Path, ran_out: bool | None) -> adherence_eval.GradedSession:
    evidence = scoring.forced_stop_evidence(tmp_path, ROLE, ran_out)
    return adherence_eval.grade(evidence, FORCED_STOP_CHECKS)


# -- C5 binds only on running out of turns ----------------------------------------------------


def test_a_role_the_harness_stopped_at_its_cap_is_scored_on_the_forced_stop_check(
    tmp_path: Path,
) -> None:
    graded = graded_forced_stop(tmp_path, ran_out=True)

    assert graded.outcome("C5").kind in {"passed", "failed"}


def test_a_role_that_ended_before_its_cap_is_not_applicable_on_c5_and_scored_on_c2(
    tmp_path: Path,
) -> None:
    graded = graded_forced_stop(tmp_path, ran_out=False)

    assert graded.outcome("C5").kind == "not applicable"
    assert "cap" in (graded.outcome("C5").reason or ""), graded.outcome("C5")
    assert graded.outcome("C2").kind in {"passed", "failed"}


def test_a_session_that_cannot_establish_whether_the_cap_was_reached_is_withheld_on_c5(
    tmp_path: Path,
) -> None:
    graded = graded_forced_stop(tmp_path, ran_out=None)

    assert graded.outcome("C5").kind == "withheld"
    assert graded.outcome("C5").reason, "C5 was withheld without a reason"


def test_the_report_counts_forced_stop_sessions_by_how_they_ended_per_role_and_arm(
    tmp_path: Path,
) -> None:
    path = scoring.forced_stop_results(
        tmp_path, ROLE, both_ran_out_pairs=5, ended_before_cap={"full": 1, "lean": 3}
    )

    report = scoring.render(path, tmp_path).text

    assert scoring.forced_stop_counts(report, ROLE, "full") == scoring.RunOutCounts(5, 1)
    assert scoring.forced_stop_counts(report, ROLE, "lean") == scoring.RunOutCounts(5, 3)
    assert scoring.differential_run_out_rate(report, ROLE) != 0


def test_the_run_out_counts_never_change_the_verdict(tmp_path: Path) -> None:
    even = scoring.forced_stop_results(tmp_path / "even", ROLE, both_ran_out_pairs=5)
    skewed = scoring.forced_stop_results(
        tmp_path / "skewed", ROLE, both_ran_out_pairs=5, ended_before_cap={"lean": 4}
    )

    verdicts = [
        scoring.flip_verdict_class(scoring.render(p, tmp_path).text, ROLE) for p in (even, skewed)
    ]

    assert verdicts[0] == verdicts[1]


@pytest.mark.parametrize(("pairs", "covered"), [(4, False), (5, True)])
def test_c5_is_listed_not_covered_under_five_pairs_that_ran_out_on_both_sides(
    tmp_path: Path, pairs: int, covered: bool
) -> None:
    path = scoring.forced_stop_results(tmp_path, ROLE, both_ran_out_pairs=pairs)

    block = scoring.check_block(scoring.render(path, tmp_path).text, ROLE, "C5")

    assert ("not covered" not in block) is covered, block


@pytest.mark.parametrize("run_id", sorted(scoring.recorded_verdicts()))
def test_each_recorded_results_file_still_renders_the_verdict_it_showed(
    tmp_path: Path, run_id: str
) -> None:
    rendering = scoring.render(scoring.recorded_results_file(run_id), tmp_path)

    shown = {
        role: scoring.flip_verdict_class(rendering.text, role)
        for role in scoring.recorded_verdicts()[run_id]
    }

    assert rendering.exit_code == 0, rendering.stderr[-2000:]
    assert shown == scoring.recorded_verdicts()[run_id]


# -- Allowances from the trial's own discordance ---------------------------------------------------


@pytest.mark.parametrize("discordant", range(25))
def test_a_net_discordance_at_the_exact_quantile_is_no_regression(discordant: int) -> None:
    allowance = exact_allowance(discordant)

    verdict = mechanical_verdict({"C1": (discordant, allowance)})

    assert verdict.check_verdicts["C1"] == "no regression"


@pytest.mark.parametrize("discordant", [d for d in range(25) if exact_allowance(d) + 2 <= d])
def test_a_net_discordance_past_the_exact_quantile_is_a_regression(discordant: int) -> None:
    beyond = exact_allowance(discordant) + 2

    verdict = mechanical_verdict({"C1": (discordant, beyond)})

    assert verdict.check_verdicts["C1"] == "regression"


def test_each_check_takes_the_allowance_of_its_own_discordant_count(tmp_path: Path) -> None:
    verdict = mechanical_verdict({"C1": (20, 8), "C4": (5, 5)})

    assert verdict.check_verdicts == {"C1": "no regression", "C4": "regression"}


def test_an_allowance_offered_by_a_calibration_run_is_never_taken() -> None:
    verdict = mechanical_verdict({"C1": (5, 5)}, calibrated_allowances={"C1": 5})

    assert verdict.check_verdicts["C1"] == "regression"


def test_a_check_whose_allowance_exceeds_the_margin_is_listed_not_covered() -> None:
    verdict = mechanical_verdict({"C1": (15, 7), "C4": (2, 2)})

    assert "C1" in verdict.not_covered
    assert "C4" not in verdict.not_covered


def test_the_report_states_each_checks_discordance_and_allowance_beside_the_margin(
    tmp_path: Path,
) -> None:
    measurement = adherence_eval.RoleMeasurement(
        checks=[adherence_eval.CheckSpec("C1", "mechanical")],
        pairs=scoring.discordant_pairs("C1", 15, 7),
        first_request_tokens={"full": 40_000, "lean": 30_000},
    )

    report = adherence_eval.render_report(
        {"researcher": measurement}, adherence_eval.FlipSettings()
    )
    statement = scoring.allowance_statement(report, "researcher", "C1")

    assert (statement.discordant, statement.allowance_pairs) == (15, 7)
    assert round(statement.allowance_points) == 29
    assert statement.margin_points == scoring.MARGIN_PP
    assert "not covered" in scoring.check_block(report, "researcher", "C1")
