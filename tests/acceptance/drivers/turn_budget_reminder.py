"""Driver for the turn-budget reminder, reached only as a PreToolUse hook.

The harness runs a hook as a subprocess, writes the tool call's JSON payload to its
stdin, and reads an optional JSON object from its stdout. This driver does the same and
never imports the hook. It also lays out a session the way the harness does: the main
session's transcript at `<project>/<session>.jsonl`, and each subagent's own transcript
at `<project>/<session>/subagents/agent-<agent id>.jsonl`, one line per transcript
entry, with every line of one API request sharing that request's `requestId`.

Confirmed against the live harness (2.1.289): a subagent's tool-call payload carries
`agent_id` and `agent_type` beside the session's `transcript_path`, and the main
session's payload carries neither. The reminder is `hooks/remind_turn_budget.py`, the
script the plugin registers for PreToolUse.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS_MANIFEST = REPO_ROOT / "hooks" / "hooks.json"
REMINDER_SCRIPT = REPO_ROOT / "hooks" / "remind_turn_budget.py"
AGENTS_DIR = REPO_ROOT / "agents"

# The agent types a payload names: a plugin agent by its namespaced name, and a built-in
# agent whose definition declares no maxTurns.
IMPLEMENTER_AGENT_TYPE = "praxion:implementer"
IMPLEMENTER_DEFINITION = "implementer"
UNCAPPED_AGENT_TYPE = "general-purpose"

LINE_PATTERN = re.compile(r"^\[turn-budget\] (\d+) of (\d+) turns used\. (.+)$", re.DOTALL)


def reminder_script() -> Path:
    """The hook script the plugin registers as the turn-budget reminder."""
    return REMINDER_SCRIPT


def declared_max_turns(agent_name: str) -> int:
    """The `maxTurns` an agent definition declares in its frontmatter."""
    text = (AGENTS_DIR / f"{agent_name}.md").read_text(encoding="utf-8")
    match = re.search(r"^maxTurns:\s*(\d+)\s*$", text.split("---", 2)[1], re.MULTILINE)
    if match is None:
        raise AssertionError(f"{agent_name} declares no maxTurns")
    return int(match.group(1))


@dataclass(frozen=True)
class Session:
    project_dir: Path
    session_id: str
    cwd: Path

    @property
    def transcript_path(self) -> Path:
        return self.project_dir / f"{self.session_id}.jsonl"

    def agent_transcript(self, agent_id: str) -> Path:
        return self.project_dir / self.session_id / "subagents" / f"agent-{agent_id}.jsonl"


def new_session(workspace: Path, *, main_requests: int = 90) -> Session:
    """A session whose own transcript already holds `main_requests` distinct API requests."""
    cwd = workspace / "repo"
    cwd.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=cwd, check=True, capture_output=True, timeout=30)
    session = Session(
        project_dir=workspace / "projects" / "-tmp-repo",
        session_id=str(uuid.uuid4()),
        cwd=cwd,
    )
    session.project_dir.mkdir(parents=True)
    _write_requests(session.transcript_path, main_requests, agent_id=None)
    return session


def new_agent_id() -> str:
    return "a" + uuid.uuid4().hex[:16]


def _entries(count: int, agent_id: str | None, start: int) -> list[dict]:
    """`count` API requests; each request writes two entries (text, then a tool call)."""
    entries = []
    for n in range(start, start + count):
        request_id = f"req_{agent_id or 'main'}_{n:04d}"
        for block in ({"type": "text", "text": "Working."}, {"type": "tool_use", "name": "Bash"}):
            entries.append(
                {
                    "type": "assistant",
                    "requestId": request_id,
                    "agentId": agent_id,
                    "isSidechain": agent_id is not None,
                    "message": {"role": "assistant", "content": [block]},
                }
            )
        entries.append(
            {
                "type": "user",
                "agentId": agent_id,
                "isSidechain": agent_id is not None,
                "message": {"role": "user", "content": [{"type": "tool_result"}]},
            }
        )
    return entries


def _write_requests(path: Path, count: int, *, agent_id: str | None, start: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as transcript:
        for entry in _entries(count, agent_id, start):
            transcript.write(json.dumps(entry) + "\n")


def grow_agent_transcript(session: Session, agent_id: str, total_requests: int) -> None:
    """Extend the agent's own transcript until it holds `total_requests` distinct requests."""
    path = session.agent_transcript(agent_id)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            request_id = json.loads(line).get("requestId")
            if request_id:
                seen.add(request_id)
    _write_requests(path, total_requests - len(seen), agent_id=agent_id, start=len(seen))


def subagent_payload(session: Session, agent_id: str, agent_type: str) -> dict:
    """The PreToolUse payload for a tool call made by a subagent."""
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session.session_id,
        "transcript_path": str(session.transcript_path),
        "cwd": str(session.cwd),
        "permission_mode": "default",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "description": "list files"},
    }


def main_session_payload(session: Session) -> dict:
    """The PreToolUse payload for a tool call made by the main session."""
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session.session_id,
        "transcript_path": str(session.transcript_path),
        "cwd": str(session.cwd),
        "permission_mode": "default",
        "tool_name": "Bash",
        "tool_input": {"command": "ls", "description": "list files"},
    }


@dataclass(frozen=True)
class HookRun:
    exit_code: int
    stdout: str
    stderr: str

    def reminders(self) -> list[str]:
        """The `additionalContext` lines the hook asked the harness to inject."""
        if not self.stdout.strip():
            return []
        output = json.loads(self.stdout)
        specific = output["hookSpecificOutput"]
        if specific.get("hookEventName") != "PreToolUse":
            raise AssertionError(f"the reminder answered for another event: {output}")
        return [specific["additionalContext"]]


def run_reminder(payload: dict | str, *, cwd: Path) -> HookRun:
    """Run the reminder as the harness does, with `payload` (or raw text) on stdin."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(reminder_script())],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        timeout=30,
    )
    return HookRun(result.returncode, result.stdout, result.stderr)


def parse_line(line: str) -> tuple[int, int, str]:
    """`[turn-budget] <used> of <max> turns used. <action>` as (used, max, action)."""
    match = LINE_PATTERN.match(line)
    if match is None:
        raise AssertionError(f"the reminder does not follow its line grammar: {line!r}")
    return int(match.group(1)), int(match.group(2)), match.group(3)


def pre_tool_use_registrations() -> list[tuple[str | None, str]]:
    """Every (matcher, command) the plugin registers for PreToolUse."""
    manifest = json.loads(HOOKS_MANIFEST.read_text(encoding="utf-8"))
    groups = manifest.get("hooks", manifest).get("PreToolUse", [])
    return [
        (group.get("matcher"), hook.get("command", ""))
        for group in groups
        for hook in group.get("hooks", [])
    ]


def matches_every_tool(matcher: str | None) -> bool:
    """Whether a registration's matcher lets the hook see a call to any tool."""
    if matcher in (None, "", "*"):
        return True
    return all(re.fullmatch(matcher, tool) for tool in ("Bash", "Edit", "Read", "Write", "Agent"))
