"""Each step's attempt cap comes from status, and the orientation renders attempts against it.

`status --json` reports, for every step, the cap its attempts are counted against: the
driver's attempt cap for an ordinary step, the step's own iteration budget for a goal step.
The post-compaction orientation renders a step's attempts against the cap status reports
for that step, so a goal step's attempts show against its own budget and no copy of the
driver's cap is left to drift.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers import compaction_orientation as orientation
from tests.acceptance.drivers.goal_loop import build_goal, goal_step_id
from tests.acceptance.drivers.pocket_gate import status_attempt_cap
from tests.acceptance.drivers.step_loop import Step, build_loop, next_action, status

GOAL_ITERATIONS = 6


def test_status_reports_the_drivers_attempt_cap_for_an_ordinary_step(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2"))
    asked = next_action(task)
    assert asked.request is not None, asked.doc

    caps = [status_attempt_cap(task, "1"), status_attempt_cap(task, "2")]

    assert caps == [asked.request["attempt_cap"]] * 2


def test_status_reports_a_goal_steps_own_iteration_budget_as_its_cap(tmp_path):
    task = build_goal(tmp_path, iterations=GOAL_ITERATIONS)

    cap = status_attempt_cap(task, goal_step_id(task))

    assert cap == GOAL_ITERATIONS


def test_the_orientation_renders_a_goal_steps_attempts_against_its_own_budget(tmp_path):
    task = build_goal(tmp_path, iterations=GOAL_ITERATIONS)
    next_action(task)
    state = status(task, as_json=True).json()
    (step,) = [s for s in state["steps"] if s["step"] == goal_step_id(task)]

    context = orientation.orient(task.root).context

    rendered = rf"\b{step['attempts']}\s*(/|of)\s*{GOAL_ITERATIONS}\b"
    assert re.search(rendered, context), context
