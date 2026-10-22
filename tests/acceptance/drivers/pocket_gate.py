"""Driver for the step-loop gate over more than one pocket, and for reading the loop's state.

Builds on the step-loop driver (`step_loop`): a scenario adds a second pocket to the
checkout (a directory with its own pytest configuration, as the resolver finds pockets),
lets the spawned agent change files in it, and reads back what the gate wrote, what the
next prompt carries and what `status` reports.

Bound here, because the specification or the base commit fixes them:

- a gate's block in `TEST_RESULTS.md` opens on a `## Step <id>` heading that names the
  request it gated and runs to the next level-2 heading;
- the shape checker is `scripts/check_test_results_shape.py FILE`, exit 0 clean;
- the next attempt's prompt is the file the spawn request's `prompt_path` names;
- the step `next` acts on is its spawn request's step, or its stop's step;
- `status --json` lists each step under `steps` with its `verdict`.

Not yet bound (each raises until a binding step binds it to the designed interface):

- how a scenario sets the time bound the gate allows one pocket's run;
- where `status --json` reports the attempt cap of each step.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import step_loop
from tests.acceptance.drivers.step_loop import Envelope, LoopTask, step_id_of

REPO_ROOT = Path(__file__).resolve().parents[3]
SHAPE_CHECKER = REPO_ROOT / "scripts" / "check_test_results_shape.py"
GREEN_SECTION_CEILING_BYTES = 1024


def pocket_config(name: str) -> str:
    """A pocket's own runner configuration: a project with pytest settings of its own."""
    return (
        f'[project]\nname = "{name}"\nversion = "0.0.0"\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )


# -- The gate's time bound for one pocket (not yet bound) ---------------------------------


class PocketBoundNotBoundError(NotImplementedError):
    pass


def bound_pocket_run(task: LoopTask, pocket_root: str, seconds: int) -> None:
    """Make the gate allow the run of the pocket rooted at `pocket_root` at most `seconds`."""
    raise PocketBoundNotBoundError(
        "a scenario cannot yet set the time bound the gate allows one pocket's run: "
        f"wanted {seconds} s for the pocket at {pocket_root!r} of {task.root}"
    )


# -- What the gate wrote ------------------------------------------------------------------


def gate_block(task: LoopTask, request_id: str) -> str:
    """The block of TEST_RESULTS.md whose heading names `request_id`."""
    text = (task.task_dir / "TEST_RESULTS.md").read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^(?=## )", text)
    named = [b for b in blocks if b.startswith("## ") and request_id in b.splitlines()[0]]
    assert len(named) == 1, f"expected one block for {request_id}, found {len(named)}:\n{text}"
    return named[0]


def shape_check(workspace: Path, block: str) -> subprocess.CompletedProcess[str]:
    """Run the result-file shape checker over a file holding only `block`."""
    target = workspace / "BLOCK_UNDER_CHECK.md"
    target.write_text(block, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SHAPE_CHECKER), str(target)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def prompt_of(envelope: Envelope) -> str:
    assert envelope.request is not None, envelope.doc
    return Path(envelope.request["prompt_path"]).read_text(encoding="utf-8")


# -- The loop's state, as next and status give it ------------------------------------------


def step_next_acts_on(envelope: Envelope) -> str | None:
    """The step `next` spawns or stops on; None when the plan is complete or nothing is named."""
    if envelope.request is not None:
        return step_id_of(envelope.request["step"])
    if envelope.stop is not None and envelope.stop.get("step") is not None:
        return step_id_of(envelope.stop["step"])
    return None


def status_verdicts(task: LoopTask) -> dict[str, str]:
    state = step_loop.status(task, as_json=True).json()
    return {step_id_of(s["step"]): str(s["verdict"]) for s in state["steps"]}


def disagreement(task: LoopTask) -> str | None:
    """Why status and next disagree on a step's state, or None when they agree."""
    asked = step_loop.next_action(task)
    verdicts = status_verdicts(task)
    acted_on = step_next_acts_on(asked)
    if acted_on is not None and verdicts.get(acted_on) == "verified-complete":
        return f"status reports step {acted_on} verified while next acts on it: {asked.doc}"
    if asked.outcome == "complete" and any(v != "verified-complete" for v in verdicts.values()):
        return f"next reports the plan complete while status reports {verdicts}"
    return None


def status_attempt_cap(task: LoopTask, step_id: str) -> int:
    """The attempt cap `status --json` reports for one step."""
    state = step_loop.status(task, as_json=True).json()
    (entry,) = [s for s in state["steps"] if step_id_of(s["step"]) == step_id]
    if "attempt_cap" not in entry:
        raise NotImplementedError(
            "status in its JSON form does not yet report the attempt cap each step's "
            f"attempts are counted against: {entry}"
        )
    return int(entry["attempt_cap"])


# -- A record call cut off and run again ----------------------------------------------------


def start_record(task: LoopTask, request_id: str, agent_id: str) -> subprocess.Popen[str]:
    """`record` started in a session of its own, so the whole call can be cut off."""
    return subprocess.Popen(
        [
            sys.executable,
            str(step_loop.STEP_LOOP),
            "record",
            task.slug,
            "--request",
            request_id,
            "--agent-id",
            agent_id,
            "--marker",
            "complete",
            "--repo-root",
            str(task.root),
            "--base-ref",
            task.base,
        ],
        cwd=task.root,
        env=task.env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def wait_for_lines(path: Path, count: int, *, deadline_seconds: float) -> list[str]:
    """Wait, within a deadline, until `path` holds at least `count` lines."""
    stop_at = time.monotonic() + deadline_seconds
    while time.monotonic() < stop_at:
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if len(lines) >= count:
                return lines
        time.sleep(0.2)
    seen = path.read_text(encoding="utf-8") if path.exists() else "(no file)"
    raise AssertionError(f"{path} did not reach {count} lines in {deadline_seconds} s: {seen}")


def cut_off(process: subprocess.Popen[str]) -> None:
    """Cut the call off as a caller's ceiling does: its whole process group, at once."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=30)


def meeting_test(own: str, other: str, log: Path, release: Path) -> str:
    """A test that logs its pocket's run, and waits for `release` when the other pocket ran first.

    Whichever pocket's run comes second in one gate blocks, so a call cut off then has
    finished exactly one pocket run: the first line of `log`.
    """
    return (
        "import time\nfrom pathlib import Path\n\n"
        f"LOG = Path({str(log)!r})\nRELEASE = Path({str(release)!r})\n\n\n"
        "def test_meets_the_other_pocket():\n"
        "    earlier = LOG.read_text().splitlines() if LOG.exists() else []\n"
        f"    with LOG.open('a') as out:\n        out.write({own!r} + '\\n')\n"
        f"    if {other!r} in earlier[-1:]:\n"
        "        stop_at = time.monotonic() + 300\n"
        "        while not RELEASE.exists() and time.monotonic() < stop_at:\n"
        "            time.sleep(0.2)\n"
        "    assert True\n"
    )


def ledger_commits(task: LoopTask) -> list[Any]:
    records, _ = step_loop.ledger_records(task)
    return [r.get("commit") for r in records]


def as_json(value: Any) -> str:
    return json.dumps(value, indent=1)
