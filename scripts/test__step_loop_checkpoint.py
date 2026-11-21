"""Tests for the pockets a step's gate leaves for the loop's checkpoint (`_step_loop_checkpoint`).

A gate that leaves a widened pocket unrun writes one `Deferred:` line for it in the step's block
of `TEST_RESULTS.md`. Which pockets wait, and for which steps, is never stored: it is derived on
every call from that file and the ledger's records. A pocket waits from the first committed step
that deferred it until a green checkpoint block for its root appears after the deferral.

The module is pure, so every input here is plain text and plain records; nothing touches a disk.
Step ids are bare (`"41"`), the form the driver's `status` and stop envelopes print them in; a
ledger record carries the labelled form, the id after the word "Step".
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _step_loop_checkpoint import (  # noqa: E402
    WaitingPocket,
    deferred_line,
    deferred_roots,
    waiting_pockets,
)
from _step_loop_files import STEP_LABEL, gate_heading  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

ROOT_POCKET = "."
BENCH = "bench"
SERVICE = "services/api"
GREEN_RESULT = "Result: pass=12 fail=0 skip=0 pending=0 by=step-loop"
RED_RESULT = "Result: pass=11 fail=1 skip=0 pending=0 by=step-loop"
CUT_OFF_RESULT = "Result: none — the run was cut off at its bound by=step-loop"


# -- Builders: what the gate and the checkpoint write, and what the ledger holds ----------------


def gate_block(step_id: str, request: str, *, deferred: tuple[str, ...] = ()) -> str:
    """A step's gate block as the gate writes it: scope, one `Deferred:` per pocket, then `Result:`."""
    lines = [
        gate_heading(step_id, request),
        "",
        "Scope: . files=2 tests=4 narrow",
        *(deferred_line(root) for root in deferred),
        GREEN_RESULT,
    ]
    return "\n".join(lines) + "\n"


def checkpoint_block(
    root: str, steps: tuple[str, ...], result: str = GREEN_RESULT, head: str = "1a2b3c4"
) -> str:
    """A checkpoint block as the checkpoint writes it: its own heading, `Covers:`, scope, result."""
    covers = ", ".join(f"{STEP_LABEL}{step}" for step in steps)
    lines = [
        f"## Checkpoint {root} at {head}",
        "",
        f"Covers: {covers}",
        f"Scope: {root} files=12 tests=12 widened",
        result,
    ]
    return "\n".join(lines) + "\n"


def results_file(*blocks: str) -> str:
    return "# Test results\n\n" + "\n".join(blocks)


def record(step_id: str, request: str, *, commit: str | None = "a1b2c3d") -> IterationRecord:
    """A step-loop ledger record; a null `commit` states that no commit holds the attempt's work."""
    return IterationRecord(
        step=f"{STEP_LABEL}{step_id}",
        attempt=1,
        agent_id="agent-1",
        verdict="verified-complete" if commit else "failed",
        decided_by="check",
        test_result="Result: pass=3 fail=0 skip=0",
        commit=commit,
        stop_reason="end_turn",
        request=request,
    )


def waiting_by_root(pockets: tuple[WaitingPocket, ...]) -> dict[str, tuple[str, ...]]:
    return {pocket.root: pocket.steps for pocket in pockets}


# -- The `Deferred:` line -------------------------------------------------------------------------


def test_deferred_line_names_the_pocket_and_says_its_whole_suite_waits() -> None:
    assert deferred_line(BENCH) == "Deferred: bench (widened): whole suite waits for the checkpoint"


def test_deferred_line_names_the_root_pocket_by_a_dot() -> None:
    assert deferred_line(ROOT_POCKET) == (
        "Deferred: . (widened): whole suite waits for the checkpoint"
    )


@pytest.mark.parametrize("root", [ROOT_POCKET, BENCH, SERVICE])
def test_deferred_roots_reads_back_the_root_a_deferred_line_was_written_for(root: str) -> None:
    assert deferred_roots([deferred_line(root)]) == (root,)


def test_deferred_roots_returns_each_root_in_the_order_its_line_appears() -> None:
    lines = [deferred_line(BENCH), deferred_line(ROOT_POCKET), deferred_line(SERVICE)]

    assert deferred_roots(lines) == (BENCH, ROOT_POCKET, SERVICE)


def test_deferred_roots_ignores_every_line_that_does_not_open_with_the_marker() -> None:
    lines = [
        "Scope: . files=2 tests=4 narrow",
        deferred_line(BENCH),
        GREEN_RESULT,
        "Failed: tests/test_a.py::test_b",
    ]

    assert deferred_roots(lines) == (BENCH,)


def test_deferred_roots_ignores_a_line_that_is_indented() -> None:
    lines = ["  " + deferred_line(BENCH), "\t" + deferred_line(SERVICE), deferred_line(ROOT_POCKET)]

    assert deferred_roots(lines) == (ROOT_POCKET,)


