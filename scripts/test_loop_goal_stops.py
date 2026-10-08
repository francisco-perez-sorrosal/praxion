"""Tests that a stalled goal step stops as `stalled` and every reader of the bound agrees.

A goal step is spent exactly when its last two iterations kept no commit. The driver's state,
its decision, the status table and object, `record`'s replay path (which publishes the stall on
the `Attempts:` line) and the reconciler must give one answer on that, at any count of
iterations; an ordinary step keeps its two attempts and its `attempts-exhausted` stop.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _step_loop_cli as cli  # noqa: E402
import reconcile_pipeline_state as rps  # noqa: E402
from _loop_fields import parse_attempts  # noqa: E402
from _plan_steps import parse_plan_steps  # noqa: E402
from _step_loop_action import (  # noqa: E402
    BUDGET_CAUSE,
    HUMAN_CAUSES,
    Spawn,
    Stop,
    issuable_action,
    next_action,
)
from _step_loop_record import record_return  # noqa: E402
from _step_loop_render import _ACTIONS, RequestKey, stop_next_action, stop_stderr  # noqa: E402
from _step_loop_state import Exhausted, Failed, LoopInputs, series_states, step_series  # noqa: E402
from iteration_ledger import IterationRecord  # noqa: E402

STEP = "Step "
STEP_ID = "1"
OTHER_ID = "2"
LABEL = f"{STEP}{STEP_ID}"
SLUG = "goal-stops"
BUDGET = 5
STALL = "stalled"
EXHAUSTED = "attempts-exhausted"
KEPT = "c" * 40
GATE = "Result: pass=0 fail=1 skip=0 pending=0 by=step-loop"
CHECK = "**Check**: `python3 -m pytest -q` expects pass>=1 fail=0"
BLOCK = f"## Steps\n\n### {LABEL}: Drive the goal\n\n**Assignee**: implementer\n"
FILES = "**Files**: `src/a.py`\n"
ORDINARY_PLAN = f"# Plan\n\n{BLOCK}{FILES}{CHECK}\n"
GOAL_PLAN = f"{ORDINARY_PLAN}**Iterations**: {BUDGET}\n"
TWO_ITERATIONS_PLAN = f"{ORDINARY_PLAN}**Iterations**: 2\n"
MIXED_PLAN = (
    f"# Plan\n\n{BLOCK}{FILES}{CHECK}\n**Iterations**: 3\n\n"
    f"### {STEP}{OTHER_ID}: Ordinary work\n\n**Assignee**: implementer\n"
    f"**Files**: `src/b.py`\n{CHECK}\n"
)
WIP_HEAD = f"# WIP\n\n## Progress\n\n- [ ] {LABEL}: Drive the goal\n"
WIP_TAIL = "\n## Progress record\n\n- nothing kept yet\n"
UNKEPT_TWICE = (None, None)
TWO_KEPT_THEN_UNKEPT = (KEPT, KEPT, None)
ALTERNATING = (None, KEPT, None)
HANDOFF = Path("HANDOFF.md")


def the_step(plan, index=0):
    return parse_plan_steps(plan)[index]


def records(plan, commits, stop_reason="completed"):
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
            stop_reason=stop_reason,
            request=RequestKey(STEP_ID, attempt, "implement", 1).id,
            step_digest=step.digest,
        )
        for attempt, commit in enumerate(commits, start=1)
    )


def inputs(plan, commits, verdict=None, stop_reason="completed"):
    rows = () if verdict is None else ({"step": LABEL, **verdict},)
    steps = parse_plan_steps(plan)
    return LoopInputs.read(steps, {}, records(plan, commits, stop_reason), rows)


@dataclass(frozen=True)
class Task:
    """What `record` reads of a task on disk."""

    slug: str
    repo: Path
    work: Path
    dir: Path
    base_ref: str
    inputs: LoopInputs


def written_task(tmp_path, plan, commits):
    """The task directory after the ended attempts, `WIP.md` counting them as `record` leaves it."""
    loop = inputs(plan, commits)
    work = tmp_path / ".ai-work"
    task_dir = work / SLUG
    task_dir.mkdir(parents=True)
    line = f"  - Attempts: {LABEL} count={len(commits)} request={loop.records[-1].request}\n"
    (task_dir / "WIP.md").write_text(f"{WIP_HEAD}{line}{WIP_TAIL}", encoding="utf-8")
    (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    (task_dir / "TEST_RESULTS.md").write_text("", encoding="utf-8")
    return Task(SLUG, tmp_path, work, task_dir, "HEAD", loop)


@dataclass(frozen=True)
class Readings:
    """What each of the five readers says of one series of recorded iterations."""

    state: Any
    action: Any
    replayed: bool
    replan: str | None
    verdict: str
    status: dict[str, Any]
    table: str


def status_of(loop):
    action = issuable_action(loop)
    stop = cli.stop_object(SLUG, action, "x", HANDOFF) if isinstance(action, Stop) else None
    return cli.status_object(SLUG, loop, series_states(loop), action, stop), action


def read_everywhere(tmp_path, plan, commits):
    task = written_task(tmp_path, plan, commits)
    last = task.inputs.records[-1].request
    taken = record_return(task, last, "agent", "complete")
    attempt = parse_attempts((task.dir / "WIP.md").read_text("utf-8"), frozenset({last}))
    (reconciled,) = rps.reconcile(
        SLUG,
        tmp_path,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        assume_recorded=frozenset({last}),
    )
    loop = inputs(plan, commits, {"verdict": reconciled["verdict"]})
    status, action = status_of(loop)
    table = cli.status_table(status, cli.next_line(SLUG, action, "x"), loop.steps)
    return Readings(
        step_series(the_step(plan), task.inputs),
        next_action(task.inputs),
        taken.recorded["replayed"],
        attempt.counts[LABEL].replan,
        reconciled["verdict"],
        status,
        table,
    )


# --- Two unkept iterations in a row: one stall, read by every reader ---------------------------


def test_two_unkept_iterations_read_as_one_stall_through_all_five_readers(tmp_path):
    seen = read_everywhere(tmp_path, GOAL_PLAN, UNKEPT_TWICE)

    spent = {
        "state": isinstance(seen.state, Exhausted),
        "next": isinstance(seen.action, Stop) and seen.action.cause == STALL,
        "status object": seen.status["stop"]["cause"] == STALL,
        "status table": f"next: stopped ({STALL}):" in seen.table,
        "record's replay": seen.replayed and seen.replan is not None,
        "reconciler": seen.verdict == EXHAUSTED,
    }
    assert spent == dict.fromkeys(spent, True)


def test_the_stall_stop_names_the_step_and_lists_those_two_iterations(tmp_path):
    seen = read_everywhere(tmp_path, GOAL_PLAN, UNKEPT_TWICE)

    stop = seen.action
    assert (stop.step, [a.agent_id for a in stop.attempts]) == (STEP_ID, ["agent-1", "agent-2"])
    assert stop.replan_request is not None


def test_a_stall_lists_only_its_last_two_iterations_after_earlier_progress():
    stop = next_action(inputs(GOAL_PLAN, (KEPT, None, None)))

    assert isinstance(stop, Stop)
    assert (stop.cause, [a.attempt for a in stop.attempts]) == (STALL, [2, 3])


def test_status_shows_the_stall_as_the_next_action_in_its_table_and_its_object(tmp_path):
    seen = read_everywhere(tmp_path, GOAL_PLAN, UNKEPT_TWICE)

    assert seen.status["outcome"] == "needs-human"
    assert seen.status["stop"]["cause"] == STALL
    assert seen.table.splitlines()[-1].startswith(f"next: stopped ({STALL}): ")


@pytest.mark.parametrize(
    "commits",
    [
        pytest.param(TWO_KEPT_THEN_UNKEPT, id="two-kept-then-one-unkept"),
        pytest.param(ALTERNATING, id="alternating-kept-and-unkept"),
    ],
)
def test_a_progressing_iteration_resets_the_count_so_no_reader_reads_spent(tmp_path, commits):
    seen = read_everywhere(tmp_path, GOAL_PLAN, commits)

    spent = {
        "state": isinstance(seen.state, Exhausted),
        "next": not isinstance(seen.action, Spawn),
        "status object": seen.status["stop"] is not None,
        "record's replay": seen.replan is not None,
        "reconciler": seen.verdict == EXHAUSTED,
    }
    assert spent == dict.fromkeys(spent, False)
    assert isinstance(seen.state, Failed)


# --- The stall, the budget and the markers ----------------------------------------------------


def test_a_stall_is_reported_ahead_of_a_spent_budget():
    stop = next_action(inputs(TWO_ITERATIONS_PLAN, UNKEPT_TWICE))

    assert isinstance(stop, Stop)
    assert (stop.cause, stop.step) == (STALL, STEP_ID)


@pytest.mark.parametrize(
    ("commits", "expected"),
    [
        pytest.param((None, KEPT), "spawn", id="under-the-step's-own-iterations"),
        pytest.param(ALTERNATING, BUDGET_CAUSE, id="the-step's-iterations-spent-unstalled"),
    ],
)
def test_no_goal_request_goes_past_its_iterations_even_in_a_mixed_plan(commits, expected):
    action = next_action(inputs(MIXED_PLAN, commits))

    assert getattr(action, "cause", "spawn") == expected


def test_the_spent_goal_budget_stop_belongs_to_no_step_and_names_the_count():
    stop = next_action(inputs(MIXED_PLAN, ALTERNATING))

    assert isinstance(stop, Stop)
    assert (stop.step, stop.evidence) == (None, f"3 of 3 iterations used at {LABEL}")


@pytest.mark.parametrize("marker", ["blocked", "conflict"])
def test_a_blocked_or_conflict_return_stops_a_goal_step_for_a_human_at_once(marker):
    stop = next_action(inputs(GOAL_PLAN, (None,), stop_reason=marker))

    assert isinstance(stop, Stop)
    assert (stop.cause, stop.step) == (f"{marker}-marker", STEP_ID)


# --- An ordinary step keeps its two attempts --------------------------------------------------


def test_an_ordinary_steps_two_failed_attempts_still_stop_as_attempts_exhausted(tmp_path):
    seen = read_everywhere(tmp_path, ORDINARY_PLAN, UNKEPT_TWICE)

    stop = seen.action
    assert isinstance(stop, Stop)
    assert stop.cause == EXHAUSTED
    assert stop.evidence == f"2 of 2 fresh attempts at {LABEL} ended unverified"
    assert len(stop.attempts) == len(UNKEPT_TWICE)
    assert (seen.verdict, seen.replan is not None) == (EXHAUSTED, True)


# --- The closed set of causes and the stop's invariants ----------------------------------------


def test_stalled_joins_the_human_causes_and_the_stop_texts_cover_every_cause():
    assert STALL in HUMAN_CAUSES
    assert set(HUMAN_CAUSES) | {BUDGET_CAUSE} == set(_ACTIONS)
    assert len(HUMAN_CAUSES) == len(set(HUMAN_CAUSES))


def test_the_stderr_block_and_the_handoff_paragraph_say_what_to_do_about_a_stall():
    stop = next_action(inputs(GOAL_PLAN, UNKEPT_TWICE))
    view = cli.stop_view(stop, SLUG, "step_loop.py")

    block, paragraph = stop_stderr(view), stop_next_action(view)

    assert f"({STALL})" in block
    assert _ACTIONS[STALL] in block
    assert _ACTIONS[STALL] in paragraph
    assert f"stopped at `{LABEL}`: {STALL} (exit 2)" in paragraph


@pytest.mark.parametrize("cause", [STALL, EXHAUSTED])
def test_a_spent_bounds_stop_carries_its_replan_request(cause):
    stop = Stop(cause, STEP_ID, "evidence", (), "replan text")

    assert (stop.cause, stop.replan_request) == (cause, "replan text")


@pytest.mark.parametrize(
    ("cause", "replan"),
    [
        pytest.param(STALL, None, id="a-stall-without-a-replan"),
        pytest.param(EXHAUSTED, None, id="exhausted-without-a-replan"),
        pytest.param("human-verdict", "text", id="another-cause-with-a-replan"),
    ],
)
def test_a_replan_request_goes_with_a_spent_bound_and_nothing_else(cause, replan):
    with pytest.raises(ValueError, match="replan request"):
        Stop(cause, STEP_ID, "evidence", (), replan)
