"""Driver for the headless worker `run` starts: a substitute `claude` on `PATH`.

The substitute stands in for the harness's print mode. Its contract, which is what the
scenarios assume of the real program:

- it is the first executable named `claude` on `PATH`, started by `run` once per
  iteration; it records how it was started (argument vector, working directory, standard
  input) and every result object it printed, beside itself;
- it does the scripted iteration's edits in its working directory (a goal driver
  `Iteration`), appending its progress line to the task's `WIP.md`, the task named by the
  prompt's `Task slug:` line;
- it writes a top-level session transcript at `<config>/projects/<project>/<session
  id>.jsonl`, `<config>` being `CLAUDE_CONFIG_DIR` from its own environment, else
  `~/.claude`, and `<project>` its working directory with every character that is not a
  letter or a digit replaced by `-`; the transcript opens with a user record whose text is
  the prompt and carries `requestId` on every assistant record;
- it prints one JSON result object on standard output (`type`, `subtype`, `is_error`,
  `num_turns`, `session_id`, `total_cost_usd`, `permission_denials`, and `result` unless
  the run stopped at its turn bound or the script omits it) and exits with the scripted
  status. `num_turns` equals the transcript's count of distinct requests.

A call beyond the script edits nothing and ends with no marker, so an unexpected start is
visible in the call log and never reaches a real harness.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tests.acceptance.drivers.goal_loop import (
    CHECK_COMMAND,
    Iteration,
    apply_iteration,
    run_command,
)
from tests.acceptance.drivers.step_loop import (
    CONFIG_DIR_VARIABLE,
    PYTHON,
    REPO_ROOT,
    Envelope,
    LoopTask,
    assert_well_formed,
)

_WORKER_SCRIPT = "worker-script.json"
_WORKER_CALLS = "worker-calls.jsonl"
_WORKER_RESULTS = "worker-results.jsonl"


# -- A top-level session's transcript ----------------------------------------------------


def project_dir_name(cwd: Path | str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def session_transcript_path(config_dir: Path, cwd: Path | str, session_id: str) -> Path:
    return config_dir / "projects" / project_dir_name(cwd) / f"{session_id}.jsonl"


def _session_entry(session_id: str, cwd: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "sessionId": session_id, "cwd": cwd, "isSidechain": False, **extra}


def write_session_transcript(
    config_dir: Path,
    cwd: Path | str,
    session_id: str,
    *,
    prompt: str,
    requests: int,
    final_text: str,
    ended: bool,
) -> Path:
    """A top-level session's transcript: the prompt, then `requests` distinct API requests.

    Each request but an ended session's last is a text block and a `tool_use` sharing one
    `requestId`, answered by a tool result; an ended session closes on a text-only request,
    a session stopped at its turn bound on an unanswered `tool_use`.
    """
    cwd = str(cwd)
    user = {"role": "user", "content": prompt}
    lines = [_session_entry(session_id, cwd, "user", message=user)]
    tool_requests = requests - 1 if ended else requests
    for n in range(tool_requests):
        request_id = f"req_{session_id[:8]}_{n:04d}"
        last = not ended and n == tool_requests - 1
        for block in ({"type": "text", "text": "Working."}, {"type": "tool_use", "name": "Bash"}):
            message = {"role": "assistant", "content": [block]}
            lines.append(
                _session_entry(session_id, cwd, "assistant", requestId=request_id, message=message)
            )
        if not last:
            answer = {"role": "user", "content": [{"type": "tool_result"}]}
            lines.append(_session_entry(session_id, cwd, "user", message=answer))
    if ended:
        message = {"role": "assistant", "content": [{"type": "text", "text": final_text}]}
        final_request = f"req_{session_id[:8]}_{tool_requests:04d}"
        lines.append(
            _session_entry(session_id, cwd, "assistant", requestId=final_request, message=message)
        )
    path = session_transcript_path(config_dir, cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def config_dir(task: LoopTask) -> Path:
    return Path(task.env[CONFIG_DIR_VARIABLE])


# -- The substitute for `claude` ----------------------------------------------------------


@dataclass(frozen=True)
class WorkerCall:
    argv: list[str]
    cwd: str
    stdin: str

    def option(self, name: str) -> str | None:
        """The value given to option `name`, as `--name value` or `--name=value`."""
        for index, token in enumerate(self.argv):
            if token == name and index + 1 < len(self.argv):
                return self.argv[index + 1]
            if token.startswith(name + "="):
                return token.split("=", 1)[1]
        return None

    def values_of(self, name: str) -> list[str]:
        """Every token after option `name` up to the next option."""
        values: list[str] = []
        for index, token in enumerate(self.argv):
            if token == name:
                for later in self.argv[index + 1 :]:
                    if later.startswith("-"):
                        break
                    values.append(later)
            elif token.startswith(name + "="):
                values.append(token.split("=", 1)[1])
        return values

    @property
    def prompt(self) -> str:
        """The prompt the worker was given: the argument opening with the task slug, or stdin."""
        return next((a for a in self.argv if a.startswith("Task slug:")), self.stdin)

    @property
    def request_id(self) -> str:
        match = re.search(r"^Spawn request:\s*(\S+)", self.prompt, re.MULTILINE)
        if match is None:
            raise AssertionError(f"the worker's prompt names no spawn request: {self.prompt!r}")
        return match.group(1)

    def carries_prompt(self, prompt: str) -> bool:
        """The prompt reached the worker verbatim, as an argument or on standard input."""
        return prompt in self.argv or self.stdin.strip() == prompt.strip()


@dataclass(frozen=True)
class Worker:
    bin_dir: Path
    iterations: tuple[Iteration, ...] = field(default=())

    def calls(self) -> list[WorkerCall]:
        """Every start of the worker, in order."""
        return [WorkerCall(**doc) for doc in _json_lines(self.bin_dir / _WORKER_CALLS)]

    def results(self) -> list[dict[str, Any]]:
        """Every result object the worker printed, in order."""
        return _json_lines(self.bin_dir / _WORKER_RESULTS)


def _json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def install_worker(task: LoopTask, *iterations: Iteration) -> Worker:
    """Put the substitute `claude` first on the checkout's `PATH`, scripted with `iterations`
    in order; a call beyond the script does nothing and ends with no marker."""
    bin_dir = task.root.parent / "worker-bin"
    bin_dir.mkdir(exist_ok=True)
    program = bin_dir / "claude"
    program.write_text(
        f"#!{PYTHON}\nimport sys\nsys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from tests.acceptance.drivers.headless_worker import worker_main\n"
        "sys.exit(worker_main(__file__, sys.argv[1:]))\n",
        encoding="utf-8",
    )
    program.chmod(program.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (bin_dir / _WORKER_SCRIPT).write_text(
        json.dumps([asdict(i) for i in iterations]), encoding="utf-8"
    )
    task.env["PATH"] = f"{bin_dir}{os.pathsep}{task.env['PATH']}"
    return Worker(bin_dir=bin_dir, iterations=tuple(iterations))


def remove_claude_from_path(task: LoopTask) -> None:
    """Leave no `claude` on the checkout's `PATH` at all."""
    entries = task.env["PATH"].split(os.pathsep)
    task.env["PATH"] = os.pathsep.join(e for e in entries if not (Path(e) / "claude").exists())