def test_deferred_roots_ignores_a_line_inside_a_code_fence() -> None:
    lines = ["```", deferred_line(BENCH), "```", deferred_line(ROOT_POCKET)]

    assert deferred_roots(lines) == (ROOT_POCKET,)


def test_deferred_roots_is_empty_for_lines_that_defer_nothing() -> None:
    assert deferred_roots(["Scope: . files=2 tests=4 narrow", GREEN_RESULT]) == ()


# -- A waiting pocket and its invariants ----------------------------------------------------------


def test_waiting_pocket_keeps_its_root_and_its_steps() -> None:
    pocket = WaitingPocket(BENCH, ("9", "12"))

    assert (pocket.root, pocket.steps) == (BENCH, ("9", "12"))


def test_waiting_pocket_accepts_steps_in_plan_order_with_lettered_ids() -> None:
    assert WaitingPocket(BENCH, ("1", "1b", "2", "10")).steps == ("1", "1b", "2", "10")


def test_waiting_pocket_is_frozen() -> None:
    pocket = WaitingPocket(BENCH, ("41",))

    with pytest.raises(dataclasses.FrozenInstanceError):
        pocket.root = "elsewhere"  # type: ignore[misc]


def test_waiting_pocket_refuses_no_steps() -> None:
    with pytest.raises(ValueError, match="(?i)step"):
        WaitingPocket(BENCH, ())


def test_waiting_pocket_refuses_a_step_named_twice() -> None:
    with pytest.raises(ValueError, match="41"):
        WaitingPocket(BENCH, ("41", "41"))


def test_waiting_pocket_refuses_steps_out_of_plan_order() -> None:
    with pytest.raises(ValueError, match="12"):
        WaitingPocket(BENCH, ("12", "9"))


# -- Which pockets wait ---------------------------------------------------------------------------


def test_a_committed_deferral_makes_its_pocket_wait_with_the_step() -> None:
    text = results_file(gate_block("41", "req-41", deferred=(BENCH,)))

    waiting = waiting_pockets(text, [record("41", "req-41")])

    assert waiting == (WaitingPocket(BENCH, ("41",)),)


def test_a_deferral_in_an_attempt_that_was_not_committed_adds_nothing() -> None:
    text = results_file(gate_block("41", "req-41", deferred=(BENCH,)))

    assert waiting_pockets(text, [record("41", "req-41", commit=None)]) == ()


def test_a_deferral_in_a_block_no_ledger_record_names_adds_nothing() -> None:
    text = results_file(gate_block("41", "req-41", deferred=(BENCH,)))

    assert waiting_pockets(text, [record("41", "some-other-request")]) == ()


def test_a_step_that_deferred_a_pocket_on_two_committed_attempts_is_named_once() -> None:
    text = results_file(
        gate_block("41", "req-41-first", deferred=(BENCH,)),
        gate_block("41", "req-41-second", deferred=(BENCH,)),
    )
    records = [record("41", "req-41-first"), record("41", "req-41-second", commit="d4e5f6a")]

    assert waiting_pockets(text, records) == (WaitingPocket(BENCH, ("41",)),)


def test_a_committed_attempt_counts_though_an_uncommitted_one_of_the_same_step_deferred_too() -> (
    None
):
    text = results_file(
        gate_block("41", "req-41-first", deferred=(BENCH,)),
        gate_block("41", "req-41-second", deferred=(BENCH,)),
    )
    records = [record("41", "req-41-first", commit=None), record("41", "req-41-second")]

    assert waiting_pockets(text, records) == (WaitingPocket(BENCH, ("41",)),)


def test_two_steps_that_deferred_the_same_pocket_share_one_waiting_pocket() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        gate_block("42", "req-42", deferred=(BENCH,)),
    )

    waiting = waiting_pockets(text, [record("41", "req-41"), record("42", "req-42")])

    assert waiting == (WaitingPocket(BENCH, ("41", "42")),)


def test_waiting_steps_are_in_plan_order_whatever_order_the_records_come_in() -> None:
    text = results_file(
        gate_block("12", "req-12", deferred=(BENCH,)),
        gate_block("9", "req-9", deferred=(BENCH,)),
        gate_block("1b", "req-1b", deferred=(BENCH,)),
    )
    records = [record("12", "req-12"), record("1b", "req-1b"), record("9", "req-9")]

    assert waiting_pockets(text, records) == (WaitingPocket(BENCH, ("1b", "9", "12")),)


def test_a_step_that_deferred_two_pockets_is_named_under_each() -> None:
    text = results_file(gate_block("41", "req-41", deferred=(ROOT_POCKET, BENCH)))

    waiting = waiting_pockets(text, [record("41", "req-41")])

    assert waiting_by_root(waiting) == {ROOT_POCKET: ("41",), BENCH: ("41",)}


def test_each_pocket_waits_only_for_the_steps_that_deferred_it() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        gate_block("42", "req-42", deferred=(SERVICE,)),
    )

    waiting = waiting_pockets(text, [record("41", "req-41"), record("42", "req-42")])

    assert waiting_by_root(waiting) == {BENCH: ("41",), SERVICE: ("42",)}


