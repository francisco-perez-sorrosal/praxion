"""Driver for the Stop-time guard, reached the way the harness reaches it.

A scenario builds a step loop with the step-loop driver's own builder (`step_loop`):
a checkout whose plan the real `scripts/step_loop.py` issues requests for, and the
Agent tool's test double that leaves a spawned agent's transcript where the harness
leaves it. It then fires the `Stop` event at the guard and reads what the guard did.

Bound here, because the specification or the harness fixes them:

- the guard is the one synchronous command hook registered under `Stop` in
  `hooks/hooks.json` beyond the five the base commit registers (frozen below, so no
  scenario reads git history). It runs as its registered command line through a shell,
  with `${CLAUDE_PLUGIN_ROOT}` the plugin root, `python3` on `PATH` the suite's
  interpreter, and the working directory the project's root. Until such a hook is
  registered every scenario stops on `GuardNotRegisteredError`;
- the `Stop` input is Claude Code's: `session_id`, `transcript_path` (the main
  session's transcript, `<config>/projects/<project>/<session>.jsonl`), `cwd`,
  `hook_event_name`, `stop_hook_active`, `last_assistant_message`, `background_tasks`.
  A subagent's own transcript sits beside it, under `<session>/subagents/` (the
  harness's documented layout, the one the step-loop driver's double writes), and the
  config directory is exported as `CLAUDE_CONFIG_DIR`;
- a held stop is the harness's: exit 2 with the message on stderr, or exit 0 with a
  JSON object whose `decision` is `block` and whose `reason` is the message. A stop let
  through is exit 0 with nothing on stdout or stderr (any other exit shows the session a
  hook error, which is printing to it);
- what the guard read and started is watched by `process_probe`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tests.acceptance.drivers import process_probe, step_loop
from tests.acceptance.drivers.step_loop import (
    SANDBOX_PROJECT_DIR,
    SANDBOX_SESSION,
    LoopTask,
    Step,
    agent_transcript_path,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
MESSAGE_CAP_BYTES = 600
EARLIER_SESSION = "session-loop-earlier"

# The `Stop` command hooks the base commit registers; the guard is the one beyond them.
BASE_STOP_COMMANDS = frozenset(
    {
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/send_event.py 2>/dev/null",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/capture_session.py 2>/dev/null",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/notify_bg_session_state.py",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/sidecar_autocommit.py",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/remind_calibration.py",
    }
)


class GuardNotRegisteredError(NotImplementedError):
    """The plugin registers no Stop-time guard yet."""


@dataclass(frozen=True)
class Registration:
    command: str
    timeout: float | None
    synchronous: bool


def guard_registration() -> Registration:
    """The one synchronous `Stop` command hook the base commit did not register."""
    groups = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"].get("Stop", [])
    added = [
        hook
        for group in groups
        for hook in group.get("hooks", [])
        if hook.get("type") == "command" and hook.get("command") not in BASE_STOP_COMMANDS
    ]
    if not added:
        raise GuardNotRegisteredError(
            "no Stop hook beyond the base's is registered in hooks/hooks.json: nothing holds "
            "a stop when a step-loop request's agent has ended and no record holds its return"
        )
    assert len(added) == 1, f"expected one new Stop command hook, found {len(added)}: {added}"
    (hook,) = added
    return Registration(
        command=hook["command"],
        timeout=hook.get("timeout"),
        synchronous=not hook.get("async", False),
    )


# -- The session the guard runs in -------------------------------------------------------


def main_transcript(task: LoopTask, session: str = SANDBOX_SESSION) -> Path:
    """The main session's own transcript, beside its `<session>/subagents/` directory."""
    assert task.sandbox_home is not None
    path = task.sandbox_home / ".claude" / "projects" / SANDBOX_PROJECT_DIR / f"{session}.jsonl"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        line = {"type": "user", "message": {"role": "user", "content": "Relay the step loop."}}
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return path


