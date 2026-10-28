"""A move's verdict gates on final state alone, and its report states what the run could see.

Over constructed move pairs: the verdict equals the shared flip rule's verdict over the same
final states; history outcomes never change it, and a final-state regression is one whatever
the history shows. Each mechanical allowance is the exact one-sided quantile at that run's own
discordant count for that move and check, never another check's and never moved by a floor
session. The report shows, per arm and governed check, the final-state counts, the history
outcomes, the arrival timing by channel and the trigger failures apart from failures with
arrival; the floor failures out of the floor sessions and a sensitivity line (the net
discordance a total loss would be expected to produce at the paired target, from the floor's
failure rate against the full arm's) beside the check's allowance in percentage points and the
margin; and per-kind counts beside the pooled verdict. A check not covered, by its allowance or
by its sensitivity, is listed and named in the clearance claim. The wording claims bounded
non-regression within the margin and nothing about one channel beating another.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import run_in_eval
from tests.acceptance.drivers.move_eval import FIRST_MOVE, GOVERNED_CHECKS, TARGET_PAIRS
from tests.acceptance.drivers.move_scoring import (
    ArmOutcome,
    Final,
    MoveMeasurement,
    MovePair,
    exact_allowance,
    move_report,
    move_verdict,
    pairs_of,
    shared_rule_verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MESSAGE, STAGING = GOVERNED_CHECKS
BOTH_PASS: dict[str, Final] = {MESSAGE: "passed", STAGING: "passed"}
PAIRED_TASKS = 24


def _measurement(*pairs: tuple[MovePair, ...], floor=(), restricted_to=None) -> MoveMeasurement:
    return MoveMeasurement(
        FIRST_MOVE,
        GOVERNED_CHECKS,
        tuple(p for group in pairs for p in group),
        tuple(floor),
        restricted_to=restricted_to,
    )


def _floor(message: int, staging: int, sessions: int = 8, errored: int = 0) -> tuple:
    """Floor sessions: the first `message` fail the message check, the first `staging` staging."""
    scored = tuple(
        ArmOutcome(
            {
                MESSAGE: "failed" if i < message else "passed",
                STAGING: "failed" if i < staging else "passed",
            }
        )
        for i in range(sessions - errored)
    )
    return scored + (None,) * errored


# A run with discordance on both checks: the message check has 4 pairs where only lean fails and
# 3 where only full fails (7 discordant, net 1); staging has 1 and 1 (2 discordant, net 0).
DISCORDANT = _measurement(
    pairs_of(4, "managed", BOTH_PASS, {MESSAGE: "failed", STAGING: "passed"}),
    pairs_of(3, "unmanaged", {MESSAGE: "failed", STAGING: "passed"}, BOTH_PASS),
    pairs_of(1, "managed", BOTH_PASS, {MESSAGE: "passed", STAGING: "failed"}, start=10),
    pairs_of(1, "unmanaged", {MESSAGE: "passed", STAGING: "failed"}, BOTH_PASS, start=10),
    pairs_of(8, "managed", BOTH_PASS, BOTH_PASS, start=20),
    pairs_of(7, "unmanaged", BOTH_PASS, BOTH_PASS, start=20),
    floor=_floor(message=2, staging=1),
)
# A run the lean arm loses on final state: 12 pairs where only lean fails the message check.
REGRESSING = _measurement(
    pairs_of(12, "managed", BOTH_PASS, {MESSAGE: "failed", STAGING: "passed"}),
    pairs_of(12, "unmanaged", BOTH_PASS, BOTH_PASS),
    floor=_floor(message=8, staging=8),
)


def _with_history(measurement: MoveMeasurement, arm: str, history: str) -> MoveMeasurement:
    pairs = tuple(
        replace(
            pair,
            **{arm: replace(getattr(pair, arm), history=dict.fromkeys(GOVERNED_CHECKS, history))},
        )
        for pair in measurement.pairs
    )
    return replace(measurement, pairs=pairs)


# -- The verdict ------------------------------------------------------------------------------


@pytest.mark.parametrize("measurement", [DISCORDANT, REGRESSING], ids=["discordant", "regressing"])
def test_the_move_verdict_equals_the_shared_rule_over_the_same_final_states(measurement):
    assert dict(move_verdict(measurement).check_verdicts) == dict(shared_rule_verdict(measurement))


def test_history_outcomes_that_differ_while_final_states_agree_change_no_verdict():
    first_time = _with_history(DISCORDANT, "lean", "right first time")
    repaired = _with_history(DISCORDANT, "lean", "repaired")

    assert move_verdict(first_time).check_verdicts == move_verdict(repaired).check_verdicts


def test_a_final_state_regression_is_reported_whatever_the_history_shows():
    repaired = _with_history(REGRESSING, "lean", "repaired")

    assert move_verdict(repaired).check_verdicts[MESSAGE] == "regression"


def test_each_allowance_is_the_exact_quantile_at_its_own_checks_discordant_count():
    verdict = move_verdict(DISCORDANT)

    assert dict(verdict.discordant) == {MESSAGE: 7, STAGING: 2}
    assert dict(verdict.allowances) == {MESSAGE: exact_allowance(7), STAGING: exact_allowance(2)}


def test_floor_sessions_move_no_allowance_and_enter_no_paired_count():
    without_floor = replace(DISCORDANT, floor=())

    assert move_verdict(DISCORDANT).allowances == move_verdict(without_floor).allowances
    assert move_verdict(DISCORDANT).complete_pairs == move_verdict(without_floor).complete_pairs


def test_an_errored_pair_enters_no_complete_pair():
    errored = MovePair("unmanaged-task-099", "unmanaged", ArmOutcome(dict(BOTH_PASS)), None)

    with_error = replace(DISCORDANT, pairs=(*DISCORDANT.pairs, errored))

    assert move_verdict(with_error).complete_pairs == PAIRED_TASKS


# -- The report: counts, history, timing ------------------------------------------------------


@pytest.fixture(scope="module")
def discordant_report():
    return move_report(DISCORDANT)


def test_the_report_shows_final_state_failures_per_arm_and_check(discordant_report):
    message = discordant_report.checks[MESSAGE]

    assert dict(message.final_failures) == {"full": 3, "lean": 4}


def test_the_report_shows_history_outcomes_per_arm_and_check():
    report = move_report(_with_history(DISCORDANT, "lean", "repaired"))

    assert report.checks[MESSAGE].history["lean"].get("repaired") == PAIRED_TASKS


def test_the_report_shows_arrival_timing_by_channel_and_trigger_failures_apart():
    late = ArmOutcome(
        {MESSAGE: "failed", STAGING: "passed"},
        arrivals={MESSAGE: {"hook context": "after execution"}},
    )
    never = ArmOutcome(
        {MESSAGE: "failed", STAGING: "passed"},
        arrivals={MESSAGE: {"hook context": "never"}},
    )
    pairs = (
        MovePair("managed-task-000", "managed", ArmOutcome(dict(BOTH_PASS)), late),
        MovePair("managed-task-001", "managed", ArmOutcome(dict(BOTH_PASS)), never),
        MovePair("managed-task-002", "managed", ArmOutcome(dict(BOTH_PASS)), never),
    )

    message = move_report(replace(DISCORDANT, pairs=pairs)).checks[MESSAGE]

    assert message.timing["lean"]["hook context"] == {"after execution": 1, "never": 2}
    assert (message.trigger_failures["lean"], message.failures_with_arrival["lean"]) == (2, 1)


def test_the_report_claims_bounded_non_regression_within_the_margin_and_nothing_about_channels(
    discordant_report,
):
    text = discordant_report.text.lower()

    assert "non-regression" in text
    assert "margin" in text
    assert "channel" in text, "the report does not say it shows nothing about channels"
    assert not any(word in text for word in ("improve", "better than", "outperform")), text


# -- The report: floor, sensitivity, allowance and coverage -----------------------------------


def test_the_report_shows_floor_failures_out_of_the_floor_sessions(discordant_report):
    message = discordant_report.checks[MESSAGE]

    assert (message.floor_failures, message.floor_sessions) == (2, 8)


def test_an_errored_floor_session_enters_no_failure_count():
    report = move_report(replace(DISCORDANT, floor=_floor(message=2, staging=1, errored=1)))

    assert report.checks[MESSAGE].floor_failures == 2


def test_the_sensitivity_line_is_the_net_discordance_a_total_loss_would_produce_at_the_target(
    discordant_report,
):
    floor_rate, full_rate = 1 / 8, 1 / PAIRED_TASKS

    expected = discordant_report.checks[STAGING].expected_total_loss_discordance

    assert expected == pytest.approx(TARGET_PAIRS * (floor_rate - full_rate), abs=0.05)


def test_a_check_whose_total_loss_would_not_exceed_its_allowance_is_not_covered_and_named(
    discordant_report,
):
    assert exact_allowance(2) <= 0.10 * PAIRED_TASKS, "the check must be covered at the margin"
    assert discordant_report.checks[STAGING].not_covered
    assert STAGING in discordant_report.clearance_claim


def test_a_check_whose_total_loss_would_exceed_its_allowance_within_the_margin_is_covered():
    report = move_report(replace(DISCORDANT, floor=_floor(message=8, staging=8)))

    assert not report.checks[STAGING].not_covered
    assert STAGING not in report.clearance_claim


def test_each_allowance_is_shown_in_points_beside_the_declared_margin(discordant_report):
    staging = discordant_report.checks[STAGING]

    assert staging.allowance_pp == pytest.approx(100 * exact_allowance(2) / PAIRED_TASKS, abs=0.05)
    assert discordant_report.margin_pp == pytest.approx(10.0)


def test_an_allowance_beyond_the_margin_times_the_usable_pairs_is_not_covered_and_named():
    wide = _measurement(
        pairs_of(8, "managed", BOTH_PASS, {MESSAGE: "failed", STAGING: "passed"}),
        pairs_of(7, "unmanaged", {MESSAGE: "failed", STAGING: "passed"}, BOTH_PASS),
        pairs_of(9, "unmanaged", BOTH_PASS, BOTH_PASS, start=20),
        floor=_floor(message=8, staging=8),
    )

    report = move_report(wide)

    assert exact_allowance(15) > 0.10 * PAIRED_TASKS
    assert report.checks[MESSAGE].not_covered
    assert MESSAGE in report.clearance_claim


# -- The report: fixture kinds ----------------------------------------------------------------


def test_the_report_shows_per_kind_counts_beside_the_pooled_verdict(discordant_report):
    assert dict(discordant_report.per_kind_pairs) == {"managed": 13, "unmanaged": 11}
    assert dict(discordant_report.pooled_verdict) == dict(move_verdict(DISCORDANT).check_verdicts)


def test_relabelling_pairs_between_fixture_kinds_leaves_the_pooled_verdict_unchanged():
    relabelled = replace(
        REGRESSING, pairs=tuple(replace(pair, fixture_kind="managed") for pair in REGRESSING.pairs)
    )

    assert move_verdict(relabelled).check_verdicts == move_verdict(REGRESSING).check_verdicts


def test_a_move_restricted_to_one_fixture_kind_names_the_restriction_in_its_report():
    managed_only = _measurement(
        pairs_of(PAIRED_TASKS, "managed", BOTH_PASS, BOTH_PASS),
        floor=_floor(message=8, staging=8),
        restricted_to="managed",
    )

    report = move_report(managed_only)

    assert report.restriction == "managed"
    assert "managed" in report.text.lower()


# -- Results files recorded before moves existed ----------------------------------------------

_RECORDED_RESULTS = REPO_ROOT / ".ai-state" / "eval_ledger" / "adherence"
_VERDICTS_BEFORE = REPO_ROOT / "tests" / "fixtures" / "move_eval" / "verdicts_before_moves.json"
_VERDICT_LINE = re.compile(r"^\s*(Role \S+:|verdict:)")
_RENDER_ALL = """
import json, sys
from pathlib import Path
from praxion_evals.adherence import report, results
print(json.dumps({Path(p).name: report.render(results.load(Path(p))) for p in json.load(sys.stdin)}))
"""


def test_every_results_file_recorded_before_moves_renders_the_verdict_it_showed():
    frozen = json.loads(_VERDICTS_BEFORE.read_text(encoding="utf-8"))
    paths = [str(_RECORDED_RESULTS / name) for name in sorted(frozen)]

    rendered = run_in_eval(_RENDER_ALL, paths)

    shown = {
        name: [line.strip() for line in text.splitlines() if _VERDICT_LINE.match(line)]
        for name, text in rendered.items()
    }
    assert shown == frozen
