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


def test_a_marked_stop_names_a_few_files_and_the_count_when_many_were_left():
    many = tuple(f"scripts/m{n:02d}.py" for n in range(40))
    _, inputs = marked_inputs("conflict", {"1": many})

    stop = next_action(inputs)

    assert isinstance(stop, Stop)
    assert many[0] in stop.evidence
    assert many[-1] not in stop.evidence
    assert "40 files" in stop.evidence
    assert len(stop.evidence) < 400, stop.evidence


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


def test_a_marked_steps_uncommitted_files_are_every_path_the_attempt_left(repo):
    (repo / "scripts" / "a.py").write_text("x = 2\n")
    (repo / "scripts" / "other.py").write_text("x = 4\n")
    (repo / "scripts" / "stray.py").write_text("x = 5\n")

    found = uncommitted_files(repo, two_steps("conflict"))

    assert found == {"1": ("scripts/a.py", "scripts/other.py", "scripts/stray.py")}


def test_the_pipelines_own_and_hook_maintained_state_is_not_named(repo):
    for rel in (".ai-work/slug/WIP.md", ".ai-state/observations_summary.jsonl"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("{}\n")
    (repo / "scripts" / "a.py").write_text("x = 2\n")

    found = uncommitted_files(repo, two_steps("blocked"))

    assert found == {"1": ("scripts/a.py",)}


def test_a_marked_step_with_a_clean_tree_has_no_entry(repo):
    assert uncommitted_files(repo, two_steps("blocked")) == {}


def test_no_step_that_is_not_marked_has_an_entry(repo):
    (repo / "scripts" / "a.py").write_text("x = 2\n")
    (repo / "scripts" / "other.py").write_text("x = 4\n")

    assert uncommitted_files(repo, two_steps("completed")) == {}
