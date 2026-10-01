"""Driver that delivers hook events the way the harness does, and reads the logs back.

The harness delivers an event by running every command that `hooks/hooks.json`
registers for it (matcher permitting), with the payload as one JSON object on
stdin and `CLAUDE_PLUGIN_ROOT` set to the plugin root. This driver does exactly
that and nothing more: it never imports a hook, and it learns which commands to
run from the registration file at delivery time, so a hook added or removed by a
change is delivered to without touching the driver.

Isolation: each harness gets its own HOME, a `python3` on PATH that is the
suite's interpreter, no inherited `CLAUDE_*`, `PRAXION_*`, `GIT_*` or
`ANTHROPIC_*` variables (no API key, so no hook makes a network call),
and the opt-outs that stop sibling hooks from reaching outside the scratch area
(event posting to a live server, the first-run installer, sidecar commits). The
recording-mode setting is set only when a scenario names a mode.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"

STATE_DIR = ".ai-state"
LOG_NAME = "observations.jsonl"
ARCHIVE_NAME = "observations.jsonl.1"
SUMMARY_NAME = "observations_summary.jsonl"

# The payload field a registration's matcher is tested against, per event.
_MATCHER_FIELD = {
    "PreToolUse": "tool_name",
    "PostToolUse": "tool_name",
    "SessionStart": "source",
    "SubagentStart": "agent_type",
    "SubagentStop": "agent_type",
    "PreCompact": "trigger",
    "PostCompact": "trigger",
}

_ISOLATING_OPT_OUTS = {
    "PRAXION_DISABLE_EVENT_POSTING": "1",
    "PRAXION_DISABLE_AUTO_COMPLETE": "1",
    "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT": "1",
}


# -- Scratch checkouts ---------------------------------------------------------


def new_checkout(path: Path, *, recording: bool = True) -> Path:
    """A fresh git working tree at `path`; `recording` gives its root a `.ai-state/`."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True, timeout=30)
    if recording:
        (path / STATE_DIR).mkdir()
    return path


def subdirectory(root: Path, relative: str) -> Path:
    directory = root / relative
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# -- Reading the logs ----------------------------------------------------------


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def log_rows(state_dir: Path) -> list[dict]:
    """Every row of the log in `state_dir`, the rotated archive first."""
    return _jsonl(state_dir / ARCHIVE_NAME) + _jsonl(state_dir / LOG_NAME)


def summary_rows(state_dir: Path) -> list[dict]:
    return _jsonl(state_dir / SUMMARY_NAME)


def logs_under(directory: Path) -> list[Path]:
    """Every observation log (active or archived) anywhere below `directory`."""
    return sorted(
        p for p in directory.rglob("observations.jsonl*") if p.name in (LOG_NAME, ARCHIVE_NAME)
    )


def write_log_lines(state_dir: Path, lines: list[str], *, archive: list[str] = ()) -> None:
    """Seed a log with literal rows, as an earlier version of the hooks left them."""
    state_dir.mkdir(parents=True, exist_ok=True)
    if archive:
        (state_dir / ARCHIVE_NAME).write_text("\n".join(archive) + "\n")
    if lines:
        (state_dir / LOG_NAME).write_text("\n".join(lines) + "\n")


# -- Delivering events -------------------------------------------------------


@dataclass(frozen=True)
class HookExit:
    command: str
    exit_code: int | None  # None: the hook outlived its registered timeout


@dataclass(frozen=True)
class Delivery:
    event: str
    exits: tuple[HookExit, ...]

    def failures(self) -> list[HookExit]:
        return [e for e in self.exits if e.exit_code != 0]


def _matches(matcher: str, value: object) -> bool:
    if matcher in ("", "*"):
        return True
    if not isinstance(value, str):
        return False
    return re.fullmatch(matcher, value) is not None


def registered_commands(event: str, payload: object) -> list[tuple[str, int]]:
    """(command, timeout) for every hook `hooks.json` runs for this event and payload."""
    registrations = json.loads(HOOKS_JSON.read_text())["hooks"].get(event, [])
    field_name = _MATCHER_FIELD.get(event)
    value = payload.get(field_name) if isinstance(payload, dict) and field_name else None
    commands = []
    for group in registrations:
        if _matches(group.get("matcher", ""), value):
            for hook in group["hooks"]:
                commands.append((hook["command"], int(hook.get("timeout", 60))))
    return commands


