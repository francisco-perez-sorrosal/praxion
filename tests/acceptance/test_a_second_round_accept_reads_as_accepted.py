"""A second-round accept is read as accepted, whatever the first round left below it.

A reviewer of round 2 writes its own verdict on the file's first line and keeps the
superseded round-1 record, with its bare `verdict: revise` line, after a separator. The
loop reads that file as accepted and moves to the next step. Files a reviewer writes as the
review prompt asks keep the reading they have today.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.loop_repairs import (
    answer_review,
    next_request,
    partial_first_file,
    second_round_file,
    to_second_review,
)
from tests.acceptance.drivers.step_loop import (
    Step,
    attempt,
    build_loop,
    leave_review_verdict,
    next_action,
    record,
)

FORCED = ("**review**: force",)


def test_a_second_round_accept_above_the_superseded_revise_reads_as_accepted(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    second = to_second_review(task)

    recorded = answer_review(task, second, second_round_file("1", "accept"), "accept")

    assert recorded.recorded["review_verdict"] == "accept", recorded.doc
    assert (recorded.stop or {}).get("cause") != "review-revised-twice", recorded.doc


def test_after_a_second_round_accept_the_loop_goes_on_to_the_next_step(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    second = to_second_review(task)
    answer_review(task, second, second_round_file("1", "accept"), "accept")

    following = next_request(task)

    assert following["step"] == "2", following
    assert following["kind"] == "implement", following


def test_a_second_round_whose_own_verdict_is_revise_still_stops_for_a_human(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    second = to_second_review(task)
    answer_review(task, second, second_round_file("1", "revise"), "revise")

    after = next_action(task)

    assert after.stop is not None, after.doc
    assert after.stop["cause"] == "review-revised-twice", after.doc


@pytest.mark.parametrize(
    ("verdict", "kind_next"),
    [("accept", "implement"), ("revise", "revise")],
    ids=["accept-last", "revise-last"],
)
def test_a_single_round_written_as_the_prompt_asks_reads_by_its_last_verdict(
    tmp_path, verdict, kind_next
):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task)
    review = next_request(task)

    recorded = answer_review(task, review, partial_first_file("1", verdict), verdict)
    following = next_request(task)

    assert recorded.recorded["review_verdict"] == verdict, recorded.doc
    assert following["kind"] == kind_next, following


def test_a_review_whose_only_verdict_is_partial_reads_as_unfinished(tmp_path):
    task = build_loop(tmp_path, Step("1", annotations=FORCED), Step("2"))
    attempt(task)
    review = next_request(task)

    recorded = record(
        task,
        review["id"],
        agent_id=leave_review_verdict(task, review, "unfinished"),
        marker="complete",
    )

    assert recorded.recorded["review_verdict"] not in ("accept", "revise"), recorded.doc
