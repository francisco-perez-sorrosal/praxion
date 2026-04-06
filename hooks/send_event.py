#!/usr/bin/env python3
"""Forward Claude Code hook events to the Task Chronograph server via HTTP POST.
Exits 0 unconditionally -- must never block agent execution.
"""

import hashlib, json, os, re, subprocess, sys, urllib.request  # noqa: E401

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


def _resolve_project_root(cwd):
    """Resolve the main repo root when running inside a git worktree.

    Worktrees have a different path than the main repo, but must derive the
    same chronograph port. Uses git-common-dir which points to the shared
    .git directory in the real repo for worktrees, or .git for regular clones.
    Falls back to cwd on any failure (non-git directory, missing git, etc.).
    """
    if not cwd:
        return cwd
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=cwd,
            timeout=2,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        abs_common = os.path.normpath(os.path.join(cwd, common))
        # common-dir is the .git directory; its parent is the project root
        if os.path.basename(abs_common) == ".git":
            return os.path.dirname(abs_common)
        return cwd
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return cwd


TASK_SLUG_RE = re.compile(r"Task\s+slug:\s*(\S+)")


def _git_context(cwd):
    """Capture current git branch and worktree info. Fail-open: returns empty dict."""
    if not cwd:
        return {}
    context = {}
    try:
        branch = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        context["git_branch"] = branch
    except Exception:
        pass
    try:
        toplevel = (
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=cwd,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        context["git_toplevel"] = toplevel
        git_dir = (
            subprocess.check_output(
                ["git", "rev-parse", "--git-dir"],
                cwd=cwd,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        common_dir = (
            subprocess.check_output(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=cwd,
                timeout=2,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
        # Worktree detection: git-dir differs from git-common-dir
        is_worktree = os.path.abspath(os.path.join(cwd, git_dir)) != os.path.abspath(
            os.path.join(cwd, common_dir)
        )
        context["is_worktree"] = is_worktree
        if is_worktree:
            context["worktree_name"] = os.path.basename(toplevel)
    except Exception:
        pass
    return context


def _extract_task_slug(description):
    """Extract task slug from agent description (e.g. 'Task slug: auth-flow')."""
    if not description:
        return ""
    match = TASK_SLUG_RE.search(description)
    return match.group(1) if match else ""


PROGRESS_LINE_RE = re.compile(
    r"\[([^\]]+)\]\s+\[([^\]]+)\]\s+(?:Phase\s+(\d+)/(\d+):\s+(\S+)\s+--\s+)?(.+)"
)

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|token|password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style
    re.compile(r"sk-ant-[a-zA-Z0-9]{20,}"),  # Anthropic-style
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub PAT
    re.compile(r"gho_[a-zA-Z0-9]{36}"),  # GitHub OAuth
    re.compile(r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}"),  # Fine-grained PAT
    re.compile(r"xox[bpoas]-[a-zA-Z0-9\-]+"),  # Slack tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
]


def _redact_secrets(text: str) -> str:
    """Replace common secret patterns with [REDACTED]."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


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
        return _redact_secrets(_truncate(tool_input))
    # Common patterns: file_path, command, pattern, content
    parts = []
    for key in ("file_path", "command", "pattern", "query", "prompt", "url"):
        if key in tool_input:
            parts.append(f"{key}={tool_input[key]}")
    return _redact_secrets(
        _truncate(", ".join(parts)) if parts else _truncate(json.dumps(tool_input))
    )


def _summarize_tool_output(data):
    """Build a short summary of tool output from the hook payload."""
    output = data.get("tool_response", data.get("tool_output", ""))
    if isinstance(output, dict):
        output = json.dumps(output)
    return _redact_secrets(_truncate(str(output) if output else ""))


def _project_dir(data):
    """Get project directory from hook payload (cwd) or environment fallback."""
    return data.get("cwd", "") or os.environ.get("CLAUDE_PROJECT_DIR", "")


_MCP_PRAXION_PREFIX = "mcp__plugin_i-am_"


def _classify_mcp_tool(tool_name):
    """Extract MCP server and tool name from Praxion MCP tool names.

    Returns (server, tool) tuple, or None if not a Praxion MCP tool.

    Claude Code MCP tool names use ``__`` as the primary delimiter, but
    the plugin name (``i-am``) and server name are joined with ``_`` inside
    the second segment. Actual format:
        mcp__plugin_i-am_<server>__<tool>
    Split on ``__`` gives: ``['mcp', 'plugin_i-am_<server>', '<tool>']``
    We strip the known prefix to get ``<server>__<tool>``, then split once.
    """
    if not tool_name.startswith(_MCP_PRAXION_PREFIX):
        return None
    remainder = tool_name[len(_MCP_PRAXION_PREFIX) :]
    if "__" in remainder:
        server, tool = remainder.split("__", 1)
    else:
        server = remainder
        tool = ""
    return (server, tool)


def _build_events(data):
    """Map a Claude Code hook payload to Chronograph events + interactions."""
    hook = data.get("hook_event_name", "")
    sid = data.get("session_id", "")
    aid = data.get("agent_id", "")
    proj = _project_dir(data)
    git = _git_context(proj)
    events = []
    interactions = []

    if hook == "SessionStart":
        events.append(
            {
                "event_type": "session_start",
                "agent_type": "",
                "session_id": sid,
                "project_dir": proj,
                "metadata": {"git": git},
            }
        )

    elif hook == "Stop":
        events.append(
            {
                "event_type": "session_stop",
                "agent_type": "",
                "session_id": sid,
                "project_dir": proj,
                "metadata": {"git": git},
            }
        )

    elif hook == "SubagentStart":
        agent = data.get("agent_type", "")
        label = _agent_label(data)
        description = data.get("description", "")
        task_slug = _extract_task_slug(data.get("prompt", "") or description)
        event = {
            "event_type": "agent_start",
            "agent_type": agent or label,
            "session_id": sid,
            "agent_id": aid,
            "parent_session_id": sid,
            "message": f"Agent {label} started",
            "project_dir": proj,
            "metadata": {"git": git},
        }
        if task_slug:
            event["metadata"]["task_slug"] = task_slug
        events.append(event)
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
        event = {
            "event_type": "agent_stop",
            "agent_type": agent or label,
            "session_id": sid,
            "agent_id": aid,
            "parent_session_id": sid,
            "message": f"Agent {label} stopped",
            "project_dir": proj,
        }
        transcript = data.get("agent_transcript_path", "")
        if transcript:
            event["metadata"] = {"agent_transcript_path": transcript}
        events.append(event)
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
        tool_input = data.get("tool_input", {})
        fp = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""

        # Detect Skill invocations
        if tool_name == "Skill":
            skill_name = (
                tool_input.get("skill", "") if isinstance(tool_input, dict) else ""
            )
            if skill_name:
                events.append(
                    {
                        "event_type": "skill_use",
                        "agent_type": data.get("agent_type", ""),
                        "agent_id": aid,
                        "session_id": sid,
                        "tool_name": f"skill:{skill_name}",
                        "project_dir": proj,
                        "metadata": {
                            "artifact_type": "skill",
                            "artifact_name": skill_name,
                            "args": tool_input.get("args", "")
                            if isinstance(tool_input, dict)
                            else "",
                        },
                    }
                )

        # Build metadata for tool_use event with MCP enrichment
        meta = {
            "input_summary": _summarize_tool_input(data),
            "output_summary": _summarize_tool_output(data),
        }
        mcp_info = _classify_mcp_tool(tool_name)
        if mcp_info:
            meta["artifact_type"] = "mcp_tool"
            meta["mcp_server"] = mcp_info[0]
            meta["mcp_tool"] = mcp_info[1]

        # Always emit a tool_use event for every tool call
        events.append(
            {
                "event_type": "tool_use",
                "agent_type": data.get("agent_type", ""),
                "agent_id": aid,
                "session_id": sid,
                "tool_name": tool_name,
                "project_dir": proj,
                "metadata": meta,
            }
        )

        # Additionally detect PROGRESS.md writes for phase transitions
        if PROGRESS_MARKER in fp:
            content = (
                tool_input.get("content", "") if isinstance(tool_input, dict) else ""
            )
            if not content:
                content = (
                    tool_input.get("new_string", "")
                    if isinstance(tool_input, dict)
                    else ""
                )
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
            port = _derive_port(_resolve_project_root(data.get("cwd", "")))
        for event in events:
            _post(port, "/api/events", event)
        for interaction in interactions:
            _post(port, "/api/interactions", interaction)
    except Exception as e:
        sys.stderr.write(f"chronograph hook: {e}\n")


if __name__ == "__main__":
    main()
