"""Tests for how `status` and every stop name the pockets that wait for the checkpoint.

The `waiting` key of a status object and of a stop object is present exactly when a pocket
waits, so an object printed when nothing waits is the one the base printed; the status table
and both stop texts (the stderr block and the handoff's next-action paragraph) name each waiting
pocket with its steps. Every case passes values in and reads values out: nothing is mocked.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import step_loop  # noqa: E402
from _loop_state_testkit import PLAIN_STEP, read, verified  # noqa: E402
from _step_loop_action import BUDGET_CAUSE, Stop, issuable_action  # noqa: E402
from _step_loop_checkpoint import WaitingPocket  # noqa: E402
from _step_loop_render import Invocation, StopView, stop_next_action, stop_stderr  # noqa: E402
from _step_loop_state import series_states  # noqa: E402

SLUG, INVOKE = "demo", "python3 scripts/step_loop.py"
HANDOFF = Path("HANDOFF.md")
NEXT = f"{INVOKE} next {SLUG}"
BENCH, API = WaitingPocket("bench", ("1", "2")), WaitingPocket("services/api", ("2",))
BLOCKED = Stop("blocked-marker", "1", "the return was blocked")
WAITING_OBJECT = [
    {"pocket": "bench", "steps": ["1", "2"]},
    {"pocket": "services/api", "steps": ["2"]},
]


def status_of(waiting, action=None):
    """The status object and table of a one-step plan whose step is done, with `waiting` pockets."""
    loop = replace(read([PLAIN_STEP], records=[verified(PLAIN_STEP)]), waiting=waiting)
    action = action or issuable_action(loop)
    stop = (
        cli.stop_object(SLUG, action, INVOKE, HANDOFF, waiting)
        if isinstance(action, Stop)
        else None
    )
    status = cli.status_object(SLUG, loop, series_states(loop), action, stop, INVOKE)
    table = cli.status_table(status, cli.next_line(SLUG, action, INVOKE), loop.steps)
    return status, table


def view_of(waiting) -> StopView:
    return cli.stop_view(BLOCKED, SLUG, INVOKE, waiting)


# --- The status object and its table ---------------------------------------------------------


def test_status_has_no_waiting_key_when_no_pocket_waits() -> None:
    status, table = status_of(())

    assert "waiting" not in status
    assert "waiting for the checkpoint" not in table


def test_status_lists_each_waiting_pocket_with_its_steps() -> None:
    status, _ = status_of((BENCH, API))

    assert status["waiting"] == WAITING_OBJECT


def test_the_status_table_names_each_waiting_pocket_with_its_steps() -> None:
    _, table = status_of((BENCH, API))

    assert "waiting for the checkpoint: bench (steps 1, 2); services/api (steps 2)" in table


def test_status_of_a_done_plan_with_a_pocket_waiting_reports_the_checkpoint_due_stop() -> None:
    loop = replace(read([PLAIN_STEP], records=[verified(PLAIN_STEP)]), waiting=(BENCH,))
    task = SimpleNamespace(slug=SLUG, dir=HANDOFF.parent, inputs=loop)

    reply = step_loop.run_status(task, Namespace(json=False), Invocation(INVOKE))

    stop = reply.doc["stop"]
    assert (reply.doc["outcome"], reply.doc["selected_step"]) == ("needs-human", None)
    assert (stop["cause"], stop["step"], stop["resume"]) == ("checkpoint-due", None, NEXT)
    assert reply.doc["waiting"] == stop["waiting"] == [{"pocket": "bench", "steps": ["1", "2"]}]
    assert f"next: every step is done; run `{NEXT}` to run the checkpoint" in reply.table


def test_status_of_a_done_plan_with_nothing_waiting_is_unchanged() -> None:
    status, table = status_of(())

    assert status["outcome"] == "complete"
    assert table.splitlines()[-1] == "next: every step is done"


# --- The stop object --------------------------------------------------------------------------


def test_a_stop_object_has_no_waiting_key_when_no_pocket_waits() -> None:
    assert "waiting" not in cli.stop_object(SLUG, BLOCKED, INVOKE, HANDOFF)


@pytest.mark.parametrize(
    "stop",
    [
        BLOCKED,
        Stop(BUDGET_CAUSE, None, "the iteration budget is used up"),
        Stop("checkpoint-red", None, "bench is red"),
    ],
    ids=["blocked", "budget", "checkpoint-red"],
)
def test_every_stop_cause_carries_the_waiting_pockets(stop) -> None:
    stop_object = cli.stop_object(SLUG, stop, INVOKE, HANDOFF, (BENCH, API))

    assert stop_object["waiting"] == WAITING_OBJECT


def test_the_stop_envelope_carries_the_waiting_pockets_under_stop() -> None:
    frame = cli.Frame(SLUG)

    doc = cli.stop_envelope(frame, BLOCKED, INVOKE, HANDOFF, (BENCH,))

    assert doc["stop"]["waiting"] == [{"pocket": "bench", "steps": ["1", "2"]}]
    assert "waiting" not in cli.stop_envelope(frame, BLOCKED, INVOKE, HANDOFF)["stop"]


def test_a_status_stop_carries_the_waiting_pockets_in_the_stop_and_beside_it() -> None:
    status, _ = status_of((BENCH,), action=BLOCKED)

    assert (
        status["stop"]["waiting"] == status["waiting"] == [{"pocket": "bench", "steps": ["1", "2"]}]
    )


# --- The stop's texts -------------------------------------------------------------------------


def test_the_stderr_block_names_each_waiting_pocket_and_its_steps() -> None:
    block = stop_stderr(view_of((BENCH, API)))

    assert "Waiting for the checkpoint: bench (steps 1, 2); services/api (steps 2)" in block


def test_the_handoff_paragraph_names_each_waiting_pocket_and_its_steps() -> None:
    paragraph = stop_next_action(view_of((BENCH, API)))

    assert "Waiting for the checkpoint: bench (steps 1, 2); services/api (steps 2)" in paragraph


def test_the_stop_texts_are_unchanged_when_no_pocket_waits() -> None:
    plain = StopView(BLOCKED.cause, BLOCKED.step, BLOCKED.evidence, (), SLUG, INVOKE)

    assert view_of(()) == plain
    assert "Waiting" not in stop_stderr(plain)
    assert "Waiting" not in stop_next_action(plain)
