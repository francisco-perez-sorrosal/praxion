"""A goal iteration returning [CONFLICT] or [BLOCKED] commits nothing and keeps its edits.

A goal step is a step like any other here: whatever its check shows, an iteration whose
worker called its scope incomplete leaves HEAD where it was, the goal's progress line
unticked and every edit the iteration made in the working tree; the iteration ledger
records the return with no commit, and the loop stops for a person naming the step, the
marker and the uncommitted file. The step stays open, so `next` keeps stopping on it with
the same cause, and `status` reads the same state `next` acts on.

Each scenario starts from a goal one function short of its check, and the iteration
implements that function and appends its progress line: the work alone would be
committed and would complete the goal. Only the marker says otherwise.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.goal_loop import (
    ALL_FUNCTIONS,
    PROGRESS_LINE,
    WIDGET,
    Iteration,
    build_goal,
    goal_step_id,
    iterate_by_relay,
    progress_lines,
    ticked,
    widget_source,
)
from tests.acceptance.drivers.step_loop import (
    head,
    ledger_records,
    next_action,
    step_id_of,
)

MARKERS = ("blocked", "conflict")


def _goal_iteration_marked(tmp_path, marker):
    task = build_goal(tmp_path, implemented=("one", "two"))
    head_before = head(task)
    relayed = iterate_by_relay(task, Iteration(implemented=ALL_FUNCTIONS, marker=marker))
    return task, head_before, relayed


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_iteration_whose_check_passes_commits_nothing(tmp_path, marker):
    task, head_before, relayed = _goal_iteration_marked(tmp_path, marker)

    returned = relayed.returned
    assert returned.recorded is not None, returned.doc
    assert returned.recorded["commit"] is None, returned.doc
    assert head(task) == head_before


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_iteration_keeps_every_edit_and_leaves_the_goal_unticked(tmp_path, marker):
    task, _, _ = _goal_iteration_marked(tmp_path, marker)

    widget_now = (task.root / WIDGET).read_text(encoding="utf-8")

    assert widget_now == widget_source(ALL_FUNCTIONS), widget_now
    assert PROGRESS_LINE in progress_lines(task)
    assert not ticked(task)


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_iteration_is_one_ledger_record_with_no_commit(tmp_path, marker):
    task, _, _ = _goal_iteration_marked(tmp_path, marker)

    records, _ = ledger_records(task)

    assert [r.get("commit") for r in records] == [None], records


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_iteration_stops_naming_the_step_the_marker_and_the_uncommitted_file(
    tmp_path, marker
):
    task, _, relayed = _goal_iteration_marked(tmp_path, marker)

    returned = relayed.returned
    said = returned.text()
    assert returned.outcome == "needs-human", returned.doc
    assert returned.stop is not None, returned.doc
    assert step_id_of(returned.stop["step"]) == goal_step_id(task)
    assert marker in said.lower(), said
    assert WIDGET in said, said


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_step_stops_with_the_same_cause_on_every_next(tmp_path, marker):
    task, _, relayed = _goal_iteration_marked(tmp_path, marker)

    again = next_action(task)
    once_more = next_action(task)

    assert relayed.returned.stop is not None, relayed.returned.doc
    assert again.outcome == "needs-human", again.doc
    assert again.stop is not None, again.doc
    assert once_more.stop is not None, once_more.doc
    assert again.stop["cause"] == relayed.returned.stop["cause"] == once_more.stop["cause"]
    assert step_id_of(again.stop["step"]) == goal_step_id(task)


@pytest.mark.parametrize("marker", MARKERS)
def test_status_reports_the_state_next_acts_on_for_a_marked_goal_step(tmp_path, marker):
    task, _, _ = _goal_iteration_marked(tmp_path, marker)

    disagreement = pocket_gate.disagreement(task)
    verdicts = pocket_gate.status_verdicts(task)

    assert disagreement is None, disagreement
    assert verdicts[goal_step_id(task)] != "verified-complete", verdicts