def stop_input(task: LoopTask, *, stop_hook_active: bool = False) -> dict[str, Any]:
    return {
        "session_id": SANDBOX_SESSION,
        "transcript_path": str(main_transcript(task)),
        "cwd": str(task.root),
        "permission_mode": "default",
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": "Waiting for the implementer to finish.",
        "background_tasks": [],
        "session_crons": [],
    }


@dataclass(frozen=True)
class StopOutcome:
    exit_code: int
    stdout: str
    stderr: str
    probe: process_probe.Probe
    task: LoopTask

    def _decision(self) -> dict[str, Any] | None:
        if self.exit_code != 0 or not self.stdout.strip():
            return None
        try:
            doc = json.loads(self.stdout)
        except json.JSONDecodeError:
            return None
        return doc if isinstance(doc, dict) else None

    @property
    def held(self) -> bool:
        if self.exit_code == 2:
            return True
        decision = self._decision()
        return decision is not None and decision.get("decision") == "block"

    @property
    def message(self) -> str:
        assert self.held, f"the stop was not held: {self.describe()}"
        if self.exit_code == 2:
            return self.stderr.strip()
        return str((self._decision() or {}).get("reason", "")).strip()

    @property
    def let_through_silently(self) -> bool:
        return self.exit_code == 0 and not self.stdout.strip() and not self.stderr.strip()

    def describe(self) -> str:
        return f"exit {self.exit_code}\nstdout: {self.stdout!r}\nstderr: {self.stderr!r}"

    def sandbox_files_read(self) -> list[Path]:
        assert self.task.sandbox_home is not None
        return self.probe.opened_under(self.task.root, self.task.sandbox_home)

    def transcripts_read(self) -> list[Path]:
        assert self.task.sandbox_home is not None
        return self.probe.opened_under(self.task.sandbox_home)

    def processes_started(self) -> list[str]:
        return self.probe.processes_started()


def _shim_dir(workspace: Path) -> Path:
    bin_dir = workspace / "guard-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    shim.chmod(0o755)
    return bin_dir


def fire_stop(
    task: LoopTask, *, stdin: str | None = None, stop_hook_active: bool = False
) -> StopOutcome:
    """Fire `Stop` at the guard as the harness does; `stdin` overrides the input verbatim."""
    registration = guard_registration()
    workspace = task.root.parent
    probe = process_probe.install(workspace / "guard-probe")
    probe.forget()
    payload = (
        stdin
        if stdin is not None
        else json.dumps(stop_input(task, stop_hook_active=stop_hook_active))
    )
    env = {
        k: v
        for k, v in task.env.items()
        if not k.startswith(("CLAUDE", "PRAXION_", "PYTHON", "VIRTUAL_ENV"))
    }
    assert task.sandbox_home is not None
    env.update(
        {
            "PATH": os.pathsep.join([str(_shim_dir(workspace)), "/usr/bin", "/bin"]),
            "HOME": str(task.sandbox_home),
            "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
            "CLAUDE_PROJECT_DIR": str(task.root),
            "CLAUDE_CONFIG_DIR": str(task.sandbox_home / ".claude"),
            step_loop.END_WAIT_VARIABLE: "0",
            **probe.env(),
        }
    )
    command = registration.command.replace(PLUGIN_ROOT_VARIABLE, str(REPO_ROOT))
    budget = (registration.timeout or 60) + 30
    result = subprocess.run(
        ["/bin/sh", "-c", command],
        input=payload,
        capture_output=True,
        text=True,
        cwd=task.root,
        env=env,
        timeout=budget,
    )
    return StopOutcome(result.returncode, result.stdout, result.stderr, probe, task)


# -- Loops in the states a scenario names ---------------------------------------------------


def loop(workspace: Path, *steps: Step, done: tuple[str, ...] = ()) -> LoopTask:
    return step_loop.build_loop(workspace, *steps, done=done)


def second_task(task: LoopTask, slug: str, *steps: Step) -> LoopTask:
    """Another task under the same checkout's `.ai-work/`, with a plan of its own."""
    other = replace(task, slug=slug, steps=tuple(steps))
    other.task_dir.mkdir(parents=True)
    other.plan_path.write_text(step_loop._plan(other.steps), encoding="utf-8")
    other.wip_path.write_text(step_loop._wip(other.steps, frozenset(), {}), encoding="utf-8")
    (other.task_dir / "TASK_BRIEF.md").write_text(step_loop._brief(), encoding="utf-8")
    return other


