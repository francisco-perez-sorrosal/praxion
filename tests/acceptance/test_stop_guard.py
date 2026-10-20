"""The Stop-time guard holds a stop once on an ended, unrecorded step-loop request.

When the main session would end its turn while an agent it started on a driver-issued
request has ended and no record holds the return, the stop is held with one short
message naming the exact `record` call. Otherwise the stop goes through untouched: the
agent may still be running, the guard already held this stop, an input is unreadable,
or no step loop is active, and in every case the guard only reads.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import stop_guard
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    leave_agent_transcript,
    new_agent_id,
    record,
)
from tests.acceptance.drivers.stop_guard import (
    END_SHAPES,
    MESSAGE_CAP_BYTES,
    fire_stop,
    issue,
    leave_ended_agent,
    leave_running_agent,
    loop,
)


def _ended_unrecorded(tmp_path, shape="a final text with a marker"):
    task = loop(tmp_path, Step("1"))
    request = issue(task)
    ended = leave_ended_agent(task, request, shape)
    return task, request, ended


# -- Holding a stop ------------------------------------------------------------------------


@pytest.mark.parametrize("shape", END_SHAPES)
def test_an_ended_unrecorded_request_holds_the_stop_with_the_exact_record_call(tmp_path, shape):
    task, request, ended = _ended_unrecorded(tmp_path, shape)

    outcome = fire_stop(task)

    assert outcome.held, outcome.describe()
    assert stop_guard.record_command(task, request, ended) in outcome.message, outcome.message


def test_the_held_message_is_short_and_says_the_return_is_not_recorded(tmp_path):
    task, request, ended = _ended_unrecorded(tmp_path)

    message = fire_stop(task).message

    assert len(message.encode("utf-8")) <= MESSAGE_CAP_BYTES, len(message.encode("utf-8"))
    assert request["id"] in message
    assert ended.agent_id in message
    assert re.search(r"not (yet )?recorded", message, re.IGNORECASE), message


@pytest.mark.parametrize("shape", END_SHAPES)
def test_whenever_the_guard_holds_record_accepts_the_agent_as_ended(tmp_path, shape):
    task, request, ended = _ended_unrecorded(tmp_path, shape)
    assert fire_stop(task).held

    recorded = stop_guard.record_return(task, request, ended)

    assert not (recorded.error and recorded.error.get("code") == "agent-running"), recorded.doc


def test_a_held_stop_writes_nothing(tmp_path):
    task, _, _ = _ended_unrecorded(tmp_path)
    before = stop_guard.files_and_bytes(task)

    outcome = fire_stop(task)

    assert outcome.held
    assert stop_guard.files_and_bytes(task) == before


def _two_ended_unrecorded(tmp_path):
    """Two tasks, each with an ended, unrecorded request; the first task's issued first."""
    first = loop(tmp_path, Step("1"))
    second = stop_guard.second_task(first, "loop-task-b", Step("8"))
    pairs = [(task, issue(task)) for task in (first, second)]
    return [
        (task, request, leave_ended_agent(task, request, END_SHAPES[0])) for task, request in pairs
    ]


def test_of_two_qualifying_requests_the_oldest_is_named_first_and_the_other_once_it_is_recorded(
    tmp_path,
):
    (older, older_request, older_end), (newer, newer_request, newer_end) = _two_ended_unrecorded(
        tmp_path
    )

    named_first = fire_stop(older).message
    stop_guard.record_return(older, older_request, older_end)
    named_next = fire_stop(older).message

    assert stop_guard.record_command(older, older_request, older_end) in named_first, named_first
    assert stop_guard.record_command(newer, newer_request, newer_end) in named_next, named_next


def test_a_request_still_unrecorded_is_named_again_on_the_next_stop(tmp_path):
    (older, older_request, older_end), _ = _two_ended_unrecorded(tmp_path)
    expected = stop_guard.record_command(older, older_request, older_end)

    first = fire_stop(older).message
    again = fire_stop(older).message

    assert expected in first, first
    assert expected in again, again


# -- Letting a stop through -------------------------------------------------------------------


def test_a_running_agent_never_holds_the_stop_and_record_refuses_it(tmp_path):
    task = loop(tmp_path, Step("1"))
    request = issue(task)
    agent_id = leave_running_agent(task, request)

    outcome = fire_stop(task)
    refused = record(task, request["id"], agent_id=agent_id, marker="complete")

    assert outcome.let_through_silently, outcome.describe()
    assert refused.error is not None, refused.doc
    assert refused.error["code"] == "agent-running", refused.doc


