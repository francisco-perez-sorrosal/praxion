"""`record` takes three relayed values and derives everything else from ground truth.

The orchestrator relays only the request id, the agent id and the marker it saw. The
loop derives the attempt's turns (the distinct API requests in the agent's own
transcript, against its declared cap), its stop reason, its test result and its commit;
says so when the transcript cannot be read; refuses a `record` that arrives before the
agent's end or names a stale request; and writes one ledger record per return, never
two for a replayed call.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    head,
    implementer_max_turns,
    leave_agent_transcript,
    ledger_records,
    new_agent_id,
    next_action,
    record,
    snapshot,
    status,
    work_on,
)


def test_record_derives_the_turns_from_the_agents_own_transcript_against_its_cap(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    recorded = attempt(task, Work(requests=17)).recorded

    assert recorded["turns"] == 17
    assert recorded["max_turns"] == implementer_max_turns()


@pytest.mark.parametrize(
    ("marker", "stop_reason"),
    [
        ("complete", "completed"),
        ("blocked", "blocked"),
        ("conflict", "conflict"),
        ("partial", "partial"),
        ("none", "no-marker"),
    ],
)
def test_the_stop_reason_tells_each_kind_of_return_apart(tmp_path, marker, stop_reason):
    task = build_loop(tmp_path, Step("1"))

    recorded = attempt(task, Work(final_marker=marker, requests=9)).recorded

    assert recorded["stop_reason"] == stop_reason


def test_an_agent_that_used_its_whole_turn_cap_without_a_marker_stopped_at_the_cap(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    recorded = attempt(
        task, Work(final_marker="none", requests=implementer_max_turns(), passes=False)
    ).recorded

    assert recorded["stop_reason"] == "turn-cap"


def test_an_unreadable_transcript_records_the_turns_as_unknown_and_says_so(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    request = next_action(task).request
    agent_id = new_agent_id()
    leave_agent_transcript(
        task, request, agent_id, requests=5, final_text="[COMPLETE]", ended=True, readable=False
    )

    recorded = record(task, request["id"], agent_id=agent_id, marker="complete")

    assert recorded.recorded["turns"] is None
    assert "transcript-unreadable" in recorded.warning_codes


def test_a_relayed_marker_the_transcript_contradicts_is_flagged(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    request = next_action(task).request
    agent_id = work_on(task, request, Work(final_marker="complete"))

    recorded = record(task, request["id"], agent_id=agent_id, marker="none")

    assert "marker-disagreement" in recorded.warning_codes
    assert recorded.recorded["marker"] == "complete"


def test_a_record_before_the_agent_has_ended_is_refused_and_changes_nothing(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    request = next_action(task).request
    agent_id = new_agent_id()
    leave_agent_transcript(
        task, request, agent_id, requests=4, final_text="Still editing.", ended=False
    )
    head_before, files_before = head(task), snapshot(task)

    refused = record(task, request["id"], agent_id=agent_id, marker="complete")

    assert refused.exit_code == 4
    assert refused.outcome == "error"
    assert head(task) == head_before
    assert snapshot(task) == files_before
    assert status(task, as_json=True).json()["pending_request"] == request["id"]


def test_each_return_adds_exactly_one_ledger_record_and_the_ledger_reads_clean(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    failed = attempt(task, Work(passes=False))
    verified = attempt(task, Work())

    records, findings = ledger_records(task)

    assert findings == []
    assert [r["agent_id"] for r in records] == [
        failed.recorded["agent_id"],
        verified.recorded["agent_id"],
    ]
    assert records[0]["commit"] is None
    assert records[1]["commit"] is not None
    assert verified.recorded["commit"].startswith(records[1]["commit"][:7])


def test_a_replayed_record_adds_nothing_and_says_it_is_a_replay(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    request = next_action(task).request
    agent_id = work_on(task, request, Work())
    record(task, request["id"], agent_id=agent_id, marker="complete")
    head_after_first, records_after_first = head(task), ledger_records(task)[0]

    replay = record(task, request["id"], agent_id=agent_id, marker="complete")

    assert replay.recorded["replayed"] is True
    assert head(task) == head_after_first
    assert ledger_records(task)[0] == records_after_first


def test_a_record_naming_a_request_that_is_not_pending_is_refused_naming_the_pending_one(
    tmp_path,
):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    pending = next_action(task).request
    files_before = snapshot(task)

    refused = record(task, "s2-a1-implement", agent_id=new_agent_id(), marker="complete")

    assert refused.exit_code == 4
    assert refused.error["code"] == "request-not-pending"
    assert pending["id"] in refused.error["message"]
    assert snapshot(task) == files_before


def test_a_record_when_nothing_is_pending_is_refused_saying_none_is_pending(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    refused = record(task, "s1-a1-implement", agent_id=new_agent_id(), marker="complete")

    message = refused.error["message"].lower()
    assert refused.exit_code == 4
    assert refused.error["code"] == "request-not-pending"
    assert "pending" in message
    assert re.search(r"\bnone?\b", message), message
