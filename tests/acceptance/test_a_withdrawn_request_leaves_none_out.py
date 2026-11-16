"""A request no agent started can be taken back, leaving no request out.

Recording an issued request as not started takes it back: the envelope issues nothing and
prints the call that continues the loop, the progress file names no request out and status
agrees. In that moment a person may amend the plan -- put a step ahead, or revise the
withdrawn step's block -- and the next `next` issues exactly one request, for the step the
plan now puts first. Left alone, the withdrawn attempt is issued again with the same number.
No sequence of calls ever leaves two requests out, and an attempts line whose request
disagrees with its own count is named rather than acted on.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.loop_repairs import (
    finish_with,
    insert_step_ahead,
    printed_commands,
    requests_named_out,
    status_json,
)
from tests.acceptance.drivers.step_loop import (
    SLUG,
    Step,
    build_loop,
    leave_agent_transcript,
    new_agent_id,
    next_action,
    record,
    record_not_started,
    revise_step,
)

REASON = "the Agent tool call failed before launch"
FIRST = "1"


def _withdrawn(tmp_path, *steps):
    task = build_loop(tmp_path, *steps)
    issued = next_action(task).request
    withdrawn = record_not_started(task, issued["id"], REASON)
    return task, issued, withdrawn


def test_a_withdrawal_issues_no_request_and_prints_the_call_that_continues(tmp_path):
    _, _, withdrawn = _withdrawn(tmp_path, Step("1"))

    assert withdrawn.outcome != "spawn", withdrawn.doc
    assert withdrawn.request is None, withdrawn.doc
    continuing = [c for c in printed_commands(withdrawn.text()) if f" next {SLUG}" in c]
    assert continuing, f"the withdrawal prints no `next` call to continue: {withdrawn.doc}"


def test_after_a_withdrawal_neither_the_progress_file_nor_status_names_a_request_out(tmp_path):
    task, issued, _ = _withdrawn(tmp_path, Step("1"))

    out_in_progress = requests_named_out(task)
    state = status_json(task)

    assert issued["id"] not in out_in_progress, task.wip_path.read_text(encoding="utf-8")
    assert state["pending_request"] is None, state


def test_a_withdrawn_attempt_is_issued_again_with_its_number_and_costs_no_attempt(tmp_path):
    task, issued, _ = _withdrawn(tmp_path, Step("1"))

    again = next_action(task)

    assert again.outcome == "spawn", again.doc
    assert again.request["step"] == issued["step"]
    assert again.request["attempt"] == issued["attempt"]
    assert status_json(task)["steps"][0]["attempts"] == issued["attempt"]


def test_a_step_put_ahead_of_the_withdrawn_one_is_issued_first_without_a_warning(tmp_path):
    task, _, _ = _withdrawn(tmp_path, Step("2"))
    insert_step_ahead(task, Step("1", title="Prepare the widget"), before="2")

    asked = next_action(task)

    assert asked.outcome == "spawn", asked.doc
    assert asked.request["step"] == "1", asked.doc
    assert asked.doc.get("warnings", []) == [], asked.doc
    assert asked.stop is None, asked.doc
    assert asked.error is None, asked.doc
    assert requests_named_out(task) == [asked.request["id"]], task.wip_path.read_text(
        encoding="utf-8"
    )


def test_the_withdrawn_steps_own_revised_block_is_issued_without_a_warning(tmp_path):
    task, issued, _ = _withdrawn(tmp_path, Step("1"))
    revise_step(
        task, "1", "Write `src/step_1.py` returning the step id, revised while none was out."
    )

    asked = next_action(task)

    assert asked.outcome == "spawn", asked.doc
    assert asked.request["step"] == issued["step"]
    assert asked.doc.get("warnings", []) == [], asked.doc
    assert requests_named_out(task) == [asked.request["id"]], task.wip_path.read_text(
        encoding="utf-8"
    )


def test_the_step_put_ahead_is_recorded_and_the_loop_moves_on(tmp_path):
    task, _, _ = _withdrawn(tmp_path, Step("2"))
    insert_step_ahead(task, Step("1", title="Prepare the widget"), before="2")
    first = next_action(task).request

    recorded = record(
        task,
        first["id"],
        agent_id=finish_with(task, first, f"Step {FIRST} done.\n[COMPLETE]"),
        marker="complete",
    )
    following = next_action(task)

    assert recorded.error is None, recorded.doc
    assert following.outcome == "spawn", following.doc
    assert following.request["step"] == "2", following.doc


def test_a_plan_changed_while_a_request_is_out_never_yields_a_second_request(tmp_path):
    task = build_loop(tmp_path, Step("2"))
    outstanding = next_action(task).request
    insert_step_ahead(task, Step("1", title="Prepare the widget"), before="2")

    asked = next_action(task)

    reissued = asked.request is not None and asked.request["id"] == outstanding["id"]
    named = outstanding["id"] in asked.text() and "record" in asked.text()
    assert reissued or (asked.request is None and named), asked.doc
    assert requests_named_out(task) == [outstanding["id"]], task.wip_path.read_text(
        encoding="utf-8"
    )


def test_one_withdrawal_after_a_plan_change_at_the_wrong_moment_restores_the_loop(tmp_path):
    task = build_loop(tmp_path, Step("2"))
    outstanding = next_action(task).request
    insert_step_ahead(task, Step("1", title="Prepare the widget"), before="2")
    next_action(task)

    withdrawn = record_not_started(task, outstanding["id"], REASON)
    asked = next_action(task)

    assert withdrawn.error is None, withdrawn.doc
    assert asked.outcome == "spawn", asked.doc
    assert asked.request["step"] == "1", asked.doc
    assert requests_named_out(task) == [asked.request["id"]], task.wip_path.read_text(
        encoding="utf-8"
    )


def test_status_never_reports_two_requests_out_after_a_plan_change(tmp_path):
    task = build_loop(tmp_path, Step("2"))
    outstanding = next_action(task).request
    insert_step_ahead(task, Step("1", title="Prepare the widget"), before="2")
    next_action(task)
    next_action(task)

    state = status_json(task)

    assert state["pending_request"] in (outstanding["id"], None), state
    assert state["stop"] is None or "loop-state-defect" not in str(state["stop"]), state


# -- An attempts line that disagrees with itself ----------------------------------------------

DISAGREEING = f"  - Attempts: Step {FIRST} count=2 request=s{FIRST}-a1-implement"


def test_next_names_an_attempts_line_whose_request_disagrees_with_its_count(tmp_path):
    task = build_loop(tmp_path, Step("1"), extra_progress={"1": DISAGREEING})

    asked = next_action(task)

    issued_attempt = asked.request["attempt"] if asked.request is not None else None
    assert issued_attempt in (None, 2), f"a request whose attempt is not the count: {asked.doc}"
    named = [w for w in (asked.doc.get("warnings", []) + [asked.stop or {}]) if w]
    said = " ".join(str(w) for w in named)
    assert "s1-a1-implement" in said, f"the disagreement names no request: {asked.doc}"
    assert re.search(r"count\W{0,3}2\b", said), f"the disagreement names no count: {asked.doc}"


def test_record_names_an_attempts_line_whose_request_disagrees_with_its_count(tmp_path):
    task = build_loop(tmp_path, Step("1"), extra_progress={"1": DISAGREEING})
    request = {
        "id": "s1-a1-implement",
        "step": "1",
        "agent_call": {"prompt": "Spawn request: s1-a1-implement"},
    }
    agent_id = new_agent_id()
    leave_agent_transcript(
        task, request, agent_id, requests=3, final_text="Done.\n[COMPLETE]", ended=True
    )

    recorded = record(task, "s1-a1-implement", agent_id=agent_id, marker="complete")

    assert recorded.recorded is None or recorded.recorded.get("commit") is None, recorded.doc
    assert "s1-a1-implement" in recorded.text(), recorded.doc
    assert "count" in recorded.text(), recorded.doc
