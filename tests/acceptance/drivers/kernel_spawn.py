"""Driver that spawns a subagent the way the harness announces it, and reads what it got.

Claude Code announces a subagent by running every command `hooks/hooks.json`
registers for `SubagentStart` (matcher tested against `agent_type`), each as its
own process with the event as one JSON object on stdin and `CLAUDE_PLUGIN_ROOT`
set to the plugin root. What reaches the subagent is the
`hookSpecificOutput.additionalContext` string each command prints as JSON; plain
stdout is not context for this event. This driver does exactly that against a
plugin checkout (usually a sandbox) and hands back those strings in registration
order, so a hook added by a change is delivered to without touching the driver.

The host-native preamble is reached the same way, through the `PreToolUse` hooks
registered for the `Agent` tool: the preamble is the text a hook's `updatedInput`
puts ahead of the original prompt.

Bound here: the payload shapes, the `event_type` field that names an observation
row's kind (`kernel_injected` for a delivered kernel), the project log read through
the observation harness's own reader (never by file name), the fields of a
`kernel_injected` row, and the liveness check that expects one per spawn of a role
at trial or switched.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import isolated_env
from tests.acceptance.drivers.observation_harness import log_rows

KERNEL_ROW = "kernel_injected"
ORIGINAL_PROMPT = "ORIGINAL-PROMPT: map the repository layout."

# The SubagentStart registrations before this change: what "the hook removed from
# the install" leaves behind.
SUBAGENT_START_BEFORE = (
    "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/send_event.py 2>/dev/null",
    "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/capture_session.py 2>/dev/null",
)


def project_checkout(path: Path, *, managed: bool = True, instructions: str | None = None) -> Path:
    """A git working tree; `managed` gives it `.ai-state/`, `instructions` a root CLAUDE.md."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        env=isolated_env(path.parent / f".{path.name}-git"),
        check=True,
        capture_output=True,
        timeout=30,
    )
    if managed:
        (path / ".ai-state").mkdir(exist_ok=True)
    if instructions is not None:
        (path / "CLAUDE.md").write_text(instructions, encoding="utf-8")
    return path


def _registrations(plugin_root: Path, event: str, value: object) -> list[tuple[str, int]]:
    groups = json.loads((plugin_root / "hooks" / "hooks.json").read_text())["hooks"].get(event, [])
    chosen = []
    for group in groups:
        matcher = group.get("matcher", "")
        if matcher not in ("", "*") and not (
            isinstance(value, str) and re.fullmatch(matcher, value)
        ):
            continue
        chosen += [(h["command"], int(h.get("timeout", 60))) for h in group["hooks"]]
    return chosen


@dataclass(frozen=True)
class HookExit:
    command: str
    exit_code: int | None  # None: the process outlived its registered timeout
    stdout: str


def _deliver(
    plugin_root: Path, event: str, payload: object, stdin: str, cwd: Path, scratch: Path
) -> list[HookExit]:
    match_field = {"SubagentStart": "agent_type", "PreToolUse": "tool_name"}[event]
    value = payload.get(match_field) if isinstance(payload, dict) else None
    env = isolated_env(scratch, CLAUDE_PLUGIN_ROOT=str(plugin_root))
    exits = []
    for command, timeout in _registrations(plugin_root, event, value):
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", command],
                input=stdin,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exits.append(HookExit(command, proc.returncode, proc.stdout))
        except subprocess.TimeoutExpired:
            exits.append(HookExit(command, None, ""))
    return exits


def _hook_output(stdout: str) -> dict:
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return {}
    return parsed.get("hookSpecificOutput") or {} if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class Injection:
    strings: tuple[str, ...]  # every additionalContext, in registration order
    exits: tuple[HookExit, ...]

    @property
    def joined(self) -> str:
        return "".join(self.strings)


_spawns = iter(range(1, 1_000_000))


