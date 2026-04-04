"""Lifecycle hook: capture session and agent events as memory observations.

Fires on SessionStart, Stop, SubagentStart, SubagentStop.
Async hook (async: true) -- never blocks.
Exit 0 unconditionally.
"""

from __future__ import annotations

import fcntl
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EVENT_MAP = {
    "SessionStart": "session_start",
    "Stop": "session_stop",
    "SubagentStart": "agent_start",
    "SubagentStop": "agent_stop",
}


def _build_summary(event_type: str, payload: dict) -> str:
    """Build a human-readable summary for lifecycle events."""
    agent_type = payload.get("agent_type", "")
    description = payload.get("description", "")

    if event_type == "session_start":
        return "Session started"
    if event_type == "session_stop":
        return "Session ended"
    if event_type == "agent_start":
        label = description or agent_type or "unknown"
        return f"Agent started: {label[:150]}"
    if event_type == "agent_stop":
        label = description or agent_type or "unknown"
        return f"Agent completed: {label[:150]}"
    return event_type


def _append_observation(obs_path: Path, observation: dict) -> None:
    """Append a single observation to the JSONL file with exclusive locking."""
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = obs_path.parent / "observations.lock"
    lock_path.touch(exist_ok=True)

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            with open(obs_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(observation, separators=(",", ":")) + "\n")
                f.flush()
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    hook_event = payload.get("hook_event_name", "")
    event_type = EVENT_MAP.get(hook_event)
    if event_type is None:
        return

    cwd = payload.get("cwd", ".")
    ai_state_dir = Path(cwd) / ".ai-state"
    if not ai_state_dir.exists():
        return  # graceful degradation

    obs_path = ai_state_dir / "observations.jsonl"
    summary = _build_summary(event_type, payload)
    session_id = payload.get("session_id", "")
    agent_id = payload.get("agent_id", "") or session_id  # main agent uses session_id

    observation = {
        "timestamp": datetime.now(UTC).isoformat(),
        "session_id": session_id,
        "agent_type": payload.get("agent_type", "main"),
        "agent_id": agent_id,
        "project": Path(cwd).name,
        "event_type": event_type,
        "tool_name": None,
        "summary": summary,
        "file_paths": [],
        "outcome": None,
        "classification": None,
    }

    _append_observation(obs_path, observation)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
