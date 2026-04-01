#!/usr/bin/env python3
"""Forward Claude Code hook events to the Task Chronograph server via HTTP POST.
Exits 0 unconditionally -- must never block agent execution.
"""

import hashlib, json, os, re, sys, urllib.request  # noqa: E401

PROGRESS_MARKER = "PROGRESS.md"
DEFAULT_PORT = 8765
PORT_RANGE_SIZE = 1000


def _derive_port(project_dir):
    """Derive a deterministic port from the project directory.

    Must match the logic in server.py:derive_port() so hooks POST to the
    correct chronograph instance when multiple projects run simultaneously.
    """
    if not project_dir:
        return DEFAULT_PORT
    digest = hashlib.sha256(os.path.abspath(project_dir).encode()).digest()
    offset = int.from_bytes(digest[:2], "big") % PORT_RANGE_SIZE
    return DEFAULT_PORT + offset


PROGRESS_LINE_RE = re.compile(
    r"\[([^\]]+)\]\s+\[([^\]]+)\]\s+(?:Phase\s+(\d+)/(\d+):\s+(\S+)\s+--\s+)?(.+)"
)


def _post(port, path, payload):
    """POST JSON to the Chronograph server. Log failures to stderr."""
    try:
        req = urllib.request.Request(
            f"http://localhost:{port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        sys.stderr.write(f"chronograph: POST {path} to :{port} failed: {e}\n")


def _parse_last_progress_line(content):
    """Parse the last non-empty line from PROGRESS.md content."""
    lines = [line for line in content.strip().splitlines() if line.strip()]
    if not lines:
        return None
    match = PROGRESS_LINE_RE.match(lines[-1].strip())
    if not match:
        return None
    ts, agent, phase, total, phase_name, rest = match.groups()
    return {
        "agent_type": agent,
        "phase": int(phase) if phase else 0,
        "total_phases": int(total) if total else 0,
        "phase_name": phase_name or "",
        "message": rest.split("#")[0].strip(),
    }


def _agent_label(data):
    """Best available human-readable label for the agent in this hook payload."""
    agent_type = data.get("agent_type", "")
    if agent_type:
        return agent_type
    # Prefer description (human-readable) over agent_id (UUID-like)
    description = data.get("description", "")
    if description:
        return description[:50]
    return data.get("agent_id", "") or "unknown-agent"


def _truncate(text, max_bytes=4096):
    """Truncate text to max_bytes, appending '...' if truncated."""
    if not text or len(text) <= max_bytes:
        return text or ""
    return text[:max_bytes] + "..."


def _summarize_tool_input(data):
    """Build a short summary of tool input from the hook payload."""
    tool_input = data.get("tool_input", {})
    if isinstance(tool_input, str):
        return _truncate(tool_input)
    # Common patterns: file_path, command, pattern, content
    parts = []
    for key in ("file_path", "command", "pattern", "query", "prompt", "url"):
        if key in tool_input:
            parts.append(f"{key}={tool_input[key]}")
    return _truncate(", ".join(parts)) if parts else _truncate(json.dumps(tool_input))


def _summarize_tool_output(data):
    """Build a short summary of tool output from the hook payload."""
    output = data.get("tool_response", data.get("tool_output", ""))
    if isinstance(output, dict):
        output = json.dumps(output)
    return _truncate(str(output) if output else "")


def _project_dir(data):
    """Get project directory from hook payload (cwd) or environment fallback."""
    return data.get("cwd", "") or os.environ.get("CLAUDE_PROJECT_DIR", "")


def _build_events(data):
    """Map a Claude Code hook payload to Chronograph events + interactions."""
    hook = data.get("hook_event_name", "")
    sid = data.get("session_id", "")
    aid = data.get("agent_id", "")
    proj = _project_dir(data)
    events = []
    interactions = []

    if hook == "SessionStart":
        events.append(
            {
                "event_type": "session_start",
                "agent_type": "",
                "session_id": sid,
                "project_dir": proj,
            }
        )

    elif hook == "Stop":
        events.append(
            {
                "event_type": "session_stop",
                "agent_type": "",
                "session_id": sid,
                "project_dir": proj,
            }
        )

    elif hook == "SubagentStart":
        agent = data.get("agent_type", "")
        label = _agent_label(data)
        events.append(
            {
                "event_type": "agent_start",
                "agent_type": agent or label,
                "session_id": sid,
                "agent_id": aid,
                "parent_session_id": sid,
                "message": f"Agent {label} started",
                "project_dir": proj,
            }
        )
        interactions.append(
            {
                "source": "main_agent",
                "target": aid or agent or label,
                "summary": f"Delegated to {label}",
                "interaction_type": "delegation",
            }
        )

    elif hook == "SubagentStop":
        agent = data.get("agent_type", "")
        label = _agent_label(data)
        events.append(
            {
                "event_type": "agent_stop",
                "agent_type": agent or label,
                "session_id": sid,
                "agent_id": aid,
                "parent_session_id": sid,
                "message": f"Agent {label} stopped",
                "project_dir": proj,
            }
        )
        transcript = data.get("agent_transcript_path", "")
        if transcript:
            events[-1]["metadata"] = {"agent_transcript_path": transcript}
        interactions.append(
            {
                "source": aid or agent or label,
                "target": "main_agent",
                "summary": f"{label} returned results",
                "interaction_type": "result",
            }
        )

    elif hook == "PostToolUse":
        tool_name = data.get("tool_name", "")
        fp = data.get("tool_input", {}).get("file_path", "")

        # Always emit a tool_use event for every tool call
        events.append(
            {
                "event_type": "tool_use",
                "agent_type": data.get("agent_type", ""),
                "agent_id": aid,
                "session_id": sid,
                "tool_name": tool_name,
                "project_dir": proj,
                "metadata": {
                    "input_summary": _summarize_tool_input(data),
                    "output_summary": _summarize_tool_output(data),
                },
            }
        )

        # Additionally detect PROGRESS.md writes for phase transitions
        if PROGRESS_MARKER in fp:
            content = data.get("tool_input", {}).get("content", "")
            if not content:
                content = data.get("tool_input", {}).get("new_string", "")
            parsed = _parse_last_progress_line(content) if content else None
            if parsed:
                events.append(
                    {
                        "event_type": "phase_transition",
                        "agent_type": parsed["agent_type"],
                        "agent_id": aid,
                        "session_id": sid,
                        "phase": parsed["phase"],
                        "total_phases": parsed["total_phases"],
                        "phase_name": parsed["phase_name"],
                        "message": parsed["message"],
                        "project_dir": proj,
                    }
                )

    elif hook == "PostToolUseFailure":
        tool_name = data.get("tool_name", "")
        error_msg = data.get("error", data.get("message", "Tool call failed"))
        if isinstance(error_msg, dict):
            error_msg = json.dumps(error_msg)
        events.append(
            {
                "event_type": "error",
                "agent_type": data.get("agent_type", ""),
                "agent_id": aid,
                "session_id": sid,
                "tool_name": tool_name,
                "message": str(error_msg),
                "project_dir": proj,
                "metadata": {
                    "input_summary": _summarize_tool_input(data),
                },
            }
        )

    return events, interactions


def main():
    try:
        data = json.loads(sys.stdin.read())
        events, interactions = _build_events(data)
        # Explicit env var overrides, otherwise derive from project dir
        if os.environ.get("CHRONOGRAPH_PORT"):
            port = int(os.environ["CHRONOGRAPH_PORT"])
        else:
            port = _derive_port(data.get("cwd", ""))
        for event in events:
            _post(port, "/api/events", event)
        for interaction in interactions:
            _post(port, "/api/interactions", interaction)
    except Exception as e:
        sys.stderr.write(f"chronograph hook: {e}\n")


if __name__ == "__main__":
    main()
