"""Each goal iteration is gated on ground truth and only a progressing one is committed.

A goal step's prompt carries the goal's state from disk. The gate holds the goal's own
failing tests as pending and any other failing test as red. An iteration is committed, by
pathspec with the request trailer, exactly when it is not red, does not regress the
check's counts, changes a path in scope and adds a progress line; otherwise its diff is
kept as a patch named by its request. A change under a protected path stops the loop for
a human. The goal's check, never the worker's marker, decides completion. Driven through
the relay, the iterations' ledger records carry no cost.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.drivers.goal_loop import (
    BROKEN_SHARED,
    CHECK_COMMAND,
    EXPECTS,
    GOAL_SENTENCE,
    OUTER_LOOP_TEST,
    PROTECTED_DOC,
    SHARED_FILES,
    SHARED_MODULE,
    WIDGET,
    Iteration,
    build_goal,
    commit_holds_trailer,
    iterate_by_relay,
    names_count,
    patch_files,
    prompt_text,
    ticked,
)
from tests.acceptance.drivers.step_loop import (
    commit_message,
    commits_after,
    files_in_commit,
    head,
    ledger_records,
    next_action,
)

PROGRESS_SAID = "- Implemented one; two and three remain; the tests import by name (line 23)."
STRAY_EDIT = ("README.md", "# widget, edited on the way\n")

PROMPT_PARTS = {
    "the goal sentence": GOAL_SENTENCE,
    "the check command": CHECK_COMMAND,
    "the check's expectation": EXPECTS,
    "the path in scope": WIDGET,
    "a protected path given by name": PROTECTED_DOC,
    "the default outer-loop protected path": "tests/acceptance",
    "the progress record to append to": "Progress record",
    "the instruction to leave the tree committable": "committable",
    "the instruction never to commit": "never commit",
    "the marker for an impossible goal": "[BLOCKED]",
}


def test_a_partial_step_toward_the_goal_is_committed_while_the_goals_other_tests_fail(tmp_path):
    task = build_goal(tmp_path)
    head_before = head(task)

    iteration = iterate_by_relay(task, Iteration(implemented=("one",)))

    commits = commits_after(task, head_before)
    assert iteration.returned.recorded["commit"] is not None, iteration.returned.doc
    assert len(commits) == 1
    assert commit_holds_trailer(commit_message(task, commits[0]), iteration.request["id"])


def test_a_progressing_iterations_commit_holds_only_its_paths_in_scope(tmp_path):
    task = build_goal(tmp_path)

    iteration = iterate_by_relay(task, Iteration(implemented=("one",), other_edits=(STRAY_EDIT,)))

    commit = iteration.returned.recorded["commit"]
    assert commit is not None, iteration.returned.doc
    assert files_in_commit(task, commit) == {WIDGET}


def test_a_failing_test_outside_the_goals_targets_makes_the_iteration_red(tmp_path):
    task = build_goal(tmp_path, base_files=SHARED_FILES, paths=(WIDGET, SHARED_MODULE))
    head_before = head(task)

    breaking = Iteration(implemented=("one",), other_edits=((SHARED_MODULE, BROKEN_SHARED),))
    iteration = iterate_by_relay(task, breaking)

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_before


def test_an_iteration_that_lowers_the_passes_below_the_base_reading_commits_nothing(tmp_path):
    task = build_goal(tmp_path, implemented=("one",))
    head_before = head(task)

    iteration = iterate_by_relay(task, Iteration(implemented=(), note="rewritten from scratch"))

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_before


def test_an_iteration_that_regresses_the_last_committed_reading_commits_nothing(tmp_path):
    task = build_goal(tmp_path)
    iterate_by_relay(task, Iteration(implemented=("one", "two")))
    head_after_progress = head(task)

    iteration = iterate_by_relay(task, Iteration(implemented=("three",)))

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_after_progress


def test_an_iteration_that_changes_no_path_in_scope_commits_nothing(tmp_path):
    task = build_goal(tmp_path)
    head_before = head(task)

    iteration = iterate_by_relay(task, Iteration(touches_widget=False, other_edits=(STRAY_EDIT,)))

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_before


def test_an_iteration_that_adds_no_progress_line_commits_nothing(tmp_path):
    task = build_goal(tmp_path)
    head_before = head(task)

    iteration = iterate_by_relay(task, Iteration(implemented=("one",), progress=None))

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_before


def test_a_non_progressing_iterations_diff_is_kept_as_a_patch_named_by_its_request(tmp_path):
    task = build_goal(tmp_path)

    iteration = iterate_by_relay(task, Iteration(implemented=("one",), progress=None))

    patches = patch_files(task, iteration.request["id"])
    assert patches, sorted(p.name for p in task.task_dir.iterdir())
    assert "return 1" in "".join(p.read_text(encoding="utf-8") for p in patches)


@pytest.mark.parametrize(
    ("path", "text"),
    [
        pytest.param(OUTER_LOOP_TEST, "def test_weakened():\n    pass\n", id="an-outer-loop-test"),
        pytest.param(PROTECTED_DOC, "# Contract, rewritten\n", id="a-path-given-to-protect"),
        pytest.param("rules/widget.md", "# A new rule\n", id="a-new-file-under-a-default"),
    ],
)
def test_a_change_under_a_protected_path_commits_nothing_and_stops_for_a_human(
    tmp_path, path, text
):
    task = build_goal(tmp_path)
    head_before = head(task)

    iteration = iterate_by_relay(task, Iteration(implemented=("one",), other_edits=((path, text),)))
    stopped = next_action(task)

    assert iteration.returned.recorded["commit"] is None
    assert head(task) == head_before
    assert stopped.exit_code == 2
    assert stopped.outcome == "needs-human"
    assert path in json.dumps(stopped.stop["evidence"]), stopped.stop


def test_an_iteration_that_meets_the_check_is_committed_and_completes_the_goal(tmp_path):
    task = build_goal(tmp_path, implemented=("one", "two"))

    iteration = iterate_by_relay(task, Iteration(implemented=("one", "two", "three")))
    finished = next_action(task)

    assert iteration.returned.recorded["commit"] is not None, iteration.returned.doc
    assert ticked(task)
    assert finished.exit_code == 0
    assert finished.outcome == "complete"


def test_a_complete_marker_whose_check_is_unmet_never_completes_the_goal(tmp_path):
    task = build_goal(tmp_path)

    iterate_by_relay(task, Iteration(implemented=("one",), marker="complete"))
    asked = next_action(task)

    assert asked.outcome == "spawn", asked.doc
    assert not ticked(task)


@pytest.mark.parametrize("part", list(PROMPT_PARTS))
def test_the_goal_prompt_carries_its_fixed_part(tmp_path, part):
    task = build_goal(tmp_path)

    prompt = prompt_text(next_action(task).request)

    assert PROMPT_PARTS[part] in prompt, f"the prompt lacks {part}:\n{prompt}"


def test_the_goal_prompt_names_its_own_request(tmp_path):
    task = build_goal(tmp_path)

    request = next_action(task).request

    assert request["id"] in prompt_text(request)


def test_the_next_prompt_carries_the_progress_so_far_and_the_checks_latest_reading(tmp_path):
    task = build_goal(tmp_path)
    iterate_by_relay(task, Iteration(implemented=("one",), progress=PROGRESS_SAID))

    prompt = prompt_text(next_action(task).request)

    assert PROGRESS_SAID in prompt
    assert names_count(prompt, "pass", 1), prompt
    assert names_count(prompt, "fail", 2), prompt


def test_the_next_prompt_names_the_patch_a_non_progressing_iteration_left(tmp_path):
    task = build_goal(tmp_path)
    left = iterate_by_relay(task, Iteration(implemented=("one",), progress=None))
    patches = patch_files(task, left.request["id"])

    prompt = prompt_text(next_action(task).request)

    assert patches, "the non-progressing iteration left no patch named by its request"
    assert patches[0].name in prompt


def test_iterations_driven_through_the_relay_carry_no_cost_in_the_ledger(tmp_path):
    task = build_goal(tmp_path)
    iterate_by_relay(task, Iteration(implemented=("one",)))

    records, findings = ledger_records(task)

    assert findings == []
    assert len(records) == 1
    assert "cost_usd" not in records[0], records[0]
