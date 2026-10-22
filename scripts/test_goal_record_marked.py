"""A goal iteration whose agent returned [CONFLICT] or [BLOCKED] is not judged, kept or restored.

The agent called its scope incomplete, so the recorder commits nothing, ticks nothing and leaves
every edit in the tree, whatever the check shows; one ledger record carries the return with no
commit, and the loop stops on the marker. The scratch goal checkout and the verbs come from
``scripts/test_goal_record.py``, which holds the recorder's behaviour through the `record` verb.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from test_goal_record import (  # noqa: E402,F401
    PROGRESS_LINE,
    SLUG,
    WIDGET,
    Work,
    ask,
    build_goal,
    do_work,
    head,
    leave_transcript,
    ledger,
    patch_of,
    record,
    sandbox,  # the autouse environment of the scratch checkout
    snapshot_of,
    tree_text,
    verb,
    widget_source,
)

ALL_FUNCTIONS = ("one", "two", "three")
MARKERS = ("blocked", "conflict")


def iterate_marked(goal, marker, implemented=ALL_FUNCTIONS):
    """One iteration whose agent finished `implemented` and then returned `marker`."""
    work = Work(implemented=implemented, marker=f"[{marker.upper()}]")
    request = ask(goal)
    do_work(goal, work)
    leave_transcript(goal, request, "a1b2c3d4e5f60718", work)
    return request, record(goal, request, marker=marker)


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_iteration_whose_check_passes_commits_and_ticks_nothing(tmp_path, marker):
    goal = build_goal(tmp_path, implemented=("one", "two"))
    before = head(goal)

    _, reply = iterate_marked(goal, marker)

    assert (reply.recorded["commit"], head(goal)) == (None, before)
    assert "- [x]" not in (goal.task_dir / "WIP.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_iteration_keeps_every_edit_in_the_tree_and_saves_no_patch(tmp_path, marker):
    goal = build_goal(tmp_path, implemented=("one", "two"))

    request, _ = iterate_marked(goal, marker)

    assert tree_text(goal, WIDGET) == widget_source(ALL_FUNCTIONS)
    assert PROGRESS_LINE in (goal.task_dir / "WIP.md").read_text(encoding="utf-8")
    assert not patch_of(goal, request).exists()
    assert not snapshot_of(goal, request).exists()


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_iteration_whose_check_still_fails_restores_nothing_either(tmp_path, marker):
    goal = build_goal(tmp_path)
    before = head(goal)

    request, reply = iterate_marked(goal, marker, implemented=("one",))

    assert (reply.recorded["commit"], head(goal)) == (None, before)
    assert tree_text(goal, WIDGET) == widget_source(("one",))
    assert not patch_of(goal, request).exists()


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_iteration_is_one_ledger_record_with_no_commit_and_the_markers_stop(
    tmp_path, marker
):
    goal = build_goal(tmp_path, implemented=("one", "two"))

    iterate_marked(goal, marker)

    records = ledger(goal)
    assert [(r["commit"], r["stop_reason"]) for r in records] == [(None, marker)]


@pytest.mark.parametrize("marker", MARKERS)
def test_a_marked_goal_step_stops_next_on_its_marker_and_status_reads_it_marked(tmp_path, marker):
    goal = build_goal(tmp_path, implemented=("one", "two"))
    iterate_marked(goal, marker)

    first, again = verb(goal, "next", SLUG), verb(goal, "next", SLUG)
    verdicts = {s["step"]: s["verdict"] for s in verb(goal, "status", SLUG).doc["steps"]}

    assert (first.doc["outcome"], first.stop["cause"]) == ("needs-human", f"{marker}-marker")
    assert again.stop["cause"] == first.stop["cause"]
    assert set(verdicts.values()) == {"marked"}
