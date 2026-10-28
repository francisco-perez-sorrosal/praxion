"""A move's report states what the paired run could see, in wording bounded to non-regression."""

from __future__ import annotations

import re

import pytest

from praxion_evals.adherence.moves.report import render
from praxion_evals.adherence.moves.verdict import Measurement

MESSAGE, STAGING = "commit-message-form", "staging-discipline"
TARGET = 20
OK = {MESSAGE: "passed", STAGING: "passed"}
LEAN_BREAKS_MESSAGE = {MESSAGE: "failed", STAGING: "passed"}
LEAN_BREAKS_STAGING = {MESSAGE: "passed", STAGING: "failed"}
IMPROVEMENT_WORDS = ("improve", "better than", "outperform", "superior", "gain")


def side(final, history=None, arrivals=None):
    wire = {"final": dict(final)}
    if history is not None:
        wire["history"] = history
    if arrivals is not None:
        wire["arrivals"] = arrivals
    return wire


def pairs(count, full, lean, start=0, kind="managed"):
    return [
        {
            "task_id": f"{kind}-task-{start + i:03d}",
            "fixture_kind": kind,
            "full": side(full),
            "lean": side(lean),
        }
        for i in range(count)
    ]


def floor(message_failures, staging_failures, sessions=8, errored=0):
    scored = [
        {
            MESSAGE: "failed" if i < message_failures else "passed",
            STAGING: "failed" if i < staging_failures else "passed",
        }
        for i in range(sessions - errored)
    ]
    return [*scored, *([None] * errored)]


def measurement(wire_pairs, floor_sessions=(), restriction=None, target=TARGET) -> Measurement:
    return Measurement.from_json(
        {
            "checks": [MESSAGE, STAGING],
            "margin_pp": 10.0,
            "target_pairs": target,
            "kind_restriction": restriction,
            "pairs": wire_pairs,
            "floor": [None if s is None else side(s) for s in floor_sessions],
        }
    )


# 24 pairs: message has 4 lean-only and 3 full-only failures, staging 1 and 1.
DISCORDANT = (
    pairs(4, OK, LEAN_BREAKS_MESSAGE)
    + pairs(3, LEAN_BREAKS_MESSAGE, OK, start=10, kind="unmanaged")
    + pairs(1, OK, LEAN_BREAKS_STAGING, start=20)
    + pairs(1, LEAN_BREAKS_STAGING, OK, start=30, kind="unmanaged")
    + pairs(8, OK, OK, start=40)
    + pairs(7, OK, OK, start=50, kind="unmanaged")
)
USABLE = 24


def figures(report, subject, topic):
    """The values of every `figure | subject | topic | ...` line."""
    prefix = f"figure | {subject} | {topic} | "
    return [
        line[len(prefix) :].split(" | ") for line in report.splitlines() if line.startswith(prefix)
    ]


def only(report, subject, topic):
    (found,) = figures(report, subject, topic)
    return found


def with_lean(history=None, arrivals=None, count=USABLE):
    wire = pairs(count, OK, OK)
    for pair in wire:
        pair["lean"] = side(OK, history=history, arrivals=arrivals)
    return wire


def lean_failures(arrivals_by_pair):
    wire = pairs(len(arrivals_by_pair), OK, OK)
    for pair, arrivals in zip(wire, arrivals_by_pair, strict=True):
        pair["lean"] = side(LEAN_BREAKS_MESSAGE, arrivals={MESSAGE: arrivals})
    return wire


# -- Counts, history and timing ---------------------------------------------------------------


def test_final_state_failures_are_shown_per_arm_and_check():
    report = render(measurement(DISCORDANT, floor(2, 1)))

    assert figures(report, MESSAGE, "final") == [["full", "3"], ["lean", "4"]]
    assert figures(report, STAGING, "final") == [["full", "1"], ["lean", "1"]]


def test_history_outcomes_are_counted_per_arm_without_touching_the_verdict():
    report = render(measurement(with_lean(history={MESSAGE: "repaired"}), floor(2, 1)))

    assert ["lean", "repaired", str(USABLE)] in figures(report, MESSAGE, "history")
    assert only(report, MESSAGE, "verdict") == ["no regression"]


def test_arrival_timing_is_counted_by_channel_with_trigger_failures_apart():
    late = {"hook_context": "after execution"}
    never = {"hook_context": "never"}
    wire = lean_failures([late, never, never])

    report = render(measurement(wire, floor(2, 1)))

    assert figures(report, MESSAGE, "timing") == [
        ["lean", "hook_context", "after execution", "1"],
        ["lean", "hook_context", "never", "2"],
    ]
    assert figures(report, MESSAGE, "trigger") == [["full", "0", "0", "0"], ["lean", "2", "1", "0"]]


def test_a_failure_whose_arrival_the_record_could_not_tell_is_neither_a_trigger_failure_nor_arrived():
    wire = lean_failures([{"hook_context": "unknown"}, {}])

    report = render(measurement(wire, floor(2, 1)))

    assert ["lean", "0", "0", "2"] in figures(report, MESSAGE, "trigger")


def test_a_failure_with_one_channel_arrived_and_another_never_is_a_failure_with_arrival():
    wire = lean_failures([{"hook_context": "never", "gate_refusal": "before execution"}])

    report = render(measurement(wire, floor(2, 1)))

    assert ["lean", "0", "1", "0"] in figures(report, MESSAGE, "trigger")


