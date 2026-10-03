"""The spawn tally counts a pipeline's spawns across the repository's checkouts.

A slug's spawns recorded in the main checkout's log and in the log (archives
included) of every existing worktree all count, each once even when merge-in
copied its row into a second log; a merged and removed worktree's spawns still
count through the main log; a log the tally could not read is named and the
tally is not reported complete.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_segments import (
    active_log,
    append_lines,
    make_unreadable,
    rotate,
    running_as_root,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.repository import add_worktree, new_repository, remove_worktree
from tests.acceptance.drivers.spawn_tally import Tally, spawn_count

SLUG = "split-pipeline"
PROMPT = f"Task slug: {SLUG}\nDo the next step."
SESSION_ID = "5e551011-0000-4000-8000-000000100001"


@pytest.fixture
def main(tmp_path: Path) -> Path:
    return new_repository(tmp_path / "main-repo")


@pytest.fixture
def session(tmp_path: Path, main: Path) -> Session:
    return Session(HookHarness(tmp_path / "harness"), SESSION_ID, main)


def _tally(tmp_path: Path, root: Path) -> Tally:
    return spawn_count(root, SLUG, scratch=tmp_path / "tally", budget=99)


def _copy_log_into_main(worktree: Path, main: Path) -> None:
    """What merge-in leaves in the main log: the worktree's rows, unchanged."""
    lines = active_log(state_dir_of(worktree)).read_text(encoding="utf-8").splitlines()
    append_lines(state_dir_of(main), lines)


@pytest.mark.parametrize("where", ["under-claude-worktrees", "elsewhere"])
def test_the_tally_from_the_main_checkout_counts_spawns_in_every_existing_worktree(
    tmp_path: Path, main: Path, session: Session, where: str
) -> None:
    parent = None if where == "under-claude-worktrees" else tmp_path / "elsewhere"
    worktree = add_worktree(main, "wt", parent=parent)
    session.spawn_foreground(PROMPT, "a-main-0001", cwd=main)
    session.spawn_foreground(PROMPT, "a-wt-archived", cwd=worktree)
    rotate(Session(session.harness, SESSION_ID, worktree), state_dir_of(worktree), 1)
    session.spawn_foreground(PROMPT, "a-wt-active", cwd=worktree)

    tally = _tally(tmp_path, main)

    assert tally.spawns == 3, tally.describe()


def test_the_tally_from_a_worktree_counts_the_main_checkouts_spawns(
    tmp_path: Path, main: Path, session: Session
) -> None:
    worktree = add_worktree(main, "wt")
    session.spawn_foreground(PROMPT, "a-main-0001", cwd=main)
    session.spawn_foreground(PROMPT, "a-wt-0001", cwd=worktree)

    tally = _tally(tmp_path, worktree)

    assert tally.spawns == 2, tally.describe()


def test_a_spawn_copied_into_the_main_log_counts_once(
    tmp_path: Path, main: Path, session: Session
) -> None:
    worktree = add_worktree(main, "wt")
    session.spawn_foreground(PROMPT, "a-wt-0001", cwd=worktree)
    _copy_log_into_main(worktree, main)

    tally = _tally(tmp_path, main)

    assert (tally.spawns, tally.resumes) == (1, 0), tally.describe()


def test_a_merged_and_removed_worktrees_spawns_still_count(
    tmp_path: Path, main: Path, session: Session
) -> None:
    merged = add_worktree(main, "merged-wt")
    running = add_worktree(main, "running-wt")
    session.spawn_foreground(PROMPT, "a-merged-0001", cwd=merged)
    session.spawn_foreground(PROMPT, "a-running-0001", cwd=running)
    session.spawn_foreground(PROMPT, "a-main-0001", cwd=main)
    _copy_log_into_main(merged, main)
    remove_worktree(main, merged)

    tally = _tally(tmp_path, main)

    assert tally.spawns == 3, tally.describe()


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_the_tally_names_an_unreadable_worktree_log_and_does_not_report_complete(
    tmp_path: Path, main: Path, session: Session
) -> None:
    worktree = add_worktree(main, "wt")
    session.spawn_foreground(PROMPT, "a-main-0001", cwd=main)
    session.spawn_foreground(PROMPT, "a-wt-0001", cwd=worktree)
    unreadable = active_log(state_dir_of(worktree))
    make_unreadable(unreadable)

    tally = _tally(tmp_path, main)

    assert str(unreadable) in tally.stderr + json.dumps(tally.report), tally.describe()
    assert not (tally.exit_code == 0 and (tally.report or {}).get("verdict") == "within"), (
        tally.describe()
    )
