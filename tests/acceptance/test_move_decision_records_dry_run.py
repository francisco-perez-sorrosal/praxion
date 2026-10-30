"""The adr-conventions move's dry run prices both runs, session by session, and launches nothing.

`praxion-evals-adherence --move adr-conventions --dry-run` prints every session the floor run
and the paired run would launch (task, fixture kind, wording variant, arm), the count per task
and the totals: 56 sessions at the defaults, 48 paired over 24 tasks and 8 floor, every task's
fixture kind managed. The move is no longer refused for want of a task kit. A stand-in `claude`
first on the run's PATH records any launch; the checkout is the same after as before.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import FakeClaude, install_fake_claude
from tests.acceptance.drivers.decision_kit import DECISION_MOVE
from tests.acceptance.drivers.move_eval import (
    DEFAULT_FLOOR_SESSIONS,
    DEFAULT_PAIRED_TASKS,
    DEFAULT_TOTAL_SESSIONS,
    MoveListing,
    MoveRun,
    move_checkout,
    move_listing,
    run_move,
    tracked_snapshot,
    working_state,
)

NO_KIT_REFUSAL = "no task kit"


@dataclass(frozen=True)
class DryRun:
    stand_in: FakeClaude
    exit_code: int
    stdout: str
    stderr: str
    unchanged: bool

    def listing(self) -> MoveListing:
        assert self.exit_code == 0, f"the move's dry run failed: {self.stderr[-2000:]}"
        return move_listing(self.stdout)


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory: pytest.TempPathFactory) -> DryRun:
    workspace: Path = tmp_path_factory.mktemp("decision-dry-run")
    checkout = move_checkout(workspace)
    stand_in = install_fake_claude(workspace)
    before = (tracked_snapshot(checkout), working_state(checkout))
    result = run_move(MoveRun(DECISION_MOVE, checkout, dry_run=True), stand_in.bin_dir)
    after = (tracked_snapshot(checkout), working_state(checkout))
    return DryRun(stand_in, result.exit_code, result.stdout, result.stderr, before == after)


@pytest.fixture(scope="module")
def listing(dry_run: DryRun) -> MoveListing:
    return dry_run.listing()


def test_the_dry_run_is_no_longer_refused_for_want_of_a_task_kit(dry_run):
    assert dry_run.exit_code == 0, dry_run.stderr[-2000:]
    assert NO_KIT_REFUSAL not in (dry_run.stdout + dry_run.stderr).lower()


def test_the_dry_run_launches_no_session_and_leaves_the_checkout_as_it_was(dry_run):
    assert dry_run.exit_code == 0, dry_run.stderr[-2000:]
    assert dry_run.stand_in.launches() == []
    assert dry_run.unchanged, "the dry run changed the checkout"


def test_the_dry_run_totals_fifty_six_sessions_at_the_defaults(listing):
    assert dict(listing.totals) == {
        "paired": 2 * DEFAULT_PAIRED_TASKS,
        "floor": DEFAULT_FLOOR_SESSIONS,
        "all": DEFAULT_TOTAL_SESSIONS,
    }


def test_the_printed_sessions_match_the_printed_totals_and_per_task_counts(listing):
    by_run = Counter(session.run for session in listing.sessions)
    by_task = Counter((session.run, session.task_id) for session in listing.sessions)

    assert by_run == {"paired": listing.totals["paired"], "floor": listing.totals["floor"]}
    assert dict(listing.per_task) == dict(by_task)


def test_the_paired_run_lists_one_full_and_one_lean_session_for_each_of_its_tasks(listing):
    arms = Counter((s.task_id, s.arm) for s in listing.sessions if s.run == "paired")
    tasks = {task for task, _ in arms}

    assert len(tasks) == DEFAULT_PAIRED_TASKS
    assert set(arms) == {(task, arm) for task in tasks for arm in ("full", "lean")}
    assert set(arms.values()) == {1}


def test_every_listed_session_is_on_a_managed_fixture_and_fully_described(listing):
    incomplete = [
        s
        for s in listing.sessions
        if not (s.task_id and s.fixture and s.wording_variant) or s.fixture_kind != "managed"
    ]

    assert listing.sessions, "the dry run listed no session"
    assert incomplete == [], incomplete[:3]


def test_no_two_paired_tasks_share_both_fixture_and_wording_variant(listing):
    tasks = {
        s.task_id: (s.fixture, s.wording_variant) for s in listing.sessions if s.run == "paired"
    }

    assert len(set(tasks.values())) == len(tasks)
