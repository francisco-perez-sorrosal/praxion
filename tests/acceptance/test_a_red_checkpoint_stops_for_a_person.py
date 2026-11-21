"""A red checkpoint run stops the loop for a person; waiting pockets outlive every stop.

A checkpoint run is red on a failing test or a run cut off at its bound. The loop then
prints `needs-human` with the stop cause `checkpoint-red`, names the red pocket, its failing
tests and every step that deferred it since its last green run, writes `HANDOFF.md`, and
changes no commit, tick or verdict. The red pocket keeps waiting with the same steps, a
pocket green in the same checkpoint stops waiting, and after a person's remedy the next
call runs the red pocket again. The waiting pockets are read from the task directory by
every later call, `status` lists them, and every stop names them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers import deferred_pockets as dp
from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.deferred_pockets import BENCH, ROOT, Pocket
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    commits_after,
    handoff_section,
    head,
    next_action,
    record,
    revise_step,
    status,
    work_on,
)

LAB = Pocket("lab", "lab")
CUT_BOUND_SECONDS = 5
BLOCKED = Work(touches_files=False, final_marker="blocked")


def _red_checkpoint_plan(tmp_path, *, outcome="fails"):
    """Two steps each defer the bench pocket, whose whole suite is red; both commit.

    The bench pocket's runs are bounded at CUT_BOUND_SECONDS from the start, so a suite
    that hangs is cut off wherever it runs."""
    steps = (dp.widening_step("41", BENCH), dp.widening_step("42", BENCH))
    task = dp.build_pocket_loop(tmp_path, *steps, outcomes={BENCH.label: outcome})
    pocket_gate.bound_pocket_run(task, BENCH.root, CUT_BOUND_SECONDS)
    for step in steps:
        recorded = attempt(task, dp.widening_work(step.id, BENCH))
        assert (recorded.recorded or {}).get("commit") is not None, recorded.doc
    return task


def _three_pockets_with_bench_red(tmp_path):
    """One step widens every pocket and commits; only the bench pocket's suite is red."""
    task = dp.build_pocket_loop(
        tmp_path,
        dp.everywhere_step("41"),
        pockets=(ROOT, BENCH, LAB),
        outcomes={BENCH.label: "fails"},
    )
    recorded = attempt(task, dp.everywhere_work("41"))
    assert (recorded.recorded or {}).get("commit") is not None, recorded.doc
    return task


def _one_waiting_pocket_then(tmp_path, second: Step):
    task = dp.build_pocket_loop(tmp_path, dp.widening_step("41", BENCH), second)
    recorded = attempt(task, dp.widening_work("41", BENCH))
    assert (recorded.recorded or {}).get("commit") is not None, recorded.doc
    return task


def _stop_on_the_second_step(task, cause: str):
    """Bring the loop to the stop `cause` names on step 42."""
    if cause == "blocked-marker":
        return attempt(task, BLOCKED)
    return next_action(task)


def _exhaust_the_next_step(task) -> None:
    cap = next_action(task).request["attempt_cap"]
    for _ in range(cap):
        attempt(task, Work(passes=False))


def _handoff_next_action(stopped) -> str:
    text = Path(stopped.stop["handoff"]).read_text(encoding="utf-8")
    return handoff_section(text, "§2 Next action")


# -- A red checkpoint stops for a person ----------------------------------------------------------


def test_a_red_checkpoint_run_stops_for_a_person_with_the_cause_checkpoint_red(tmp_path):
    task = _red_checkpoint_plan(tmp_path)

    stopped = dp.next_until_settled(task)

    assert stopped.outcome == "needs-human", stopped.doc
    assert stopped.exit_code == 2
    assert stopped.stop["cause"] == "checkpoint-red", stopped.stop


def test_the_checkpoint_red_stop_names_the_pocket_and_its_failing_test(tmp_path):
    task = _red_checkpoint_plan(tmp_path)

    stopped = dp.next_until_settled(task)

    assert dp.names_pocket(stopped.text(), BENCH), stopped.text()
    assert BENCH.suite_test_name in stopped.text(), stopped.text()


def test_the_checkpoint_red_handoff_names_the_cause_the_pocket_and_its_failing_test(tmp_path):
    task = _red_checkpoint_plan(tmp_path)

    handoff = _handoff_next_action(dp.next_until_settled(task))

    assert "checkpoint-red" in handoff, handoff
    assert dp.names_pocket(handoff, BENCH), handoff
    assert BENCH.suite_test_name in handoff, handoff


def test_the_checkpoint_red_stop_names_every_step_that_deferred_the_pocket_once(tmp_path):
    task = _red_checkpoint_plan(tmp_path)

    stopped = dp.next_until_settled(task)

    assert dp.waiting_named_by_stop(stopped) == {BENCH.root: ["41", "42"]}


def test_a_red_checkpoint_changes_no_commit_tick_or_step_verdict(tmp_path):
    task = _red_checkpoint_plan(tmp_path)
    head_before, ticks_before, verdicts_before = head(task), dp.checklist(task), dp.verdicts(task)

    stopped = dp.next_until_settled(task)

    assert stopped.stop["cause"] == "checkpoint-red", stopped.doc
    assert head(task) == head_before
    assert dp.checklist(task) == ticks_before
    assert dp.verdicts(task) == verdicts_before


