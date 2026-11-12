"""Helpers for the step loop's stop and refusal texts, on top of the step-loop driver.

Everything runs through `tests/acceptance/drivers/step_loop.py` (the command line,
the plan, the Agent tool's test double); this module adds only what a scenario about
recovering from a stop needs: the two surfaces a stop is told on, a hand-appended
iteration-ledger record made with the ledger's own command, a hand edit of `WIP.md`,
and putting the plan back as it stood when a request was issued.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from tests.acceptance.drivers.step_loop import LEDGER, Envelope, LoopTask, handoff_section

# What a stop owes its reader, each as patterns that must all appear (case-insensitive).
CLEARS_ONLY_BY_REVISING_THE_PLAN = (r"IMPLEMENTATION_PLAN\.md", r"\bonly\b", r"revis", r"record")
NEXT_ISSUES_THE_STEP_AFRESH = (
    r"\bnext\b",
    r"afresh|\bfresh\b|\banew\b|\bagain\b|new attempt|re-?issue",
    r"revis",
)
LEDGER_OR_WIP_EDITS_LEAVE_IT_STANDING = (
    r"ledger",
    r"WIP\.md",
    r"still stand|stands|leaves? the stop|does not clear|doesn't clear|won't clear|not clear|remains|stays",
)


def missing_patterns(text: str, patterns: tuple[str, ...]) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE) is None]


def stop_block(stopped: Envelope) -> str:
    """The stop block the command printed on stderr."""
    return stopped.stderr


def handoff_next_action(stopped: Envelope) -> str:
    """The next-action section of the HANDOFF.md the stop left behind."""
    if stopped.stop is None or not stopped.stop.get("handoff"):
        raise AssertionError(f"the stop names no handoff: {stopped.doc}")
    text = Path(stopped.stop["handoff"]).read_text(encoding="utf-8")
    return handoff_section(text, "§2 Next action")


def append_ledger_record(task: LoopTask, step_id: str, *, attempt: int) -> None:
    """A record appended by hand with the ledger's own command, claiming a completed return."""
    result = subprocess.run(
        [
            sys.executable,
            str(LEDGER),
            "append",
            task.slug,
            "--step",
            step_id,
            "--attempt",
            str(attempt),
            "--agent-id",
            "a-hand-appended",
            "--stop-reason",
            "completed",
            "--no-commit",
            "--base-ref",
            task.base,
            "--repo-root",
            str(task.root),
        ],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=120,
        env=task.env,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"the ledger refused the hand-appended record:\n{result.stdout}{result.stderr}"
        )


def mark_blocker_resolved_in_wip(task: LoopTask) -> None:
    """An orchestrator writes the resolution into WIP.md and nowhere else."""
    wip = task.wip_path.read_text(encoding="utf-8")
    edited = wip.replace("## Blockers\n\nNone\n", "## Blockers\n\nResolved: the blocker is gone.\n")
    if edited == wip:
        raise AssertionError(f"WIP.md has no Blockers section to edit:\n{wip}")
    task.wip_path.write_text(edited, encoding="utf-8")


def plan_text(task: LoopTask) -> str:
    return task.plan_path.read_text(encoding="utf-8")


def put_plan(task: LoopTask, text: str) -> None:
    task.plan_path.write_text(text, encoding="utf-8")
