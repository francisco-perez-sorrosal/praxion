"""A run stops itself on a repeated identical infrastructure failure, and on nothing behavioural.

Every session is a stand-in. N sessions in a row of one arm ending in the same counting
error kind with the same masked tail stop the run after exactly N sessions of that arm:
nothing more launches, the stop reason sits in the results file and the report, and the
run exits incomplete. Volatile tokens are masked; genuinely different tails never merge;
any session that ran breaks the streak; isolation breaches and graded failures never
count. The stop count is declared before the first launch, at least 3.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers.adherence_runs import (
    DEFAULT_STOP_COUNT,
    INCOMPLETE_EXIT,
    Plan,
    Script,
    connection_refused,
    crashed,
    credit_exhausted,
    graded_failure,
    isolation_breach,
    ran,
)

N = DEFAULT_STOP_COUNT
SAME_CRASH = "fatal: the session channel closed unexpectedly"


def run(tmp_path: Path, script: Script, plan: Plan | None = None) -> runs.StandInRun:
    plan = plan or Plan()
    checkout = runs.new_checkout(tmp_path)
    return runs.run_with_stand_in(tmp_path, checkout, plan, script)


def lean_credit_streak() -> Script:
    return Script(by_arm={"lean": [credit_exhausted(i) for i in range(12)]})


def test_n_identical_errors_in_one_arm_stop_the_run_after_exactly_n_sessions_of_that_arm(
    tmp_path: Path,
) -> None:
    result = run(tmp_path, lean_credit_streak())

    assert len(result.launches_in("lean")) == N
    assert result.launches[-1] == result.launches_in("lean")[-1], (
        "a session launched after the streak's last session"
    )


def test_a_stopped_run_exits_incomplete_with_its_stop_reason_recorded(tmp_path: Path) -> None:
    result = run(tmp_path, lean_credit_streak())

    reason = runs.stop_reason(result.results_path)

    assert result.exit_code == INCOMPLETE_EXIT
    assert reason is not None, "the results file records no stop"
    assert len(reason.streak) == N
    assert {s.arm for s in reason.streak} == {"lean"}
    assert "credit balance is too low" in reason.masked_tail.lower()


def test_the_report_of_a_stopped_run_states_its_stop(tmp_path: Path) -> None:
    result = run(tmp_path, lean_credit_streak())

    report = runs.run_report(tmp_path, result.results_path)

    assert "credit balance is too low" in report.lower(), "the report does not state the stop"


def test_a_stop_records_whether_the_other_arm_failed_the_same_way_inside_the_streak(
    tmp_path: Path,
) -> None:
    both = Script(
        by_arm={arm: [credit_exhausted(i) for i in range(12)] for arm in ("full", "lean")}
    )

    one_arm = runs.stop_reason(run(tmp_path / "one", lean_credit_streak()).results_path)
    both_arms = runs.stop_reason(run(tmp_path / "both", both).results_path)

    assert one_arm is not None
    assert both_arms is not None
    assert (one_arm.other_arm_same, both_arms.other_arm_same) == (False, True)


def test_tails_differing_only_in_masked_tokens_count_as_identical(tmp_path: Path) -> None:
    varied = Script(by_arm={"lean": [credit_exhausted(i) for i in range(12)]})

    result = run(tmp_path, varied)

    assert len(result.launches_in("lean")) == N, "volatile tokens kept identical errors apart"


def test_two_genuinely_different_errors_of_one_kind_never_merge_into_a_streak(
    tmp_path: Path,
) -> None:
    alternating = Script(by_arm={"lean": [credit_exhausted(), connection_refused()] * 6})

    result = run(tmp_path, alternating)

    assert runs.stop_reason(result.results_path) is None
    assert len(result.launches_in("lean")) > N


def test_a_task_and_its_retry_erroring_identically_then_a_lean_session_running_leave_the_run_going(
    tmp_path: Path,
) -> None:
    script = Script(by_arm={"lean": [crashed(SAME_CRASH), crashed(SAME_CRASH), ran()]})

    result = run(tmp_path, script)

    assert runs.stop_reason(result.results_path) is None


def test_n_minus_one_identical_errors_then_a_session_that_ran_break_the_streak(
    tmp_path: Path,
) -> None:
    errors = [credit_exhausted()] * (N - 1)
    script = Script(by_arm={"lean": [*errors, ran(), *errors, ran()]})

    result = run(tmp_path, script)

    assert runs.stop_reason(result.results_path) is None


NEVER_COUNTED = {"isolation breaches": isolation_breach(), "graded failures": graded_failure()}


@pytest.mark.parametrize("ending", NEVER_COUNTED.values(), ids=NEVER_COUNTED.keys())
def test_n_sessions_ending_in_an_outcome_that_never_counts_leave_the_run_going(
    tmp_path: Path, ending: runs.Ending
) -> None:
    script = Script(by_arm={"full": [ending] * (N + 2)})

    result = run(tmp_path, script)

    assert runs.stop_reason(result.results_path) is None
    assert len(result.launches_in("full")) >= N + 2


@pytest.mark.parametrize("stop_count", [0, 1, 2])
def test_a_stop_count_below_three_is_refused_before_any_launch(
    tmp_path: Path, stop_count: int
) -> None:
    checkout = runs.new_checkout(tmp_path)

    result = runs.stop_count_refusal(tmp_path, checkout, stop_count)

    assert result.exit_code != 0, "a stop count below 3 was accepted"
    assert result.launches == ()
    printed = result.stdout + result.stderr
    # The refusal may come through the command line's own error path, which prints the usage
    # line and every option name; only the floor the declaration missed, in the spec's words,
    # tells it apart from the command line rejecting an option it does not know.
    assert re.search(r"stop[ _-]count", printed, re.IGNORECASE), (
        f"the refusal does not name the stop count: {printed}"
    )
    assert re.search(r"\bat least 3\b", printed), f"the refusal does not state the floor: {printed}"


def test_the_stop_settings_are_declared_before_the_first_launch(tmp_path: Path) -> None:
    result = run(tmp_path, Script(), Plan(stop_count=4))

    settings = runs.declared_stop_settings(result.results_path)

    assert settings.stop_count == 4
    assert settings.declared_before_first_launch
    assert settings.masking_rule, "the masking rule is not declared"
    assert {"timeout", "error result"} <= {k.replace("_", " ") for k in settings.counting_kinds}
    assert not any("exception" in kind for kind in settings.counting_kinds), (
        "an evaluation exception counts toward the stop"
    )


def test_the_stop_count_defaults_to_three(tmp_path: Path) -> None:
    result = run(tmp_path, Script())

    assert runs.declared_stop_settings(result.results_path).stop_count == 3