@dataclass
class HookHarness:
    """Delivers events to the registered hooks inside one isolated environment."""

    scratch: Path
    mode: str | None = None
    _env: dict = field(init=False)

    def __post_init__(self) -> None:
        home = self.scratch / "home"
        shim = self.scratch / "bin"
        home.mkdir(parents=True, exist_ok=True)
        shim.mkdir(parents=True, exist_ok=True)
        python3 = shim / "python3"
        if not python3.exists():
            python3.symlink_to(sys.executable)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_"))
        }
        env.update(_ISOLATING_OPT_OUTS)
        env["HOME"] = str(home)
        env["PATH"] = f"{shim}{os.pathsep}{env.get('PATH', '')}"
        env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
        if self.mode is not None:
            env["PRAXION_OBSERVATION_LOG"] = self.mode
        self._env = env

    def deliver(
        self,
        event: str,
        payload: object,
        *,
        raw_stdin: str | None = None,
        process_cwd: Path | None = None,
    ) -> Delivery:
        """Run every hook registered for `event`; `raw_stdin` overrides the JSON payload."""
        stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
        if process_cwd is None:
            cwd = payload.get("cwd") if isinstance(payload, dict) else None
            process_cwd = Path(cwd) if isinstance(cwd, str) and Path(cwd).is_dir() else self.scratch
        exits = []
        for command, timeout in registered_commands(event, payload):
            try:
                result = subprocess.run(
                    ["/bin/sh", "-c", command],
                    input=stdin,
                    capture_output=True,
                    text=True,
                    cwd=process_cwd,
                    env=self._env,
                    timeout=timeout + 30,
                )
                exits.append(HookExit(command, result.returncode))
            except subprocess.TimeoutExpired:
                exits.append(HookExit(command, None))
        return Delivery(event, tuple(exits))


# -- A session: payloads in the shapes and orders the harness uses -----------


