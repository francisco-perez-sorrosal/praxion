"""Driver for a detached gate run that nobody comes back for.

Builds on `step_loop` and `pocket_gate`: a scenario plants a slow pocket whose tests hang
past the pocket's bound, starts `record` in a session of its own, waits until the hanging
test has started (it writes its own process number and its child's to a file), then cuts
the `record` call off the way a caller's ceiling does. The gate run, detached from the
call, keeps running; the scenario then waits, with no further call, for its processes.

Bound here, because the specification or the base commit fixes them:

- a pocket's bound is set through `PRAXION_STEP_LOOP_POCKET_TIMEOUTS` in the task
  environment, or through the pocket's own `pyproject.toml` under
  `[tool.praxion.step-loop] gate-timeout-seconds` (the documented sources);
- a detached run keeps its launcher's process number in a file `<n>.pid` beside
  `<n>.start` and `<n>.log` under the task directory (the documented run files), used
  only to plant a reused process number;
- "no tool the systems do not ship" is a `PATH` of the systems' own directories plus a
  shim for this suite's interpreter, a scratch `HOME`, and no plugin root.

A run past its bound is stopped no later than `STOP_ALLOWANCE_SECONDS` (30) past the bound.
Scenarios measure from the moment the `record` call is cut off, which is after the run
started, so the wait they allow never ends before the allowance does.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Iterable
from pathlib import Path

from tests.acceptance.drivers import pocket_gate
from tests.acceptance.drivers.step_loop import LoopTask, Work, next_action, work_on

SLOW_POCKET = "eval"
SLOW_TESTS = "eval/tests/test_slow_pocket.py"
BOUND_SECONDS = 15
STOP_ALLOWANCE_SECONDS = 30
_MARGIN_SECONDS = 0
SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def slow_pocket_config(*, bound_seconds: int | None = None) -> str:
    text = pocket_gate.pocket_config("evals")
    if bound_seconds is not None:
        text += f"\n[tool.praxion.step-loop]\ngate-timeout-seconds = {bound_seconds}\n"
    return text


def hanging_tests(
    pids_file: Path,
    *,
    failures: bool = True,
    finish_after: float | None = None,
    done_file: Path | None = None,
) -> str:
    """Tests that may fail first, then one that starts a child and hangs (or finishes).

    The hanging test appends `<its pid> <its child's pid>` to `pids_file` each time it starts.
    """
    failing = (
        "def test_first_slow_failure():\n    assert 1 == 2\n\n\n"
        "def test_second_slow_failure():\n    assert 'a' == 'b'\n\n\n"
        if failures
        else ""
    )
    wait = "600" if finish_after is None else repr(finish_after)
    done = "" if done_file is None else f"    Path({str(done_file)!r}).touch()\n"
    return (
        "import os\nimport subprocess\nimport sys\nimport time\nfrom pathlib import Path\n\n\n"
        + failing
        + "def test_waits_with_a_child():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        f"    with open({str(pids_file)!r}, 'a') as out:\n"
        "        out.write(f'{os.getpid()} {child.pid}\\n')\n"
        f"    time.sleep({wait})\n"
        "    child.kill()\n" + done
    )


def abandon_a_gate_run(
    task: LoopTask, slow_tests_text: str, pids_file: Path, *, passes: bool = True
) -> tuple[str, str, list[int]]:
    """Start `record` for the next request, let the slow test start, then cut the call off.

    Returns the request id, the agent id and the process numbers the hanging test wrote.
    """
    asked = next_action(task)
    assert asked.request is not None, asked.doc
    work = Work(passes=passes, other_edits=((SLOW_TESTS, slow_tests_text),))
    agent_id = work_on(task, asked.request, work)
    call = pocket_gate.start_record(task, asked.request["id"], agent_id)
    try:
        line = pocket_gate.wait_for_lines(pids_file, 1, deadline_seconds=120)[0]
    finally:
        pocket_gate.cut_off(call)
    return asked.request["id"], agent_id, [int(n) for n in line.split()]


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def still_running_after_the_allowance(pids: Iterable[int], bound_seconds: int) -> list[int]:
    """The processes still alive once the bound and the stop allowance have passed."""
    pids = list(pids)
    stop_at = time.monotonic() + bound_seconds + STOP_ALLOWANCE_SECONDS + _MARGIN_SECONDS
    while time.monotonic() < stop_at:
        alive = [pid for pid in pids if is_alive(pid)]
        if not alive:
            return []
        time.sleep(0.5)
    return [pid for pid in pids if is_alive(pid)]


def reap(pids_file: Path) -> None:
    """Kill whatever a scenario's hanging tests left running, so nothing outlives the test."""
    if not pids_file.exists():
        return
    for line in pids_file.read_text(encoding="utf-8").splitlines():
        for pid in (int(n) for n in line.split()):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def slow_run_pid_file(task: LoopTask) -> Path:
    """The `<n>.pid` file of the detached run of the slow pocket's tests."""
    candidates = [
        pid_file
        for pid_file in task.task_dir.rglob("*.pid")
        if pid_file.with_suffix(".start").exists()
        and Path(SLOW_TESTS).name
        in pid_file.with_suffix(".log").read_text(encoding="utf-8", errors="replace")
    ]
    assert len(candidates) == 1, f"expected one run of {SLOW_TESTS}, found {candidates}"
    return candidates[0]


def systems_own_tools_only(task: LoopTask, scratch: Path) -> None:
    """Leave `record` only the systems' own directories on PATH, a scratch HOME, no plugin."""
    shim = scratch / "interpreter-shim"
    shim.mkdir(parents=True, exist_ok=True)
    for name in ("python", "python3"):
        target = shim / name
        target.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        target.chmod(0o755)
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    task.env["PATH"] = os.pathsep.join((str(shim), *SYSTEM_PATH))
    task.env["HOME"] = str(home)
    for name in [k for k in task.env if k.startswith("CLAUDE_PLUGIN")]:
        del task.env[name]


def wait_past_the_allowance(bound_seconds: int) -> None:
    """Give a stop every chance to happen: wait out the bound, the allowance and a margin."""
    time.sleep(bound_seconds + STOP_ALLOWANCE_SECONDS + _MARGIN_SECONDS)


def appears_within(path: Path, seconds: float) -> bool:
    """Whether `path` exists within `seconds`, with no call made meanwhile."""
    stop_at = time.monotonic() + seconds
    while time.monotonic() < stop_at:
        if path.exists():
            return True
        time.sleep(0.2)
    return path.exists()