def spawn(
    plugin_root: Path,
    project: Path,
    agent_type: str,
    *,
    process_cwd: Path | None = None,
    raw_stdin: str | None = None,
) -> Injection:
    """Announce one subagent of `agent_type` started in `project`."""
    number = next(_spawns)
    cwd = process_cwd or project
    payload = {
        "session_id": f"kernel-acceptance-{number}",
        "transcript_path": str(project.parent / f"session-{number}.jsonl"),
        "cwd": str(cwd),
        "hook_event_name": "SubagentStart",
        "agent_id": f"agent-{number:04d}",
        "agent_type": agent_type,
    }
    stdin = raw_stdin if raw_stdin is not None else json.dumps(payload)
    scratch = project.parent / f".spawn-{project.name}"
    exits = _deliver(plugin_root, "SubagentStart", payload, stdin, cwd, scratch)
    strings = tuple(
        out["additionalContext"]
        for out in (_hook_output(e.stdout) for e in exits)
        if isinstance(out.get("additionalContext"), str)
    )
    return Injection(strings, tuple(exits))


def preamble(plugin_root: Path, project: Path, agent_type: str) -> str | None:
    """The text the Agent-tool hooks put ahead of a spawn's prompt; None when nothing."""
    number = next(_spawns)
    payload = {
        "session_id": f"kernel-preamble-{number}",
        "transcript_path": str(project.parent / f"preamble-{number}.jsonl"),
        "cwd": str(project),
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_use_id": f"toolu_preamble_{number:04d}",
        "tool_input": {
            "prompt": ORIGINAL_PROMPT,
            "subagent_type": agent_type,
            "description": "acceptance spawn",
        },
    }
    scratch = project.parent / f".preamble-{project.name}"
    exits = _deliver(plugin_root, "PreToolUse", payload, json.dumps(payload), project, scratch)
    for exit_ in exits:
        prompt = (_hook_output(exit_.stdout).get("updatedInput") or {}).get("prompt")
        if isinstance(prompt, str) and prompt.endswith(ORIGINAL_PROMPT):
            return prompt[: -len(ORIGINAL_PROMPT)]
    return None


def unregister_kernel_hooks(plugin_root: Path) -> None:
    """Remove from the install every SubagentStart hook this change added."""
    path = plugin_root / "hooks" / "hooks.json"
    config = json.loads(path.read_text())
    kept = []
    for group in config["hooks"].get("SubagentStart", []):
        hooks = [h for h in group["hooks"] if h["command"] in SUBAGENT_START_BEFORE]
        if hooks:
            kept.append({**group, "hooks": hooks})
    config["hooks"]["SubagentStart"] = kept
    path.write_text(json.dumps(config, indent=2) + "\n")


# -- The observation log -------------------------------------------------------------


def kernel_rows(project: Path) -> list[dict]:
    return [r for r in log_rows(project / ".ai-state") if r.get("event_type") == KERNEL_ROW]


@dataclass(frozen=True)
class KernelRow:
    role: str
    parts: tuple[str, ...]  # the modules or parts delivered
    char_counts: tuple[int, ...]  # one per injected string, in delivery order
    kernel_identity: str  # which kernel version was delivered


def describe_kernel_row(row: dict) -> KernelRow:
    """Read a kernel_injected row's role, parts, character counts and kernel identity."""
    strings = row["strings"]
    parts = tuple(
        entry["module"] if entry.get("part") is None else f"{entry['module']}-{entry['part']}"
        for entry in strings
    )
    return KernelRow(
        role=row["role"],
        parts=parts,
        char_counts=tuple(entry["chars"] for entry in strings),
        kernel_identity=row["kernel_version"],
    )


LIVENESS_CHECKER = "scripts/check_kernel_manifest.py"


def kernel_liveness_findings(project: Path, plugin_root: Path) -> str:
    """The liveness check's report on spawns of a trial or switched role without a kernel row.

    The checker runs from the plugin root (its own index and ledger) over `project`'s
    observation log; exit 0 means no findings, 1 findings, anything else a refused input.
    """
    assert (plugin_root / LIVENESS_CHECKER).is_file(), (
        f"there is no kernel manifest checker at {LIVENESS_CHECKER}"
    )
    scratch = project.parent / f".liveness-{project.name}"
    proc = subprocess.run(
        [sys.executable, LIVENESS_CHECKER, "--liveness", "--repo-root", str(project), "--json"],
        cwd=plugin_root,
        env=isolated_env(scratch),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode in (0, 1), (
        f"the liveness check refused its input (exit {proc.returncode}):\n{proc.stdout}{proc.stderr}"
    )
    return proc.stdout + proc.stderr
