"""Tests for the one ownership rule of the step-loop driver (``scripts/_step_loop_ownership.py``).

One `Read-only:` entry is read three ways: the gate asks who owns a failed node, the commit
asks which files it leaves out and the prompt asks what a step may do with its own entries.
The tests pin each reading and that the three stay consistent with one another.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_gate as gate  # noqa: E402
import _step_loop_io as io  # noqa: E402
import _step_loop_ownership as ownership  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_ownership import (  # noqa: E402
    BarePath,
    NodeEntry,
    Ownership,
    entry_owns,
    own_node_permissions,
    read_only_entry,
    withheld,
)

STEP = "Step "
FILE = "tests/test_widget.py"
NODE = f"{FILE}::test_value"
OUTER_LOOP_FILE = "tests/acceptance/test_journey.py"


def step_of(files: tuple[str, ...], read_only: tuple[str, ...]):
    """The plan step a plan declaring these two fields yields."""
    quoted = lambda names: ", ".join(f"`{name}`" for name in names)  # noqa: E731
    plan = f"### {STEP}1: t\n\n**Files**: {quoted(files)}\n**Read-only**: {quoted(read_only)}\n"
    (step,) = parse_plan_steps(plan)
    return step


# --- One entry, parsed once ---


@pytest.mark.parametrize(
    ("text", "entry"),
    [
        ("tests/test_a.py", BarePath("tests/test_a.py")),
        ("tests/", BarePath("tests/")),
        ("tests/test_a.py::test_x", NodeEntry("tests/test_a.py", "test_x")),
        (
            "tests/test_a.py::TestK::test_x[a::b]",
            NodeEntry("tests/test_a.py", "TestK::test_x[a::b]"),
        ),
        ("weird[1].txt", BarePath("weird[1].txt")),
    ],
)
def test_an_entry_is_cut_at_the_first_double_colon_only(text: str, entry) -> None:
    assert read_only_entry(text) == entry


# --- The gate's reading: who owns a failed node ---


@pytest.mark.parametrize(
    ("entry", "node", "owns"),
    [
        ("tests/test_a.py", "tests/test_a.py::test_x", True),
        ("tests/", "tests/test_a.py::test_x", True),
        ("tests/test_a.py", "tests/test_ab.py::test_x", False),
        ("tests/test_a.py::test_x", "tests/test_a.py::test_x", True),
        ("tests/test_a.py::test_x", "tests/test_a.py::test_x[param]", True),
        ("tests/test_a.py::test_x", "tests/test_a.py::test_xy", False),
        ("tests/test_a.py::test_x", "tests/test_a.py::test_y", False),
    ],
)
def test_an_entry_owns_the_nodes_it_is_a_prefix_of_at_a_boundary(
    entry: str, node: str, owns: bool
) -> None:
    assert entry_owns(entry, node) is owns


def test_a_node_a_later_step_owns_is_pending_for_the_step_before_it() -> None:
    rule = Ownership("1", {"1": (), "2": (NODE,)}, frozenset())

    assert (rule.is_pending(NODE), rule.is_pending(f"{FILE}::test_other")) == (True, False)


def test_a_node_the_step_owns_with_a_later_step_is_not_pending() -> None:
    rule = Ownership("1", {"1": (NODE,), "2": (NODE,)}, frozenset())

    assert rule.is_pending(NODE) is False


# --- The commit's reading: which files it leaves out ---


@pytest.mark.parametrize(
    ("path", "entries", "left_out"),
    [
        (FILE, [BarePath(FILE)], True),
        (FILE, [BarePath("tests")], True),
        (FILE, [BarePath("tests/")], False),  # a caller normalises: no trailing slash by here
        (f"{FILE}x", [BarePath(FILE)], False),
        (FILE, [NodeEntry(FILE, "test_value")], False),
        (FILE, [NodeEntry(FILE, "test_value"), BarePath(FILE)], True),
        (FILE, [], False),
        (OUTER_LOOP_FILE, [], True),
        (OUTER_LOOP_FILE, [NodeEntry(OUTER_LOOP_FILE, "test_journey")], True),
        ("tests/e2e/drivers/d.py", [], True),
        ("tests/acceptance_helpers.py", [], False),
    ],
)
def test_a_bare_path_withholds_its_files_a_node_entry_none_and_the_outer_loop_always(
    path: str, entries: list, left_out: bool
) -> None:
    assert withheld(path, entries) is left_out


# --- The prompt's reading: what a step may do with its own node entries ---


def test_a_step_whose_files_name_the_file_of_its_node_entry_is_told_the_file_is_its_to_edit() -> (
    None
):
    step = step_of((FILE,), (NODE,))

    (sentence,) = own_node_permissions(step)

    assert (NODE in sentence, f"`{FILE}` is yours to edit" in sentence) == (True, True)


@pytest.mark.parametrize("directory", ["tests/unit", "./tests/unit"])
def test_a_step_whose_files_name_the_directory_of_its_node_entry_is_told_the_same(
    directory: str,
) -> None:
    node = "tests/unit/test_widget.py::test_value"

    assert len(own_node_permissions(step_of((directory,), (node,)))) == 1


def test_a_step_is_told_once_for_each_node_entry() -> None:
    step = step_of((FILE,), (NODE, f"{FILE}::test_other"))

    assert len(own_node_permissions(step)) == 2


@pytest.mark.parametrize(
    ("files", "read_only"),
    [
        pytest.param(("src/a.py",), (NODE,), id="a-file-its-files-do-not-name"),
        pytest.param((FILE,), (FILE,), id="a-bare-path"),
        pytest.param((OUTER_LOOP_FILE,), (f"{OUTER_LOOP_FILE}::test_journey",), id="outer-loop"),
        pytest.param((FILE,), (), id="no-entry"),
    ],
)
def test_a_step_is_told_nothing_when_it_has_no_node_entry_of_a_file_it_declares(
    files: tuple[str, ...], read_only: tuple[str, ...]
) -> None:
    assert own_node_permissions(step_of(files, read_only)) == ()


# --- The three readers agree ---


@pytest.mark.parametrize("entry", [FILE, "tests", NODE])
def test_the_gate_the_commit_and_the_prompt_read_one_entry_alike(entry: str) -> None:
    parsed = read_only_entry(entry)
    gate_owns = entry_owns(entry, NODE)
    commit_withholds = withheld(FILE, [parsed])
    prompt_grants = bool(own_node_permissions(step_of((FILE,), (entry,))))

    assert (gate_owns, commit_withholds, prompt_grants) == (
        True,
        isinstance(parsed, BarePath),
        isinstance(parsed, NodeEntry),
    )


def test_the_commit_split_leaves_a_node_entrys_file_in_and_a_bare_paths_file_out() -> None:
    kept, left_out = io.split_outer_loop([FILE, "docs/guide.md"], [NODE, "docs/guide.md"])

    assert (kept, left_out) == ((FILE,), ("docs/guide.md",))


# --- Where the rule lives ---


def test_the_gate_and_the_io_adapter_re_export_what_moved() -> None:
    assert (
        gate.Ownership is ownership.Ownership,
        gate.entry_owns is ownership.entry_owns,
        io.OUTER_LOOP_PREFIXES is ownership.OUTER_LOOP_PREFIXES,
    ) == (True, True, True)


def test_the_rule_module_imports_only_the_standard_library_at_run_time() -> None:
    tree = ast.parse((SCRIPT_DIR / "_step_loop_ownership.py").read_text())
    imported = {
        (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", ())
    }

    assert imported <= set(sys.stdlib_module_names), imported
