"""The step loop picks the plan's next step the way the planner ordered it, every time.

`next` returns the first step in plan order that is not verified-complete and whose
declared dependencies all are; a parallel group never makes a step wait for a sibling;
asking again before the pending request is recorded reissues the same request and
changes nothing; a plan whose remaining steps can never start stops for a human; a
step assigned to another agent is never skipped or read as done; and `status` reports
all of it without writing anything.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.step_loop import (
    Step,
    build_loop,
    next_action,
    snapshot,
    status,
    step_id_of,
)


def test_a_fresh_plan_starts_with_its_first_step(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2", depends_on=("1",)), Step("3"))

    asked = next_action(task)

    assert asked.outcome == "spawn"
    assert asked.request["step"] == "1"


def test_a_step_whose_dependency_is_verified_is_the_next_one(tmp_path):
    task = build_loop(
        tmp_path, Step("1"), Step("2", depends_on=("1",)), Step("3", depends_on=("2",)), done=("1",)
    )

    asked = next_action(task)

    assert asked.request["step"] == "2"


def test_a_step_waiting_on_an_unverified_dependency_is_passed_over_for_a_later_one(tmp_path):
    task = build_loop(
        tmp_path, Step("1", depends_on=("3",)), Step("2", depends_on=("1",)), Step("3")
    )

    asked = next_action(task)

    assert asked.request["step"] == "3"


def test_a_parallel_group_never_makes_a_step_wait_for_its_sibling(tmp_path):
    task = build_loop(
        tmp_path,
        Step("1", parallel_group="A", depends_on=("3",)),
        Step("2", parallel_group="A"),
        Step("3", depends_on=("2",)),
    )

    asked = next_action(task)

    assert asked.request["step"] == "2"


def test_asking_twice_reissues_the_pending_request_and_changes_no_file(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    first = next_action(task)
    files_after_first = snapshot(task)

    second = next_action(task)

    assert second.request["id"] == first.request["id"]
    assert first.request["reissued"] is False
    assert second.request["reissued"] is True
    assert snapshot(task) == files_after_first


def test_selection_over_unchanged_inputs_is_the_same_in_a_second_identical_checkout(tmp_path):
    steps = (Step("1", depends_on=("2",)), Step("2"), Step("3", parallel_group="B"))
    one = build_loop(tmp_path / "one", *steps)
    two = build_loop(tmp_path / "two", *steps)

    assert next_action(one).request["id"] == next_action(two).request["id"]


def test_a_dependency_on_a_step_the_plan_lacks_stops_for_a_human_naming_both(tmp_path):
    task = build_loop(tmp_path, Step("4a", depends_on=("12b",)))

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    said = stopped.text()
    assert re.search(r"\b4a\b", said), f"the stop does not name the step that cannot start:\n{said}"
    assert re.search(r"\b12b\b", said), f"the stop does not name the missing dependency:\n{said}"


def test_a_dependency_cycle_stops_for_a_human_naming_each_step_in_it(tmp_path):
    task = build_loop(tmp_path, Step("5a", depends_on=("6a",)), Step("6a", depends_on=("5a",)))

    stopped = next_action(task)

    assert stopped.exit_code == 2
    said = stopped.text()
    assert re.search(r"\b5a\b", said), f"the stop does not name the step 5a of the cycle:\n{said}"
    assert re.search(r"\b6a\b", said), f"the stop does not name the step 6a of the cycle:\n{said}"


def test_a_step_assigned_to_another_agent_is_neither_skipped_nor_read_as_done(tmp_path):
    task = build_loop(
        tmp_path, Step("1", assignee="test-engineer", declares_check=False), Step("2")
    )

    asked = next_action(task)

    assert asked.outcome != "complete"
    assert asked.outcome != "spawn" or asked.request["step"] == "1", (
        f"the loop moved past an unverified step assigned to another agent: {asked.doc}"
    )


def test_a_plan_whose_steps_are_all_verified_is_complete_with_no_request(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"), done=("1", "2"))

    finished = next_action(task)

    assert finished.exit_code == 0
    assert finished.outcome == "complete"
    assert finished.request is None


def test_status_reports_the_pending_request_and_each_step_without_writing(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"), done=("1",))
    pending = next_action(task)
    files_before = snapshot(task)

    report = status(task, as_json=True)

    state = report.json()
    assert report.exit_code == 0
    assert state["pending_request"] == pending.request["id"]
    assert [step_id_of(s["step"]) for s in state["steps"]] == ["1", "2"]
    assert state["steps"][0]["verdict"] == "verified-complete"
    assert state["iterations"]["budget"] >= 1
    assert snapshot(task) == files_before


def test_status_without_json_prints_a_readable_table_naming_each_step(tmp_path):
    task = build_loop(tmp_path, Step("7c"), Step("8d"))

    report = status(task, as_json=False)

    assert report.exit_code == 0
    assert re.search(r"\b7c\b", report.stdout), report.stdout
    assert re.search(r"\b8d\b", report.stdout), report.stdout
