"""Driver for task directories the base commit's step-loop driver wrote, read back by today's.

The fixture `tests/acceptance/fixtures/per_step_gate/` freezes, as tarballs, checkouts whose
task directory the base commit's driver wrote over a step whose change widened a pocket
(so its block carries a `Scope: ... widened` line and no `Deferred:` line), and what that
driver printed for `status --json` and a repeated `next` over them, with every spelling of
the scratch workspace replaced by a placeholder when it was recorded. This driver restores a
case under a fresh workspace and runs today's `step_loop.py` over it the same way.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from tests.acceptance.drivers.step_loop import (
    CONFIG_DIR_VARIABLE,
    END_WAIT_VARIABLE,
    STEP_LOOP,
    _clean_env,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "per_step_gate"
FROZEN = json.loads((FIXTURES / "read_by_the_base_driver.json").read_text(encoding="utf-8"))
CASES = sorted(FROZEN["cases"])
PLACEHOLDER = FROZEN["root_placeholder"]


def restore(workspace: Path, case: str) -> Path:
    """The case's checkout, unpacked under `workspace`; returns its root."""
    with tarfile.open(FIXTURES / f"{case}.tar.gz") as tar:
        tar.extractall(workspace, filter="data")
    return workspace / "project"


def _spellings(workspace: Path) -> list[str]:
    """Every spelling of the workspace a reading may hold, longest first (macOS prefixes
    `/private` to the temporary root once it is resolved)."""
    found: set[str] = set()
    for path in (str(workspace), str(workspace.resolve())):
        bare = path.removeprefix("/private")
        found.update({path, bare, "/private" + bare})
    return sorted(found, key=len, reverse=True)


def _normalized(value: Any, workspace: Path) -> Any:
    text = json.dumps(value, sort_keys=True)
    for spelling in _spellings(workspace):
        text = text.replace(spelling, PLACEHOLDER)
    return json.loads(text)


def read_back(workspace: Path, case: str) -> tuple[Any, Any]:
    """Today's `status --json` and `next` over the restored case, normalized as recorded."""
    root = workspace / "project"
    env = {
        **_clean_env(),
        CONFIG_DIR_VARIABLE: str(workspace / "home" / ".claude"),
        END_WAIT_VARIABLE: "0",
    }
    location = ["--repo-root", str(root), "--base-ref", FROZEN["cases"][case]["scratch_base"]]

    def run(*args: str) -> Any:
        done = subprocess.run(
            [sys.executable, str(STEP_LOOP), *args, FROZEN["slug"], *location],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"`step_loop.py {args[0]}` printed no JSON (exit {done.returncode}):\n"
                f"{done.stdout}{done.stderr}"
            ) from exc

    return _normalized(run("status", "--json"), workspace), _normalized(run("next"), workspace)


def frozen(case: str, reading: str) -> Any:
    return FROZEN["cases"][case][reading]


def task_records(workspace: Path) -> dict[str, bytes]:
    """Every file of the restored task directory, with its bytes."""
    task = workspace / "project" / ".ai-work" / FROZEN["slug"]
    return {
        str(p.relative_to(task)): p.read_bytes() for p in sorted(task.rglob("*")) if p.is_file()
    }
