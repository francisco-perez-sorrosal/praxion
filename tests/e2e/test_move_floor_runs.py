"""Floor runs, stops and continuations of a move, under the discipline every run has.

A planted streak of identical infrastructure errors stops a floor run as continuable, and its
continuation launches again only the streak's tasks; a citation of any part of the finished
floor lineage resolves to the whole lineage. While a stopped run of the move is neither
continued nor closed, a fresh run of the move is refused; once it is closed with a reason a
fresh run is accepted, and a paired run citing the stopped or closed floor run is refused. A
paired run stops on the launch a role run stops on: the session completing the stop count of
identical failures in a row among one arm's sessions in launch order (a retry being that arm's
next session), the other arm's sessions between them neither breaking nor extending the streak.
Its continuation is refused when the moved rule's text or the declaration differs. A paired run
declaring a governed check its cited floor run never failed on final state is refused.

Each journey runs once per module and its tests only read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.acceptance.drivers.move_eval import (
    FIRST_MOVE,
    FLOOR_MINIMUM,
    MOVED_RULES,
    PAIRED_ARMS,
    Arm,
    close_run,
    continue_run,
    declare,
    move_checkout,
    read_move_results,
)
from tests.e2e.drivers.move_journey import (
    Ending,
    RunOutcome,
    Script,
    commit_change,
    copy_checkout,
    install_stand_in,
    observe,
    run,
)

STOP_COUNT = 3
STREAK: dict[tuple[Arm, int], Ending] = {
    ("floor", n): "infrastructure error" for n in range(1, STOP_COUNT + 1)
}
LEAN_STREAK: dict[tuple[Arm, int], Ending] = {
    ("lean", n): "infrastructure error" for n in range(1, STOP_COUNT + 1)
}


def _refused(outcome: RunOutcome) -> None:
    assert outcome.cli.exit_code != 0, f"the run was not refused: {outcome.describe()}"
    assert outcome.launches == (), "a refused run launched a session"
    assert outcome.written == (), "a refused run wrote a results file"


# -- A floor lineage: stopped, continued, cited -----------------------------------------------


@dataclass(frozen=True)
class FloorLineage:
    stopped: RunOutcome
    continued: RunOutcome
    paired: RunOutcome


@pytest.fixture(scope="module")
def lineage(tmp_path_factory: pytest.TempPathFactory) -> FloorLineage:
    workspace = tmp_path_factory.mktemp("floor-lineage")
    checkout = move_checkout(workspace)
    stand_in = install_stand_in(workspace, Script(by_arm={"floor": "violating"}, by_launch=STREAK))
    stopped = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM, stop_count=STOP_COUNT)
    stand_in.rescript(Script(by_arm={"floor": "violating"}))
    continued = observe(
        stand_in, checkout, lambda: continue_run(checkout, stopped.results, stand_in.bin_dir)
    )
    paired = run(stand_in, checkout, "paired", max_tasks=1, floor_citation=stopped.results)
    return FloorLineage(stopped, continued, paired)


def test_a_streak_of_identical_infrastructure_errors_stops_a_floor_run_as_continuable(lineage):
    stopped = read_move_results(lineage.stopped.results)

    assert stopped.ending == "stopped"
    assert len(lineage.stopped.launches) == STOP_COUNT


def test_the_floor_runs_continuation_launches_again_only_the_streaks_tasks(lineage):
    streak_tasks = {launch.task_id for launch in lineage.stopped.launches}
    continued_tasks = [launch.task_id for launch in lineage.continued.launches]

    assert lineage.continued.cli.exit_code == 0, lineage.continued.describe()
    assert streak_tasks <= set(continued_tasks), "a task of the streak was not launched again"
    assert len(continued_tasks) == len(set(continued_tasks)) == FLOOR_MINIMUM


def test_a_citation_of_a_part_of_a_finished_floor_lineage_resolves_to_the_whole_lineage(lineage):
    cited = read_move_results(lineage.paired.results).cited_floor_lineage

    assert set(cited) == {lineage.stopped.results.stem, lineage.continued.results.stem}


# -- An open stopped run, then closed ---------------------------------------------------------


@dataclass(frozen=True)
class ClosedFloor:
    fresh_while_open: RunOutcome
    paired_citing_stopped: RunOutcome
    closed: RunOutcome
    fresh_after_close: RunOutcome
    paired_citing_closed: RunOutcome
    stopped_id: str


@pytest.fixture(scope="module")
def closed_floor(tmp_path_factory: pytest.TempPathFactory) -> ClosedFloor:
    workspace = tmp_path_factory.mktemp("closed-floor")
    checkout = move_checkout(workspace)
    stand_in = install_stand_in(workspace, Script(by_arm={"floor": "violating"}, by_launch=STREAK))
    stopped = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM, stop_count=STOP_COUNT)
    stand_in.rescript(Script(by_arm={"floor": "violating"}))
    fresh_while_open = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)
    citing_stopped = run(stand_in, checkout, "paired", max_tasks=1, floor_citation=stopped.results)
    reason = "the stand-in credential was revoked; the floor will be redrawn"
    closed = observe(
        stand_in, checkout, lambda: close_run(checkout, stopped.results, reason, stand_in.bin_dir)
    )
    fresh_after_close = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)
    citing_closed = run(stand_in, checkout, "paired", max_tasks=1, floor_citation=stopped.results)
    return ClosedFloor(
        fresh_while_open,
        citing_stopped,
        closed,
        fresh_after_close,
        citing_closed,
        stopped.results.stem,
    )


def test_a_fresh_run_is_refused_while_a_continuable_stopped_run_is_neither_continued_nor_closed(
    closed_floor,
):
    _refused(closed_floor.fresh_while_open)
    output = closed_floor.fresh_while_open.cli.stderr + closed_floor.fresh_while_open.cli.stdout
    assert closed_floor.stopped_id in output, "the refusal does not name the stopped run"


def test_a_paired_run_citing_a_floor_run_that_stopped_before_finishing_is_refused(closed_floor):
    _refused(closed_floor.paired_citing_stopped)


def test_a_fresh_run_is_accepted_once_the_stopped_run_is_closed_with_a_reason(closed_floor):
    assert closed_floor.closed.cli.exit_code == 0, closed_floor.closed.describe()
    assert closed_floor.fresh_after_close.cli.exit_code == 0, (
        closed_floor.fresh_after_close.describe()
    )
    assert len(closed_floor.fresh_after_close.launches) == FLOOR_MINIMUM


def test_a_paired_run_citing_a_closed_floor_run_is_refused(closed_floor):
    _refused(closed_floor.paired_citing_closed)


# -- A paired run's stop and its continuation -------------------------------------------------


@dataclass(frozen=True)
class StoppedPaired:
    checkout: Path
    floor: RunOutcome
    stopped: RunOutcome


@pytest.fixture(scope="module")
def stopped_paired(tmp_path_factory: pytest.TempPathFactory) -> StoppedPaired:
    workspace = tmp_path_factory.mktemp("stopped-paired")
    checkout = move_checkout(workspace)
    stand_in = install_stand_in(
        workspace, Script(by_arm={"floor": "violating"}, by_launch=LEAN_STREAK)
    )
    floor = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)
    stopped = run(
        stand_in,
        checkout,
        "paired",
        max_tasks=4,
        floor_citation=floor.results,
        stop_count=STOP_COUNT,
    )
    return StoppedPaired(checkout, floor, stopped)


def test_a_paired_move_run_stops_after_its_third_identical_lean_failure_in_a_row(stopped_paired):
    launches = stopped_paired.stopped.launches

    assert read_move_results(stopped_paired.stopped.results).ending == "stopped"
    assert [launch.arm for launch in launches].count("lean") == STOP_COUNT
    assert launches[-1].arm == "lean", "the run went on past the third lean failure"


def test_the_other_arms_identical_failures_do_not_extend_a_streak(stopped_paired, tmp_path):
    copy = copy_checkout(stopped_paired.checkout, tmp_path)
    floor = copy / stopped_paired.floor.results.relative_to(stopped_paired.checkout)
    two_each: dict[tuple[Arm, int], Ending] = {
        (arm, n): "infrastructure error" for arm in PAIRED_ARMS for n in (1, 2)
    }
    stand_in = install_stand_in(tmp_path, Script(by_launch=two_each))

    outcome = run(
        stand_in, copy, "paired", max_tasks=2, floor_citation=floor, stop_count=STOP_COUNT
    )

    assert outcome.cli.exit_code == 0, outcome.describe()
    assert read_move_results(outcome.results).ending == "finished", (
        "four identical failures, two per arm, stopped the run"
    )


def test_a_continuation_after_the_moved_rule_text_changed_is_refused(stopped_paired, tmp_path):
    copy = copy_checkout(stopped_paired.checkout, tmp_path)
    rule = MOVED_RULES[FIRST_MOVE]
    commit_change(copy, rule, (copy / rule).read_text(encoding="utf-8") + "\n- One more line.\n")
    stopped = copy / stopped_paired.stopped.results.relative_to(stopped_paired.checkout)
    stand_in = install_stand_in(tmp_path, Script())

    _refused(observe(stand_in, copy, lambda: continue_run(copy, stopped, stand_in.bin_dir)))


def test_a_continuation_under_a_differing_declaration_is_refused(stopped_paired, tmp_path):
    copy = copy_checkout(stopped_paired.checkout, tmp_path)
    stopped = copy / stopped_paired.stopped.results.relative_to(stopped_paired.checkout)
    stand_in = install_stand_in(tmp_path, Script())
    declared = declare(FIRST_MOVE, "a change confined to the lean arm", tmp_path)

    outcome = observe(
        stand_in, copy, lambda: continue_run(copy, stopped, stand_in.bin_dir, declared)
    )

    _refused(outcome)


# -- A floor run that never saw a check fail --------------------------------------------------


def test_a_paired_run_declaring_a_check_its_floor_never_failed_is_refused_naming_it(tmp_path):
    checkout = move_checkout(tmp_path)
    stand_in = install_stand_in(tmp_path, Script(by_arm={"floor": "violating the message only"}))
    floor = run(stand_in, checkout, "floor", max_tasks=FLOOR_MINIMUM)

    outcome = run(stand_in, checkout, "paired", max_tasks=1, floor_citation=floor.results)

    _refused(outcome)
    assert "stag" in (outcome.cli.stderr + outcome.cli.stdout).lower(), outcome.describe()
