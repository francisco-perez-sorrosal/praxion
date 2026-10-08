"""Driver for the spawn tally of a pipeline whose implementer steps the loop drives.

A scenario runs the loop (the step-loop command and the Agent tool's double from the
`step_loop` driver), then lets the observation hooks see the spawns the orchestrator
made, exactly as the harness delivers them, and finally runs `spawn_count.py --json`
through the `spawn_tally` driver. The ledger the counter reads is the task's own
`ITERATION_LEDGER.jsonl`, written by the loop's `record` or, for a ledger whose records
carry no request id, by the ledger's own `append` command. Nothing here writes the ledger
or the observation log by hand.

Bound to the existing surfaces. One assumption about the report, stated where it is read:
the counter's JSON report names the agents the loop requested and the ledger recorded
under an `iterations` key, as a list of agent ids or of objects that carry `agent_id`
(the shape `agents` already has), or under `{"agents": [...]}`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.acceptance.drivers.observation_harness import HookHarness, Session
from tests.acceptance.drivers.spawn_tally import Tally, spawn_count
from tests.acceptance.drivers.step_loop import LEDGER, LoopTask

SESSION_ID = "5e551011-0000-4000-8000-0000005ea701"
PLANNER = "praxion:implementation-planner"
IMPLEMENTER = "praxion:implementer"


def observe_spawns(task: LoopTask, workspace: Path, spawns: list[tuple[str, str]]) -> None:
    """The orchestrator's Agent calls, each (agent id, agent type), stating the task's slug.

    The checkout starts recording only now, so the loop's own commands ran on a tree
    the observation log never touched.
    """
    (task.root / ".ai-state").mkdir(exist_ok=True)
    session = Session(HookHarness(workspace / "harness"), SESSION_ID, task.root)
    for agent_id, agent_type in spawns:
        session.spawn_foreground(f"Task slug: {task.slug}\n\nDo your part.", agent_id, agent_type)


def append_legacy_record(task: LoopTask, step: str, agent_id: str) -> None:
    """A ledger record written without the loop: no request id, through `append`."""
    result = subprocess.run(
        [
            sys.executable,
            str(LEDGER),
            "append",
            task.slug,
            "--repo-root",
            str(task.root),
            "--step",
            step,
            "--attempt",
            "1",
            "--agent-id",
            agent_id,
            "--stop-reason",
            "completed",
            "--no-commit",
            "--base-ref",
            task.base,
        ],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=60,
        env=task.env,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"the ledger's append command refused a record (exit {result.returncode}):\n"
            f"{result.stdout}{result.stderr}"
        )


def tally(task: LoopTask, workspace: Path, budget: int) -> Tally:
    return spawn_count(task.root, task.slug, scratch=workspace / "tally", budget=budget)


def iteration_agents(found: Tally) -> set[str]:
    """The agents the report lists among its iterations; none when it lists no iterations."""
    assert found.report is not None, f"no report: {found.describe()}"
    listed: Any = found.report.get("iterations") or []
    if isinstance(listed, dict):
        listed = listed.get("agents") or []
    if isinstance(listed, int):
        raise AssertionError(
            "the report counts iterations but does not name the agents it counts among "
            f"them: {found.describe()}"
        )
    return {item["agent_id"] if isinstance(item, dict) else str(item) for item in listed}
