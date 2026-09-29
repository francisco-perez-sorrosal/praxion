"""Driver for the task-brief reminder, reached only as a PreToolUse hook.

The harness runs the hook as a subprocess, writes the spawn's JSON payload to
its stdin, and reads an optional JSON object from its stdout. This driver does
the same and nothing more: it never imports the hook.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
REMINDER = _REPO_ROOT / "hooks" / "remind_task_brief.py"

ADVISORY_PREFIX = "[task-brief-reminder]"


def spawn_payload(
    prompt: str,
    cwd: Path,
    *,
    subagent_type: str = "praxion:systems-architect",
    tool_name: str = "Agent",
) -> dict:
    """The PreToolUse payload the harness sends for an Agent (or Task) spawn."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "cwd": str(cwd),
        "session_id": "acceptance",
        "tool_input": {
            "subagent_type": subagent_type,
            "description": "spawn",
            "prompt": prompt,
        },
    }


@dataclass(frozen=True)
class HookRun:
    exit_code: int
    stdout: str

    def advisories(self) -> list[dict]:
        """Every JSON object printed on stdout, in order."""
        decoder = json.JSONDecoder()
        objects, text, index = [], self.stdout, 0
        while True:
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                return objects
            obj, index = decoder.raw_decode(text, index)
            objects.append(obj)


def run_reminder(payload: dict) -> HookRun:
    env = dict(os.environ)
    env.pop("PRAXION_DISABLE_TASK_BRIEF_REMINDER", None)
    result = subprocess.run(
        [sys.executable, str(REMINDER)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=payload["cwd"],
        env=env,
        timeout=30,
    )
    return HookRun(exit_code=result.returncode, stdout=result.stdout)


def new_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True, timeout=30)
    return path


def write_brief(repo: Path, slug: str) -> None:
    brief = repo / ".ai-work" / slug / "TASK_BRIEF.md"
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("# Task Brief\n", encoding="utf-8")