def test_a_request_whose_agent_call_was_never_made_lets_the_stop_through(tmp_path):
    task = loop(tmp_path, Step("1"))
    issue(task)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()


def test_a_request_an_earlier_session_started_lets_the_stop_through(tmp_path):
    task, _, ended = _ended_unrecorded(tmp_path)
    stop_guard.move_to_earlier_session(task, ended.agent_id)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()


def test_a_stop_already_held_once_goes_through_without_reading_anything(tmp_path):
    task, _, _ = _ended_unrecorded(tmp_path)

    outcome = fire_stop(task, stop_hook_active=True)

    assert outcome.let_through_silently, outcome.describe()
    assert outcome.sandbox_files_read() == []
    assert outcome.processes_started() == []


def _unreadable_wip(task):
    task.wip_path.unlink()
    task.wip_path.mkdir()


def _malformed_ledger(task):
    (task.task_dir / "ITERATION_LEDGER.jsonl").write_text("{not json\n\x00\x01 garbage\n")


UNREADABLE_INPUTS = {
    "an empty hook input": ("", None),
    "a hook input that is not JSON": ("{stop_hook_active: false", None),
    "a hook input that is a JSON list": ("[1, 2, 3]", None),
    "a step record that cannot be read": (None, _unreadable_wip),
    "an iteration ledger that cannot be parsed": (None, _malformed_ledger),
}


@pytest.mark.parametrize("case", sorted(UNREADABLE_INPUTS))
def test_an_input_the_guard_cannot_read_lets_the_stop_through_silently(tmp_path, case):
    task, _, _ = _ended_unrecorded(tmp_path)
    stdin, spoil = UNREADABLE_INPUTS[case]
    if spoil is not None:
        spoil(task)

    outcome = fire_stop(task, stdin=stdin)

    assert outcome.let_through_silently, f"{case}: {outcome.describe()}"


def test_an_ended_transcript_holding_an_unparseable_line_lets_the_stop_through(tmp_path):
    task = loop(tmp_path, Step("1"))
    request = issue(task)
    agent_id = new_agent_id()
    leave_agent_transcript(
        task,
        request,
        agent_id,
        requests=9,
        final_text="Done.\n[COMPLETE]",
        ended=True,
        readable=False,
    )

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()


def test_an_unreadable_agent_transcript_lets_the_stop_through_silently(tmp_path):
    task, _, ended = _ended_unrecorded(tmp_path)
    stop_guard.make_transcript_unreadable(task, ended.agent_id)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()


@pytest.mark.parametrize(
    "case", ["a running agent", "a request never started", "an unreadable hook input"]
)
def test_a_stop_let_through_writes_nothing(tmp_path, case):
    task = loop(tmp_path, Step("1"))
    request = issue(task)
    if case == "a running agent":
        leave_running_agent(task, request)
    before = stop_guard.files_and_bytes(task)

    outcome = fire_stop(task, stdin="not json" if case == "an unreadable hook input" else None)

    assert outcome.let_through_silently, outcome.describe()
    assert stop_guard.files_and_bytes(task) == before


def test_the_guard_is_registered_to_run_synchronously_within_a_time_bound():
    registration = stop_guard.guard_registration()

    assert registration.synchronous, "an asynchronous Stop hook can never hold a stop"
    assert isinstance(registration.timeout, (int, float)), registration
    assert registration.timeout > 0


# -- No step loop -----------------------------------------------------------------------------


def test_a_checkout_with_no_pipeline_directory_reads_nothing_and_starts_nothing(tmp_path):
    task = loop(tmp_path, Step("1"))
    stop_guard.remove_pipeline_directory(task)

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    assert outcome.sandbox_files_read() == []
    assert outcome.processes_started() == []


def test_a_pipeline_outside_a_step_loop_reads_only_its_step_record(tmp_path):
    task = loop(tmp_path, Step("1"))

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    assert set(outcome.sandbox_files_read()) <= stop_guard.cheap_reads(task)
    assert outcome.transcripts_read() == []
    assert outcome.processes_started() == []


def test_a_loop_whose_every_request_is_recorded_reads_no_transcript(tmp_path):
    task = loop(tmp_path, Step("1"), Step("2"))
    attempt(task, Work())
    attempt(task, Work())

    outcome = fire_stop(task)

    assert outcome.let_through_silently, outcome.describe()
    assert set(outcome.sandbox_files_read()) <= stop_guard.cheap_reads(task)
    assert outcome.transcripts_read() == []
    assert outcome.processes_started() == []