@dataclass
class Session:
    """One Claude Code session whose events reach the hooks through `harness`."""

    harness: HookHarness
    session_id: str
    cwd: Path
    _tool_uses: int = 0
    deliveries: list[Delivery] = field(default_factory=list)

    # -- raw events --

    def _base(self, event: str, cwd: Path | None, inside: tuple[str, str] | None) -> dict:
        payload = {
            "session_id": self.session_id,
            "cwd": str(cwd or self.cwd),
            "hook_event_name": event,
            "transcript_path": str(self.harness.scratch / f"{self.session_id}.jsonl"),
        }
        if inside is not None:
            payload["agent_id"], payload["agent_type"] = inside
        return payload

    def _send(self, event: str, payload: dict) -> Delivery:
        delivery = self.harness.deliver(event, payload)
        self.deliveries.append(delivery)
        return delivery

    def new_tool_use_id(self) -> str:
        self._tool_uses += 1
        return f"toolu_{self.session_id[:8]}_{self._tool_uses:03d}"

    def session_start(self, *, cwd: Path | None = None) -> Delivery:
        payload = self._base("SessionStart", cwd, None)
        payload["source"] = "startup"
        return self._send("SessionStart", payload)

    def stop(self, *, cwd: Path | None = None) -> Delivery:
        payload = self._base("Stop", cwd, None)
        payload["stop_hook_active"] = False
        return self._send("Stop", payload)

    def subagent_start(
        self, agent_id: str, agent_type: str, *, cwd: Path | None = None
    ) -> Delivery:
        payload = self._base("SubagentStart", cwd, None)
        payload.update(agent_id=agent_id, agent_type=agent_type)
        return self._send("SubagentStart", payload)

    def subagent_stop(self, agent_id: str, agent_type: str, *, cwd: Path | None = None) -> Delivery:
        payload = self._base("SubagentStop", cwd, None)
        payload.update(
            agent_id=agent_id,
            agent_type=agent_type,
            agent_transcript_path=str(self.harness.scratch / f"agent-{agent_id}.jsonl"),
        )
        return self._send("SubagentStop", payload)

    def tool_event(
        self,
        event: str,
        tool_name: str,
        tool_input: dict,
        tool_use_id: str,
        *,
        tool_response: object = None,
        cwd: Path | None = None,
        inside: tuple[str, str] | None = None,
    ) -> Delivery:
        payload = self._base(event, cwd, inside)
        payload.update(tool_name=tool_name, tool_input=tool_input, tool_use_id=tool_use_id)
        if event == "PostToolUse":
            payload["tool_response"] = tool_response
        return self._send(event, payload)

    # -- the Agent and SendMessage tools --

    @staticmethod
    def agent_input(prompt: object, agent_type: str, *, background: bool) -> dict:
        return {
            "prompt": prompt,
            "subagent_type": agent_type,
            "description": "acceptance spawn",
            "run_in_background": background,
        }

    def agent_call(
        self,
        prompt: object,
        agent_type: str,
        *,
        background: bool = False,
        cwd: Path | None = None,
        inside: tuple[str, str] | None = None,
    ) -> tuple[str, dict]:
        """PreToolUse for an Agent call; returns its tool_use_id and tool input."""
        tool_use_id = self.new_tool_use_id()
        tool_input = self.agent_input(prompt, agent_type, background=background)
        self.tool_event("PreToolUse", "Agent", tool_input, tool_use_id, cwd=cwd, inside=inside)
        return tool_use_id, tool_input

    def agent_result(
        self,
        tool_use_id: str,
        tool_input: dict,
        agent_id: str,
        *,
        cwd: Path | None = None,
        inside: tuple[str, str] | None = None,
    ) -> Delivery:
        status = "async_launched" if tool_input["run_in_background"] else "completed"
        response = {"agentId": agent_id, "status": status, "prompt": tool_input["prompt"]}
        return self.tool_event(
            "PostToolUse",
            "Agent",
            tool_input,
            tool_use_id,
            tool_response=response,
            cwd=cwd,
            inside=inside,
        )

    # -- whole spawns, in the documented delivery orders --

    def spawn_foreground(
        self,
        prompt: str,
        agent_id: str,
        agent_type: str = "praxion:implementer",
        *,
        cwd: Path | None = None,
        inside: tuple[str, str] | None = None,
    ) -> None:
        """PreToolUse, SubagentStart, SubagentStop, PostToolUse (completed)."""
        tool_use_id, tool_input = self.agent_call(prompt, agent_type, cwd=cwd, inside=inside)
        self.subagent_start(agent_id, agent_type, cwd=cwd)
        self.subagent_stop(agent_id, agent_type, cwd=cwd)
        self.agent_result(tool_use_id, tool_input, agent_id, cwd=cwd, inside=inside)

    def spawn_background(
        self,
        prompt: str,
        agent_id: str,
        agent_type: str = "praxion:implementer",
        *,
        result_first: bool,
        cwd: Path | None = None,
        inside: tuple[str, str] | None = None,
    ) -> None:
        """PreToolUse, then PostToolUse (async_launched) and SubagentStart in either order."""
        tool_use_id, tool_input = self.agent_call(
            prompt, agent_type, background=True, cwd=cwd, inside=inside
        )
        if result_first:
            self.agent_result(tool_use_id, tool_input, agent_id, cwd=cwd, inside=inside)
            self.subagent_start(agent_id, agent_type, cwd=cwd)
        else:
            self.subagent_start(agent_id, agent_type, cwd=cwd)
            self.agent_result(tool_use_id, tool_input, agent_id, cwd=cwd, inside=inside)
        self.subagent_stop(agent_id, agent_type, cwd=cwd)

    def resume(
        self,
        agent_id: str,
        agent_type: str = "praxion:implementer",
        *,
        message: str = "Continue with the next step.",
        cwd: Path | None = None,
    ) -> None:
        """A SendMessage call, then a further SubagentStart with the same agent_id."""
        tool_use_id = self.new_tool_use_id()
        tool_input = {"to": agent_id, "message": message}
        self.tool_event("PreToolUse", "SendMessage", tool_input, tool_use_id, cwd=cwd)
        self.tool_event(
            "PostToolUse",
            "SendMessage",
            tool_input,
            tool_use_id,
            tool_response={"resumedAgentId": agent_id},
            cwd=cwd,
        )
        self.subagent_start(agent_id, agent_type, cwd=cwd)
        self.subagent_stop(agent_id, agent_type, cwd=cwd)

    def plain_tool_use(
        self, *, cwd: Path | None = None, inside: tuple[str, str] | None = None
    ) -> None:
        """A Bash call that touches no file, before and after."""
        tool_use_id = self.new_tool_use_id()
        tool_input = {"command": "true", "description": "no-op"}
        self.tool_event("PreToolUse", "Bash", tool_input, tool_use_id, cwd=cwd, inside=inside)
        self.tool_event(
            "PostToolUse",
            "Bash",
            tool_input,
            tool_use_id,
            tool_response={"stdout": "", "stderr": "", "interrupted": False},
            cwd=cwd,
            inside=inside,
        )

    def hook_failures(self) -> list[tuple[str, HookExit]]:
        return [(d.event, e) for d in self.deliveries for e in d.failures()]
