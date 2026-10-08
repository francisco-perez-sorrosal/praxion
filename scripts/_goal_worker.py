"""The headless worker: one fresh `claude -p` process per spawn request, its result read once.

`HeadlessWorker` is a `Spawner` (see `step_loop.py`). It never continues an earlier session and
never widens the worker's permissions. The profile it starts with:

- it reads (`Read`, `Glob`, `Grep`) and runs the goal's check and the test-scope resolver;
- it edits only the paths in `writable`, as `Edit(...)` rules (one rule covers every tool that
  edits files); an empty `writable` is a read-only worker;
- it is denied what `denied` lists, which beats every pre-approval its settings files grant;
- it loads no MCP server the person did not name on this command line (`--strict-mcp-config`).

After the process exits, its standard output is parsed once at this boundary into the result
object, written to the task directory's worker file before `record` is called, and read back
from that file when a request comes again, so a request whose worker may have run is never
started a second time.

Runs on the plain `python3` the scripts are invoked with, so no `X | Y` at runtime.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _step_loop_cli import SCRIPT as DRIVER_SCRIPT
from _step_loop_cli import invocation
from _step_loop_files import NoWorkerResult, WorkerEnd, read_worker_end, write_worker_end

DEFAULT_MAX_TURNS = 40
DEFAULT_MAX_BUDGET_USD = 2.00
WALL_CLOCK_SECONDS = 3600
STDOUT_TAIL_CHARS = 2000
PROGRAM = "claude"
RESOLVER_SCRIPT = "resolve_test_scope.py"
_READ_TOOLS = ("Read", "Glob", "Grep")
_TERMINAL_MARKERS = ("complete", "blocked", "conflict", "partial")
_RESULT_KEYS = ("session_id", "subtype")
_PYTEST_PREFIX = re.compile(r"(.*?(?:^|[\s/])pytest)(?=\s|$)")


def resolver_invocation(argv0: str, path: str) -> str:
    """The resolver as the caller can run it: by name when the driver itself was started from
    `PATH`, else the checkout's form (the same test as the driver's own `invocation`)."""
    if invocation(argv0, path) == DRIVER_SCRIPT:
        return RESOLVER_SCRIPT
    return f"python3 scripts/{RESOLVER_SCRIPT}"


def shell_rule(command: str) -> str:
    """`Bash(<command>:*)`. A rule cannot carry a parenthesis, so a command holding one is
    allowed up to and including its `pytest` token."""
    if "(" in command or ")" in command:
        prefix = _PYTEST_PREFIX.match(command)
        if prefix is None:
            raise ValueError(
                f"the check cannot be allow-listed (it holds a parenthesis): {command}"
            )
        command = prefix.group(1)
    return f"Bash({command}:*)"


def terminal_marker(final_text: object) -> str:
    """The terminal marker the last line of the final text carries, else `none`."""
    lines = final_text.strip().splitlines() if isinstance(final_text, str) else []
    last = lines[-1].strip() if lines else ""
    word = last[1:-1].lower() if last.startswith("[") and last.endswith("]") else ""
    return word if word in _TERMINAL_MARKERS else "none"


def _result_object(stdout: str) -> dict[str, Any] | None:
    """The result object the worker printed; one without a session id and subtype is none."""
    try:
        document = json.loads(stdout)
    except ValueError:
        return None
    usable = all(
        isinstance(document, dict) and isinstance(document.get(k), str) for k in _RESULT_KEYS
    )
    return document if usable else None


@dataclass(frozen=True)
class _Exit:
    code: int
    stdout: str
    timed_out: bool


@dataclass(frozen=True)
class HeadlessWorker:
    """Starts the print-mode worker for a request in `repo`; `task_dir` keeps its worker files."""

    repo: Path
    task_dir: Path
    check: str
    resolver: str
    max_turns: int = DEFAULT_MAX_TURNS
    max_budget_usd: float = DEFAULT_MAX_BUDGET_USD
    timeout: float = WALL_CLOCK_SECONDS
    writable: tuple[str, ...] = ()
    denied: tuple[str, ...] = ()

    def argv(self, request: Mapping[str, Any]) -> list[str]:
        call = request["agent_call"]
        allowed = (*_READ_TOOLS, *self.writable, shell_rule(self.check), shell_rule(self.resolver))
        refused = ["--disallowedTools", *self.denied] if self.denied else []
        return [
            PROGRAM, "-p", call["prompt"],
            "--model", call["model"],
            "--max-turns", str(self.max_turns),
            "--max-budget-usd", f"{self.max_budget_usd:.2f}",
            "--permission-mode", "dontAsk",
            "--permission-prompts", "none",
            "--allowedTools", *allowed,
            *refused,
            "--strict-mcp-config",
            "--output-format", "json",
        ]  # fmt: skip

    def not_started(self, reason: str) -> Any:
        """The driver's `NotStarted` for a request this worker could not start."""
        return _return_types()[1](reason)

    def spawn(self, request: Mapping[str, Any]) -> Any:
        ran = _return_types()[0]
        earlier = read_worker_end(self.task_dir, request["id"])
        if isinstance(earlier, WorkerEnd):
            return ran(earlier.session_id, terminal_marker(earlier.final_text))
        if isinstance(earlier, NoWorkerResult):
            return self.not_started(earlier.detail)
        if request.get("reissued"):
            return self.not_started(
                "a reissued request has no worker file, so its worker may have run"
            )
        argv = self.argv(request)
        try:
            ended = self._run(argv)
        except FileNotFoundError:
            return self.not_started(f"no `{PROGRAM}` on PATH")
        result = None if ended.timed_out else _result_object(ended.stdout)
        write_worker_end(
            self.task_dir,
            request["id"],
            argv=argv,
            exit_code=ended.code,
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
            stdout_tail=ended.stdout[-STDOUT_TAIL_CHARS:],
            result=result,
        )
        if result is None:
            cause = (
                f"stopped after {self.timeout:g} s" if ended.timed_out else f"exited {ended.code}"
            )
            return self.not_started(f"the worker {cause} and printed no result object")
        return ran(result["session_id"], terminal_marker(result.get("result")))

    def _run(self, argv: list[str]) -> _Exit:
        """Start the process in its own group, input closed; kill the group at the bound."""
        process = subprocess.Popen(  # noqa: S603 -- a fixed argument vector, no shell
            argv,
            cwd=self.repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, _ = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate()
            return _Exit(process.returncode, stdout or "", timed_out=True)
        return _Exit(process.returncode, stdout, timed_out=False)


def _return_types() -> tuple[Any, Any]:
    """`AgentRan` and `NotStarted` of the driver module in use. They live in `step_loop`, which
    imports this module's caller, so they are fetched late; the driver started as a script is
    `__main__`, whose classes are not those of a fresh `import step_loop`."""
    main = sys.modules.get("__main__")
    if hasattr(main, "AgentRan") and hasattr(main, "NotStarted"):
        return main.AgentRan, main.NotStarted
    import step_loop

    return step_loop.AgentRan, step_loop.NotStarted