_IDLE = Iteration(touches_widget=False, progress=None, marker="none")


def _from_dict(raw: dict[str, Any]) -> Iteration:
    raw = dict(raw)
    raw["implemented"] = tuple(raw["implemented"])
    raw["other_edits"] = tuple(tuple(pair) for pair in raw["other_edits"])
    return Iteration(**raw)


def _slug_of(prompt: str) -> str:
    match = re.search(r"^Task slug:\s*(\S+)", prompt, re.MULTILINE)
    if match is None:
        raise SystemExit(f"the worker's prompt names no task slug: {prompt!r}")
    return match.group(1)


def worker_main(program: str, argv: list[str]) -> int:
    """The substitute `claude`: record the call, do the scripted iteration, print a result."""
    bin_dir = Path(program).resolve().parent
    stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    log = bin_dir / _WORKER_CALLS
    earlier = len(log.read_text("utf-8").splitlines()) if log.exists() else 0
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "stdin": stdin}) + "\n")
    script = [_from_dict(raw) for raw in json.loads((bin_dir / _WORKER_SCRIPT).read_text("utf-8"))]
    iteration = script[earlier] if earlier < len(script) else _IDLE
    if not iteration.prints_result:
        print("the worker crashed before it could report")
        return iteration.exit_status or 1
    prompt = WorkerCall(argv=argv, cwd=os.getcwd(), stdin=stdin).prompt
    apply_iteration(Path(os.getcwd()), _slug_of(prompt), iteration)
    configured = os.environ.get(CONFIG_DIR_VARIABLE)
    config = Path(configured) if configured else Path.home() / ".claude"
    session_id = str(uuid.uuid4())
    write_session_transcript(
        config,
        os.getcwd(),
        session_id,
        prompt=prompt,
        requests=iteration.requests,
        final_text=iteration.final_text,
        ended=not iteration.stopped_at_turn_bound,
    )
    result: dict[str, Any] = {
        "type": "result",
        "subtype": "error_max_turns" if iteration.stopped_at_turn_bound else "success",
        "is_error": iteration.stopped_at_turn_bound,
        "num_turns": iteration.requests,
        "session_id": session_id,
        "total_cost_usd": iteration.cost_usd,
        "permission_denials": [
            {"tool_name": "Bash", "tool_use_id": f"toolu_{n}", "tool_input": {"command": "ls"}}
            for n in range(iteration.permission_denials)
        ],
    }
    if not (iteration.omits_result_text or iteration.stopped_at_turn_bound):
        result["result"] = iteration.final_text
    with (bin_dir / _WORKER_RESULTS).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result) + "\n")
    print(json.dumps(result))
    return iteration.exit_status


