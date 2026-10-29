"""A move's dry run prices every session before the user's go, and launches nothing.

The operator names the git-conventions move and adds `--dry-run`: the entry prints, for the
floor run and the paired run, every session it would launch (task, fixture kind, wording
variant, arm), the count per task and the totals, with no calibration run among them. At the
defaults that is 56 sessions: 48 paired over 24 tasks, and 8 floor. A stand-in `claude` first
on the run's PATH records any launch, and the checkout is the same after the dry run as before.

Every test here reads one dry run, shared by the module; only the seed check runs a second.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.adherence_eval import FakeClaude, install_fake_claude
from tests.acceptance.drivers.move_eval import (
    DEFAULT_FLOOR_SESSIONS,
    DEFAULT_PAIRED_TASKS,
    DEFAULT_TOTAL_SESSIONS,
    FIRST_MOVE,
    FIXTURE_KINDS,
    MOVE_ARMS,
    MoveListing,
    MoveRun,
    move_checkout,
    move_listing,
    run_move,
    tracked_snapshot,
    working_state,
)
from tests.acceptance.drivers.scope_resolver import RESOLVER, pocket

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_PACKAGE_FILE = "eval/src/praxion_evals/adherence/report.py"
ROOT_MODULES_DRIVING_A_MOVE_RUN = (
    "tests/acceptance/test_move_dry_run.py",
    "tests/acceptance/test_move_arms.py",
    "tests/acceptance/test_move_session_take.py",
    "tests/acceptance/test_move_governed_checks.py",
    "tests/acceptance/test_move_verdict_and_report.py",
    "tests/e2e/test_move_run_journey.py",
    "tests/e2e/test_move_floor_runs.py",
)


@dataclass(frozen=True)
class DryRun:
    checkout: Path
    stand_in: FakeClaude
    exit_code: int
    stdout: str
    stderr: str
    before: tuple[dict[str, str], tuple[str, str]]
    after: tuple[dict[str, str], tuple[str, str]]

    def listing(self) -> MoveListing:
        assert self.exit_code == 0, f"the move's dry run failed: {self.stderr[-2000:]}"
        return move_listing(self.stdout)


def _dry_run(workspace: Path) -> DryRun:
    checkout = move_checkout(workspace)
    stand_in = install_fake_claude(workspace)
    before = (tracked_snapshot(checkout), working_state(checkout))
    result = run_move(MoveRun(FIRST_MOVE, checkout, dry_run=True), stand_in.bin_dir)
    after = (tracked_snapshot(checkout), working_state(checkout))
    return DryRun(checkout, stand_in, result.exit_code, result.stdout, result.stderr, before, after)


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory: pytest.TempPathFactory) -> DryRun:
    return _dry_run(tmp_path_factory.mktemp("move-dry-run"))


@pytest.fixture(scope="module")
def listing(dry_run: DryRun) -> MoveListing:
    return dry_run.listing()


# -- Nothing is launched, nothing is written ---------------------------------------------------


def test_a_move_dry_run_launches_no_session(dry_run):
    assert dry_run.exit_code == 0, f"the move's dry run failed: {dry_run.stderr[-2000:]}"
    assert dry_run.stand_in.launches() == [], "a dry run of a move started a session"


def test_a_move_dry_run_leaves_the_checkout_byte_identical(dry_run):
    assert dry_run.exit_code == 0, f"the move's dry run failed: {dry_run.stderr[-2000:]}"
    assert dry_run.after == dry_run.before, "the dry run changed the checkout"


# -- The price at the defaults ----------------------------------------------------------------


def test_the_dry_run_totals_fifty_six_sessions_at_the_defaults(listing):
    assert dict(listing.totals) == {
        "paired": 2 * DEFAULT_PAIRED_TASKS,
        "floor": DEFAULT_FLOOR_SESSIONS,
        "all": DEFAULT_TOTAL_SESSIONS,
    }


def test_the_printed_sessions_match_the_printed_totals(listing):
    by_run = Counter(session.run for session in listing.sessions)

    assert by_run == {"paired": listing.totals["paired"], "floor": listing.totals["floor"]}


def test_the_paired_run_lists_one_full_and_one_lean_session_for_each_of_its_tasks(listing):
    arms_per_task = Counter(
        (session.task_id, session.arm) for session in listing.sessions if session.run == "paired"
    )

    tasks = {task for task, _ in arms_per_task}
    assert len(tasks) == DEFAULT_PAIRED_TASKS
    assert set(arms_per_task) == {(task, arm) for task in tasks for arm in ("full", "lean")}
    assert set(arms_per_task.values()) == {1}, "a paired task lists an arm more than once"


def test_the_floor_run_lists_only_floor_sessions_on_tasks_of_the_move(listing):
    floor = [s for s in listing.sessions if s.run == "floor"]
    paired_tasks = {s.task_id for s in listing.sessions if s.run == "paired"}

    assert {s.arm for s in floor} == {"floor"}
    assert {s.task_id for s in floor} <= paired_tasks, "a floor session runs a task the move lacks"


def test_the_listing_prints_each_tasks_session_count(listing):
    counted = Counter((session.run, session.task_id) for session in listing.sessions)

    assert dict(listing.per_task) == dict(counted)


def test_every_listed_session_names_its_task_fixture_kind_wording_variant_and_arm(listing):
    incomplete = [
        s
        for s in listing.sessions
        if not (s.task_id and s.fixture and s.wording_variant)
        or s.fixture_kind not in FIXTURE_KINDS
        or s.arm not in MOVE_ARMS
    ]

    assert incomplete == [], f"sessions listed without their full description: {incomplete[:3]}"


def test_the_dry_run_prices_no_calibration_session(listing):
    assert listing.calibration_sessions == 0


# -- What the listing shows of the task list --------------------------------------------------


def test_at_least_a_third_of_the_paired_tasks_come_from_each_fixture_kind(listing):
    kind_of_task = {s.task_id: s.fixture_kind for s in listing.sessions if s.run == "paired"}
    per_kind = Counter(kind_of_task.values())

    assert min(per_kind[kind] for kind in FIXTURE_KINDS) * 3 >= DEFAULT_PAIRED_TASKS, per_kind


def test_no_two_paired_tasks_share_both_fixture_and_wording_variant(listing):
    tasks = {
        s.task_id: (s.fixture, s.wording_variant) for s in listing.sessions if s.run == "paired"
    }

    assert len(set(tasks.values())) == len(tasks), "two tasks share fixture and wording"


def test_the_same_seed_lists_the_same_launch_order_for_every_task(listing, tmp_path):
    again = _dry_run(tmp_path).listing()

    assert [(s.run, s.task_id, s.arm) for s in again.sessions] == [
        (s.run, s.task_id, s.arm) for s in listing.sessions
    ]


# -- The root tests driving a move run stay selected ------------------------------------------


@pytest.fixture(scope="module")
def selected_by_an_eval_change() -> frozenset[str]:
    """The root tests the resolver selects for a change inside the eval package."""
    result = subprocess.run(
        [sys.executable, str(RESOLVER), "--json", "--changed", EVAL_PACKAGE_FILE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return frozenset(test["path"] for test in pocket(json.loads(result.stdout), ".")["tests"])


@pytest.mark.parametrize("module", ROOT_MODULES_DRIVING_A_MOVE_RUN)
def test_a_change_inside_the_eval_package_selects_each_root_module_driving_a_move_run(
    module, selected_by_an_eval_change
):
    assert module in selected_by_an_eval_change, f"{EVAL_PACKAGE_FILE} did not select {module}"