def test_a_gate_block_that_deferred_nothing_makes_no_pocket_wait() -> None:
    text = results_file(gate_block("41", "req-41"))

    assert waiting_pockets(text, [record("41", "req-41")]) == ()


# -- What stops a pocket from waiting ------------------------------------------------------------


def test_a_green_checkpoint_after_the_deferral_clears_the_pocket() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        checkpoint_block(BENCH, ("41",)),
    )

    assert waiting_pockets(text, [record("41", "req-41")]) == ()


def test_a_deferral_placed_after_a_green_checkpoint_waits_without_the_earlier_steps() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        checkpoint_block(BENCH, ("41",)),
        gate_block("42", "req-42", deferred=(BENCH,)),
    )

    waiting = waiting_pockets(text, [record("41", "req-41"), record("42", "req-42")])

    assert waiting == (WaitingPocket(BENCH, ("42",)),)


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(RED_RESULT, id="a-failing-test"),
        pytest.param(CUT_OFF_RESULT, id="a-run-cut-off-at-its-bound"),
    ],
)
def test_a_red_checkpoint_clears_nothing(result: str) -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        checkpoint_block(BENCH, ("41",), result),
    )

    waiting = waiting_pockets(text, [record("41", "req-41")])

    assert waiting == (WaitingPocket(BENCH, ("41",)),)


def test_a_green_checkpoint_for_one_pocket_leaves_another_pocket_waiting() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(ROOT_POCKET, BENCH)),
        checkpoint_block(BENCH, ("41",)),
    )

    waiting = waiting_pockets(text, [record("41", "req-41")])

    assert waiting == (WaitingPocket(ROOT_POCKET, ("41",)),)


def test_a_green_checkpoint_clears_every_earlier_deferral_of_its_pocket() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        gate_block("42", "req-42", deferred=(BENCH,)),
        checkpoint_block(BENCH, ("41", "42")),
    )

    assert waiting_pockets(text, [record("41", "req-41"), record("42", "req-42")]) == ()


def test_a_red_checkpoint_then_a_green_one_clears_the_pocket() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(BENCH,)),
        checkpoint_block(BENCH, ("41",), RED_RESULT, head="1111111"),
        checkpoint_block(BENCH, ("41",), head="2222222"),
    )

    assert waiting_pockets(text, [record("41", "req-41")]) == ()


@pytest.mark.parametrize(
    ("timeline", "expected"),
    [
        pytest.param(
            [("defer", "41"), ("checkpoint", "red"), ("defer", "42")],
            {BENCH: ("41", "42")},
            id="a-red-run-keeps-the-old-steps-and-a-new-one-joins",
        ),
        pytest.param(
            [("defer", "41"), ("checkpoint", "green"), ("defer", "42"), ("checkpoint", "red")],
            {BENCH: ("42",)},
            id="a-red-run-after-a-green-one-keeps-only-the-steps-since-the-green-one",
        ),
        pytest.param(
            [("defer", "41"), ("checkpoint", "green"), ("defer", "42"), ("checkpoint", "green")],
            {},
            id="every-green-run-empties-the-pocket",
        ),
        pytest.param(
            [("defer", "9"), ("checkpoint", "green"), ("defer", "12"), ("defer", "41")],
            {BENCH: ("12", "41")},
            id="steps-since-the-last-green-run-wait-together",
        ),
    ],
)
def test_the_waiting_steps_follow_the_deferrals_and_checkpoints_in_file_order(
    timeline: list[tuple[str, str]], expected: dict[str, tuple[str, ...]]
) -> None:
    blocks: list[str] = []
    records: list[IterationRecord] = []
    for event, detail in timeline:
        if event == "defer":
            blocks.append(gate_block(detail, f"req-{detail}", deferred=(BENCH,)))
            records.append(record(detail, f"req-{detail}"))
        else:
            result = GREEN_RESULT if detail == "green" else RED_RESULT
            blocks.append(checkpoint_block(BENCH, ("0",), result, head=f"{len(blocks):07x}"))

    assert waiting_by_root(waiting_pockets(results_file(*blocks), records)) == expected


# -- What the derivation promises about itself ----------------------------------------------------


def test_the_same_text_and_records_give_the_same_answer_every_time() -> None:
    text = results_file(
        gate_block("41", "req-41", deferred=(ROOT_POCKET, BENCH)),
        gate_block("42", "req-42", deferred=(BENCH,)),
    )
    records = [record("41", "req-41"), record("42", "req-42")]

    assert waiting_pockets(text, records) == waiting_pockets(text, records)


def test_a_results_file_written_before_deferrals_existed_makes_no_pocket_wait() -> None:
    text = results_file(
        gate_block("41", "req-41"),
        gate_block("42", "req-42"),
    )

    assert waiting_pockets(text, [record("41", "req-41"), record("42", "req-42")]) == ()


def test_an_empty_results_file_and_no_records_make_no_pocket_wait() -> None:
    assert waiting_pockets("", []) == ()