def test_a_checkpoint_run_cut_off_at_its_bound_is_red_and_says_it_was_cut_off(tmp_path):
    task = _red_checkpoint_plan(tmp_path, outcome="hangs")

    stopped = dp.next_until_settled(task)

    assert stopped.stop["cause"] == "checkpoint-red", stopped.doc
    assert "cut off" in stopped.text().lower(), stopped.text()


def test_after_a_remedy_the_next_call_runs_the_red_pocket_again_and_not_the_green_ones(tmp_path):
    task = _three_pockets_with_bench_red(tmp_path)
    stopped = dp.next_until_settled(task)
    assert stopped.stop["cause"] == "checkpoint-red", stopped.doc
    fixed = dp.whole_suite_test(BENCH, dp.run_log_path(tmp_path), outcome="passes", hold=None)
    dp.commit_by_hand(task, BENCH.suite_test, fixed)

    finished = dp.next_until_settled(task)

    assert finished.outcome == "complete", finished.doc
    runs = dp.whole_suite_runs(task, ROOT), dp.whole_suite_runs(task, BENCH)
    assert runs + (dp.whole_suite_runs(task, LAB),) == (1, 2, 1)


def test_a_red_pocket_keeps_its_waiting_steps_while_a_green_one_stops_waiting(tmp_path):
    task = _three_pockets_with_bench_red(tmp_path)

    dp.next_until_settled(task)

    assert dp.waiting_in_status(task) == {BENCH.root: ["41"]}


# -- The waiting pockets survive a stop ----------------------------------------------------------


def test_status_lists_each_waiting_pocket(tmp_path):
    task = _one_waiting_pocket_then(tmp_path, Step("42"))

    table = status(task, as_json=False)

    assert dp.names_pocket(table.stdout, BENCH), table.stdout


def test_the_waiting_pockets_read_the_same_before_and_after_a_stop(tmp_path):
    task = _one_waiting_pocket_then(tmp_path, Step("42"))
    before = dp.waiting_in_status(task)
    attempt(task, BLOCKED)

    after_the_stop = dp.waiting_in_status(task)

    assert before == after_the_stop == {BENCH.root: ["41"]}


def test_a_record_call_cut_off_and_made_again_counts_its_deferral_once(tmp_path):
    log, release = tmp_path / "check-runs.log", tmp_path / "release"
    step = dp.widening_step("41", BENCH)
    task = dp.build_pocket_loop(tmp_path, step)
    asked = next_action(task)
    agent_id = work_on(task, asked.request, dp.widening_work("41", BENCH))
    holding_check = pocket_gate.meeting_test("check", "check", log, release)
    (task.root / step.unit_test).write_text(holding_check, encoding="utf-8")
    log.write_text("check\n", encoding="utf-8")
    call = pocket_gate.start_record(task, asked.request["id"], agent_id)
    pocket_gate.wait_for_lines(log, 2, deadline_seconds=300)
    pocket_gate.cut_off(call)
    release.touch()

    returned = record(task, asked.request["id"], agent_id=agent_id, marker="complete")

    assert returned.recorded["commit"] is not None, returned.doc
    assert len(commits_after(task, task.base)) == 1
    assert dp.waiting_in_status(task) == {BENCH.root: ["41"]}


# -- Every stop names the waiting pockets ----------------------------------------------------------


@pytest.mark.parametrize(
    ("second", "cause"),
    [
        pytest.param(Step("42"), "blocked-marker", id="blocked"),
        pytest.param(Step("42", assignee="doc-engineer"), "not-driven", id="not-driven"),
    ],
)
def test_a_stop_while_a_pocket_waits_names_the_pocket_in_the_stop(tmp_path, second, cause):
    task = _one_waiting_pocket_then(tmp_path, second)

    stopped = _stop_on_the_second_step(task, cause)

    assert stopped.stop["cause"] == cause, stopped.doc
    assert dp.names_pocket(stopped.text(), BENCH), stopped.text()


def test_a_stop_while_a_pocket_waits_names_the_pocket_in_the_handoff(tmp_path):
    task = _one_waiting_pocket_then(tmp_path, Step("42"))

    stopped = attempt(task, BLOCKED)

    assert dp.names_pocket(_handoff_next_action(stopped), BENCH), stopped.stop


def test_a_stop_while_a_pocket_waits_names_its_waiting_steps(tmp_path):
    task = _one_waiting_pocket_then(tmp_path, Step("42"))

    stopped = attempt(task, BLOCKED)

    assert dp.waiting_named_by_stop(stopped) == {BENCH.root: ["41"]}


def test_a_budget_stop_while_a_pocket_waits_names_the_pocket(tmp_path):
    task = _one_waiting_pocket_then(tmp_path, Step("42"))
    _exhaust_the_next_step(task)
    revise_step(task, "42", "Write `src/step_42.py` returning the step id, smaller this time.")

    stopped = next_action(task)

    assert stopped.outcome == "budget-exhausted", stopped.doc
    assert dp.names_pocket(stopped.text(), BENCH), stopped.text()
