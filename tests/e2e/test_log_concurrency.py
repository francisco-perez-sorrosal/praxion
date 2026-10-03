"""Concurrent writers never split, duplicate or drop a row across a rotation or a merge-in.

Several sessions start at the moment the active log reaches its cap: the log
rotates once and records each session's row exactly once, whole. Sessions that
record into the main log while merge-in copies a worktree's rows into it lose
nothing either. Real hook processes run in parallel threads, so these scenarios
carry the `large` marker.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_merge_in import merge_in
from tests.acceptance.drivers.log_segments import (
    archive_generations,
    fill_to_cap,
    history_rows,
    rotate,
    session_ids_in,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session, new_checkout
from tests.acceptance.drivers.repository import add_worktree, new_repository
from tests.e2e.drivers.log_retention import run_alongside, start_sessions_concurrently

pytestmark = pytest.mark.large

SESSIONS = [f"5e551011-0000-4000-8000-0000001100{n:02d}" for n in range(6)]


def test_concurrent_appends_at_the_cap_rotate_once_and_record_each_row_once(tmp_path: Path) -> None:
    checkout = new_checkout(tmp_path / "busy-repo")
    harness = HookHarness(tmp_path / "harness")
    Session(harness, "5e551011-0000-4000-8000-0000001100ff", checkout).session_start()
    fill_to_cap(state_dir_of(checkout), 1)

    start_sessions_concurrently(harness, checkout, SESSIONS)

    assert archive_generations(state_dir_of(checkout)) == [{1}]
    assert Counter(session_ids_in(state_dir_of(checkout))) >= Counter(SESSIONS)
    assert [session_ids_in(state_dir_of(checkout)).count(s) for s in SESSIONS] == [1] * 6


def test_hooks_appending_during_merge_in_record_every_row_once(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    worktree = add_worktree(main, "wt")
    harness = HookHarness(tmp_path / "harness")
    in_worktree = Session(harness, "5e551011-0000-4000-8000-0000001100fe", worktree)
    in_worktree.session_start()
    rotate(in_worktree, state_dir_of(worktree), 1)
    worktree_rows = Counter(
        json.dumps(r, sort_keys=True) for r in history_rows(state_dir_of(worktree))
    )

    run_alongside(lambda: merge_in(main, worktree), harness, main, SESSIONS)

    main_rows = Counter(json.dumps(r, sort_keys=True) for r in history_rows(state_dir_of(main)))
    assert worktree_rows - main_rows == Counter(), "a merged row was lost"
    assert {main_rows[row] for row in worktree_rows} == {1}, "a merged row was duplicated"
    assert [session_ids_in(state_dir_of(main)).count(s) for s in SESSIONS] == [1] * 6
