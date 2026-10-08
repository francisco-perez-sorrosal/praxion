"""Tests for what the driver's rendered texts say about what happened.

A goal iteration is kept as progress whether or not its check also passes, so the commit message
must not call it verified; an ordinary step is still called verified, byte for byte. The remedy
for a conflict marker names the order a person has to follow.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_render import (  # noqa: E402
    RequestKey,
    StopView,
    commit_message,
    spawn_request,
    stop_next_action,
    stop_stderr,
)
from test_goal_record import (  # noqa: E402
    SLUG,
    STEP_LABEL,
    TRAILER,
    build_goal,
    git,
    iterate,
    plan_text,
    sandbox,  # noqa: F401  (autouse: a scratch config directory and no wait for an end)
)

WORK = "/repo/.ai-work/demo"
INVOKE = "python3 scripts/step_loop.py"
ITERATIONS_LINE = "**Iterations**: 5\n"
RESULT = "Result: pass=3 fail=0 skip=0 by=step-loop"
GOAL_SENTENCE = "kept by the step-loop driver as progress toward the goal."
ORDINARY_SENTENCE = "verified by the step-loop driver."
CONFLICT_EVIDENCE = "a path outside the declared files changed"


def step_of(text: str):
    return parse_plan_steps(text)[0]


def goal_step():
    return step_of(plan_text())


def ordinary_step():
    return step_of(plan_text().replace(ITERATIONS_LINE, ""))


def request_for(step, attempt=1):
    key = RequestKey(step.id, attempt, "implement")
    return spawn_request(SLUG, step, key, 5, WORK)


def conflict_remedy() -> str:
    stop = StopView("conflict-marker", "1", CONFLICT_EVIDENCE, (), SLUG, INVOKE)
    (line,) = [row for row in stop_stderr(stop).splitlines() if row.startswith("  Next:")]
    return line


def test_a_goal_iterations_message_says_it_was_kept_as_progress():
    step = goal_step()

    message = commit_message(step, SLUG, request_for(step, attempt=3), RESULT)

    expected = f"{STEP_LABEL} of {SLUG}, iteration 3: {GOAL_SENTENCE}"
    assert message.splitlines()[2] == expected


def test_a_goal_iterations_message_never_says_verified():
    step = goal_step()

    message = commit_message(step, SLUG, request_for(step), RESULT)

    assert "verified" not in message


def test_an_ordinary_steps_message_keeps_its_form():
    step = ordinary_step()

    message = commit_message(step, SLUG, request_for(step, attempt=2), RESULT)

    assert message.splitlines() == [
        "Make every widget test pass",
        "",
        f"{STEP_LABEL} of {SLUG}, attempt 2: {ORDINARY_SENTENCE}",
        RESULT,
        "",
        "Step-Loop-Request: s1-a2-implement",
    ]


def test_the_conflict_remedy_names_recording_the_return_before_the_files_line():
    remedy = conflict_remedy()

    assert remedy.index("record") < remedy.index("Files:")


def test_the_handoff_paragraph_gives_the_same_order():
    stop = StopView("conflict-marker", "1", CONFLICT_EVIDENCE, (), SLUG, INVOKE)

    paragraph = stop_next_action(stop)

    assert paragraph.index("record the return first") < paragraph.index("Files:")


def test_a_kept_goal_iteration_commits_with_the_goal_sentence(tmp_path):
    goal = build_goal(tmp_path)

    request, reply = iterate(goal)

    message = git(goal.root, "log", "-1", "--format=%B")
    assert reply.recorded["commit"]
    assert f"{STEP_LABEL} of {SLUG}, iteration 1: {GOAL_SENTENCE}" in message.splitlines()
    assert f"{TRAILER}{request['id']}" in message.splitlines()
    assert "verified" not in message
