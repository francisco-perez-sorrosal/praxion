"""A [CONFLICT] or [BLOCKED] return commits nothing, keeps its edits, and the step stays open.

Whatever the step's check shows, a return whose agent called its scope incomplete leaves
HEAD where it was, the step's progress line unticked and every file the attempt edited as
the agent left it; the iteration ledger records the return with no commit, and the loop
stops for a person naming the step, the marker and each uncommitted file. A conflicted
step stops `next` with the same cause until its block is revised in the plan; the revision
opens a fresh series whose first prompt names the edits the conflicting attempt left.
`status` and `next` read one state for every step.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.pocket_gate import prompt_of
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    head,
    ledger_records,
    next_action,
    record,
    revise_step,
    step_id_of,
    work_on,
)

STEP_FILES = ("src/step_1.py", "tests/test_step_1.py")
UNTICKED = "- [ ] Step 1: "  # id-citation-discipline:ignore
# The agent's work passes the step's check; only its marker says the scope is incomplete.
COMPLETE_WORK_MARKED = {
    "conflict": Work(final_marker="conflict", ticks_checkbox=False),
    "blocked": Work(final_marker="blocked", ticks_checkbox=False),
}
REVISED = "Write `src/step_1.py` returning the step id, with its scope settled."


def _return_marked(tmp_path, marker):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    head_before = head(task)
    asked = next_action(task)
    agent_id = work_on(task, asked.request, COMPLETE_WORK_MARKED[marker])
    left = {path: (task.root / path).read_bytes() for path in STEP_FILES}
    returned = record(task, asked.request["id"], agent_id=agent_id, marker=marker)
    return task, head_before, left, returned


@pytest.mark.parametrize("marker", sorted(COMPLETE_WORK_MARKED))
def test_a_marked_return_whose_check_passes_commits_nothing(tmp_path, marker):
    task, head_before, _, returned = _return_marked(tmp_path, marker)

    assert returned.recorded["commit"] is None, returned.doc
    assert head(task) == head_before


@pytest.mark.parametrize("marker", sorted(COMPLETE_WORK_MARKED))
def test_a_marked_return_leaves_every_edit_byte_for_byte_and_the_step_unticked(tmp_path, marker):
    task, _, left, _ = _return_marked(tmp_path, marker)

    now = {path: (task.root / path).read_bytes() for path in STEP_FILES}
    assert now == left
    assert UNTICKED in task.wip_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("marker", sorted(COMPLETE_WORK_MARKED))
def test_a_marked_return_is_one_ledger_record_with_no_commit(tmp_path, marker):
    task, _, _, _ = _return_marked(tmp_path, marker)

    records, _ = ledger_records(task)

    assert [r.get("commit") for r in records] == [None], records


@pytest.mark.parametrize("marker", sorted(COMPLETE_WORK_MARKED))
def test_a_marked_return_stops_naming_the_step_the_marker_and_each_uncommitted_file(
    tmp_path, marker
):
    _, _, _, returned = _return_marked(tmp_path, marker)

    said = returned.text()
    assert returned.outcome == "needs-human", returned.doc
    assert step_id_of(returned.stop["step"]) == "1"
    assert marker in said.lower(), said
    assert all(path in said for path in STEP_FILES), said


def test_a_conflicted_step_stops_with_the_same_cause_until_its_block_is_revised(tmp_path):
    task, _, _, returned = _return_marked(tmp_path, "conflict")

    again = next_action(task)
    once_more = next_action(task)

    assert again.outcome == "needs-human", again.doc
    assert again.stop["cause"] == returned.stop["cause"] == once_more.stop["cause"]
    assert step_id_of(again.stop["step"]) == "1"


def test_after_the_revision_the_step_restarts_at_attempt_one_naming_the_kept_edits(tmp_path):
    task, _, _, _ = _return_marked(tmp_path, "conflict")
    revise_step(task, "1", REVISED)

    resumed = next_action(task)

    assert resumed.outcome == "spawn", resumed.doc
    assert step_id_of(resumed.request["step"]) == "1"
    assert resumed.request["attempt"] == 1
    prompt = prompt_of(resumed)
    assert all(path in prompt for path in STEP_FILES), prompt


def test_the_conflicting_attempt_counts_as_one_iteration_of_the_loop(tmp_path):
    task, _, _, returned = _return_marked(tmp_path, "conflict")
    revise_step(task, "1", REVISED)

    resumed = next_action(task)

    assert returned.iterations["used"] == 1, returned.doc
    assert resumed.iterations["used"] >= 1, resumed.doc


# -- status and next read one state ---------------------------------------------------------


def _not_started(tmp_path):
    return build_loop(tmp_path, Step("1"), Step("2"))


def _running(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    next_action(task)
    return task


def _verified(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    attempt(task, Work())
    return task


def _verified_then_revised(tmp_path):
    task = _verified(tmp_path)
    revise_step(task, "1", REVISED)
    return task


def _done_outside_the_loop(tmp_path):
    return build_loop(tmp_path, Step("1"), Step("2"), done=("1",))


def _done_outside_the_loop_then_revised(tmp_path):
    task = _done_outside_the_loop(tmp_path)
    revise_step(task, "1", REVISED)
    return task


def _failed(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    attempt(task, Work(passes=False))
    return task


def _exhausted(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    cap = next_action(task).request["attempt_cap"]
    for _ in range(cap):
        attempt(task, Work(passes=False))
    return task


def _marked(marker):
    def build(tmp_path):
        task, _, _, _ = _return_marked(tmp_path, marker)
        return task

    return build


STATES = {
    "not started": _not_started,
    "running": _running,
    "verified": _verified,
    "verified then revised": _verified_then_revised,
    "done outside the loop": _done_outside_the_loop,
    "done outside the loop then revised": _done_outside_the_loop_then_revised,
    "failed": _failed,
    "exhausted": _exhausted,
    "marked by a conflict": _marked("conflict"),
    "marked by a blocker": _marked("blocked"),
}


@pytest.mark.parametrize("state", sorted(STATES))
def test_status_reports_the_state_next_acts_on(tmp_path, state):
    task = STATES[state](tmp_path)

    disagreement = pocket_gate.disagreement(task)

    assert disagreement is None, disagreement
