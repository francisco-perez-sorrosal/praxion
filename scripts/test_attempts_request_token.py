"""Tests for the `request=` token of the `Attempts:` line (``scripts/_loop_fields.py``).

A line without the token must read exactly as it always did. A line that names a
request reads as outstanding until the ledger records that request, and the one
renderer writes back exactly what the parser reads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _loop_fields as fields  # noqa: E402

STEP = "Step "
REQUEST = "s7-a1-implement"
OTHER_REQUEST = "s7-a2-implement"
NOTHING_RECORDED: frozenset = frozenset()


def wip(*lines: str) -> str:
    return "\n".join(lines) + "\n"


def counts_of(text: str, recorded: frozenset = NOTHING_RECORDED) -> dict:
    return fields.parse_attempts(text, recorded).counts


# --- a line without the token reads as it always did ---


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (f"- Attempts: {STEP}3 count=1", fields.Attempt(1)),
        (f"- Attempts: {STEP}3 count=02", fields.Attempt(2)),
        (
            f"- Attempts: {STEP}3 count=2 [BLOCKED] replan: split the step",
            fields.Attempt(2, "split the step"),
        ),
    ],
)
def test_a_line_without_a_request_always_reads_as_an_attempt(line, expected):
    assert counts_of(wip(line)) == {f"{STEP}3": expected}


def test_a_line_without_a_request_ignores_the_recorded_set():
    text = wip(f"- Attempts: {STEP}3 count=1")

    assert counts_of(text, frozenset({REQUEST})) == counts_of(text)


# --- a line with the token ---


def test_an_unrecorded_request_reads_as_an_outstanding_attempt():
    text = wip(f"- Attempts: {STEP}7 count=1 request={REQUEST}")

    assert counts_of(text) == {f"{STEP}7": fields.OutstandingAttempt(1, REQUEST)}


def test_a_recorded_request_reads_as_an_ended_attempt_that_keeps_its_request():
    text = wip(f"- Attempts: {STEP}7 count=1 request={REQUEST}")

    assert counts_of(text, frozenset({REQUEST})) == {f"{STEP}7": fields.Attempt(1, None, REQUEST)}


def test_a_recorded_request_may_carry_a_replan():
    text = wip(f"- Attempts: {STEP}7 count=2 request={REQUEST} [BLOCKED] replan: split it")

    expected = fields.Attempt(2, "split it", REQUEST)

    assert counts_of(text, frozenset({REQUEST})) == {f"{STEP}7": expected}


def test_an_outstanding_attempt_with_a_replan_is_an_unreadable_line_for_its_step():
    text = wip(f"- Attempts: {STEP}7 count=2 request={REQUEST} [BLOCKED] replan: split it")

    reading = fields.parse_attempts(text)

    assert (reading.counts, list(reading.unreadable)) == ({}, [f"{STEP}7"])
    assert "cannot carry a replan" in reading.unreadable[f"{STEP}7"]


@pytest.mark.parametrize(
    "token",
    ["request=", "request=S7-A1", "request=-s7", "request=s7_a1", "request=s7 a1", "request"],
)
def test_a_malformed_request_token_is_unreadable_for_its_step(token):
    reading = fields.parse_attempts(wip(f"- Attempts: {STEP}7 count=1 {token}"))

    assert (reading.counts, list(reading.unreadable)) == ({}, [f"{STEP}7"])


def test_a_line_inside_a_code_fence_declares_nothing_even_with_a_request():
    text = wip("```", f"- Attempts: {STEP}7 count=1 request={REQUEST}", "```")

    assert counts_of(text) == {}


def test_the_highest_count_wins_across_an_outstanding_and_an_ended_line():
    text = wip(
        f"- Attempts: {STEP}7 count=2 request={OTHER_REQUEST}",
        f"- Attempts: {STEP}7 count=1 request={REQUEST}",
    )

    expected = {f"{STEP}7": fields.OutstandingAttempt(2, OTHER_REQUEST)}

    assert counts_of(text, frozenset({REQUEST})) == expected


# --- the constructors are the enforcement point ---


def test_an_outstanding_attempt_with_a_replan_cannot_be_constructed():
    with pytest.raises(ValueError, match="cannot carry a replan"):
        fields.OutstandingAttempt(1, REQUEST, replan="split it")


@pytest.mark.parametrize(
    ("build", "complaint"),
    [
        (lambda: fields.Attempt(0), "at least 1"),
        (lambda: fields.Attempt(1, request="Bad Id"), "request id"),
        (lambda: fields.Attempt(1, replan=""), "one non-blank line"),
        (lambda: fields.Attempt(1, replan=" padded "), "one non-blank line"),
        (lambda: fields.Attempt(1, replan="two\nlines"), "one non-blank line"),
        (lambda: fields.OutstandingAttempt(0, REQUEST), "at least 1"),
        (lambda: fields.OutstandingAttempt(1, ""), "request id"),
    ],
)
def test_an_attempt_that_the_line_cannot_say_cannot_be_constructed(build, complaint):
    with pytest.raises(ValueError, match=complaint):
        build()


# --- the renderer and the parser are inverse ---


@pytest.mark.parametrize(
    ("attempt", "recorded"),
    [
        (fields.Attempt(1), NOTHING_RECORDED),
        (fields.Attempt(2, "split the step"), NOTHING_RECORDED),
        (fields.Attempt(1, None, REQUEST), frozenset({REQUEST})),
        (fields.Attempt(2, "split the step", REQUEST), frozenset({REQUEST})),
        (fields.OutstandingAttempt(1, REQUEST), NOTHING_RECORDED),
        (fields.OutstandingAttempt(12, "s12b-p2-a1-implement"), NOTHING_RECORDED),
    ],
)
@pytest.mark.parametrize("step_id", ["7", "12b"])
def test_a_rendered_line_parses_back_to_exactly_what_was_rendered(attempt, recorded, step_id):
    rendered = fields.render_attempts_line(step_id, attempt)

    assert counts_of(wip(rendered), recorded) == {f"{STEP}{step_id}": attempt}


def test_the_renderer_writes_the_documented_line():
    rendered = fields.render_attempts_line("7", fields.OutstandingAttempt(1, REQUEST))

    assert rendered == f"- Attempts: {STEP}7 count=1 request={REQUEST}"


@pytest.mark.parametrize("step_id", ["", f"{STEP}7", "7 8", "-1"])
def test_the_renderer_refuses_a_step_id_the_plan_cannot_spell(step_id):
    with pytest.raises(ValueError, match="not a step id"):
        fields.render_attempts_line(step_id, fields.Attempt(1))


def test_the_attempt_cap_is_unchanged_and_defined_once():
    assert fields.ATTEMPT_CAP == 2


# --- the deciding Result: line reports whether the driver ran it ---


CHECK = fields.parse_check_field("Check: `run it` expects pass>=3 fail=0")


def results(*result_lines: str) -> str:
    body = "\n".join(result_lines)
    return f"## {STEP}7 — A step\n\nCommand: `run it`\n{body}\n"


@pytest.mark.parametrize(
    ("result_line", "by_driver"),
    [
        ("Result: pass=3 fail=0 skip=0 by=step-loop", True),
        ("Result: pass=3 fail=0 skip=0", False),
        ("Result: pass=3 fail=0 skip=0 by=hand", False),
        ("Result: pass=3 fail=0 skip=0 by=step-loopy", False),
    ],
)
def test_a_met_check_reports_whether_the_deciding_line_is_the_drivers_own(result_line, by_driver):
    outcome = fields.evaluate_check(CHECK, "7", results(result_line))

    assert outcome == fields.Met(by_step_loop=by_driver)


def test_an_unmet_check_reports_the_driver_marker_too():
    outcome = fields.evaluate_check(CHECK, "7", results("Result: pass=1 fail=0 by=step-loop"))

    assert outcome == fields.Unmet((fields.UnmetExpectation("pass", ">=", 3, 1),), True)


def test_only_the_latest_line_decides_whether_the_driver_ran_it():
    text = results("Result: pass=3 fail=0 by=step-loop", "Result: pass=3 fail=0 skip=0")

    assert fields.evaluate_check(CHECK, "7", text) == fields.Met(by_step_loop=False)
