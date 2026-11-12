"""A record refused after a mid-flight plan revision names the cause and the way back.

Revising a step block of IMPLEMENTATION_PLAN.md while a request is outstanding makes
the loop no longer issue that request, so its `record` is refused with
`request-not-pending` and exit 4. The refusal keeps that code and status and adds the
cause, the recovery (put the revised block back as it was when the request was issued,
record the request, then re-apply the revision and run `next`) and the order that
avoids it (record the outstanding request before revising any step block). The
refusal of a request that is neither pending nor recorded is unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    new_agent_id,
    next_action,
    record,
    revise_step,
    work_on,
)
from tests.acceptance.drivers.step_loop_recovery import missing_patterns, plan_text, put_plan

REVISION = "Write `src/step_1.py` returning the step id, revised while its request was out."

CAUSE = (r"IMPLEMENTATION_PLAN\.md", r"revis", r"outstanding|pending|issued|\bout\b")
RECOVERY = (
    r"(put|restore|revert|set)\b.{0,60}\bback|as it (was|stood)|restore|revert",
    r"\brecord\b",
    r"re-?apply",
    r"\bnext\b",
)
ORDER = (r"record\b.{0,120}\bbefore\b.{0,60}revis|before revising",)


def _refused_after_a_mid_flight_revision(tmp_path: Path):
    """A failed first attempt, a second request issued, the step revised before it is recorded."""
    task = build_loop(tmp_path, Step("1"), Step("2"))
    attempt(task, Work(passes=False))
    request = next_action(task).request
    agent_id = work_on(task, request, Work())
    as_issued = plan_text(task)
    revise_step(task, "1", REVISION)
    refused = record(task, request["id"], agent_id=agent_id, marker="complete")
    return task, request, agent_id, as_issued, refused


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(CAUSE, id="names-the-revision-as-the-cause"),
        pytest.param(RECOVERY, id="gives-the-recovery"),
        pytest.param(ORDER, id="gives-the-order-that-avoids-it"),
    ],
)
def test_the_refusal_after_a_mid_flight_revision_says_what_happened_and_what_to_do(
    tmp_path: Path, statement: tuple[str, ...]
) -> None:
    _, _, _, _, refused = _refused_after_a_mid_flight_revision(tmp_path)

    assert refused.exit_code == 4
    assert refused.error["code"] == "request-not-pending"
    missing = missing_patterns(refused.error["message"], statement)
    assert missing == [], f"the refusal lacks {missing}: {refused.error['message']}"


def test_following_the_recovery_records_the_request_and_resumes_the_loop(tmp_path: Path) -> None:
    task, request, agent_id, as_issued, _ = _refused_after_a_mid_flight_revision(tmp_path)
    revised = plan_text(task)
    put_plan(task, as_issued)

    recorded = record(task, request["id"], agent_id=agent_id, marker="complete")
    put_plan(task, revised)
    resumed = next_action(task)

    assert recorded.exit_code == 0, recorded.doc
    assert recorded.recorded["request"] == request["id"]
    assert resumed.exit_code == 0, resumed.doc


def test_the_refusal_of_an_unknown_request_is_unchanged(tmp_path: Path) -> None:
    task = build_loop(tmp_path, Step("1"), Step("2"))
    pending = next_action(task).request["id"]

    refused = record(task, "s9-a1-implement", agent_id=new_agent_id(), marker="complete")

    assert refused.exit_code == 4
    assert refused.error["code"] == "request-not-pending"
    assert refused.error["message"] == (
        "record failed because s9-a1-implement is neither pending nor recorded "
        f"(the pending request is {pending}). To fix: record the pending request, "
        "or run next to get one."
    )
    assert re.search(r"re-?apply", refused.error["message"]) is None
