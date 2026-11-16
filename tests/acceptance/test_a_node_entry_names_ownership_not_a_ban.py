"""A `path::node` entry says who owns a node's verdict, not that its file may not be committed.

The commit of a step whose Files names a test file includes that file even when a later
step's Read-only names one node of it, and the step's prompt tells it that the file is its
to edit. An outer-loop test, or a file some step names by a bare Read-only path, is still
withheld from the commit and warned about, as before.
"""

from __future__ import annotations

import json

import pytest

from tests.acceptance.drivers.loop_repairs import (
    lines_granting_edit,
    outside_step_block,
    prompt_text,
)
from tests.acceptance.drivers.step_loop import (
    Step,
    Work,
    attempt,
    build_loop,
    files_in_commit,
    head,
    next_action,
)

NODE = "tests/test_step_1.py::test_value_is_the_step_id"
OUTER_LOOP_TEST = "tests/acceptance/test_widget_journey.py"
SHARED_TEST = "tests/test_shared.py"
JOURNEY = "def test_journey():\n    assert True\n"
SHARED = "def test_shared():\n    assert True\n"


def _warnings_naming(envelope, code: str, path: str) -> list[dict]:
    return [
        w for w in envelope.doc.get("warnings", []) if w["code"] == code and path in json.dumps(w)
    ]


def test_a_node_entry_of_a_later_step_does_not_withhold_the_file_from_its_owning_step(tmp_path):
    task = build_loop(tmp_path, Step("1"), Step("2", read_only=(NODE,)))

    recorded = attempt(task, Work())

    assert head(task) != task.base, f"the step committed nothing: {recorded.doc}"
    assert "tests/test_step_1.py" in files_in_commit(task, head(task)), recorded.doc
    assert _warnings_naming(recorded, "outer-loop-edit", "tests/test_step_1.py") == [], recorded.doc


@pytest.mark.parametrize(
    ("steps", "base_files", "edited", "text"),
    [
        pytest.param(
            (Step("1", more_files=(OUTER_LOOP_TEST,)), Step("2")),
            {},
            OUTER_LOOP_TEST,
            JOURNEY,
            id="an-outer-loop-test",
        ),
        pytest.param(
            (Step("1"), Step("2", read_only=(SHARED_TEST,))),
            {SHARED_TEST: SHARED},
            SHARED_TEST,
            SHARED.replace("True", "1 == 1"),
            id="a-bare-read-only-path-the-step-does-not-declare",
        ),
        pytest.param(
            (Step("1", more_files=(SHARED_TEST,)), Step("2", read_only=(SHARED_TEST,))),
            {SHARED_TEST: SHARED},
            SHARED_TEST,
            SHARED.replace("True", "1 == 1"),
            id="a-bare-read-only-path-the-step-also-declares",
        ),
    ],
)
def test_an_outer_loop_or_bare_read_only_file_is_still_withheld_and_warned_about(
    tmp_path, steps, base_files, edited, text
):
    task = build_loop(tmp_path, *steps, base_files=base_files)

    recorded = attempt(task, Work(other_edits=((edited, text),)))

    assert edited not in files_in_commit(task, head(task)), recorded.doc
    assert _warnings_naming(recorded, "outer-loop-edit", edited), recorded.doc


def test_a_step_told_of_a_node_of_its_own_file_is_told_the_file_is_its_to_edit(tmp_path):
    task = build_loop(tmp_path, Step("1", read_only=(NODE,)))

    said = outside_step_block(prompt_text(next_action(task).request))

    assert lines_granting_edit(said, "tests/test_step_1.py"), said
    assert "test_value_is_the_step_id" in said, said


def test_a_step_told_of_an_outer_loop_node_is_never_told_it_may_edit_that_file(tmp_path):
    task = build_loop(tmp_path, Step("1", read_only=(f"{OUTER_LOOP_TEST}::test_journey",)))

    said = outside_step_block(prompt_text(next_action(task).request))

    assert lines_granting_edit(said, OUTER_LOOP_TEST) == [], said
