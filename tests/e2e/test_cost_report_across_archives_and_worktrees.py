"""The cost report counts every retained archive and each agent once across checkouts.

An agent cost recorded in the oldest retained archive is counted; an unreadable
archive is named while the rest are still counted; a cost in a worktree's log
and in its merged copy in the main log counts once, and a merged worktree's
costs survive the worktree's removal. The report resolves external tools on
first run, so these scenarios carry the `large` marker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.acceptance.drivers.log_rows import costed_stop
from tests.acceptance.drivers.log_segments import (
    active_log,
    append_lines,
    append_rows,
    listed_archives,
    make_unreadable,
    now_iso,
    rotate,
    running_as_root,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.repository import add_worktree, new_repository, remove_worktree
from tests.e2e.drivers.log_retention import attributed_rows, cost_report

pytestmark = pytest.mark.large

SESSION_ID = "5e551011-0000-4000-8000-000000120001"


def _costs_around_two_rotations(tmp_path: Path, checkout: Path) -> None:
    """One agent cost in the oldest archive, one in the newest archive, one in the active log."""
    state = state_dir_of(checkout)
    session = Session(HookHarness(tmp_path / "harness"), SESSION_ID, checkout)
    append_rows(state, [costed_stop("cost-oldest", at=now_iso(), project=checkout.name)])
    rotate(session, state, 1)
    append_rows(state, [costed_stop("cost-newer", at=now_iso(), project=checkout.name)])
    rotate(session, state, 2)
    append_rows(state, [costed_stop("cost-active", at=now_iso(), project=checkout.name)])


def test_an_agent_cost_in_the_oldest_retained_archive_is_counted(tmp_path: Path) -> None:
    checkout = new_repository(tmp_path / "cost-repo")
    _costs_around_two_rotations(tmp_path, checkout)

    report = cost_report(checkout)

    assert attributed_rows(report) == 3


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_the_cost_report_names_an_unreadable_archive_and_counts_the_rest(tmp_path: Path) -> None:
    checkout = new_repository(tmp_path / "cost-repo")
    _costs_around_two_rotations(tmp_path, checkout)
    archives = listed_archives(state_dir_of(checkout))
    assert len(archives) == 2, f"two rotations should keep two archives, found {archives}"
    make_unreadable(archives[1])

    report = cost_report(checkout)

    assert str(archives[1]) in json.dumps(report), "the unreadable archive was not named"
    assert attributed_rows(report) == 2


def _merged_worktree_cost(main: Path, name: str, agent_id: str) -> Path:
    worktree = add_worktree(main, name)
    append_rows(state_dir_of(worktree), [costed_stop(agent_id, at=now_iso(), project=name)])
    append_lines(state_dir_of(main), active_log(state_dir_of(worktree)).read_text().splitlines())
    return worktree


def test_an_agent_cost_in_a_worktree_and_its_merged_copy_counts_once(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    _merged_worktree_cost(main, "merged-wt", "cost-merged")

    report = cost_report(main)

    assert attributed_rows(report) == 1


def test_a_merged_worktrees_costs_survive_its_removal(tmp_path: Path) -> None:
    main = new_repository(tmp_path / "main-repo")
    merged = _merged_worktree_cost(main, "merged-wt", "cost-merged")
    running = add_worktree(main, "running-wt")
    append_rows(
        state_dir_of(running), [costed_stop("cost-running", at=now_iso(), project="running-wt")]
    )
    remove_worktree(main, merged)

    report = cost_report(main)

    assert attributed_rows(report) == 2
