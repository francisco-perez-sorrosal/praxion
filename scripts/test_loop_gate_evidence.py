"""Tests for the evidence a red gate block hands the step's next attempt.

The parser cases feed it the lines the gate itself renders (``failure_lines`` and the
``Cut off:`` line shape), so the two sides stay one grammar. The file cases write a small
``TEST_RESULTS.md`` in ``tmp_path``; the render cases pass the evidence in and read the prompt
text out. Nothing is mocked.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_files import gate_heading, latest_gate_evidence  # noqa: E402
from _step_loop_gate import GateEvidence, parse_gate_evidence  # noqa: E402
from _step_loop_record_gate import FAILED_LINES_SHOWN, failure_lines  # noqa: E402
from _step_loop_render import (  # noqa: E402
    GATE_EVIDENCE_BOUND,
    PromptInputs,
    RequestKey,
    render_prompt,
    spawn_request,
)

STEP_ID, OTHER_ID = "7", "8"
REQUEST = "s7-a1-implement"
WORK = "/repo/.ai-work/demo"
RESULTS = f"{WORK}/TEST_RESULTS.md"
LOG_DIRECTORY = ".ai-work/demo/gate/s7-a1-implement"
CUT_OFF = "eval after 7s (override)"
FIRST_FAILURE = "tests/test_widget.py::test_widget_returns_its_id"
SECOND_FAILURE = "eval/tests/test_slow.py::test_slow_answer"
GREEN_RESULT = "Result: pass=4 fail=0 skip=0 pending=0 by=step-loop"
RED_RESULT = "Result: pass=3 fail=1 skip=0 pending=0 by=step-loop"
STEP_TEXT = f"""\
### Step {STEP_ID}: Add the widget

**Assignee**: implementer
**Implementation**: Build the widget.
**Files**: `src/widget.py`
**Done when**: the widget exists.
"""  # id-citation-discipline:ignore


def gate_block(request, *body, step_id=STEP_ID):
    return "\n".join([gate_heading(step_id, request), "", *body, ""])


def results_file(tmp_path, *blocks):
    path = tmp_path / "TEST_RESULTS.md"
    path.write_text("# Results\n\n" + "\n".join(blocks), encoding="utf-8")
    return path


def evidence_body(text):
    """The lines inside the prompt's gate-evidence element, as one string."""
    opened = text.split("<gate-evidence", 1)[1].split(">\n", 1)[1]
    return opened.split("\n</gate-evidence>", 1)[0]


def prompt_with(evidence, kind="implement"):
    step = parse_plan_steps(STEP_TEXT)[0]
    round_ = None if kind == "implement" else 1
    request = spawn_request("demo", step, RequestKey(STEP_ID, 2, kind, 1, round_), 2, WORK)
    inputs = PromptInputs(request, step, WORK, gate_evidence=evidence, findings_text="x")
    return render_prompt(inputs)[0]


# --- Reading a gate block ---


def test_a_cut_off_block_gives_its_cut_its_failures_and_its_pocket():
    block = [
        f"Cut off: {CUT_OFF}",
        *failure_lines([FIRST_FAILURE, SECOND_FAILURE], LOG_DIRECTORY),
        RED_RESULT,
    ]

    assert parse_gate_evidence(REQUEST, block) == GateEvidence(
        REQUEST, (CUT_OFF,), (FIRST_FAILURE, SECOND_FAILURE)
    )


def test_the_pointer_to_the_failures_a_block_had_no_room_for_is_kept_apart_from_the_nodes():
    names = [f"tests/test_many.py::test_failure_{n:03d}" for n in range(FAILED_LINES_SHOWN + 5)]

    evidence = parse_gate_evidence(REQUEST, [*failure_lines(names, LOG_DIRECTORY), RED_RESULT])

    assert evidence is not None
    assert evidence.failed == tuple(names[:FAILED_LINES_SHOWN])
    assert evidence.omitted == f"… 5 more in {LOG_DIRECTORY}"


def test_a_green_block_gives_no_evidence():
    block = ["Scope: root files=3 tests=4 narrow", GREEN_RESULT]

    assert parse_gate_evidence(REQUEST, block) is None


