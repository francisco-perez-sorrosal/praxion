"""A `Follow-ups:` line in a return reaches the follow-up record when the driver records it.

Each item of the line becomes one `- [open] <item>` line, in order, appended to the task's
`FOLLOW_UPS.md` (created when absent), whatever the marker and the gate verdict; what the
record held stays as it was, and a replayed record adds nothing. A return with no such line,
or one with no item after the colon, leaves the record exactly as it was.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.loop_repairs import (
    final_text,
    finish_with,
    follow_up_items,
    follow_up_record,
    next_request,
)
from tests.acceptance.drivers.step_loop import DEFAULT_WORK, Step, Work, build_loop, record

FIRST = "1"
DONE = f"Step {FIRST} done."
LINE = "Follow-ups: rename the widget's stale helper; drop the unused fixture"
ITEMS = ["- [open] rename the widget's stale helper", "- [open] drop the unused fixture"]
EARLIER = "# Follow-ups — loop-task\n\n- [open] an item an earlier step reported\n"


def _record_return(task, body: str, marker: str = "complete", work: Work = DEFAULT_WORK):
    request = next_request(task)
    agent_id = finish_with(task, request, final_text(body, marker), work)
    return request, agent_id, record(task, request["id"], agent_id=agent_id, marker=marker)


@pytest.mark.parametrize(
    ("marker", "work"),
    [("complete", Work()), ("complete", Work(passes=False)), ("blocked", Work())],
    ids=["complete-and-green", "complete-and-red", "blocked"],
)
def test_each_item_of_the_line_is_appended_as_an_open_follow_up(tmp_path, marker, work):
    task = build_loop(tmp_path, Step("1"))

    _record_return(task, f"{DONE}\n{LINE}", marker, work)

    assert follow_up_items(task) == ITEMS, follow_up_record(task)


def test_items_already_in_the_record_stay_as_they_were(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    follow_up_record(task).write_text(EARLIER, encoding="utf-8")

    _record_return(task, f"{DONE}\n{LINE}")

    text = follow_up_record(task).read_text(encoding="utf-8")
    assert text.startswith(EARLIER), text
    assert follow_up_items(task) == ["- [open] an item an earlier step reported", *ITEMS], text


def test_a_replayed_record_appends_nothing_more(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    request, agent_id, _ = _record_return(task, f"{DONE}\n{LINE}")
    assert follow_up_items(task) == ITEMS, "the first record wrote no follow-up items"
    once = follow_up_record(task).read_bytes()

    replay = record(task, request["id"], agent_id=agent_id, marker="complete")

    assert replay.recorded is not None, replay.doc
    assert replay.recorded.get("replayed"), replay.doc
    assert follow_up_record(task).read_bytes() == once


@pytest.mark.parametrize("body", [DONE, f"{DONE}\nFollow-ups:"], ids=["no-line", "no-item"])
def test_a_return_with_no_item_leaves_an_absent_record_absent(tmp_path, body):
    task = build_loop(tmp_path, Step("1"))

    _record_return(task, body)

    assert not follow_up_record(task).exists()


@pytest.mark.parametrize("body", [DONE, f"{DONE}\nFollow-ups:"], ids=["no-line", "no-item"])
def test_a_return_with_no_item_leaves_the_record_byte_for_byte(tmp_path, body):
    task = build_loop(tmp_path, Step("1"))
    follow_up_record(task).write_text(EARLIER, encoding="utf-8")

    _record_return(task, body)

    assert follow_up_record(task).read_text(encoding="utf-8") == EARLIER
