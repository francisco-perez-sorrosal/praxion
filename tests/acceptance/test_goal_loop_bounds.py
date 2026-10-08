"""A goal step is bounded by its own iteration budget and stopped when it stops converging.

The envelope's budget is the plan's `Iterations:` value; once that many iterations are
recorded short of the goal the loop exits 3, and no request's attempt exceeds it. Two
non-progressing iterations in a row stop for a human with cause `stalled` before any
further iteration, ahead of a spent budget; a progressing iteration resets the count. A
blocked return stops at once. Every reader agrees whether the step is spent: the
reconciler reads it exhausted exactly when the loop has stalled, never merely because two
iterations have been recorded.
"""

from __future__ import annotations

from tests.acceptance.drivers.goal_loop import (
    Iteration,
    build_goal,
    goal_step_id,
    iterate_by_relay,
)
from tests.acceptance.drivers.step_loop import (
    next_action,
    reconciler_verdict,
    snapshot,
    status,
    step_id_of,
)

PROGRESS_ONE = Iteration(implemented=("one",))
PROGRESS_ONE_TWO = Iteration(implemented=("one", "two"))
NO_PROGRESS = Iteration(touches_widget=False)


def test_the_envelope_reports_the_goal_steps_iteration_field_as_its_budget(tmp_path):
    task = build_goal(tmp_path, iterations=4)

    asked = next_action(task)

    assert asked.iterations["budget"] == 4


def test_a_goal_short_of_its_check_when_the_budget_is_spent_exits_three(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    iterate_by_relay(task, PROGRESS_ONE)
    iterate_by_relay(task, PROGRESS_ONE_TWO)

    stopped = next_action(task)

    assert stopped.exit_code == 3
    assert stopped.outcome == "budget-exhausted"
    assert stopped.stop["cause"] == "iteration-budget"
    assert stopped.iterations["used"] == stopped.iterations["budget"] == 2


def test_no_request_for_a_goal_step_carries_an_attempt_beyond_its_iteration_field(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    first = iterate_by_relay(task, PROGRESS_ONE)
    second = iterate_by_relay(task, PROGRESS_ONE_TWO)

    stopped = next_action(task)

    assert [first.request["attempt"], second.request["attempt"]] == [1, 2]
    assert stopped.request is None


def test_two_non_progressing_iterations_in_a_row_stop_for_a_human_as_stalled(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    first = iterate_by_relay(task, NO_PROGRESS)
    second = iterate_by_relay(task, NO_PROGRESS)

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    assert stopped.request is None
    assert stopped.stop["cause"] == "stalled"
    assert step_id_of(stopped.stop["step"]) == goal_step_id(task)
    assert [a["agent_id"] for a in stopped.stop["attempts"]] == [first.agent_id, second.agent_id]


def test_a_stall_is_reported_ahead_of_a_spent_budget(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, NO_PROGRESS)

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.stop["cause"] == "stalled"


def test_a_progressing_iteration_resets_the_stall_count(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, PROGRESS_ONE)
    iterate_by_relay(task, NO_PROGRESS)

    asked = next_action(task)

    assert asked.outcome == "spawn", asked.doc
    assert asked.exit_code == 0


def test_a_stall_stop_repeats_and_writes_nothing_however_often_next_is_asked(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, NO_PROGRESS)
    first_stop = next_action(task)
    files_after_stop = snapshot(task)

    second_stop = next_action(task)

    assert second_stop.doc == first_stop.doc
    assert snapshot(task) == files_after_stop


def test_a_blocked_return_stops_the_goal_for_a_human_at_once(tmp_path):
    task = build_goal(tmp_path, iterations=6)

    iterate_by_relay(task, Iteration(touches_widget=False, progress=None, marker="blocked"))
    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    assert stopped.stop["cause"] == "blocked-marker"


def test_two_progressing_iterations_never_read_as_exhausted_to_any_reader(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, PROGRESS_ONE)
    iterate_by_relay(task, PROGRESS_ONE_TWO)

    asked = next_action(task)
    state = status(task, as_json=True).json()
    verdict = reconciler_verdict(task, goal_step_id(task))

    assert asked.outcome == "spawn", asked.doc
    assert verdict["verdict"] != "attempts-exhausted", verdict
    assert state["steps"][0]["verdict"] != "attempts-exhausted", state


def test_a_stalled_goal_reads_as_exhausted_to_the_reconciler_and_to_status(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, NO_PROGRESS)

    verdict = reconciler_verdict(task, goal_step_id(task))
    report = status(task, as_json=True)

    assert verdict["verdict"] == "attempts-exhausted", verdict
    assert report.json()["steps"][0]["verdict"] == "attempts-exhausted", report.stdout


def test_status_shows_the_stall_as_the_next_action(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, NO_PROGRESS)

    report = status(task, as_json=False)

    assert "stalled" in report.stdout + report.stderr, report.stdout
