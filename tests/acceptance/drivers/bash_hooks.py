"""Driver for the hook that judges Bash calls before they run: the commit gate.

It is reached as the harness reaches a command hook: the event's JSON payload on stdin, the
registered command line run with `${CLAUDE_PLUGIN_ROOT}` the plugin root.

Bound here, because the base commit or the harness fixes it: the commit gate is
`hooks/commit_gate.sh [--blocking] <checker>`; whether it started its checker is observed with a
stand-in checker that records each start in a file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMIT_GATE = REPO_ROOT / "hooks" / "commit_gate.sh"
SESSION = "session-bash-hooks"


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
