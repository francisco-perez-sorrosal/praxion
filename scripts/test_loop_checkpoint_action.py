"""Tests for the checkpoint action of the step-loop driver and what carries it.

`next_action` answers `Checkpoint` once every step is done and a pocket's whole suite still
waits, and `Complete` otherwise; `checkpoint-red` is a stop that belongs to no step and has an
action text. The checkpoint block's heading and `Covers:` line are rendered here as the writer
will write them and read back as the derivation reads them. Every case passes values in and reads
values out: no file is written, no process runs, nothing is mocked.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _loop_state_testkit import PLAIN_STEP, read, verified  # noqa: E402
from _step_loop_action import (  # noqa: E402
    HUMAN_CAUSES,
    NULL_STEP_CAUSES,
    Checkpoint,
    Complete,
    Spawn,
    Stop,
    next_action,
)
from _step_loop_checkpoint import (  # noqa: E402
    WaitingPocket,
    checkpoint_heading,
    checkpoint_root,
    covers_line,
    deferred_line,
    deferred_roots,
    waiting_pockets,
)
from _step_loop_files import STEP_LABEL, gate_heading  # noqa: E402
from _step_loop_render import _ACTIONS, StopView, stop_next_action, stop_stderr  # noqa: E402
from _step_loop_state import LoopInputs  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

BENCH_WAITING = (WaitingPocket("bench", ("1",)),)
CAUSE = "checkpoint-red"
EVIDENCE = "bench is red; it waits for 1"
SLUG, INVOKE = "demo", "python3 scripts/step_loop.py"

CHECKPOINT_MODULE = SCRIPT_DIR / "_step_loop_checkpoint.py"
MODULES_THAT_DO_IO = {"_step_loop_record_gate", "_step_loop_io"}


def done_inputs(**given) -> LoopInputs:
    """The inputs of a one-step plan whose step the ledger shows verified."""
    return replace(read([PLAIN_STEP], records=[verified(PLAIN_STEP)]), **given)


# --- The action ------------------------------------------------------------------------------


def test_loop_inputs_wait_for_no_pocket_unless_told_so() -> None:
    assert read([PLAIN_STEP]).waiting == ()


def test_every_step_done_with_a_pocket_waiting_is_a_checkpoint() -> None:
    action = next_action(done_inputs(waiting=BENCH_WAITING))

    assert action == Checkpoint(BENCH_WAITING)


def test_every_step_done_and_nothing_waiting_is_complete() -> None:
    assert next_action(done_inputs()) == Complete()


def test_a_plan_with_no_steps_and_a_waiting_pocket_is_still_a_checkpoint() -> None:
    assert next_action(replace(read([]), waiting=BENCH_WAITING)) == Checkpoint(BENCH_WAITING)


def test_a_step_still_to_do_is_spawned_though_a_pocket_waits() -> None:
    action = next_action(replace(read([PLAIN_STEP]), waiting=BENCH_WAITING))

    assert isinstance(action, Spawn)


def test_a_checkpoint_outranks_a_human_stop_as_complete_does() -> None:
    stuck = replace(done_inputs(waiting=BENCH_WAITING), unnamed=("count=2 names no step",))

    assert next_action(stuck) == Checkpoint(BENCH_WAITING)


def test_a_checkpoint_names_every_waiting_pocket() -> None:
    waiting = (*BENCH_WAITING, WaitingPocket("services/api", ("1",)))

    assert next_action(done_inputs(waiting=waiting)).waiting == waiting


def test_a_checkpoint_of_no_pocket_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="(?i)pocket"):
        Checkpoint(())


# --- The stop that ends a red checkpoint -----------------------------------------------------


def test_checkpoint_red_is_a_human_stop_that_belongs_to_no_step() -> None:
    assert CAUSE in HUMAN_CAUSES
    assert CAUSE in NULL_STEP_CAUSES


def test_a_checkpoint_red_stop_is_built_without_a_step() -> None:
    assert Stop(CAUSE, None, EVIDENCE).step is None


def test_a_checkpoint_red_stop_cannot_name_a_step() -> None:
    with pytest.raises(ValueError, match="disagree"):
        Stop(CAUSE, "1", EVIDENCE)


def test_checkpoint_red_has_an_action_text() -> None:
    assert CAUSE in _ACTIONS


def test_the_action_text_says_where_to_look_and_that_the_remedy_is_committed() -> None:
    text = _ACTIONS[CAUSE]

    assert "waiting steps" in text
    assert "commit the fix" in text


def test_the_stderr_block_of_a_red_checkpoint_names_no_step_and_the_next_call() -> None:
    block = stop_stderr(StopView(CAUSE, None, EVIDENCE, (), SLUG, INVOKE))

    assert (
        block.splitlines()[0] == f"step_loop: stopped — the loop needs a human decision ({CAUSE})."
    )
    assert f"Why: {EVIDENCE}" in block
    assert f"then run: {INVOKE} next {SLUG}" in block


def test_the_handoff_paragraph_of_a_red_checkpoint_owes_a_human_decision() -> None:
    paragraph = stop_next_action(StopView(CAUSE, None, EVIDENCE, (), SLUG, INVOKE))

    assert paragraph.splitlines()[0] == f"The step-loop driver stopped: {CAUSE} (exit 2)."
    assert _ACTIONS[CAUSE] in paragraph


# --- The checkpoint block's heading and `Covers:` line ------------------------------------------


@pytest.mark.parametrize("root", [".", "bench", "services/api"])
def test_a_rendered_checkpoint_heading_reads_back_as_its_root(root: str) -> None:
    heading = checkpoint_heading(root, "1a2b3c4")

    assert heading == f"## Checkpoint {root} at 1a2b3c4"
    assert checkpoint_root(heading.removeprefix("## ")) == root


def test_a_root_that_holds_the_word_at_reads_back_whole() -> None:
    heading = checkpoint_heading("look at this", "1a2b3c4")

    assert checkpoint_root(heading.removeprefix("## ")) == "look at this"


@pytest.mark.parametrize(
    "title",
    [
        "Notes",
        "Checkpointing",
        "Checkpoint at 1a2b3c4",
        "Checkpoint  at 1a2b3c4",
        "Checkpoint bench",
        f"{STEP_LABEL}1 gate",
    ],
)
def test_a_heading_that_is_no_checkpoint_heading_names_no_root(title: str) -> None:
    assert checkpoint_root(title) is None


def test_the_covers_line_names_each_step_with_its_label() -> None:
    assert covers_line(("41", "42")) == f"Covers: {STEP_LABEL}41, {STEP_LABEL}42"


# --- The edges of the derivation ----------------------------------------------------------------

FENCE, INDENTED_FENCE = "```", "  ```"
GREEN_RESULT = "Result: pass=12 fail=0 skip=0 pending=0 by=step-loop"


def committed_attempt(step_id: str, request: str) -> IterationRecord:
    return IterationRecord(
        step=f"{STEP_LABEL}{step_id}",
        attempt=1,
        agent_id="agent-1",
        verdict="verified-complete",
        decided_by="check",
        test_result="Result: pass=3 fail=0 skip=0",
        commit="a1b2c3d",
        stop_reason="end_turn",
        request=request,
    )


def gate_block(step_id: str, request: str, *roots: str) -> list[str]:
    return [gate_heading(step_id, request), "", *map(deferred_line, roots), GREEN_RESULT]


def checkpoint_block(root: str) -> list[str]:
    return [checkpoint_heading(root, "1a2b3c4"), "", covers_line(["1"]), GREEN_RESULT]


def waiting_in(*lines: str) -> tuple[WaitingPocket, ...]:
    return waiting_pockets("\n".join(lines) + "\n", [committed_attempt("1", "req-1")])


@pytest.mark.parametrize("fence", [FENCE, INDENTED_FENCE])
def test_a_deferred_line_inside_a_fence_names_no_root_whatever_the_fence_indent(fence: str) -> None:
    lines = [fence, deferred_line("bench"), fence, deferred_line("services/api")]

    assert deferred_roots(lines) == ("services/api",)


@pytest.mark.parametrize(
    "line",
    [
        "Deferred:  (widened): whole suite waits for the checkpoint",
        "Deferred: (widened): whole suite waits for the checkpoint",
    ],
    ids=["an-empty-root", "a-prefix-and-suffix-that-share-their-space"],
)
def test_a_line_that_names_no_root_is_no_deferral(line: str) -> None:
    assert deferred_roots([line]) == ()


@pytest.mark.parametrize("fence", [FENCE, INDENTED_FENCE])
def test_a_gate_block_inside_a_fence_is_no_block(fence: str) -> None:
    fenced = [fence, *gate_block("1", "req-1", "bench"), fence]

    assert waiting_in(*fenced) == ()


def test_a_gate_block_after_a_closed_fence_counts() -> None:
    lines = [FENCE, "an example", FENCE, *gate_block("1", "req-1", "bench")]

    assert waiting_in(*lines) == (WaitingPocket("bench", ("1",)),)


def test_a_green_checkpoint_for_a_pocket_nothing_waits_on_clears_nothing() -> None:
    lines = [*checkpoint_block("bench"), "", *gate_block("1", "req-1", "services/api")]

    assert waiting_in(*lines) == (WaitingPocket("services/api", ("1",)),)


# --- The leaf stays a leaf -----------------------------------------------------------------------


def test_the_checkpoint_module_imports_no_module_that_does_io() -> None:
    tree = ast.parse(CHECKPOINT_MODULE.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported.isdisjoint(MODULES_THAT_DO_IO)
