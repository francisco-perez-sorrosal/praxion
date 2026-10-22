"""Tests for what `record` leaves behind once the gate has run (``scripts/_step_loop_record.py``):
the commit and what each of its outcomes means for the attempt, and the step's checklist line.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_record as rec  # noqa: E402
from _loop_fields import ATTEMPT_CAP  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_io import (  # noqa: E402
    CommitInterrupted,
    CommitRefused,
    Committed,
    NothingToCommit,
    TreeDisturbed,
    TreeSnapshot,
)
from _step_loop_render import RequestKey, spawn_request  # noqa: E402

STEP = "Step "
SLUG = "demo"
REQUEST = "s1-a1-implement"
GREEN_LINE = "Result: pass=3 fail=0 skip=0 pending=0 by=step-loop"
EMPTY_SNAPSHOT = TreeSnapshot(staged=(), unstaged=(), untracked=())
PLAN = f"## Steps\n\n### {STEP}1: Do it\n\n**Assignee**: implementer\n"


# --- The commit -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "sha", "failed", "stops"),
    [
        (Committed("abc1234", ("a.py",), ()), "abc1234", False, False),
        (NothingToCommit(()), None, False, False),
        (CommitRefused("pre-commit: ruff failed\nmore"), None, True, False),
        (CommitInterrupted("timed out", EMPTY_SNAPSHOT, True), None, True, True),
        (
            TreeDisturbed(EMPTY_SNAPSHOT, EMPTY_SNAPSHOT, ("x.py",), "def5678"),
            "def5678",
            True,
            True,
        ),
    ],
)
def test_each_commit_outcome_says_what_holds_the_work_and_whether_to_stop(
    tmp_path, outcome, sha, failed, stops
):
    task = SimpleNamespace(dir=tmp_path, repo=tmp_path)

    taken = rec.judge_commit(task, REQUEST, outcome)

    assert (taken.sha, taken.failure is not None, snapshot_of(tmp_path).exists()) == (
        sha,
        failed,
        stops,
    )


def test_a_disturbed_tree_saves_the_earlier_state_beside_the_task(tmp_path):
    before = TreeSnapshot(staged=(("notes.txt", "row"),), unstaged=(), untracked=())
    task = SimpleNamespace(dir=tmp_path, repo=tmp_path)

    taken = rec.judge_commit(task, REQUEST, TreeDisturbed(before, before, ("notes.txt",), None))

    saved = snapshot_of(tmp_path)
    assert (taken.failure in saved.read_text(), "notes.txt" in saved.read_text()) == (True, True)


def snapshot_of(task_dir):
    return task_dir / f"TREE_SNAPSHOT_{REQUEST}.patch"


@pytest.mark.parametrize(
    "error",
    [
        rec.GitCommandError("fatal: bad object"),
        rec.GitUnavailableError("git is not on PATH"),
        rec.OutsideRepoError("../x leaves the repository"),
    ],
    ids=["git-refused", "git-unavailable", "path-outside-the-repository"],
)
def test_a_commit_that_could_not_run_leaves_a_snapshot_naming_why_and_no_sha(
    repo, monkeypatch, error
):
    def raising(*_):
        raise error

    monkeypatch.setattr(rec, "commit_paths", raising)
    task = SimpleNamespace(dir=repo, repo=repo, slug=SLUG, inputs=SimpleNamespace(steps=()))
    step = parse_plan_steps(PLAN)[0]
    asked = spawn_request(SLUG, step, RequestKey("1", 2, "implement", 1), ATTEMPT_CAP, str(repo))

    taken = rec.commit_attempt(task, step, asked, GREEN_LINE)

    saved = (repo / "TREE_SNAPSHOT_s1-a2-implement.patch").read_text()
    assert (taken.sha, taken.failure in saved, str(error) in saved) == (None, True, True)


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
        "-m", f"subject\n\n{rec.TRAILER}{REQUEST}")  # fmt: skip
    return tmp_path


@pytest.mark.parametrize(("request_id", "found"), [(REQUEST, True), ("s1-a2-implement", False)])
def test_a_head_commit_naming_the_request_is_reused(repo, request_id, found):
    sha = rec.head_commit_for(repo, request_id)

    assert (sha == git(repo, "rev-parse", "HEAD")) is found


def test_a_left_index_lock_is_named_in_the_stop_text(repo):
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")

    assert "index.lock exists" in rec._lock_note(repo)


# --- The checklist ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("wip", "after", "wrote"),
    [
        (f"- [ ] {STEP}1: Do it\n- [ ] {STEP}2: Next\n", f"- [x] {STEP}1: Do it\n", True),
        (f"- [x] {STEP}1: Do it\n- [ ] {STEP}2: Next\n", f"- [x] {STEP}1: Do it\n", False),
    ],
)
def test_the_step_line_is_ticked_once_and_no_other(tmp_path, wip, after, wrote):
    path = tmp_path / rec.WIP_FILE
    path.write_text(wip, encoding="utf-8")

    ticked = rec.tick_step(path, "1")

    assert (ticked, path.read_text(encoding="utf-8")) == (wrote, after + f"- [ ] {STEP}2: Next\n")
