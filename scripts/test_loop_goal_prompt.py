"""Tests for a goal step's prompt: rendered from the files alone, one iteration at a time.

The render cases pass the plan step, the document text and the goal's state in and read text
out: no file is written and nothing is mocked. The file cases write a small `TEST_RESULTS.md`
or task directory in ``tmp_path`` and read it back through the real adapters. One case runs the
real `next` over a goal plan in a throwaway checkout, to show the pieces meet.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import step_loop  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_files import (  # noqa: E402
    gate_heading,
    iteration_patches,
    latest_reading,
    restate_result,
)
from _step_loop_render import (  # noqa: E402
    PROGRESS_BOUND,
    PROMPT_CEILING,
    GoalState,
    PromptInputs,
    RequestKey,
    render_prompt,
    spawn_request,
)

STEP = "Step "
SLUG = "demo"
WORK = "/repo/.ai-work/demo"
GOAL_ID, ITERATIONS, ITERATION = "1", 5, 3
OTHER_ID = "2"
GOAL_SENTENCE = "Make the widget answer in every case (goal text 41)."
CHECK_COMMAND = "python3 -m pytest tests/test_widget.py -q"
GIVEN_PROTECTED = "docs/contract.md"
REQUEST_ID = f"s{GOAL_ID}-a{ITERATION}-implement"
PATCH_NAME = f"ITERATION_s{GOAL_ID}-a1-implement.patch"
PROGRESS_HEADING = "## Progress record"
GOAL_STEP_TEXT = f"""\
### {STEP}{GOAL_ID}: Reach the widget goal

**Assignee**: implementer
**Files**: `src/widget.py`
**Read-only**: `{GIVEN_PROTECTED}`
**Check**: `{CHECK_COMMAND}` expects pass>=3 fail=0
**Iterations**: {ITERATIONS}
**Done when**: the check is met.

{GOAL_SENTENCE}
"""
ORDINARY_STEP_TEXT = f"""\
### {STEP}{GOAL_ID}: Add the widget

