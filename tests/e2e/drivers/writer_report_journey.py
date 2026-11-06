"""A writer role's paired run, from its dry-run plan to the report of its recorded results.

The journey crosses three boundaries: the console entry's dry run, which plans the role's tasks
and names each one's mode; the results file a paired run of that plan leaves; and the console
entry's `--report`, which renders that file. No session is started: the results file is written
here in the runner's own format, its sessions carrying the planned task ids and templates, every
check passed in both arms, and one task's lean session errored so that the first mode's count of
complete pairs is one short of its planned tasks.

Bound here, because the specification or the base commit fixes them: the dry run and its plan
(`writer_kits.plan`), the results file's shape (the pins of `adherence_eval`), and `--report
<file>`, which renders a results file and launches nothing.

Bound to the designed surface (a Boundary Assumption of `ACCEPTANCE_TESTS.md`): the report reads
each recorded session's mode from its task, as the session's setup records the task id and the
template id of the plan it was drawn from; nothing else in the results file names a mode.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import adherence_eval
from tests.acceptance.drivers import writer_kits as kits
from tests.acceptance.drivers.adherence_eval import (
    ARMS,
    FAKE_CLAUDE_VERSION,
    REPORT_CHECKOUT_COMMIT,
    REPORT_DECLARED_AT,
    REPORT_STARTED_AT,
    SEED,
    FlipSettings,
    check_catalog,
)
from tests.acceptance.drivers.writer_kits import COVERED_MODES, TaskId


@dataclass(frozen=True)
class RecordedRun:
    report: str
    complete_pairs: Mapping[str, int]  # by covered mode


def report_of_a_recorded_run(workspace: Path, role: str) -> RecordedRun:
    """Plan `role`, record a run of the whole plan, and render its report."""
    plan = kits.plan(workspace / "plan", role, arms=("full",))
    first, *_ = COVERED_MODES[role]
    assert plan.tasks_in(first), f"the {role}'s plan names no {first} task"
    short_task = plan.tasks_in(first)[0]
    sessions = [
        _session(role, task, arm, errored=(task == short_task and arm == "lean"))
        for task in plan.task_ids()
        for arm in ARMS
    ]
    complete = {
        mode: len(plan.tasks_in(mode)) - (1 if mode == first else 0) for mode in COVERED_MODES[role]
    }
    path = workspace / "results" / "writer-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_document(role, sessions)), encoding="utf-8")
    return RecordedRun(_render(path), complete)


def _session(role: str, task_id: str, arm: str, *, errored: bool) -> dict:
    outcomes = {c.name: "passed" for c in check_catalog(role)}
    return {
        "setup": {
            "arm": arm,
            "checkout_commit": REPORT_CHECKOUT_COMMIT,
            "role": role,
            "task_id": task_id,
            "template_id": TaskId.parse(task_id).template,
            "seed": SEED,
        },
        "status": adherence_eval._side_json(outcomes, errored, 30_000),
        "cost_usd": 0.4,
        "duration_ms": 60_000,
        "started_at": REPORT_STARTED_AT,
    }


def _document(role: str, sessions: list[dict]) -> dict:
    return {
        "schema_version": "adherence/1",
        "run": {
            "id": "writer-journey-run",
            "model": "claude-opus-5-5",
            "claude_code_version": FAKE_CLAUDE_VERSION,
            "complete": True,
            "refused_launches": [],
            "earlier_runs": {role: []},
        },
        "settings": {
            **adherence_eval._settings_json(FlipSettings()),
            "declared_at": REPORT_DECLARED_AT,
        },
        "arms": {role: {arm: {"built": True} for arm in ARMS}},
        "catalog": {
            role: [
                {
                    "name": c.name,
                    "kind": c.kind,
                    "rule": {"file": c.rule_file, "section": c.rule_section},
                    "common": c.common,
                    "golden_bad_case": c.golden_bad_case,
                }
                for c in check_catalog(role)
            ]
        },
        "sessions": sessions,
        "verdicts": {},
        "golden_bad_case_verdicts": None,
    }


def _render(path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="writer-report-tripwire-") as scratch:
        tripwire = adherence_eval.install_tripwire(Path(scratch))
        env = adherence_eval.eval_env(
            {
                "PATH": adherence_eval._guarded_path(tripwire.bin_dir),
                "ANTHROPIC_API_KEY": adherence_eval.DUMMY_CREDENTIAL,
            }
        )
        done = subprocess.run(
            [adherence_eval._uv(), "run", "--quiet", "--python", adherence_eval.EVAL_PYTHON]
            + ["--project", str(adherence_eval.EVAL_PROJECT)]
            + [adherence_eval.adherence_console_entry().name, "--report", str(path)],
            capture_output=True,
            text=True,
            env=env,
            cwd=adherence_eval.EVAL_PROJECT,
            timeout=300,
        )
        assert not tripwire.starts(), "rendering a report started claude"
    assert done.returncode == 0, f"--report failed: {(done.stdout + done.stderr)[-2000:]}"
    return done.stdout