def issue(task: LoopTask) -> dict[str, Any]:
    """`next` issues a spawn request; the request as the envelope carries it."""
    asked = step_loop.next_action(task)
    assert asked.outcome == "spawn", asked.doc
    assert asked.request is not None, asked.doc
    return {**asked.request, "then": asked.doc["then"]}


END_SHAPES = ("a final text with a marker", "a final text without a marker", "its turn cap reached")


@dataclass(frozen=True)
class Ended:
    agent_id: str
    marker: str  # the marker `record` takes for it


def leave_ended_agent(task: LoopTask, request: dict[str, Any], shape: str) -> Ended:
    """An agent this session started on `request`, whose transcript shows it ended as `shape` says."""
    agent_id = step_loop.new_agent_id()
    if shape == "a final text with a marker":
        step_loop.leave_agent_transcript(
            task, request, agent_id, requests=9, final_text="Step done.\n[COMPLETE]", ended=True
        )
        return Ended(agent_id, "complete")
    if shape == "a final text without a marker":
        step_loop.leave_agent_transcript(
            task, request, agent_id, requests=9, final_text="Step done.", ended=True
        )
        return Ended(agent_id, "none")
    if shape == "its turn cap reached":
        step_loop.leave_agent_transcript(
            task,
            request,
            agent_id,
            requests=step_loop.implementer_max_turns(),
            final_text="Still working.",
            ended=False,
        )
        return Ended(agent_id, "none")
    raise ValueError(shape)


def leave_running_agent(task: LoopTask, request: dict[str, Any]) -> str:
    """An agent this session started on `request` that is still working: no end evidence."""
    agent_id = step_loop.new_agent_id()
    step_loop.leave_agent_transcript(
        task, request, agent_id, requests=4, final_text="Still editing.", ended=False
    )
    return agent_id


def move_to_earlier_session(task: LoopTask, agent_id: str) -> None:
    """The agent's transcript belongs to an earlier session, not the one that is stopping."""
    here = agent_transcript_path(task, agent_id)
    there = here.parents[2] / EARLIER_SESSION / "subagents" / here.name
    there.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(here), str(there))


def make_transcript_unreadable(task: LoopTask, agent_id: str) -> None:
    agent_transcript_path(task, agent_id).write_bytes(b"\xff\xfe\x00\x9c" * 64)


def record_return(task: LoopTask, request: dict[str, Any], ended: Ended) -> step_loop.Envelope:
    return step_loop.record(task, request["id"], agent_id=ended.agent_id, marker=ended.marker)


def record_command(task: LoopTask, request: dict[str, Any], ended: Ended) -> str:
    """The driver's record call for the request, the agent id and the marker filled in."""
    return (
        f"step_loop.py record {task.slug} --request {request['id']} "
        f"--agent-id {ended.agent_id} --marker {ended.marker}"
    )


def files_and_bytes(task: LoopTask) -> dict[str, bytes]:
    """Every file of the checkout and of the session's config directory, with its bytes."""
    assert task.sandbox_home is not None
    found = {}
    for root in (task.root, task.sandbox_home):
        for path in sorted(root.rglob("*")):
            parts = path.relative_to(root).parts
            if path.is_file() and ".git" not in parts and "__pycache__" not in parts:
                found[str(path)] = path.read_bytes()
    return found


def remove_pipeline_directory(task: LoopTask) -> None:
    """A checkout with no `.ai-work/` at all: the common managed project."""
    shutil.rmtree(task.root / ".ai-work")


def cheap_reads(task: LoopTask) -> set[Path]:
    """What a stop may read outside an active loop: each task's step record and ledger."""
    work = task.root / ".ai-work"
    return {
        Path(os.path.realpath(d / name))
        for d in work.iterdir()
        if d.is_dir()
        for name in ("WIP.md", "ITERATION_LEDGER.jsonl")
    }
