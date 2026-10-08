"""`record` judges a top-level session by its own transcript, as it judges a subagent.

Given a session id as the agent id, `record` finds the session's transcript where the
harness writes it, under the configuration directory's `projects/<project>/` folder, and
reads from it the first user text (which must name the request), the end, the marker and
the count of distinct requests.
"""

from __future__ import annotations

import uuid

from tests.acceptance.drivers.goal_loop import Iteration, apply_iteration, build_goal
from tests.acceptance.drivers.headless_worker import config_dir, write_session_transcript
from tests.acceptance.drivers.step_loop import ledger_records, next_action, record

SESSION_REQUESTS = 13
FINISHED = "Implemented one; two and three remain.\n[COMPLETE]"


def _session_did_the_iteration(task, request, *, prompt=None) -> str:
    """A top-level session in the checkout's root did one progressing iteration; its id."""
    apply_iteration(task.root, task.slug, Iteration(implemented=("one",)))
    session_id = str(uuid.uuid4())
    write_session_transcript(
        config_dir(task),
        task.root,
        session_id,
        prompt=prompt if prompt is not None else request["agent_call"]["prompt"],
        requests=SESSION_REQUESTS,
        final_text=FINISHED,
        ended=True,
    )
    return session_id


def test_record_counts_a_sessions_turns_from_its_own_transcript(tmp_path):
    task = build_goal(tmp_path)
    request = next_action(task).request
    session_id = _session_did_the_iteration(task, request)

    returned = record(task, request["id"], agent_id=session_id, marker="complete")

    assert returned.recorded["agent_id"] == session_id
    assert returned.recorded["turns"] == SESSION_REQUESTS
    assert "transcript-unreadable" not in returned.warning_codes
    assert returned.recorded["commit"] is not None, returned.doc


def test_record_reads_the_marker_from_the_sessions_transcript(tmp_path):
    task = build_goal(tmp_path)
    request = next_action(task).request
    session_id = _session_did_the_iteration(task, request)

    returned = record(task, request["id"], agent_id=session_id, marker="none")

    assert returned.recorded["marker"] == "complete"
    assert "marker-disagreement" in returned.warning_codes


def test_a_session_whose_first_user_text_names_another_request_is_refused(tmp_path):
    task = build_goal(tmp_path)
    request = next_action(task).request
    other_prompt = request["agent_call"]["prompt"].replace(request["id"], "s9-a9-implement")
    session_id = _session_did_the_iteration(task, request, prompt=other_prompt)

    refused = record(task, request["id"], agent_id=session_id, marker="complete")

    records, _ = ledger_records(task)
    assert refused.exit_code == 4
    assert refused.error["code"] == "agent-not-for-request"
    assert records == []