**Assignee**: implementer
**Files**: `src/widget.py`
**Check**: `{CHECK_COMMAND}` expects pass>=3 fail=0
**Done when**: the widget exists.
"""
GOAL_STEP = parse_plan_steps(GOAL_STEP_TEXT)[0]
ORDINARY_STEP = parse_plan_steps(ORDINARY_STEP_TEXT)[0]
DEFAULT_PROTECTED = ("tests/acceptance/**", "CLAUDE.md")
READING = (f"Command: `{CHECK_COMMAND}`", "1 passed, 2 failed")
REVIEW_RANGE = ("aaa111", "bbb222")
SAID = "- Implemented one; two and three remain; the tests import by name (line 23)."


def wip_with(lines):
    record = "\n".join(lines)
    return f"# WIP\n\n{PROGRESS_HEADING}\n\n{record}\n\n## Notes\n\n- sequential mode\n"


def prompt_for(step=GOAL_STEP, kind="implement", goal=None, wip_text="", cap=ITERATIONS):
    round_ = None if kind == "implement" else 1
    key = RequestKey(step.id, ITERATION, kind, round=round_)
    request = spawn_request(SLUG, step, key, cap, WORK)
    reviewed = REVIEW_RANGE if kind == "review" else None
    inputs = PromptInputs(request, step, WORK, wip_text=wip_text, goal=goal, review_range=reviewed)
    return render_prompt(inputs)


def goal_state(reading=READING, protected=DEFAULT_PROTECTED, patches=()):
    return GoalState(reading=reading, protected=protected, patches=patches)


def goal_prompt(**state):
    text = wip_with([SAID])
    return prompt_for(goal=goal_state(**state), wip_text=text)[0]


def element(text, tag):
    found = re.search(rf"<{tag}[^>]*>\n(.*?)\n</{tag}>", text, re.DOTALL)
    return found.group(1) if found else None


def progress_slot(text):
    lines = element(text, "progress-record").splitlines()
    return lines[:-1], lines[-1]


def numbered_progress(count):
    return [
        f"- iteration {n:03d}: did the {n}th unit; one remains; learned {n}" for n in range(count)
    ]


# --- The fixed parts of a goal prompt ---


GOAL_PARTS = {
    "the goal sentence": GOAL_SENTENCE,
    "the check command": CHECK_COMMAND,
    "the check's expectation": "pass>=3 fail=0",
    "the path in scope": "src/widget.py",
    "the default protected path": f"- {DEFAULT_PROTECTED[0]}",
    "the protected path given by name": f"- {DEFAULT_PROTECTED[1]}",
    "the progress record": PROGRESS_HEADING,
    "the instruction to leave the tree committable": "leave the tree committable",
    "the instruction never to commit": "never commit",
    "the check run without a pipe": "with no pipe",
    "the marker for an impossible goal": "[BLOCKED]",
    "the request id": f"Spawn request: {REQUEST_ID}",
    "the latest reading": "1 passed, 2 failed",
}
GOAL_ONLY_PARTS = {
    "the latest reading": "<latest-reading",
    "the progress record slot": "<progress-record",
    "the protected paths slot": "<protected-paths",
    "the choice of one unit": "Pick one unit of the goal",
    "the progress line to append": "Append one line to `## Progress record`",
    "the iteration opening": f"iteration {ITERATION} of {ITERATIONS}",
}


@pytest.mark.parametrize("part", list(GOAL_PARTS))
def test_a_goal_prompt_carries_each_fixed_part(part):
    assert GOAL_PARTS[part] in goal_prompt(), part


@pytest.mark.parametrize("part", list(GOAL_ONLY_PARTS))
def test_an_ordinary_prompt_lacks_the_parts_only_a_goal_prompt_has(part):
    ordinary, _ = prompt_for(step=ORDINARY_STEP, wip_text=wip_with([SAID]))
    assert GOAL_ONLY_PARTS[part] not in ordinary, part


@pytest.mark.parametrize("part", list(GOAL_ONLY_PARTS))
def test_a_goal_prompt_has_the_parts_an_ordinary_prompt_lacks(part):
    assert GOAL_ONLY_PARTS[part] in goal_prompt(), part


def test_the_opening_names_the_iteration_and_the_budget():
    opening = goal_prompt().splitlines()[2]
    assert f"iteration {ITERATION} of {ITERATIONS}" in opening
    assert "attempt" not in opening


def test_the_request_prompt_keeps_its_first_two_lines():
    first_lines = goal_prompt().splitlines()[:2]
    assert first_lines == [f"Task slug: {SLUG}", f"Spawn request: {REQUEST_ID}"]


def test_the_goal_finish_replaces_the_gate_recording_one():
    text = goal_prompt()
    assert "TEST_RESULTS.md and tick nothing" in text
    assert "Flip only" not in text
    assert "Check: Result:" not in text


# --- The reading, the progress record and the patches ---


def test_a_goal_without_a_reading_says_there_is_none_yet():
    text = prompt_for(goal=goal_state(reading=()), wip_text=wip_with([SAID]))[0]
    assert element(text, "latest-reading") == "No reading yet."


def test_the_reading_is_shown_with_its_command_and_counts():
    slot = element(goal_prompt(), "latest-reading").splitlines()
    assert slot == list(READING)


def test_a_progress_record_is_shown_newest_line_first():
    lines = numbered_progress(4)
    text = prompt_for(goal=goal_state(), wip_text=wip_with(lines))[0]
    assert element(text, "progress-record").splitlines() == list(reversed(lines))


def test_a_progress_record_over_its_bound_keeps_the_newest_lines_and_says_how_many_it_cut():
    lines = numbered_progress(120)
    text = prompt_for(goal=goal_state(), wip_text=wip_with(lines))[0]
    kept, marker = progress_slot(text)
    cut = int(re.match(r"\[(\d+) earlier lines cut", marker)[1])
    assert kept == list(reversed(lines))[: len(kept)]
    assert kept[0] == lines[-1]
    assert lines[0] not in kept
    assert cut == len(lines) - len(kept) > 0
    assert len("\n".join([*kept, marker])) <= PROGRESS_BOUND
    assert marker.endswith("WIP.md]")


def test_a_goal_prompt_with_no_progress_yet_has_no_progress_slot():
    text = prompt_for(goal=goal_state(), wip_text=wip_with([]))[0]
    assert element(text, "progress-record") is None


def test_a_patch_name_is_listed_and_no_patch_means_no_slot():
    with_patch = goal_prompt(patches=(PATCH_NAME,))
    assert element(with_patch, "iteration-patches") == PATCH_NAME
    assert element(goal_prompt(), "iteration-patches") is None


def test_a_goal_prompt_stays_within_the_ceiling_whatever_the_state_holds():
    many = tuple(f"path/{n:03d}/{'p' * 40}.py" for n in range(200))
    patches = tuple(f"ITERATION_s{GOAL_ID}-a{n}-implement.patch" for n in range(1, 120))
    reading = tuple(f"{n} passed, {n} failed" for n in range(400))
    state = goal_state(reading=reading, protected=many, patches=patches)
    text, warnings = prompt_for(goal=state, wip_text=wip_with(numbered_progress(300)))
    assert len(text) <= PROMPT_CEILING
    assert [code for code, _ in warnings] == ["slot-truncated"] * 3


# --- What an ordinary prompt is ---


def test_a_review_of_a_goal_step_is_rendered_as_ever():
    given = goal_state(patches=(PATCH_NAME,))
    base, _ = prompt_for(kind="review", wip_text=wip_with([SAID]))
    assert prompt_for(kind="review", goal=given, wip_text=wip_with([SAID]))[0] == base


def test_an_ordinary_step_with_no_goal_state_is_rendered_by_the_base_slots():
    text, warnings = prompt_for(step=ORDINARY_STEP, wip_text=wip_with([SAID]))
    assert "iteration" not in text.splitlines()[2]
    assert element(text, "previous-attempts") is None
    assert "Flip only" in text
    assert warnings == ()


# --- Reading the results file ---


def results_block(request, *body, step_id=GOAL_ID):
    return "\n".join([gate_heading(step_id, request), "", *body, ""])


BASELINE_BLOCK = results_block(
    "baseline", f"Command: `{CHECK_COMMAND}`", "Result: pass=0 fail=0 skip=0 pending=0 by=step-loop"
)
GATE_BLOCK = results_block(
    "s1-a1-implement",
    "Command: `uv run pytest scripts/test_widget_helpers.py -q`",
    f"Command: `{CHECK_COMMAND}`",
    "Result: pass=12 fail=0 skip=0 pending=0 by=step-loop",
    "Result: pass=1 fail=0 skip=0 pending=2 by=step-loop",
)
OTHER_BLOCK = results_block(
    "s2-a1-implement", "Command: `other`", "Result: pass=9 fail=9 skip=0 by=step-loop", step_id="2"
)


def results_file(tmp_path, *blocks):
    path = tmp_path / "TEST_RESULTS.md"
    path.write_text("# Results\n\n" + "\n".join(blocks), encoding="utf-8")
    return path


def test_the_latest_reading_is_the_steps_last_gate_block_with_the_checks_command(tmp_path):
    path = results_file(tmp_path, BASELINE_BLOCK, GATE_BLOCK, OTHER_BLOCK)
    assert latest_reading(path, GOAL_ID) == (
        f"Command: `{CHECK_COMMAND}`",
        "12 passed, 0 failed",
        "1 passed, 2 failed",
    )


def test_the_baseline_block_is_the_reading_until_a_gate_block_follows_it(tmp_path):
    path = results_file(tmp_path, OTHER_BLOCK, BASELINE_BLOCK)
    assert latest_reading(path, GOAL_ID) == (f"Command: `{CHECK_COMMAND}`", "0 passed, 0 failed")


def test_a_step_with_no_gate_block_has_no_reading(tmp_path):
    path = results_file(tmp_path, OTHER_BLOCK)
    assert latest_reading(path, GOAL_ID) == ()
    assert latest_reading(tmp_path / "absent.md", GOAL_ID) == ()


def test_a_block_the_implementer_wrote_is_not_a_gate_block(tmp_path):
    written = f"## {STEP}{GOAL_ID} — Reach the widget goal\n\nResult: pass=4 fail=0 skip=0\n"
    path = results_file(tmp_path, BASELINE_BLOCK, written)
    assert latest_reading(path, GOAL_ID) == (f"Command: `{CHECK_COMMAND}`", "0 passed, 0 failed")


RESTATED = [
    ("Result: pass=1 fail=0 skip=0 pending=2 by=step-loop", "1 passed, 2 failed"),
    ("Result: pass=7 fail=1 skip=3 by=step-loop", "7 passed, 1 failed"),
    ("Result: pass=7 fail=1 skip=0 error=2 pending=4", "7 passed, 7 failed"),
    ("Result: none — the run was cut off", "no run: the run was cut off"),
    ("Result: pass=x fail=0", "unreadable result"),
]


@pytest.mark.parametrize(("line", "restated"), RESTATED)
def test_a_result_line_is_restated_with_pending_tests_counted_as_failed(line, restated):
    assert restate_result(line) == restated


def touch(directory, names):
    for name in names:
        (directory / name).write_text("diff\n", encoding="utf-8")


def test_iteration_patches_lists_the_steps_own_patch_names_in_order(tmp_path):
    own = [f"ITERATION_s{GOAL_ID}-a2-implement.patch", PATCH_NAME]
    others = [f"ITERATION_s{OTHER_ID}-a1-implement.patch", "ITERATION_notes.patch"]
    snapshot = [f"TREE_SNAPSHOT_s{GOAL_ID}-a1-implement.patch", "PROMPT_s1-a1-implement.md"]
    touch(tmp_path, (*own, *others, *snapshot))
    assert iteration_patches(tmp_path, GOAL_ID) == tuple(sorted(own))


# --- The pieces meet in `next` ---


def checkout(tmp_path):
    task = tmp_path / ".ai-work" / SLUG
    task.mkdir(parents=True)
    plan = f"# Plan\n\n## Steps\n\n{GOAL_STEP_TEXT}"
    wip = f"# WIP\n\n## Progress\n\n- [ ] {STEP}{GOAL_ID}: Reach the widget goal\n\n"
    wip += f"{PROGRESS_HEADING}\n\n{SAID}\n"
    (task / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task / "WIP.md").write_text(wip, encoding="utf-8")
    (task / "TEST_RESULTS.md").write_text(f"# Results\n\n{BASELINE_BLOCK}", encoding="utf-8")
    (task / PATCH_NAME).write_text("diff\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    commit = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q"]
    subprocess.run([*commit, "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
    return task


def test_next_renders_the_goal_prompt_from_the_files_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_DIR / "step_loop.py")])
    task = checkout(tmp_path)

    reply = step_loop.execute(["next", SLUG, "--repo-root", str(tmp_path), "--base-ref", "HEAD"])

    request = reply.doc["request"]
    prompt = (task / f"PROMPT_{request['id']}.md").read_text(encoding="utf-8")
    assert reply.doc["outcome"] == "spawn", reply.doc
    assert request["id"] == "s1-a1-implement"
    assert f"iteration 1 of {ITERATIONS}" in prompt
    assert SAID in element(prompt, "progress-record")
    assert "0 passed, 0 failed" in element(prompt, "latest-reading")
    assert f"- {GIVEN_PROTECTED}" in element(prompt, "protected-paths")
    assert element(prompt, "iteration-patches") == PATCH_NAME
