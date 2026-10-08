"""Light reviews keep their place at the step boundary when the loop turns the crank.

A verified step that the light-review trigger marks risky (`tier: H`) or that carries
`review: force`, and does not carry `review: off`, yields a review request before any
later step's request. An accept advances the loop, a revise yields a revision request
for the same step, a second revise stops for a human, and a review still unfinished is
never read as an accept. At no point of a marked step's attempts or review does any
verb of the loop fail with an internal error.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    leave_review_verdict,
    next_action,
    record,
    run_raw,
    work_on,
)

RISKY = ("tier: H",)
FORCED = ("**review**: force",)
SUPPRESSED_RISKY = ("tier: H", "**review**: off")


def _answer_review(task, verdict: str):
    """The loop asks for a review; a reviewer answers with `verdict`; the answer is recorded."""
    asked = next_action(task)
    request = asked.request
    assert request is not None, f"the loop asked for no review: {asked.doc}"
    agent_id = leave_review_verdict(task, request, verdict)
    return record(task, request["id"], agent_id=agent_id, marker="complete")


def _revise(task):
    """The loop asks for a revision; the implementer revises; the return is recorded."""
    asked = next_action(task)
    request = asked.request
    assert request is not None, f"the loop asked for no revision: {asked.doc}"
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


# -- A step marked for review never breaks the driver --------------------------------------


def _fresh(task):
    """Nothing has happened yet."""


def _verified(task):
    attempt(task, Work())


def _review_asked(task):
    _verified(task)
    next_action(task)


def _revise_answered(task):
    _verified(task)
    _answer_review(task, "revise")


def _revision_asked(task):
    _revise_answered(task)
    next_action(task)


def _revised_twice(task):
    _revise_answered(task)
    _revise(task)
    _answer_review(task, "revise")


def _review_unfinished(task):
    _verified(task)
    _answer_review(task, "unfinished")


def _attempt_failed(task):
    attempt(task, Work(passes=False))


REVIEW_STATES = {
    "not-yet-attempted": _fresh,
    "verified-awaiting-review": _verified,
    "review-requested": _review_asked,
    "review-answered-revise": _revise_answered,
    "revision-requested": _revision_asked,
    "revised-twice": _revised_twice,
    "review-unfinished": _review_unfinished,
    "attempt-failed": _attempt_failed,
}


def _location(task) -> tuple[str, ...]:
    return ("--repo-root", str(task.root), "--base-ref", task.base)


def _answering_agent(task, request) -> str:
    """An ended agent that answers `request` the way its kind of agent would."""
    if request.get("kind") == "review":
        return leave_review_verdict(task, request, "accept")
    return work_on(task, request, Work())


def _exit_codes_of_every_verb(task) -> dict[str, int]:
    """`status`, then `next`, then `record` of a real answer to whatever `next` asked."""
    codes = {"status": run_raw(task, "status", task.slug, "--json", *_location(task)).returncode}
    asked = run_raw(task, "next", task.slug, *_location(task))
    codes["next"] = asked.returncode
    try:
        request = json.loads(asked.stdout).get("request")
    except (json.JSONDecodeError, AttributeError):
        request = None
    request_id = request["id"] if request else "no-pending-request"
    agent_id = _answering_agent(task, request) if request else "no-such-agent"
    codes["record"] = run_raw(
        task,
        "record",
        task.slug,
        "--request",
        request_id,
        "--agent-id",
        agent_id,
        "--marker",
        "complete",
        *_location(task),
    ).returncode
    return codes


@pytest.mark.parametrize("annotations", [RISKY, FORCED], ids=["risky-step", "forced-review"])
@pytest.mark.parametrize("state", list(REVIEW_STATES))
def test_no_verb_exits_with_an_internal_error_on_a_step_marked_for_review(
    tmp_path, annotations, state
):
    task = build_loop(tmp_path, Step("1", annotations=annotations), Step("2"))
    REVIEW_STATES[state](task)

    codes = _exit_codes_of_every_verb(task)

    assert 1 not in codes.values(), f"{state}: exit codes by verb {codes}"
