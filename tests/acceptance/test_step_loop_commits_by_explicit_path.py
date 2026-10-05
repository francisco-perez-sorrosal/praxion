"""The loop is the one committer: one commit per verified step, holding only the step's files.

A verified attempt yields exactly one commit staging, by explicit path, the step's
declared files and its own unit-test files -- never an outer-loop acceptance test, and
never anything else in the tree. A staged, an unstaged and an untracked decoy survive
byte-identical and outside the commit; an edit outside the declared files stays
uncommitted and is reported; the message names the loop and the step and carries no
AI-authorship line.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    commit_message,
    commits_after,
    files_in_commit,
    git,
    head,
    snapshot,
    staged_paths,
)

OUTER_LOOP_TEST = "tests/acceptance/test_loop_widget.py"
OUTER_LOOP_TEXT = "def test_the_widget_returns_its_id():\n    assert True\n"
STAGED_DECOY = "notes/staged.txt"
UNTRACKED_DECOY = "notes/untracked.txt"
STRAY_EDIT = "src/elsewhere.py"


def _plant_decoys(task) -> None:
    """A user's unstaged edit, a staged new file and an untracked file, all unrelated."""
    (task.root / "README.md").write_text("# loop widget, edited by the user\n", encoding="utf-8")
    (task.root / "notes").mkdir()
    (task.root / STAGED_DECOY).write_text("staged by the user\n", encoding="utf-8")
    git(task, "add", STAGED_DECOY)
    (task.root / UNTRACKED_DECOY).write_text("never added\n", encoding="utf-8")


def test_a_verified_step_yields_exactly_one_commit_holding_only_its_files(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    head_before = head(task)

    returned = attempt(task, Work())

    new_commits = commits_after(task, head_before)
    assert len(new_commits) == 1
    assert returned.recorded["commit"][:7] == new_commits[0][:7]
    assert files_in_commit(task, new_commits[0]) == set(task.step("1").files)


def test_unrelated_staged_unstaged_and_untracked_files_survive_outside_the_commit(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    _plant_decoys(task)
    decoys = ("README.md", STAGED_DECOY, UNTRACKED_DECOY)
    before = {path: snapshot(task)[path] for path in decoys}

    returned = attempt(task, Work())

    after = snapshot(task)
    assert {path: after[path] for path in decoys} == before
    assert not files_in_commit(task, returned.recorded["commit"]) & set(decoys)
    assert STAGED_DECOY in staged_paths(task)


def test_an_outer_loop_test_is_never_committed_even_when_the_step_declares_it(tmp_path):
    step = Step("1", more_files=(OUTER_LOOP_TEST,))
    task = build_loop(tmp_path, step, base_files={OUTER_LOOP_TEST: "# placeholder\n"})

    returned = attempt(task, Work(other_edits=((OUTER_LOOP_TEST, OUTER_LOOP_TEXT),)))

    assert returned.recorded["commit"] is not None
    assert OUTER_LOOP_TEST not in files_in_commit(task, returned.recorded["commit"])
    assert (task.root / OUTER_LOOP_TEST).read_text(encoding="utf-8") == OUTER_LOOP_TEXT


def test_an_edit_outside_the_declared_files_stays_uncommitted_and_is_reported(tmp_path):
    task = build_loop(tmp_path, Step("1"))

    returned = attempt(task, Work(other_edits=((STRAY_EDIT, "STRAY = True\n"),)))

    assert STRAY_EDIT not in files_in_commit(task, returned.recorded["commit"])
    assert (task.root / STRAY_EDIT).read_text(encoding="utf-8") == "STRAY = True\n"
    assert STRAY_EDIT in returned.text(), "the stray edit was left behind without a word"


def test_the_commit_message_names_the_loop_and_the_step_and_no_ai_author(tmp_path):
    task = build_loop(tmp_path, Step("7c"))

    returned = attempt(task, Work())

    message = commit_message(task, returned.recorded["commit"])
    assert re.search(r"step[ _-]loop", message, re.IGNORECASE), message
    assert re.search(r"\b7c\b", message), message
    assert "co-authored-by" not in message.lower()
    assert "claude" not in message.lower()
