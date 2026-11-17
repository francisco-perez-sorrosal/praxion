"""Tests for what `record` copies out of a return's `Follow-ups:` line
(``scripts/_step_loop_record.py``).

Each item of the line becomes an open line of the task's follow-up record when the return is
recorded, whatever the marker and the gate verdict, before the ledger record is appended. A
replayed record reads no text and appends nothing; a refused one has written nothing yet.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record as rec  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_files import STEP_LABEL  # noqa: E402
from _step_loop_record_gate import GateStillRunningError  # noqa: E402
from _step_loop_render import RequestKey  # noqa: E402
from _step_loop_state import VERIFIED, LoopInputs  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

REQUEST = "s1-a1-implement"
FOLLOW_UPS_FILE = "FOLLOW_UPS.md"
STEP_ID = "1"
PLAN = (
    f"# Plan\n\n## Steps\n\n### {STEP_LABEL}{STEP_ID}: Do it\n\n**Assignee**: implementer\n"
    "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0\n"
)
THE_STEP = parse_plan_steps(PLAN)[0]
LINE = "Follow-ups: rename the stale helper; drop the unused fixture"
OPEN_LINES = "- [open] rename the stale helper\n- [open] drop the unused fixture\n"


DONE = IterationRecord(
    step=STEP_LABEL + STEP_ID,
    attempt=1,
    agent_id="agent-1",
    verdict=VERIFIED,
    decided_by="check",
    test_result="Result: pass=1 fail=0 skip=0 pending=0 by=step-loop",
    commit="c" * 40,
    stop_reason="completed",
    request=REQUEST,
)


def _final_text(body: str, marker: str) -> str:
    return f"{body}\n[{marker.upper()}]"


@pytest.fixture
def returned(monkeypatch, tmp_path):
    """`record_return` over a stubbed gate; `take_back` runs it for a final text and verdict.

    Every effect the call would have on the repository is replaced by a stand-in, and the order
    in which the follow-up record and the ledger were written is kept in `effects.order`."""
    effects = SimpleNamespace(order=[], gate_ran=False)
    record_path = tmp_path / FOLLOW_UPS_FILE
    gate = SimpleNamespace(deciding="Result: pass=1 fail=0 skip=0 pending=0 by=step-loop")

    def take_back(
        text,
        *,
        marker="complete",
        verdict=VERIFIED,
        refuse_gate=False,
        records=(),
        kind="implement",
    ):
        key = RequestKey(
            step=STEP_ID, attempt=1, kind=kind, round=None if kind == "implement" else 1
        )
        asked = SimpleNamespace(key=key, agent_call=SimpleNamespace(subagent_type="implementer"))
        inputs = LoopInputs(steps=(THE_STEP,), attempts={}, records=records, verdicts={})
        task = SimpleNamespace(slug="demo", dir=tmp_path, repo=tmp_path, inputs=inputs)

        def the_gate(task, step, request):
            effects.gate_ran = True
            if refuse_gate:
                raise GateStillRunningError(("scripts",))
            return gate

        def the_ledger(task_dir, record):
            effects.order.append(("ledger", record_path.exists()))

        monkeypatch.setattr(
            rec, "_pending", lambda inputs, request: SimpleNamespace(step=THE_STEP, key=key)
        )
        monkeypatch.setattr(rec, "spawn_request", lambda *args: asked)
        monkeypatch.setattr(rec, "declared_max_turns", lambda subagent_type: 100)
        monkeypatch.setattr(
            rec, "await_end", lambda *args, **kwargs: SimpleNamespace(turns=5, final_text=text)
        )
        monkeypatch.setattr(
            rec, "read_return", lambda seen, relayed, asked, max_turns: (marker, "completed", ())
        )
        monkeypatch.setattr(rec, "run_gate", the_gate)
        monkeypatch.setattr(
            rec,
            "read_verdict",
            lambda task, step_id, request, gate: {"verdict": verdict, "decided_by": "check"},
        )
        monkeypatch.setattr(rec, "commit_attempt", lambda *args: rec.Committing("c" * 40, None))
        monkeypatch.setattr(rec, "tick_step", lambda wip, step_id: None)
        monkeypatch.setattr(rec, "append_ledger_record", the_ledger)
        monkeypatch.setattr(rec, "settle_replan", lambda wip, inputs, step, request: False)
        monkeypatch.setattr(rec, "edit_warnings", lambda task, step, request: ())
        return rec.record_return(cast(rec.TaskView, task), REQUEST, "agent-1", marker)

    def reviewed(text):
        """A light reviewer's return over one verified record of the step's series."""
        work = replace(DONE, request="s1-a1-implement", step_digest=THE_STEP.digest, commit=None)
        key = RequestKey(step=STEP_ID, attempt=1, kind="review", round=1)
        asked = SimpleNamespace(key=key, agent_call=SimpleNamespace(subagent_type="reviewer"))
        inputs = LoopInputs(steps=(THE_STEP,), attempts={}, records=(work,), verdicts={})
        task = SimpleNamespace(slug="demo", dir=tmp_path, repo=tmp_path, inputs=inputs)
        monkeypatch.setattr(
            rec, "_pending", lambda inputs, request: SimpleNamespace(step=THE_STEP, key=key)
        )
        monkeypatch.setattr(rec, "spawn_request", lambda *args: asked)
        monkeypatch.setattr(rec, "declared_max_turns", lambda subagent_type: 100)
        monkeypatch.setattr(
            rec, "await_end", lambda *args, **kwargs: SimpleNamespace(turns=5, final_text=text)
        )
        monkeypatch.setattr(
            rec,
            "read_return",
            lambda seen, relayed, asked, max_turns: ("complete", "completed", ()),
        )
        monkeypatch.setattr(rec, "append_ledger_record", lambda task_dir, record: None)
        return rec.record_return(cast(rec.TaskView, task), key.id, "agent-2", "complete")

    take_back.reviewed = reviewed
    take_back.record_path = record_path
    take_back.effects = effects
    return take_back


@pytest.mark.parametrize(
    ("marker", "verdict"),
    [
        ("complete", VERIFIED),
        ("complete", "mismatch"),
        ("blocked", VERIFIED),
        ("conflict", "mismatch"),
        ("partial", VERIFIED),
    ],
)
def test_each_item_of_the_line_is_appended_whatever_the_marker_and_verdict(
    returned, marker, verdict
):
    returned(_final_text(f"Done.\n{LINE}", marker), marker=marker, verdict=verdict)

    assert returned.record_path.read_text(encoding="utf-8") == f"# Follow-ups\n\n{OPEN_LINES}"


def test_the_items_are_in_the_record_before_the_ledger_record_is_appended(returned):
    returned(_final_text(f"Done.\n{LINE}", "complete"))

    assert returned.effects.order == [("ledger", True)]


def test_a_return_with_no_line_leaves_an_absent_record_absent(returned):
    returned(_final_text("Done.", "complete"))

    assert not returned.record_path.exists()


def test_a_return_with_a_line_and_no_item_leaves_the_record_byte_for_byte(returned):
    returned.record_path.write_bytes(b"# Follow-ups\n\n- [open] held\n")

    returned(_final_text("Done.\nFollow-ups:", "complete"))

    assert returned.record_path.read_bytes() == b"# Follow-ups\n\n- [open] held\n"


def test_items_the_record_already_holds_are_not_repeated(returned):
    returned.record_path.write_text("# Follow-ups\n\n- [open] drop the unused fixture\n")

    returned(_final_text(f"Done.\n{LINE}", "complete"))

    assert returned.record_path.read_text(encoding="utf-8") == (
        "# Follow-ups\n\n- [open] drop the unused fixture\n- [open] rename the stale helper\n"
    )


def test_a_refused_record_writes_no_follow_up(returned):
    with pytest.raises(GateStillRunningError):
        returned(_final_text(f"Done.\n{LINE}", "complete"), refuse_gate=True)

    assert not returned.record_path.exists()


def test_a_replayed_record_reads_no_text_and_appends_nothing(returned, monkeypatch):
    done = DONE
    monkeypatch.setattr(rec, "settle_replan", lambda wip, inputs, step, request: False)

    taken = returned(_final_text(f"Done.\n{LINE}", "complete"), records=(done,))

    assert (taken.recorded["replayed"], returned.record_path.exists()) == (True, False)
    assert returned.effects.gate_ran is False


def test_a_revise_returns_line_is_copied_like_an_implement_ones(returned):
    returned(_final_text(f"Done.\n{LINE}", "complete"), kind="revise")

    assert returned.record_path.read_text(encoding="utf-8") == f"# Follow-ups\n\n{OPEN_LINES}"


def test_a_reviews_return_copies_nothing(returned):
    taken = returned.reviewed(_final_text(f"Reviewed.\n{LINE}", "complete"))

    assert (taken.recorded["stop_reason"], returned.record_path.exists()) == ("completed", False)


@pytest.mark.parametrize("trouble", ["not utf-8", "a directory"])
def test_a_record_that_cannot_be_read_warns_and_the_ledger_record_still_lands(returned, trouble):
    if trouble == "a directory":
        returned.record_path.mkdir()
    else:
        returned.record_path.write_bytes(b"\xff\xfe")

    taken = returned(_final_text(f"Done.\n{LINE}", "complete"))

    assert [code for code, _ in taken.warnings] == ["follow-ups-not-copied"]
    assert returned.effects.order == [("ledger", True)]


def test_a_record_that_cannot_be_written_warns_and_the_ledger_record_still_lands(
    returned, monkeypatch
):
    def refuse(path, items):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(rec, "append_open", refuse)

    taken = returned(_final_text(f"Done.\n{LINE}", "complete"))

    assert [code for code, _ in taken.warnings] == ["follow-ups-not-copied"]
    assert returned.effects.order == [("ledger", False)]
