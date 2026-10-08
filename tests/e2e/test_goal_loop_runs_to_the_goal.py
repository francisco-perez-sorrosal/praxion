"""A goal runs from one scaffold command to its check, in both forms, end to end.

Scaffolded by `goal` and driven by `run` with a substitute headless worker, a goal that
takes three progressing iterations and one wasted one ends complete with exit 0: one
commit per progressing iteration holding only the path in scope and its request trailer,
one ledger record per iteration with its cost, nothing committed for the wasted one, and a
reconciler that agrees the step is done. Driven through the relay instead, the same goal
ends the same way, its records carrying no cost. A goal that stops converging pauses with
a handoff, its progressing work kept.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers.goal_loop import (
    WIDGET,
    Iteration,
    build_goal,
    commit_holds_trailer,
    goal_step_id,
)
from tests.acceptance.drivers.headless_worker import install_worker, run_loop
from tests.acceptance.drivers.step_loop import (
    commit_message,
    commits_after,
    files_in_commit,
    head,
    ledger_records,
    reconciler_verdict,
)
from tests.e2e.drivers.goal_journey import relay_goal_until_stopped

ONE = Iteration(implemented=("one",), cost_usd=0.0412)
WASTED = Iteration(touches_widget=False, cost_usd=0.0133)
ONE_TWO = Iteration(implemented=("one", "two"), cost_usd=0.0587)
ALL = Iteration(implemented=("one", "two", "three"), cost_usd=0.0624)


def test_run_takes_a_goal_from_its_scaffold_to_its_check(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    base_head = head(task)
    worker = install_worker(task, ONE, WASTED, ONE_TWO, ALL)

    finished = run_loop(task)

    commits = list(reversed(commits_after(task, base_head)))
    records, findings = ledger_records(task)
    progressing = [worker.calls()[i].request_id for i in (0, 2, 3)]
    assert finished.exit_code == 0
    assert finished.outcome == "complete"
    assert [files_in_commit(task, sha) for sha in commits] == [{WIDGET}, {WIDGET}, {WIDGET}]
    assert [
        commit_holds_trailer(commit_message(task, sha), request)
        for sha, request in zip(commits, progressing, strict=True)
    ] == [True, True, True]
    assert findings == []
    assert [r["cost_usd"] for r in records] == [0.0412, 0.0133, 0.0587, 0.0624]
    assert [r["commit"] is None for r in records] == [False, True, False, False]
    assert reconciler_verdict(task, goal_step_id(task))["verdict"] == "verified-complete"


def test_the_relay_takes_the_same_goal_to_the_same_end_without_costs(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    base_head = head(task)

    journey = relay_goal_until_stopped(task, [ONE, WASTED, ONE_TWO, ALL])

    records, _ = ledger_records(task)
    assert journey.final.exit_code == 0
    assert journey.final.outcome == "complete"
    assert len(commits_after(task, base_head)) == 3
    assert ["cost_usd" in r for r in records] == [False, False, False, False]


def test_a_goal_that_stops_converging_pauses_with_a_handoff_keeping_its_progress(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    base_head = head(task)
    install_worker(task, ONE, WASTED, WASTED)

    paused = run_loop(task)

    assert paused.exit_code == 2
    assert paused.stop["cause"] == "stalled"
    assert Path(paused.stop["handoff"]).is_file()
    assert len(commits_after(task, base_head)) == 1
