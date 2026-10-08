"""`run` drives a goal plan to an outcome, one fresh headless worker per iteration.

With a substitute `claude` first on `PATH`, `run` repeats `next`, start the worker, and
`record` until the outcome is not a spawn, then prints that outcome's envelope and exits
with its code. Each worker is a new process in the repository root, given the request's
prompt verbatim under a fixed safety profile; what the ledger records about it comes from
its result object and its transcript. One line per iteration reports its cost. A worker
that cannot start withdraws its request and exits 4; a plan with no goal step starts no
worker. Every command a stop prints keeps the base and roots `run` was given.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers.goal_loop import (
    CHECK_COMMAND,
    Iteration,
    build_goal,
    iterate_by_relay,
    names_count,
)
from tests.acceptance.drivers.headless_worker import (
    allowed_shell_patterns,
    allows_the_check,
    foreign_shell_patterns,
    install_worker,
    lines_naming_all,
    remove_claude_from_path,
    run_loop,
)
from tests.acceptance.drivers.step_loop import (
    Step,
    build_loop,
    handoff_section,
    ledger_records,
    next_action,
)

FIRST_COST, SECOND_COST = 0.0731, 0.1142
FIRST_TURNS, SECOND_TURNS = 9, 11
PROGRESS_ONE = Iteration(implemented=("one",), requests=FIRST_TURNS, cost_usd=FIRST_COST)
PROGRESS_ONE_TWO = Iteration(
    implemented=("one", "two"), requests=SECOND_TURNS, cost_usd=SECOND_COST
)
NO_PROGRESS = Iteration(touches_widget=False, cost_usd=0.0217)
COMPLETES = Iteration(implemented=("one", "two", "three"))

FIXED_OPTIONS = [
    ("--permission-mode", "dontAsk"),
    ("--permission-prompts", "none"),
    ("--output-format", "json"),
]
NEVER_PASSED = [
    "--resume",
    "-r",
    "--continue",
    "-c",
    "--dangerously-skip-permissions",
    "bypassPermissions",
    "--bare",
]


def _one_iteration(tmp_path, iteration=PROGRESS_ONE):
    """A goal with a budget of one, run through one worker that does `iteration`."""
    task = build_goal(tmp_path, iterations=1)
    worker = install_worker(task, iteration)
    return task, worker, run_loop(task)


def test_run_starts_one_new_worker_per_iteration_in_the_repository_root(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    worker = install_worker(task, PROGRESS_ONE, NO_PROGRESS, NO_PROGRESS)

    run_loop(task)

    calls = worker.calls()
    assert len(calls) == 3
    assert {call.cwd for call in calls} == {str(task.root)}
    assert len({call.request_id for call in calls}) == 3


def test_the_worker_gets_the_requests_prompt_verbatim_and_its_model(tmp_path):
    task = build_goal(tmp_path, iterations=1)
    asked = next_action(task)
    worker = install_worker(task, PROGRESS_ONE)

    run_loop(task)

    call = worker.calls()[0]
    assert call.carries_prompt(asked.request["agent_call"]["prompt"]), call
    assert call.option("--model") == asked.request["agent_call"]["model"]


def test_the_worker_runs_in_print_mode(tmp_path):
    _, worker, _ = _one_iteration(tmp_path)

    argv = worker.calls()[0].argv

    assert "-p" in argv or "--print" in argv, argv


@pytest.mark.parametrize(("option", "value"), FIXED_OPTIONS)
def test_the_worker_starts_under_the_fixed_safety_option(tmp_path, option, value):
    _, worker, _ = _one_iteration(tmp_path)

    assert worker.calls()[0].option(option) == value, worker.calls()[0].argv


def test_the_worker_is_bounded_in_turns_and_in_dollars(tmp_path):
    _, worker, _ = _one_iteration(tmp_path)

    call = worker.calls()[0]

    assert int(call.option("--max-turns")) >= 1, call.argv
    assert float(call.option("--max-budget-usd")) > 0, call.argv


@pytest.mark.parametrize("token", NEVER_PASSED)
def test_the_worker_never_resumes_a_session_or_bypasses_permissions(tmp_path, token):
    _, worker, _ = _one_iteration(tmp_path)

    argv = worker.calls()[0].argv

    assert token not in argv, argv
    assert "bypassPermissions" not in " ".join(argv), argv


def test_the_worker_may_run_the_check_and_the_resolver_and_no_other_shell_command(tmp_path):
    _, worker, _ = _one_iteration(tmp_path)

    patterns = allowed_shell_patterns(worker.calls()[0])

    assert allows_the_check(patterns), (CHECK_COMMAND, patterns)
    assert "resolve_test_scope" in " ".join(patterns), patterns
    assert foreign_shell_patterns(patterns) == [], patterns


def test_each_iteration_is_recorded_from_the_workers_result_and_transcript(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    worker = install_worker(task, PROGRESS_ONE, PROGRESS_ONE_TWO)

    run_loop(task)

    records, findings = ledger_records(task)
    calls, results = worker.calls(), worker.results()
    assert findings == []
    assert [r["request"] for r in records] == [c.request_id for c in calls]
    assert [r["agent_id"] for r in records] == [r["session_id"] for r in results]
    assert [r["turns"] for r in records] == [FIRST_TURNS, SECOND_TURNS]
    assert [r["max_turns"] for r in records] == [int(c.option("--max-turns")) for c in calls]
    assert [r["cost_usd"] for r in records] == [FIRST_COST, SECOND_COST]


@pytest.mark.parametrize(
    ("iteration", "stop_reason"),
    [
        pytest.param(Iteration(result_text="Done.\n[COMPLETE]"), "completed", id="complete"),
        pytest.param(
            Iteration(result_text="Cannot be met as stated.\n[BLOCKED]"), "blocked", id="blocked"
        ),
        pytest.param(
            Iteration(result_text="[COMPLETE]\nThen I tidied up."), "no-marker", id="not-last"
        ),
        pytest.param(Iteration(omits_result_text=True), "no-marker", id="no-result-text"),
    ],
)
def test_the_marker_is_read_from_the_last_line_of_the_result_text(tmp_path, iteration, stop_reason):
    task, _, _ = _one_iteration(tmp_path, iteration)

    records, _ = ledger_records(task)

    assert [r["stop_reason"] for r in records] == [stop_reason]


@pytest.mark.parametrize("exit_status", [0, 1], ids=["exit-zero", "exit-one"])
def test_a_worker_stopped_at_its_turn_bound_is_recorded_as_such_and_never_awaited(
    tmp_path, exit_status
):
    capped = Iteration(implemented=("one",), stopped_at_turn_bound=True, exit_status=exit_status)
    task, _, ran = _one_iteration(tmp_path, capped)

    records, _ = ledger_records(task)

    assert ran.error is None, ran.doc
    assert [r["stop_reason"] for r in records] == ["turn-cap"]


def test_with_no_claude_on_path_the_request_is_withdrawn_and_run_exits_four(tmp_path):
    task = build_goal(tmp_path, iterations=3)
    remove_claude_from_path(task)

    ran = run_loop(task)

    records, _ = ledger_records(task)
    assert ran.exit_code == 4
    assert "claude" in ran.error["message"], ran.error
    assert records == []
    assert next_action(task).request["attempt"] == 1


def test_a_worker_that_prints_no_result_object_is_not_an_attempt_and_run_exits_four(tmp_path):
    task = build_goal(tmp_path, iterations=3)
    install_worker(task, Iteration(prints_result=False))

    ran = run_loop(task)

    records, _ = ledger_records(task)
    assert ran.exit_code == 4
    assert ran.outcome == "error"
    assert records == []
    assert next_action(task).request["attempt"] == 1


def test_a_plan_with_no_goal_step_is_refused_before_any_worker_starts(tmp_path):
    task = build_loop(tmp_path, Step("1"))
    worker = install_worker(task, PROGRESS_ONE)

    ran = run_loop(task)

    assert ran.exit_code == 4
    assert ran.outcome == "error"
    assert re.search(r"goal|Iterations", ran.error["message"]), ran.error
    assert worker.calls() == []


def test_a_task_already_stopped_starts_no_worker_and_prints_the_stop(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    iterate_by_relay(task, NO_PROGRESS)
    iterate_by_relay(task, NO_PROGRESS)
    worker = install_worker(task, PROGRESS_ONE)

    ran = run_loop(task)

    assert ran.exit_code == 2
    assert ran.stop["cause"] == "stalled"
    assert worker.calls() == []


def test_run_ends_complete_with_exit_zero_once_the_goals_check_is_met(tmp_path):
    task = build_goal(tmp_path, iterations=3, implemented=("one", "two"))
    worker = install_worker(task, COMPLETES)

    ran = run_loop(task)

    assert ran.exit_code == 0
    assert ran.outcome == "complete"
    assert len(worker.calls()) == 1


def test_run_ends_on_a_stall_with_exit_two_naming_the_cause(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    install_worker(task, NO_PROGRESS, NO_PROGRESS)

    ran = run_loop(task)

    assert ran.exit_code == 2
    assert ran.outcome == "needs-human"
    assert ran.stop["cause"] == "stalled"


def test_run_ends_on_a_spent_budget_with_exit_three(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    install_worker(task, PROGRESS_ONE, PROGRESS_ONE_TWO)

    ran = run_loop(task)

    assert ran.exit_code == 3
    assert ran.outcome == "budget-exhausted"


def test_each_iteration_prints_one_line_with_its_request_turns_cost_and_commit(tmp_path):
    task = build_goal(tmp_path, iterations=2)
    worker = install_worker(task, PROGRESS_ONE, NO_PROGRESS)

    ran = run_loop(task)

    first, second = worker.calls()
    records, _ = ledger_records(task)
    committed = lines_naming_all(ran, first.request_id, str(FIRST_COST))
    assert len(committed) == 1, ran.stderr
    assert records[0]["commit"][:7] in committed[0], committed
    assert names_count(committed[0], "turn", FIRST_TURNS), committed
    assert len(lines_naming_all(ran, second.request_id, str(NO_PROGRESS.cost_usd))) == 1


def test_an_iterations_line_counts_the_permission_denials_its_worker_reported(tmp_path):
    denied = Iteration(implemented=("one",), permission_denials=2)
    _, worker, ran = _one_iteration(tmp_path, denied)

    lines = lines_naming_all(ran, worker.calls()[0].request_id, "denial")

    assert len(lines) == 1, ran.stderr
    assert names_count(lines[0], "denial", 2), lines


def test_a_stop_reached_by_run_resumes_with_the_base_and_roots_it_was_given(tmp_path):
    task = build_goal(tmp_path, iterations=6)
    install_worker(task, NO_PROGRESS, NO_PROGRESS)

    ran = run_loop(task, "--worktree-root", str(task.root))

    resume = ran.stop["resume"]
    next_section = handoff_section(
        (task.task_dir / "HANDOFF.md").read_text(encoding="utf-8"), "§2 Next action"
    )
    assert f"--base-ref {task.base}" in resume, resume
    assert f"--repo-root {task.root}" in resume, resume
    assert f"--worktree-root {task.root}" in resume, resume
    assert f"--base-ref {task.base}" in next_section, next_section
