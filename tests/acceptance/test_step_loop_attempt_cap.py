"""The attempt cap is enforced in code, write-ahead.

An attempt is counted in WIP.md before its request is printed; a capped attempt still
running is in flight, not exhausted; once the capped attempt is recorded without
verified completion -- including the golden bad case of a `[COMPLETE]` marker whose
check fails -- no further request is emitted and the loop stops for a human with a
replan request naming what stopped each attempt. Only a visible plan revision reopens
the step, and a spawn that never started costs no attempt.
"""

from __future__ import annotations

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    attempts_line,
    build_loop,
    leave_agent_transcript,
    ledger_records,
    new_agent_id,
    next_action,
    reconciler_verdict,
    record_not_started,
    revise_step,
    snapshot,
    status,
    step_id_of,
)

FAILS_ITS_CHECK_BUT_CLAIMS_DONE = Work(passes=False, final_marker="complete", claims_green=True)


def _fail_attempts(task, count):
    """Spend `count` attempts on the next step, each returning complete with its check failing."""
    for _ in range(count):
        attempt(task, FAILS_ITS_CHECK_BUT_CLAIMS_DONE)


def _exhaust(task):
    """Spend every attempt the cap allows on the next step; return the cap."""
    cap = next_action(task).request["attempt_cap"]
    _fail_attempts(task, cap)
    return cap


def test_the_attempt_is_counted_in_wip_before_its_request_is_printed(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    asked = next_action(task)

    assert asked.request["attempt"] == 1
    assert attempts_line(task, "1") is not None, task.wip_path.read_text(encoding="utf-8")
    assert "count=1" in attempts_line(task, "1")


def test_a_second_attempt_is_counted_as_two_before_its_request_is_printed(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    attempt(task, FAILS_ITS_CHECK_BUT_CLAIMS_DONE)

    asked = next_action(task)

    assert asked.request["attempt"] == 2
    assert asked.request["id"] == "s1-a2-implement"
    assert "count=2" in attempts_line(task, "1")


def test_a_capped_attempt_still_running_reads_as_in_flight_not_exhausted(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    cap = next_action(task).request["attempt_cap"]
    _fail_attempts(task, cap - 1)
    capped = next_action(task).request

    state = status(task, as_json=True).json()

    assert capped["attempt"] == cap
    assert state["pending_request"] == capped["id"]
    assert state["steps"][0]["verdict"] != "attempts-exhausted"
    assert reconciler_verdict(task, "1")["verdict"] != "attempts-exhausted"


def test_a_complete_marker_whose_check_fails_on_the_capped_attempt_stops_for_a_human(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    cap = _exhaust(task)

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    assert stopped.request is None
    assert stopped.stop["cause"] == "attempts-exhausted"
    assert step_id_of(stopped.stop["step"]) == "1"
    assert [a["attempt"] for a in stopped.stop["attempts"]] == list(range(1, cap + 1))
    assert all(a["commit"] is None for a in stopped.stop["attempts"])
    assert stopped.stop["replan_request"], "an exhausted step stops without a replan request"


def test_the_replan_request_comes_with_what_stopped_each_attempt(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)

    stopped = next_action(task)

    assert {a["stop_reason"] for a in stopped.stop["attempts"]} == {"completed"}
    assert "verified-complete" not in {a["gate"] for a in stopped.stop["attempts"]}


def test_an_exhausted_step_reads_as_attempts_exhausted_to_the_reconciler(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)

    verdict = reconciler_verdict(task, "1")

    assert verdict["verdict"] == "attempts-exhausted"


def test_no_request_beyond_the_cap_is_ever_emitted_however_often_next_is_asked(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)
    first_stop = next_action(task)
    files_after_stop = snapshot(task)

    second_stop = next_action(task)

    assert second_stop.doc == first_stop.doc
    assert snapshot(task) == files_after_stop


def test_a_plan_revision_reopens_an_exhausted_step_with_a_fresh_attempt_series(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _exhaust(task)
    next_action(task)
    revise_step(task, "1", "Write `src/step_1.py` returning the step id, smaller this time.")

    reopened = next_action(task)

    assert reopened.outcome == "spawn"
    assert reopened.request["step"] == "1"
    assert reopened.request["attempt"] == 1


def test_a_spawn_that_never_started_costs_no_attempt_and_no_ledger_record(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    first = next_action(task).request

    withdrawn = record_not_started(task, first["id"], "the Agent tool call failed before launch")
    again = next_action(task).request

    records, _ = ledger_records(task)
    assert withdrawn.exit_code == 0
    assert withdrawn.recorded["stop_reason"] == "not-started"
    assert again["attempt"] == 1
    assert records == []


def test_reporting_not_started_for_an_agent_that_did_start_is_refused_and_changes_nothing(
    tmp_path,
):
    task = build_loop(tmp_path, Step("1"))
    request = next_action(task).request
    leave_agent_transcript(
        task, request, new_agent_id(), requests=3, final_text="Working on it.", ended=False
    )
    files_before = snapshot(task)

    refused = record_not_started(task, request["id"], "the Agent tool call failed before launch")

    assert refused.exit_code == 4
    assert refused.error["code"] == "not-started-but-ran"
    assert snapshot(task) == files_before


def test_a_step_exhausted_in_a_wip_written_without_the_loop_stops_the_loop(tmp_path):
    # Two is the cap the completion-handshake procedure states; the reconciler reads it here.
    step = Step("1")
    task = build_loop(
        tmp_path, step, extra_progress={step.id: f"  - Attempts: Step {step.id} count=2"}
    )
    assert reconciler_verdict(task, "1")["verdict"] == "attempts-exhausted"

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.request is None
    assert step_id_of(stopped.stop["step"]) == "1"