# -- The bounded claim --------------------------------------------------------------------------


def test_the_wording_claims_bounded_non_regression_and_nothing_about_channels():
    text = render(measurement(DISCORDANT, floor(8, 8))).lower()

    assert "non-regression within the margin" in text
    assert "nothing about one channel beating another" in text


@pytest.mark.parametrize(
    "wire",
    [DISCORDANT, pairs(12, OK, LEAN_BREAKS_MESSAGE) + pairs(12, OK, OK, start=20), []],
    ids=["clearing", "regressing", "no pairs"],
)
def test_no_wording_of_the_report_claims_improvement(wire):
    text = render(measurement(wire, floor(8, 8))).lower()

    assert not [word for word in IMPROVEMENT_WORDS if re.search(rf"\b{word}", text)], text


def test_a_regression_withholds_the_non_regression_claim_and_names_the_check():
    wire = pairs(12, OK, LEAN_BREAKS_MESSAGE) + pairs(12, OK, OK, start=20)

    claim = only(render(measurement(wire, floor(8, 8))), "run", "clearance")[0]

    assert MESSAGE in claim
    assert "no non-regression claim" in claim


def test_a_run_short_of_the_target_makes_no_clearance_claim_yet():
    claim = only(render(measurement(DISCORDANT, floor(8, 8), target=40)), "run", "clearance")[0]

    assert "No clearance claim yet" in claim


# -- Floor, sensitivity and coverage ------------------------------------------------------------


def test_floor_failures_are_shown_out_of_the_sessions_that_scored_the_check():
    report = render(measurement(DISCORDANT, floor(2, 1, errored=1)))

    assert only(report, MESSAGE, "floor") == ["2", "7"]


def test_the_sensitivity_is_the_target_times_the_floor_rate_less_the_full_rate():
    report = render(measurement(DISCORDANT, floor(2, 1)))

    # 20 * (1/8 - 1/24)
    assert only(report, STAGING, "sensitivity") == ["1.7"]


def test_a_check_whose_figure_is_within_its_allowance_is_not_covered_and_named():
    report = render(measurement(DISCORDANT, floor(2, 1)))

    assert only(report, STAGING, "coverage") == ["not covered"]
    assert STAGING in only(report, "run", "clearance")[0]


def test_a_check_whose_figure_exceeds_its_allowance_is_covered_and_unnamed():
    report = render(measurement(DISCORDANT, floor(8, 8)))

    assert only(report, STAGING, "coverage") == ["covered"]
    assert STAGING not in only(report, "run", "clearance")[0]


def test_coverage_reads_the_unrounded_figure():
    # 20 * (1/7 - 1/24) = 2.02 against an allowance of 2: shown as 2.0, yet it exceeds it.
    report = render(measurement(DISCORDANT, floor(8, 1, errored=1)))

    assert only(report, STAGING, "sensitivity") == ["2.0"]
    assert only(report, STAGING, "coverage") == ["covered"]


def test_a_check_no_floor_session_scored_is_not_covered_and_shows_no_figure():
    report = render(measurement(DISCORDANT, []))

    assert only(report, STAGING, "sensitivity") == ["none"]
    assert only(report, STAGING, "coverage") == ["not covered"]


def test_a_check_with_no_complete_pair_shows_no_allowance_and_is_not_covered():
    report = render(measurement([], floor(8, 8)))

    assert only(report, MESSAGE, "allowance") == ["none"]
    assert only(report, MESSAGE, "coverage") == ["not covered"]
    assert only(report, MESSAGE, "verdict") == ["none"]


def test_the_allowance_is_shown_in_points_beside_the_declared_margin():
    report = render(measurement(DISCORDANT, floor(2, 1)))

    assert only(report, STAGING, "allowance") == ["8.3"]  # an allowance of 2 over 24 pairs
    assert only(report, "run", "margin") == ["10.0"]


def test_an_allowance_wider_than_the_margin_times_the_usable_pairs_is_not_covered():
    wide = pairs(8, OK, LEAN_BREAKS_MESSAGE) + pairs(7, LEAN_BREAKS_MESSAGE, OK, start=10)
    wide += pairs(9, OK, OK, start=20)

    report = render(measurement(wide, floor(8, 8)))

    assert only(report, MESSAGE, "coverage") == ["not covered"]
    assert MESSAGE in only(report, "run", "clearance")[0]


# -- Fixture kinds ------------------------------------------------------------------------------


def test_per_kind_pairs_are_shown_beside_the_pooled_verdict():
    report = render(measurement(DISCORDANT, floor(2, 1)))

    assert figures(report, "run", "kind") == [["managed", "13"], ["unmanaged", "11"]]
    assert "Pooled verdict: commit-message-form: no regression" in report


def test_a_one_kind_restriction_is_named():
    managed = pairs(USABLE, OK, OK)

    report = render(measurement(managed, floor(8, 8), restriction="managed"))

    assert only(report, "run", "restriction") == ["managed"]
    assert "Restricted to managed fixtures only" in report


def test_an_unrestricted_run_shows_none():
    assert only(render(measurement(DISCORDANT, floor(2, 1))), "run", "restriction") == ["none"]
