"""Driver for the hooks that judge Bash calls: the commit gate and the working-directory notice.

Both are reached as the harness reaches a command hook: the event's JSON payload on stdin,
the registered command line run through a shell, `${CLAUDE_PLUGIN_ROOT}` the plugin root.

Bound here, because the base commit or the harness fixes them:

- the commit gate is `hooks/commit_gate.sh [--blocking] <checker>`; whether it started its
  checker is observed with a stand-in checker that records each start in a file;
- the working-directory notice is any command hook registered in `hooks/hooks.json` under
  `PreToolUse` or `PostToolUse` whose matcher reaches Bash, beyond the ones the base commit
  registers (frozen below, so no scenario reads git history). Until one is registered the
  notice scenarios stop on `NoticeNotRegisteredError`;
- the context a hook adds is `hookSpecificOutput.additionalContext` (or a top-level
  `additionalContext`) of the JSON object it prints; the project root is `CLAUDE_PROJECT_DIR`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"
COMMIT_GATE = REPO_ROOT / "hooks" / "commit_gate.sh"
PLUGIN_ROOT_VARIABLE = "${CLAUDE_PLUGIN_ROOT}"
SESSION = "session-bash-hooks"

BASE_BASH_COMMANDS = frozenset(
    {
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh ${CLAUDE_PLUGIN_ROOT}/hooks/check_code_quality.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh ${CLAUDE_PLUGIN_ROOT}/hooks/remind_adr.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh ${CLAUDE_PLUGIN_ROOT}/hooks/remind_calibration.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/cleanup_gate.sh ${CLAUDE_PLUGIN_ROOT}/hooks/promote_learnings.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh --blocking ${CLAUDE_PLUGIN_ROOT}/scripts/check_id_citation_discipline.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh --blocking ${CLAUDE_PLUGIN_ROOT}/scripts/check_decision_records.py",
        "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.sh --blocking ${CLAUDE_PLUGIN_ROOT}/scripts/check_token_ratchet.py",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/send_event.py 2>/dev/null",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/remind_turn_budget.py 2>/dev/null",
        "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/capture_observations.py 2>/dev/null",
    }
)


def _env(home: Path, project: Path, shim: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "CLAUDE", "PRAXION_"))}
    env.update(
        {
            "HOME": str(home),
            "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
            "CLAUDE_PROJECT_DIR": str(project),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "PATH": os.pathsep.join([str(shim), env.get("PATH", "")]),
        }
    )
    return env


def _shim(workspace: Path) -> Path:
    bin_dir = workspace / "hook-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    python = bin_dir / "python3"
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    python.chmod(0o755)
    return bin_dir


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, timeout=60)


def scratch_repo(workspace: Path) -> Path:
    """A git checkout with one commit and one staged change."""
    root = (workspace / "project").resolve()
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    for key, value in (
        ("user.name", "Hooks"),
        ("user.email", "hooks@example.invalid"),
        ("commit.gpgsign", "false"),
    ):
        _git(root, "config", key, value)
    (root / "README.md").write_text("# widget\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    (root / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "widget.py")
    return root


# -- The commit gate ------------------------------------------------------------------------------


@dataclass(frozen=True)
class GateRun:
    exit_code: int
    stdout: str
    stderr: str
    checker_starts: int


def recording_checker(workspace: Path) -> tuple[Path, Path]:
    """A stand-in gated checker that records each start and finds nothing."""
    log = workspace / "checker-starts.log"
    script = workspace / "recording_checker.py"
    script.write_text(
        "import sys\nsys.stdin.read()\n"
        f"with open({str(log)!r}, 'a') as out:\n    out.write('started\\n')\n",
        encoding="utf-8",
    )
    return script, log


def bash_payload(root: Path, command: str, **fields: Any) -> str:
    payload = {
        "session_id": SESSION,
        "transcript_path": str(root.parent / "transcript.jsonl"),
        "cwd": str(root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": command,
            "description": fields.pop("description", "Run a command"),
        },
    }
    payload.update(fields)
    return json.dumps(payload)


def run_commit_gate(workspace: Path, payload: str) -> GateRun:
    root = workspace / "project"
    checker, log = recording_checker(workspace)
    result = subprocess.run(
        [str(COMMIT_GATE), "--blocking", str(checker)],
        input=payload,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        env=_env(workspace / "home", root, _shim(workspace)),
    )
    starts = len(log.read_text().splitlines()) if log.exists() else 0
    return GateRun(result.returncode, result.stdout, result.stderr, starts)


# -- The working-directory notice ------------------------------------------------------------------


class NoticeNotRegisteredError(NotImplementedError):
    """The plugin registers no Bash hook beyond the base's to say where the session moved."""


