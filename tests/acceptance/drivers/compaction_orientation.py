"""Driver for the post-compaction orientation, reached the way the harness reaches it.

The orientation is `hooks/inject_compaction_orientation.py`, registered on `SessionStart`
with matcher `compact`. A scenario runs it with `{"source": "compact"}` on stdin from the
project's root, and reads the `additionalContext` it prints.

Bound here, because the specification or the base commit fixes them:

- the hook prints nothing, or one `hookSpecificOutput.additionalContext` envelope, and
  exits 0; its registered timeout is the `compact` entry's in `hooks/hooks.json`;
- the driver's position is read by running the driver's read-only `status` from the
  plugin tree the hook runs from (`<plugin root>/scripts/step_loop.py`), so a copy of that
  tree whose driver is removed or replaced by a stand-in shows what an unreadable position
  does; the copy is exported as `CLAUDE_PLUGIN_ROOT` and nothing else on `PATH` names a
  driver;
- the orientation outside a step loop is frozen, byte for byte, in
  `tests/acceptance/fixtures/compaction_orientation_before.json`: what the hook printed at
  the base commit for each scenario `OUTSIDE_A_LOOP` builds;
- what the hook read and started is watched by `process_probe`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import process_probe

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_RELATIVE = Path("hooks") / "inject_compaction_orientation.py"
FROZEN = REPO_ROOT / "tests" / "acceptance" / "fixtures" / "compaction_orientation_before.json"
CAP_BYTES = 1024
WITHHELD_WORDS = ("spawn", "commit", "proceed to verification")
REFERENCE_INSTANT = 2_000_000_000.0  # mtimes are set from this, never from the wall clock


def registered_timeout() -> float:
    groups = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())["hooks"]["SessionStart"]
    (entry,) = [
        h
        for g in groups
        if g.get("matcher") == "compact"
        for h in g["hooks"]
        if str(HOOK_RELATIVE) in h["command"]
    ]
    return float(entry["timeout"])


@dataclass(frozen=True)
class Orientation:
    exit_code: int
    stdout: str
    seconds: float
    probe: process_probe.Probe

    @property
    def context(self) -> str:
        assert self.stdout.strip(), f"the hook printed no orientation (exit {self.exit_code})"
        return json.loads(self.stdout)["hookSpecificOutput"]["additionalContext"]


def orient(
    project: Path, *, plugin_root: Path = REPO_ROOT, home: Path | None = None
) -> Orientation:
    """Run the orientation after a compaction in `project`, from `plugin_root`."""
    workspace = project.parent
    probe = process_probe.install(workspace / "orientation-probe")
    probe.forget()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "PYTHON", "VIRTUAL_ENV", "GIT_"))
    }
    env.update(
        {
            "PATH": os.pathsep.join([str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
            "HOME": str(home or workspace / "home"),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "CLAUDE_PROJECT_DIR": str(project),
            **probe.env(),
        }
    )
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(plugin_root / HOOK_RELATIVE)],
            input=json.dumps({"source": "compact", "hook_event_name": "SessionStart"}),
            capture_output=True,
            text=True,
            cwd=project,
            env=env,
            timeout=registered_timeout() + 20,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError("the orientation ran past its registered timeout") from exc
    return Orientation(result.returncode, result.stdout, time.monotonic() - started, probe)


# -- A plugin tree whose driver cannot be read ---------------------------------------------

DRIVER_STAND_INS: dict[str, str | None] = {
    "absent": None,
    "fails": "import sys\nsys.exit(1)\n",
    "prints output that cannot be parsed": "print('step-loop status: <<garbled>> {{{')\n",
    "runs past its time bound": "import time\ntime.sleep(120)\n",
}


def plugin_copy_with_driver(workspace: Path, stand_in: str) -> Path:
    """A copy of the plugin's hooks and scripts whose `scripts/step_loop.py` is `stand_in`."""
    root = workspace / f"plugin-{stand_in.replace(' ', '-')}"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "project_metrics", "gate_probes")
    for tree in ("hooks", "scripts"):
        shutil.copytree(REPO_ROOT / tree, root / tree, ignore=ignore)
    driver = root / "scripts" / "step_loop.py"
    text = DRIVER_STAND_INS[stand_in]
    if text is None:
        driver.unlink()
    else:
        driver.write_text(text, encoding="utf-8")
    return root


# -- Pipelines outside a step loop, as the frozen orientations were taken ----------------------


def _write(path: Path, text: str, *, age: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    stamp = REFERENCE_INSTANT - age
    os.utime(path, (stamp, stamp))


PLAIN_WIP = (
    "# WIP: plain feature\n\n## Current Step\n\nStep 2 of 3: Wire up the retry queue\n\n"
    "## Status\n\n[IN-PROGRESS] - Step underway\n\n## Progress\n\n"
    "- [x] Step 1: Registry entry\n- [ ] Step 2: Wire up the retry queue\n"  # id-citation-discipline:ignore
    "- [ ] Step 3: Document the queue\n\n## Next Action\n\nFinish the retry queue tests.\n"  # id-citation-discipline:ignore
)


def _plain_task(ai_work: Path, slug: str, *, age: int) -> None:
    _write(ai_work / slug / "IMPLEMENTATION_PLAN.md", "# Plan: plain feature\n", age=age + 5)
    _write(ai_work / slug / "HANDOFF.md", "# HANDOFF: plain\n\nreadiness: ready\n", age=age + 5)
    _write(ai_work / slug / "WIP.md", PLAIN_WIP, age=age)


def a_pipeline_outside_a_loop(project: Path) -> None:
    _plain_task(project / ".ai-work", "plain-feature", age=10)


def a_newest_pipeline_outside_an_older_loop(project: Path) -> None:
    ai_work = project / ".ai-work"
    _plain_task(ai_work, "plain-feature", age=10)
    driven = ai_work / "driven-feature"
    _write(driven / "IMPLEMENTATION_PLAN.md", "# Plan: driven feature\n", age=600)
    _write(
        driven / "WIP.md",
        "# WIP: driven feature\n\n## Current Step\n\nStep 1 of 1: Driven step\n\n## Progress\n\n"
        "- [ ] Step 1: Driven step\n  - Attempts: Step 1 count=1 request=s1-a1-implement\n",  # id-citation-discipline:ignore
        age=500,
    )
    _write(driven / "ITERATION_LEDGER.jsonl", "", age=500)


def no_task_with_a_step_record(project: Path) -> None:
    _write(project / ".ai-work" / "spec-only" / "SYSTEMS_PLAN.md", "# Systems Plan\n", age=10)


OUTSIDE_A_LOOP: dict[str, Callable[[Path], None]] = {
    "a pipeline outside a step loop": a_pipeline_outside_a_loop,
    "the newest pipeline outside a loop, an older one under the driver": (
        a_newest_pipeline_outside_an_older_loop
    ),
    "no task with a step record": no_task_with_a_step_record,
}


def frozen_orientation(scenario: str) -> str:
    """What the hook printed at the base commit for `scenario`, byte for byte."""
    return json.loads(FROZEN.read_text(encoding="utf-8"))[scenario]
