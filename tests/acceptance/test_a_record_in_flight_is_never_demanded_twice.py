"""While a record call is running, the Stop guard never asks for a second one, and a second
call cannot write beside the first.

The step's own unit test holds every run of itself until the scenario releases it, so the
record call is observed mid-flight wherever it runs that test (the Check, the gate's scope).
At each such moment the Stop guard either lets the stop through or says the record is in
flight; it never demands the record command. A second record of the same request started
while the first runs is refused naming the running record, or answers as a replay; the
ledger ends with exactly one record of the request.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers import stop_guard
from tests.acceptance.drivers.loop_repairs import (
    at_each_held_run,
    envelope_of,
    held_work,
    release_all,
    start_record,
    wait_for_run,
)
from tests.acceptance.drivers.step_loop import Step, commits_after, ledger_records, work_on


def _demands_a_record(outcome, request_id: str) -> bool:
    """The stop is held with a message asking for `record` of the request (its marker filled in)."""
    if not outcome.held:
        return False
    message = outcome.message
    in_flight = re.search(r"in flight|running|in progress|already", message, re.I)
    return request_id in message and "--marker" in message and not in_flight


def test_the_stop_guard_never_demands_a_record_that_is_running(tmp_path):
    task = stop_guard.loop(tmp_path, Step("1"))
    request = stop_guard.issue(task)
    work, held = held_work(task)
    agent_id = work_on(task, request, work)
    running = start_record(task, request["id"], agent_id)

    outcomes = at_each_held_run(held, running, lambda n: stop_guard.fire_stop(task))

    assert outcomes, "the record call never ran the step's unit test"
    demanding = [o.describe() for o in outcomes if _demands_a_record(o, request["id"])]
    assert demanding == [], demanding


def test_a_second_record_while_the_first_runs_writes_beside_nothing(tmp_path):
    task = stop_guard.loop(tmp_path, Step("1"))
    request = stop_guard.issue(task)
    work, held = held_work(task)
    agent_id = work_on(task, request, work)
    first = start_record(task, request["id"], agent_id)
    assert wait_for_run(held, 1, first), "the first record never ran the step's unit test"

    second = start_record(task, request["id"], agent_id)
    release_all(held)
    first_said, second_said = envelope_of(first), envelope_of(second)

    records, _ = ledger_records(task)
    mine = [r for r in records if r.get("request") == request["id"]]
    refused = second_said.error is not None and request["id"] in second_said.error["message"]
    replayed = bool((second_said.recorded or {}).get("replayed"))
    assert len(mine) == 1, (first_said.doc, second_said.doc, records)
    assert len(commits_after(task, task.base)) <= 1, (first_said.doc, second_said.doc)
    assert refused or replayed, second_said.doc


def test_an_ended_unrecorded_request_with_no_record_running_still_holds_the_stop_once(tmp_path):
    task = stop_guard.loop(tmp_path, Step("1"))
    request = stop_guard.issue(task)
    ended = stop_guard.leave_ended_agent(task, request, "a final text with a marker")

    held_once = stop_guard.fire_stop(task)
    again = stop_guard.fire_stop(task, stop_hook_active=True)

    assert held_once.held, held_once.describe()
    assert stop_guard.record_command(task, request, ended) in held_once.message
    assert not again.held, again.describe()