def notice_registrations() -> list[tuple[str, str]]:
    """(event, command) of each Bash-reaching PreToolUse/PostToolUse hook the base did not register."""
    hooks = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]
    found = []
    for event in ("PreToolUse", "PostToolUse"):
        for group in hooks.get(event, []):
            matcher = group.get("matcher", "")
            if matcher and not re.fullmatch(matcher, "Bash"):
                continue
            for hook in group.get("hooks", []):
                command = hook.get("command", "")
                if hook.get("type") == "command" and command not in BASE_BASH_COMMANDS:
                    found.append((event, command))
    if not found:
        raise NoticeNotRegisteredError(
            "no PreToolUse or PostToolUse hook reaching Bash beyond the base's is registered in "
            "hooks/hooks.json: nothing tells the agent the session's directory moved"
        )
    return found


@dataclass(frozen=True)
class HookCall:
    event: str
    command: str
    cwd: Path


def contexts(output: str) -> list[str]:
    try:
        doc = json.loads(output)
    except json.JSONDecodeError:
        return []
    if not isinstance(doc, dict):
        return []
    found = [
        doc.get("additionalContext"),
        (doc.get("hookSpecificOutput") or {}).get("additionalContext"),
    ]
    return [c for c in found if c]


@dataclass(frozen=True)
class NoticeRun:
    contexts: list[str]
    exit_codes: list[int]


def run_session(
    workspace: Path, project: Path, calls: list[HookCall], raw: str | None = None
) -> NoticeRun:
    """Fire each call's Bash event, in order, at every notice hook; collect the context added."""
    registrations = notice_registrations()
    env = _env(workspace / "home", project, _shim(workspace))
    added: list[str] = []
    codes: list[int] = []
    for call in calls:
        payload = (
            raw
            if raw is not None
            else json.dumps(
                {
                    "session_id": SESSION,
                    "transcript_path": str(workspace / "transcript.jsonl"),
                    "cwd": str(call.cwd),
                    "hook_event_name": call.event,
                    "tool_name": "Bash",
                    "tool_input": {"command": call.command, "description": "Move around"},
                    "tool_response": {"stdout": "", "stderr": "", "interrupted": False},
                }
            )
        )
        for event, command in registrations:
            if event != call.event:
                continue
            result = subprocess.run(
                ["/bin/sh", "-c", command.replace(PLUGIN_ROOT_VARIABLE, str(REPO_ROOT))],
                input=payload,
                cwd=call.cwd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            codes.append(result.returncode)
            added += contexts(result.stdout)
    return NoticeRun(added, codes)


def moved(project: Path, command: str, after: Path, *, payload_shows_move: bool) -> list[HookCall]:
    """A Bash call running `command` from the project root that leaves the session in `after`,
    then the agent's next Bash call. Whether the moving call's own PostToolUse payload already
    shows `after` is not established, so a scenario runs both answers."""
    post_cwd = after if payload_shows_move else project
    return [
        HookCall("PreToolUse", command, project),
        HookCall("PostToolUse", command, post_cwd),
        HookCall("PreToolUse", "ls", after),
        HookCall("PostToolUse", "ls", after),
    ]
