"""Deliver one hook event to the registered hooks the way the harness does.

The harness runs every command `hooks/hooks.json` registers for an event
(matcher permitting) with `/bin/sh -c`, the payload as one JSON object on stdin,
the session's working directory as the process directory, and `CLAUDE_PLUGIN_ROOT`
set to the plugin root. This module does exactly that, and learns the commands
from the registration at delivery time, so a hook added or removed by a change
is delivered to without touching it. It imports no hook.

Isolation: a scratch `HOME`, a `python3` first on `PATH` that is this
interpreter (the registered commands say `python3`), no inherited `CLAUDE*`,
`PRAXION_*`, `GIT_*`, `ANTHROPIC_*`, `GH_TOKEN` or `GITHUB_TOKEN` (no credential
reaches a hook, so none makes a network call), and the opt-outs that stop sibling
hooks from reaching outside the scratch area: event posting to a live server, the
first-run installer, sidecar commits.

This is an independent production copy of the test driver in
`tests/acceptance/drivers/observation_harness.py`; the two are not wired
together. Payload shapes follow the ones the harness sends. Tests:
`scripts/gate_probes/test_hook_replay.py`.
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

REGISTRATION = Path("hooks") / "hooks.json"
DEFAULT_TIMEOUT_S = 60  # the harness's own default for a hook with no `timeout`
TIMEOUT_GRACE_S = 30  # the registered timeout is the hook's; the replay waits a little longer

_SCRUBBED_PREFIXES = ("CLAUDE", "PRAXION_", "GIT_", "ANTHROPIC_")
_SCRUBBED_NAMES = frozenset({"GH_TOKEN", "GITHUB_TOKEN"})
_OPT_OUTS = {
    "PRAXION_DISABLE_EVENT_POSTING": "1",
    "PRAXION_DISABLE_AUTO_COMPLETE": "1",
    "PRAXION_DISABLE_SIDECAR_AUTOCOMMIT": "1",
}

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


@dataclass(frozen=True)
class HookRun:
    command: str
    exit_code: int | None  # None: the hook outlived its registered timeout


def deliver(
    event: str,
    payload: Mapping[str, object],
    *,
    repo: Path,
    project: Path,
    cwd: Path,
    home: Path,
    base_env: Mapping[str, str] | None = None,
) -> tuple[HookRun, ...]:
    """Run every command registered for `event` and `payload`; one `HookRun` each.

    `repo` is the plugin root, `project` the checkout the session belongs to,
    `cwd` the session's working directory (the process directory too), `home` a
    scratch home. A missing or unreadable registration raises (`OSError`,
    `ValueError`): there is nothing to deliver to.
    """
    env = _hook_environment(base_env if base_env is not None else os.environ, repo, project, home)
    stdin = json.dumps(payload)
    return tuple(
        _run_command(command, timeout, stdin, cwd, env)
        for command, timeout in registered_commands(repo, event, payload)
    )


def registered_commands(
    repo: Path, event: str, payload: Mapping[str, object]
) -> tuple[tuple[str, int], ...]:
    """(command, timeout) for every hook the registration runs for this event and payload."""
    registration = json.loads((repo / REGISTRATION).read_text(encoding="utf-8"))
    field = _MATCHER_FIELD.get(event)
    value = payload.get(field) if field else None
    return tuple(
        (hook["command"], int(hook.get("timeout", DEFAULT_TIMEOUT_S)))
        for group in registration["hooks"].get(event, [])
        if _matches(group.get("matcher", ""), value)
        for hook in group["hooks"]
    )


def subagent_start_payload(
    *, session_id: str, cwd: Path, transcript_path: Path, agent_id: str, agent_type: str
) -> dict[str, object]:
    return {
        **_session_fields(session_id, cwd, transcript_path, "SubagentStart"),
        "agent_id": agent_id,
        "agent_type": agent_type,
    }


def agent_result_payload(
    *,
    session_id: str,
    cwd: Path,
    transcript_path: Path,
    tool_use_id: str,
    prompt: str,
    agent_id: str,
    agent_type: str,
) -> dict[str, object]:
    """A completed foreground `Agent` call, as `PostToolUse` delivers it."""
    tool_input = {
        "prompt": prompt,
        "subagent_type": agent_type,
        "description": "liveness spawn",
        "run_in_background": False,
    }
    return {
        **_session_fields(session_id, cwd, transcript_path, "PostToolUse"),
        "tool_name": "Agent",
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
        "tool_response": {"agentId": agent_id, "status": "completed", "prompt": prompt},
    }


def _session_fields(
    session_id: str, cwd: Path, transcript_path: Path, event: str
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(cwd),
        "hook_event_name": event,
        "transcript_path": str(transcript_path),
    }


def _matches(matcher: str, value: object) -> bool:
    if matcher in ("", "*"):
        return True
    return isinstance(value, str) and re.fullmatch(matcher, value) is not None


def _hook_environment(
    base: Mapping[str, str], repo: Path, project: Path, home: Path
) -> dict[str, str]:
    shim = _python3_shim(home)
    env = {
        name: value
        for name, value in base.items()
        if not name.startswith(_SCRUBBED_PREFIXES) and name not in _SCRUBBED_NAMES
    }
    env.update(_OPT_OUTS)
    env["HOME"] = str(home)
    env["PATH"] = f"{shim}{os.pathsep}{env.get('PATH', '')}"
    env["CLAUDE_PLUGIN_ROOT"] = str(repo)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return env


def _python3_shim(home: Path) -> Path:
    """A directory whose `python3` is this interpreter, created under the scratch home."""
    shim = home / "bin"
    shim.mkdir(parents=True, exist_ok=True)
    python3 = shim / "python3"
    if not python3.exists():
        python3.symlink_to(sys.executable)
    return shim


def _run_command(
    command: str, timeout: int, stdin: str, cwd: Path, env: Mapping[str, str]
) -> HookRun:
    """One command in its own process group, so a timeout kills what the hook started too."""
    process = subprocess.Popen(
        ["/bin/sh", "-c", command],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=dict(env),
        start_new_session=True,
    )
    try:
        process.communicate(stdin, timeout=timeout + TIMEOUT_GRACE_S)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        return HookRun(command, None)
    return HookRun(command, process.returncode)
