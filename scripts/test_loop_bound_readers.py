"""Tests that every reader of a step's bound gives one answer on whether the step is spent.

The five readers are the driver's state (``_step_loop_state.py``), its decision
(``_step_loop_action.py``), the status table (``_step_loop_cli.py``), the spawn requests
`record` and `next` build (``_step_loop_record.py``, ``step_loop.py``, through ``step_cap``) and
the reconciler's verdict policy (``_step_verdict.py``, wired by ``reconcile_pipeline_state.py``).
An ordinary step reads as it always did; a goal step is spent only at a stall, two kept-nothing
records in a row, whatever its count.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import _step_loop_settle as settle  # noqa: E402
import _step_verdict as verdicts  # noqa: E402
import reconcile_pipeline_state as rps  # noqa: E402
from _loop_fields import Attempt, parse_attempts  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import Spawn, Stop, iteration_budget, next_action  # noqa: E402
from _step_loop_render import RequestKey, spawn_request  # noqa: E402
from _step_loop_state import (  # noqa: E402
    Exhausted,
    Failed,
    HumanVerdict,
    LoopInputs,
    series_states,
    step_cap,
    step_series,
)
from iteration_ledger import IterationRecord  # noqa: E402

STEP = "Step "
STEP_ID = "1"
LABEL = f"{STEP}{STEP_ID}"
SLUG = "bound-readers"
BUDGET = 5
ORDINARY_CAP = 2
KEPT = "c" * 40
EXHAUSTED = "attempts-exhausted"
GATE = "Result: pass=0 fail=1 skip=0 pending=0 by=step-loop"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
BLOCK = f"## Steps\n\n### {LABEL}: Do it\n\n**Assignee**: implementer\n**Files**: `src/a.py`\n"
ORDINARY_PLAN = f"# Plan\n\n{BLOCK}{CHECK}\n"
GOAL_PLAN = f"{ORDINARY_PLAN}**Iterations**: {BUDGET}\n"
UNREADABLE_PLAN = f"{ORDINARY_PLAN}**Iterations**: many\n"
WIP = f"# WIP\n\n## Progress\n\n- [ ] {LABEL}: Do it\n"
READERS = (
    "_step_loop_state.py",
    "_step_loop_action.py",
    "_step_loop_cli.py",
    "_step_loop_record.py",
    "step_loop.py",
    "_step_verdict.py",
    "reconcile_pipeline_state.py",
)
THREE_KEPT = (KEPT, KEPT, KEPT)
STALLED = (KEPT, None, None)


def the_step(plan):
    return parse_plan_steps(plan)[0]


def records(plan, commits):
    step = the_step(plan)
    return tuple(
        IterationRecord(
            step=LABEL,
            attempt=attempt,
            agent_id=f"agent-{attempt}",
            verdict="mismatch",
            decided_by="check",
            test_result=GATE,
            commit=commit,
            stop_reason="completed",
            request=RequestKey(STEP_ID, attempt, "implement", 1).id,
            step_digest=step.digest,
        )
        for attempt, commit in enumerate(commits, start=1)
    )


def inputs(plan, commits, verdict=None):
    verdict_rows = () if verdict is None else ({"step": LABEL, **verdict},)
    return LoopInputs.read((the_step(plan),), {}, records(plan, commits), verdict_rows)


def table_row(loop_inputs):
    action = next_action(loop_inputs)
    states = series_states(loop_inputs)
    status = cli.status_object(SLUG, loop_inputs, states, action, None)
    table = cli.status_table(status, cli.next_line(SLUG, action, "x"), loop_inputs.steps)
    return table.splitlines()[2]


def goal_evidence(**overrides: Any):
    fields: dict[str, Any] = {
        "step_id": LABEL,
        "claim": "PENDING",
        "files": ["src/a.py"],
        "changed": ["src/a.py"],
        "unchanged": [],
        "test_status": "red",
        "tier2": {"agent_stop_seen": True, "last_write": "src/a.py"},
        "iterations": BUDGET,
    }
    return verdicts.StepEvidence(**{**fields, **overrides})


def settled_attempt(tmp_path, plan, commits):
    """What the reconciler reads off the `Attempts:` line after `record` settles the series."""
    ended = inputs(plan, commits)
    wip = tmp_path / "WIP.md"
    count = len(commits)
    request = RequestKey(STEP_ID, count, "implement", 1).id
    wip.write_text(f"{WIP}  - Attempts: {LABEL} count={count} request={request}\n", "utf-8")
    settle.settle_replan(wip, ended, the_step(plan), request)
    return parse_attempts(wip.read_text("utf-8"), frozenset({request})).counts[LABEL]


def cap_reads(module):
    tree = ast.parse((SCRIPT_DIR / module).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    return "ATTEMPT_CAP" in names | imported


# --- An ordinary step reads as at the base ------------------------------------------------------


@pytest.mark.parametrize(
    ("commits", "expected"),
    [
        pytest.param((None,), Failed, id="one-unverified-attempt-is-failed"),
        pytest.param((None, None), Exhausted, id="two-unverified-attempts-are-exhausted"),
        pytest.param((KEPT, KEPT), Exhausted, id="kept-commits-do-not-reset-the-cap"),
    ],
)
def test_an_ordinary_step_is_spent_at_the_attempt_cap_in_the_state(commits, expected):
    assert type(step_series(the_step(ORDINARY_PLAN), inputs(ORDINARY_PLAN, commits))) is expected


def test_an_ordinary_step_sizes_the_budget_and_its_requests_by_the_attempt_cap():
    step = the_step(ORDINARY_PLAN)

    assert (step_cap(step), iteration_budget([step])) == (ORDINARY_CAP, ORDINARY_CAP)


def test_an_ordinary_exhausted_stop_reads_two_of_two_as_at_the_base():
    stop = next_action(inputs(ORDINARY_PLAN, (None, None)))

    assert isinstance(stop, Stop)
    assert (stop.cause, stop.evidence) == (
        EXHAUSTED,
        f"2 of 2 fresh attempts at {LABEL} ended unverified",
    )


def test_an_ordinary_step_reads_its_attempts_against_two_in_the_status_table():
    assert " 1/2 " in table_row(inputs(ORDINARY_PLAN, (None,)))


def test_an_ordinary_step_at_the_cap_reads_exhausted_to_the_verdict_policy():
    evidence = goal_evidence(iterations=None)

    verdict = verdicts.classify_step(evidence, None, Attempt(ORDINARY_CAP))

    assert verdict["verdict"] == EXHAUSTED
    assert f"{ORDINARY_CAP} fresh attempt(s) used (cap {ORDINARY_CAP})" in verdict["evidence"]


# --- A goal step with three kept iterations is spent to no reader -------------------------------


def test_a_goal_step_with_three_kept_iterations_is_failed_not_exhausted_in_the_state():
    state = step_series(the_step(GOAL_PLAN), inputs(GOAL_PLAN, THREE_KEPT))

    assert (type(state), state.bound.iterations) == (Failed, BUDGET)


def test_a_goal_step_with_three_kept_iterations_spawns_its_fourth_under_its_budget(tmp_path):
    action = next_action(inputs(GOAL_PLAN, THREE_KEPT))

    assert isinstance(action, Spawn)
    request = spawn_request(SLUG, action.step, action.key, step_cap(action.step), str(tmp_path))
    assert (request.key.attempt, request.attempt_cap) == (len(THREE_KEPT) + 1, BUDGET)


def test_a_goal_step_with_three_kept_iterations_reads_three_of_its_budget_in_the_table():
    assert f" {len(THREE_KEPT)}/{BUDGET} " in table_row(inputs(GOAL_PLAN, THREE_KEPT))


def test_three_kept_iterations_leave_no_replan_and_the_verdict_policy_reads_no_exhaustion(
    tmp_path,
):
    attempt = settled_attempt(tmp_path, GOAL_PLAN, THREE_KEPT)

    verdict = verdicts.classify_step(goal_evidence(), None, attempt)

    assert (attempt.replan, verdict["verdict"]) == (None, "partial@src/a.py")


def test_a_goal_step_sizes_the_plan_budget_by_its_iterations():
    assert iteration_budget([the_step(GOAL_PLAN)]) == BUDGET


# --- Two kept-nothing iterations in a row: every reader reads the goal step spent ---------------


def test_two_unkept_iterations_in_a_row_read_spent_through_all_five_readers(tmp_path):
    plan, commits = GOAL_PLAN, STALLED
    state = step_series(the_step(plan), inputs(plan, commits))
    stop = next_action(inputs(plan, commits))
    attempt = settled_attempt(tmp_path, plan, commits)
    verdict = verdicts.classify_step(goal_evidence(), None, attempt)
    row = table_row(inputs(plan, commits, verdict))

    spent = {
        "state": type(state) is Exhausted,
        "action": getattr(stop, "cause", None) == "stalled",
        "record's replan line": attempt.replan is not None,
        "verdict policy": verdict["verdict"] == EXHAUSTED,
        "status table": f" {EXHAUSTED} " in row,
    }
    assert spent == dict.fromkeys(spent, True)
    assert f" {len(commits)}/{BUDGET} " in row
    assert step_cap(the_step(plan)) == BUDGET


def test_a_kept_iteration_between_two_unkept_ones_resets_the_stall():
    state = step_series(the_step(GOAL_PLAN), inputs(GOAL_PLAN, (None, KEPT, None)))

    assert type(state) is Failed


# --- The unreadable field and the readers' source ----------------------------------------------


def test_an_unreadable_iterations_field_reads_unknown_to_the_reconciler(tmp_path):
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(WIP, encoding="utf-8")
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(UNREADABLE_PLAN, encoding="utf-8")
    (task_dir / "TEST_RESULTS.md").write_text("", encoding="utf-8")

    (verdict,) = rps.reconcile(
        SLUG, tmp_path, None, _changed_files_override=[], _wal_rows_override=[]
    )

    assert verdict["verdict"] == "unknown"
    assert "Iterations: value cannot be read" in verdict["evidence"]


def test_an_unreadable_iterations_field_is_a_human_verdict_to_the_driver_state():
    state = step_series(the_step(UNREADABLE_PLAN), inputs(UNREADABLE_PLAN, ()))

    assert (type(state), state.verdict) == (HumanVerdict, "unknown")


@pytest.mark.parametrize("module", READERS)
def test_no_reader_reads_the_attempt_cap_constant_directly(module):
    assert cap_reads(module) is False, f"{module} still reads ATTEMPT_CAP"
