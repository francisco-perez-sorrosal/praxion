"""Driver for whole runs whose sessions meet a refused shell command or a failed confinement.

Every session is the stand-in of `adherence_runs`; a scenario scripts the refusing session
with `refused_command`, `sandbox_refused` or `confinement_unavailable_at_startup`.

Bound here, because the specification or the base commit fixes them: a results file's
`sessions`, each with its `setup` (`arm`, `task_id`) and its `status` (`kind`, which reads
`errored` for an infrastructure error and `measured` for a graded session), and the run's
stop on infrastructure (`adherence_runs.stop_reason`, the `infra_stopped` ending). A
session's record names a command when the command's text appears anywhere in it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers.adherence_runs import Plan, Script

MAX_TASKS = 3


@dataclass(frozen=True)
class SessionRecord:
    arm: str
    task_id: str
    status_kind: str
    raw: dict[str, Any]

    def names(self, text: str) -> bool:
        return text in json.dumps(self.raw)


def session_records(results_path: Path) -> list[SessionRecord]:
    assert results_path.is_file(), f"the run wrote no results file at {results_path}"
    document = json.loads(results_path.read_text(encoding="utf-8"))
    return [
        SessionRecord(s["setup"]["arm"], s["setup"]["task_id"], s["status"]["kind"], s)
        for s in document["sessions"]
    ]


def run(workspace: Path, role: str, script: Script) -> runs.StandInRun:
    checkout = runs.new_checkout(workspace)
    return runs.run_with_stand_in(workspace, checkout, Plan(role=role, max_tasks=MAX_TASKS), script)


def first_session_of_each_arm(ending: runs.Ending) -> Script:
    """`ending` for the first planned task in both arms, so the run's first session meets it."""
    return Script(by_task={(0, arm): ending for arm in ("full", "lean")})


def third_task_of_each_arm(ending: runs.Ending) -> Script:
    """`ending` for the third planned task in both arms; the first two tasks run as usual."""
    return Script(by_task={(2, arm): ending for arm in ("full", "lean")})
