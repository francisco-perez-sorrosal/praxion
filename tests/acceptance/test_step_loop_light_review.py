"""Light reviews keep their place at the step boundary when the loop turns the crank.

A verified step that the light-review trigger marks risky (`tier: H`) or that carries
`review: force`, and does not carry `review: off`, yields a review request before any
later step's request. An accept advances the loop, a revise yields a revision request
for the same step, a second revise stops for a human, and a review still unfinished is
never read as an accept.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    leave_review_verdict,
    next_action,
    record,
    work_on,
)

RISKY = ("tier: H",)
FORCED = ("**review**: force",)
SUPPRESSED_RISKY = ("tier: H", "**review**: off")


def _answer_review(task, verdict: str):
    """The loop asks for a review; a reviewer answers with `verdict`; the answer is recorded."""
    request = next_action(task).request
    agent_id = leave_review_verdict(task, request, verdict)
    return record(task, request["id"], agent_id=agent_id, marker="complete")


def _revise(task):
    """The loop asks for a revision; the implementer revises; the return is recorded."""
    request = next_action(task).request
    return record(task, request["id"], agent_id=work_on(task, request, Work()), marker="complete")


@pytest.mark.parametrize("annotations", [RISKY, FORCED], ids=["risky-step", "forced-review"])
def test_a_verified_step_marked_for_review_yields_a_review_before_the_next_step(
    tmp_path, annotations
):
    task = build_loop(tmp_path, Step("1", annotations=annotations), Step("2"))
    attempt(task, Work())

    request = next_action(task).request

    assert request["kind"] == "review"
    assert request["step"] == "1"
    assert request["id"] == "s1-a1-review-r1"
    assert request["agent_call"]["subagent_type"] == "praxion:verifier"
    assert request["agent_call"]["model"] == "sonnet"


@pytest.mark.parametrize(
    "annotations", [SUPPRESSED_RISKY, ()], ids=["review-off", "no-review-signal"]
)
def test_a_verified_step_not_marked_for_review_moves_straight_to_the_next_step(
    tmp_path, annotations
):
    task = build_loop(tmp_path, Step("1", annotations=annotations), Step("2"))
    attempt(task, Work())

    request = next_action(task).request

    assert request["kind"] == "implement"
    assert request["step"] == "2"


def test_an_accepted_review_advances_to_the_next_step(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task, Work())
    _answer_review(task, "accept")

    request = next_action(task).request

    assert request["kind"] == "implement"
    assert request["step"] == "2"


def test_a_revise_verdict_yields_a_revision_request_for_the_same_step(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task, Work())
    _answer_review(task, "revise")

    request = next_action(task).request

    assert request["kind"] == "revise"
    assert request["step"] == "1"
    assert request["agent_call"]["subagent_type"] == "praxion:implementer"


def test_a_second_revise_verdict_stops_for_a_human(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task, Work())
    _answer_review(task, "revise")
    _revise(task)
    _answer_review(task, "revise")

    stopped = next_action(task)

    assert stopped.exit_code == 2
    assert stopped.stop["cause"] == "review-revised-twice"


def test_an_unfinished_review_is_never_read_as_an_accept(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task, Work())
    _answer_review(task, "unfinished")

    after = next_action(task)

    assert after.outcome != "complete"
    assert after.request is None or after.request["step"] != "2", after.doc