def test_the_evidence_lines_are_the_gates_lines_with_the_cut_last():
    evidence = GateEvidence(REQUEST, (CUT_OFF,), (FIRST_FAILURE,), "… 3 more in logs")

    assert evidence.lines() == (
        f"Failed: {FIRST_FAILURE}",
        "Failed: … 3 more in logs",
        f"Cut off: {CUT_OFF}",
    )


# --- Finding the step's latest block ---


def test_the_evidence_is_the_steps_latest_blocks_not_an_earlier_red_ones(tmp_path):
    earlier = gate_block("s7-a1-implement", f"Failed: {FIRST_FAILURE}", RED_RESULT)
    latest = gate_block("s7-a2-implement", f"Failed: {SECOND_FAILURE}", RED_RESULT)
    path = results_file(tmp_path, earlier, latest)

    assert latest_gate_evidence(path, STEP_ID) == GateEvidence(
        "s7-a2-implement", failed=(SECOND_FAILURE,)
    )


def test_a_green_latest_block_gives_nothing_though_an_earlier_one_was_red(tmp_path):
    earlier = gate_block("s7-a1-implement", f"Failed: {FIRST_FAILURE}", RED_RESULT)
    latest = gate_block("s7-a2-implement", GREEN_RESULT)
    path = results_file(tmp_path, earlier, latest)

    assert latest_gate_evidence(path, STEP_ID) is None


def test_another_steps_red_block_is_not_this_steps_evidence(tmp_path):
    other = gate_block("s8-a1-implement", f"Failed: {FIRST_FAILURE}", RED_RESULT, step_id=OTHER_ID)
    path = results_file(tmp_path, other)

    assert latest_gate_evidence(path, STEP_ID) is None


def test_a_block_the_implementer_wrote_is_not_a_gate_block(tmp_path):
    written = f"## Step {STEP_ID} — Add the widget\n\nFailed: {FIRST_FAILURE}\n"  # id-citation-discipline:ignore
    path = results_file(tmp_path, written)

    assert latest_gate_evidence(path, STEP_ID) is None


def test_a_missing_results_file_gives_no_evidence(tmp_path):
    assert latest_gate_evidence(tmp_path / "absent.md", STEP_ID) is None


# --- What the prompt shows ---


def test_an_implement_prompt_shows_the_failures_and_the_cut_newest_first():
    evidence = GateEvidence(REQUEST, (CUT_OFF,), (FIRST_FAILURE, SECOND_FAILURE))

    text = prompt_with(evidence)

    assert f'<gate-evidence source="TEST_RESULTS.md, {REQUEST}">' in text
    shown = evidence_body(text)
    assert shown.splitlines() == [
        f"Cut off: {CUT_OFF}",
        f"Failed: {SECOND_FAILURE}",
        f"Failed: {FIRST_FAILURE}",
    ]


def test_without_evidence_the_prompt_has_no_gate_evidence_slot():
    assert "gate-evidence" not in prompt_with(None)


def test_a_revise_prompt_shows_no_gate_evidence():
    evidence = GateEvidence(REQUEST, failed=(FIRST_FAILURE,))

    assert "gate-evidence" not in prompt_with(evidence, kind="revise")


def test_evidence_past_its_bound_keeps_the_newest_lines_and_points_to_the_results_file():
    names = tuple(f"tests/test_many.py::test_failure_{n:03d}_{'x' * 60}" for n in range(30))
    evidence = GateEvidence(REQUEST, (CUT_OFF,), names)

    text = prompt_with(evidence)

    shown = evidence_body(text)
    kept = shown.splitlines()
    assert len(shown) <= GATE_EVIDENCE_BOUND
    assert kept[0] == f"Cut off: {CUT_OFF}"
    assert kept[1] == f"Failed: {names[-1]}"
    assert f"Failed: {names[0]}" not in kept
    assert (
        kept[-1]
        == f"[{len(names) + 1 - (len(kept) - 1)} earlier lines cut: full record in {RESULTS}]"
    )
