"""Driver for the reconciler's raw output streams, reached only through its command line.

The step-completion driver (`step_checks.py`) builds the checkout and parses verdicts;
this driver adds the one input it has no hook for -- an `Attempts:` line that names no
step -- and returns the reconciler's stdout, stderr and exit code untouched, in either
output mode, so a scenario can judge what each stream carries.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.step_checks import (
    RECONCILER,
    PipelineTask,
    StepSetup,
    build_task,
)

UNNAMED_ATTEMPTS_LINE = "  - Attempts: count=1"


def task_with_unnamed_attempts_line(workspace: Path) -> PipelineTask:
    """A checkout whose WIP.md carries, under its one step, an `Attempts:` line naming no step."""
    step = StepSetup(number="1", title="Write the widget")
    task = build_task(workspace, step)
    wip = task.root / ".ai-work" / task.slug / "WIP.md"
    text = wip.read_text(encoding="utf-8")
    entry = f"- [x] Step {step.number}: {step.title}"
    wip.write_text(text.replace(entry, f"{entry}\n{UNNAMED_ATTEMPTS_LINE}"), encoding="utf-8")
    return task


def task_without_unnamed_attempts_line(workspace: Path) -> PipelineTask:
    """The same checkout with every `Attempts:` line naming its step (here: none at all)."""
    return build_task(workspace, StepSetup(number="1", title="Write the widget"))


@dataclass(frozen=True)
class RawRun:
    exit_code: int
    stdout: str
    stderr: str


def run_reconciler(task: PipelineTask, *, machine: bool) -> RawRun:
    """Run the reconciler on the task; `machine` asks for `--json`."""
    flags = ["--json"] if machine else []
    result = subprocess.run(
        [
            sys.executable,
            str(RECONCILER),
            task.slug,
            "--repo-root",
            str(task.root),
            "--base-ref",
            task.base,
            *flags,
        ],
        cwd=task.root,
        capture_output=True,
        text=True,
        timeout=120,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )
    return RawRun(result.returncode, result.stdout, result.stderr)
