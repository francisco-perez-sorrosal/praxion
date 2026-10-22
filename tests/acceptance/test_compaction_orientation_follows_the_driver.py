"""After a compaction during a step loop, the orientation names the driver's own position.

The step the driver will act on, its state and attempts, the iterations used, a stop and
its cause, and an outstanding request with its record call come from the driver's
read-only status, never from the step record's current-step section, its first open item
or its recorded next action. A position that cannot be read says so and names the status
command. Outside a step loop the orientation is what it was, byte for byte.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import compaction_orientation as orientation
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    next_action,
    status,
)

STALE_OPEN_ITEM = "Tidy the stale fixture notes (open item 47)"
STALE_NEXT_ACTION = "Wire the stale retry queue (recorded next action 61)"


def _driven_loop(tmp_path):
    """One step verified, the next issued and outstanding; the step record's own lines are stale."""
    task = build_loop(
        tmp_path,
        Step("3"),
        Step("5"),
        done=("3",),
        extra_progress={"3": f"  - [ ] {STALE_OPEN_ITEM}"},
    )
    with task.wip_path.open("a", encoding="utf-8") as wip:
        wip.write(f"\n## Next Action\n\n{STALE_NEXT_ACTION}\n")
    (task.task_dir / "HANDOFF.md").write_text("# HANDOFF: loop\n\nreadiness: ready\n")
    asked = next_action(task)
    return task, asked


def _stale_current_step(task) -> str:
    wip = task.wip_path.read_text(encoding="utf-8")
    return wip.split("## Current Step", 1)[1].strip().splitlines()[0]


def test_the_orientation_names_the_outstanding_request_and_its_record_call(tmp_path):
    task, asked = _driven_loop(tmp_path)

    context = orientation.orient(task.root).context

    assert asked.request is not None, asked.doc
    record_call = asked.doc["then"][asked.doc["then"].index("record ") :]
    assert asked.request["id"] in context
    assert record_call in context, context


def test_the_orientation_names_the_step_the_driver_acts_on_with_its_state_and_attempts(tmp_path):
    task, asked = _driven_loop(tmp_path)
    state = status(task, as_json=True).json()
    step = next(s for s in state["steps"] if s["step"] == "5")
    assert asked.request is not None, asked.doc

    context = orientation.orient(task.root).context

    assert re.search(r"\b5\b", context), context
    assert step["verdict"] in context, context
    assert re.search(rf"\b{step['attempts']}\s*(/|of)\s*{asked.request['attempt_cap']}\b", context)
    used, budget = state["iterations"]["used"], state["iterations"]["budget"]
    assert re.search(rf"\b{used}\s*(/|of)\s*{budget}\b", context), context


def test_the_orientation_never_reports_the_step_records_stale_position(tmp_path):
    task, _ = _driven_loop(tmp_path)

    context = orientation.orient(task.root).context

    assert _stale_current_step(task) not in context
    assert STALE_OPEN_ITEM not in context
    assert STALE_NEXT_ACTION not in context


def test_the_orientation_keeps_its_cap_its_pointers_and_its_withheld_words(tmp_path):
    task, _ = _driven_loop(tmp_path)

    result = orientation.orient(task.root)

    context = result.context
    assert result.exit_code == 0
    assert len(context.encode("utf-8")) <= orientation.CAP_BYTES
    handoff = context.index(".ai-work/loop-task/HANDOFF.md")
    assert handoff < context.index(".ai-work/loop-task/IMPLEMENTATION_PLAN.md")
    assert [w for w in orientation.WITHHELD_WORDS if w in context.lower()] == []


def test_a_stopped_loop_is_reported_as_stopped_with_its_cause(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    first = next_action(task).request
    assert first is not None
    cap = first["attempt_cap"]
    for _ in range(cap):
        attempt(task, Work(passes=False))
    stop = status(task, as_json=True).json()["stop"]

    context = orientation.orient(task.root).context

    assert "stopped" in context.lower(), context
    assert stop["cause"] in context, context


def test_a_complete_loop_is_reported_as_complete(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    attempt(task, Work())
    assert status(task, as_json=True).json()["outcome"] == "complete"

    context = orientation.orient(task.root).context

    assert "complete" in context.lower(), context
    assert _stale_current_step(task) not in context


@pytest.mark.parametrize("stand_in", sorted(orientation.DRIVER_STAND_INS))
def test_an_unreadable_driver_position_names_the_status_command_never_the_stale_one(
    tmp_path, stand_in
):
    task, _ = _driven_loop(tmp_path)
    plugin = orientation.plugin_copy_with_driver(tmp_path, stand_in)

    result = orientation.orient(task.root, plugin_root=plugin)

    assert result.exit_code == 0
    assert result.seconds < orientation.registered_timeout(), result.seconds
    context = result.context
    assert re.search(rf"step_loop\.py status {task.slug}\b", context), context
    assert _stale_current_step(task) not in context
    assert STALE_NEXT_ACTION not in context


@pytest.mark.parametrize("scenario", sorted(orientation.OUTSIDE_A_LOOP))
def test_outside_a_step_loop_the_orientation_is_unchanged_byte_for_byte(tmp_path, scenario):
    project = tmp_path / "project"
    project.mkdir()
    orientation.OUTSIDE_A_LOOP[scenario](project)

    result = orientation.orient(project)

    assert result.exit_code == 0
    assert result.stdout == orientation.frozen_orientation(scenario)


@pytest.mark.parametrize("scenario", sorted(orientation.OUTSIDE_A_LOOP))
def test_outside_a_step_loop_the_orientation_starts_no_driver(tmp_path, scenario):
    project = tmp_path / "project"
    project.mkdir()
    orientation.OUTSIDE_A_LOOP[scenario](project)

    result = orientation.orient(project)

    assert result.probe.processes_started() == []