# -- The `run` verb -------------------------------------------------------------------------


def run_loop(task: LoopTask, *extra: str, base_ref: bool = True) -> Envelope:
    """`step_loop.py run <slug>` with the checkout's root and, by default, its base."""
    location = ["--repo-root", str(task.root)]
    if base_ref:
        location += ["--base-ref", task.base]
    return assert_well_formed("run", run_command(task, "run", task.slug, *location, *extra))


def allowed_shell_patterns(call: WorkerCall) -> list[str]:
    """The shell commands `--allowedTools` allows, each `Bash(...)` entry's pattern with a
    trailing `:*`, ` *` or `*` dropped; a bare `Bash` entry reads as the empty pattern."""
    listed = " ".join(call.values_of("--allowedTools"))
    entries = re.findall(r"\bBash(?:\(([^)]*)\))?", listed)
    return [re.sub(r"(:\*|\s\*|\*)$", "", entry).strip() for entry in entries]


def allows_the_check(patterns: list[str]) -> bool:
    """Some allowed pattern is the check command or a prefix of it naming pytest."""
    return any(p and "pytest" in p and CHECK_COMMAND.startswith(p) for p in patterns)


def foreign_shell_patterns(patterns: list[str]) -> list[str]:
    """Allowed shell patterns that are neither the check nor the test-scope resolver."""
    return [
        p
        for p in patterns
        if not (p and "pytest" in p and CHECK_COMMAND.startswith(p))
        and "resolve_test_scope" not in p
    ]


def lines_naming_all(envelope: Envelope, *texts: str) -> list[str]:
    """Lines under the command's stderr prefix that name every one of `texts`."""
    return [
        line
        for line in envelope.stderr.splitlines()
        if line.startswith("step_loop: ") and all(text in line for text in texts)
    ]
