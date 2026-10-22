"""Tests for the files a marked stop names (``scripts/_step_loop_action.py``, ``step_loop.py``).

A step whose latest return carried [BLOCKED] or [CONFLICT] left its edits uncommitted; the
shell reads those files for marked steps only, and the stop names the step, the marker and
each file. The pure half passes values in; the shell half runs real ``git`` in a temporary
repository built here.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from _git_runner import run_git  # noqa: E402
from _loop_state_testkit import FILES, IMPL, one, read, rec  # noqa: E402
from _step_loop_action import Stop, next_action  # noqa: E402
from _step_loop_state import STEP_LABEL  # noqa: E402
from step_loop import uncommitted_files  # noqa: E402

LEFT = ("scripts/a.py", "scripts/b.py")


def marked_inputs(stop_reason, uncommitted):
    step = one(IMPL, FILES)
    inputs = read([step], records=[rec(step, 1, stop=stop_reason)])
    return step, dataclasses.replace(inputs, uncommitted=uncommitted)


@pytest.mark.parametrize(
    ("stop_reason", "marker"), [("blocked", "BLOCKED"), ("conflict", "CONFLICT")]
)
def test_a_marked_stop_names_the_step_the_marker_and_each_uncommitted_file(stop_reason, marker):
    step, inputs = marked_inputs(stop_reason, {"1": LEFT})

    stop = next_action(inputs)

    assert isinstance(stop, Stop)
    assert stop.step == step.id
    assert f"{STEP_LABEL}1 carried [{marker}]" in stop.evidence
    assert all(path in stop.evidence for path in LEFT), stop.evidence


def test_a_marked_stop_with_no_uncommitted_file_names_only_the_step_and_the_marker():
    _, inputs = marked_inputs("conflict", {})

    stop = next_action(inputs)

    assert isinstance(stop, Stop)
    assert stop.evidence == f"the latest return at {STEP_LABEL}1 carried [CONFLICT]"


def test_the_stop_repeats_while_its_evidence_holds():
    _, inputs = marked_inputs("blocked", {"1": LEFT})

    assert next_action(inputs) == next_action(inputs)


def _git(root, *args):
    done = run_git(root, *args)
    assert done.returncode == 0, done.stderr


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    for key, value in {"user.name": "Tester", "user.email": "t@example.invalid"}.items():
        _git(root, "config", key, value)
    for name in ("a.py", "b.py", "other.py"):
        (root / "scripts" / name).write_text("x = 1\n")
    _git(root, "add", "--all")
    _git(root, "commit", "-q", "-m", "base")
    return root


def two_steps(first_stop):
    first = one(IMPL, "**Files**: `scripts/a.py`, `scripts/b.py`")
    second = one(IMPL, "**Files**: `scripts/other.py`", number="2")
    records = [rec(first, 1, stop=first_stop), rec(second, 1, stop="completed")]
    return read([first, second], records=records)


def test_a_marked_steps_uncommitted_files_are_its_declared_files_differing_from_head(repo):
    (repo / "scripts" / "a.py").write_text("x = 2\n")
    (repo / "scripts" / "b.py").write_text("x = 3\n")
    (repo / "scripts" / "other.py").write_text("x = 4\n")

    found = uncommitted_files(repo, two_steps("conflict"))

    assert found == {"1": LEFT}


def test_a_marked_step_with_a_clean_tree_has_no_entry(repo):
    assert uncommitted_files(repo, two_steps("blocked")) == {}


def test_no_step_that_is_not_marked_has_an_entry(repo):
    (repo / "scripts" / "a.py").write_text("x = 2\n")
    (repo / "scripts" / "other.py").write_text("x = 4\n")

    assert uncommitted_files(repo, two_steps("completed")) == {}
