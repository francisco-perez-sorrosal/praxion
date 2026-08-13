"""PostToolUse hook: capture tool events as append-only observations.

LEGACY FILENAME (retained for hook-registration stability). This is an
*observability* hook — it appends a JSONL line to `.ai-state/observations.jsonl`,
not curated memory. The `capture_memory` name predates dec-225's removal of the
in-house memory subsystem; it is kept because the filename is referenced from
`hooks/hooks.json`, the plugin manifest, and the Codex bridge generator, and a
rename would churn all of those for no behavioral gain. If a future change
touches those registration sites anyway, rename to `capture_observations.py`
then. Functionally this is the observations-WAL writer (see dec-248).

Extracts structured fields using pattern matching (no LLM calls).
Appends a single JSONL line to .ai-state/observations.jsonl.
Async hook (async: true) -- never blocks.
Exit 0 unconditionally.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from _hook_utils import DISABLE_OBSERVABILITY, append_observation, is_disabled

# Tools that generate too much noise to capture
BLOCKLIST = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        "TodoRead",
        "TodoWrite",
        "TaskList",
        "TaskGet",
        "TaskUpdate",
        "TaskCreate",
        "TaskOutput",
        "TaskStop",
        "ToolSearch",
    }
)

# Max length for summary/description fields to keep observations compact
MAX_SUMMARY_LEN = 200


def classify_event(tool_name: str, file_paths: list[str], command: str = "") -> str:
    """Classify a tool event based on tool name, file paths, and command content."""
    if tool_name in ("Write", "Edit"):
        for fp in file_paths:
            if ".ai-state/decisions/" in fp:
                return "decision"
            if "test_" in fp or "_test." in fp:
                return "test"
            if "src/" in fp:
                return "implementation"
            if fp.endswith(".md"):
                return "documentation"
            config_extensions = (".json", ".toml", ".yaml", ".yml")
            if any(fp.endswith(ext) for ext in config_extensions):
                return "configuration"
        return "implementation"
    if tool_name == "Bash":
        if re.search(r"\bgit\s+commit\b", command):
            return "commit"
        if re.search(r"\b(pytest|uv\s+run\s+pytest|python\s+-m\s+pytest)\b", command):
            return "test"
        if re.search(r"\b(ruff|mypy|pyright|eslint|prettier)\b", command):
            return "lint"
        if re.search(r"\bgit\s+(push|pull|fetch|merge|rebase)\b", command):
            return "git"
        if re.search(r"\b(pip|uv|npm|yarn|pnpm)\s+install\b", command):
            return "dependency"
        return "command"
    if tool_name == "Agent":
        return "delegation"
    return "tool_use"


def extract_file_paths(tool_input: dict, tool_name: str) -> list[str]:
    """Extract file paths from tool input."""
    paths: list[str] = []
    if "file_path" in tool_input:
        paths.append(str(tool_input["file_path"]))
    if "path" in tool_input:
        p = str(tool_input["path"])
        if p not in paths:
            paths.append(p)
    if "pattern" in tool_input and tool_name == "Grep":
        pass  # pattern is a regex, not a file path
    return paths


def _truncate(text: str, max_len: int = MAX_SUMMARY_LEN) -> str:
    """Truncate text to max_len, appending '...' if truncated."""
    if not text or len(text) <= max_len:
        return text or ""
    return text[:max_len] + "..."


def build_summary(tool_name: str, tool_input: dict, classification: str) -> str:
    """Build a human-readable one-line summary of what the tool did."""
    if tool_name in ("Write", "Edit"):
        fp = tool_input.get("file_path", "?")
        return _truncate(f"{tool_name} {fp}")
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        if desc:
            return _truncate(desc)
        return _truncate(cmd)
    if tool_name == "Agent":
        desc = tool_input.get("description", "")
        agent_type = tool_input.get("subagent_type", "")
        prompt_preview = _truncate(tool_input.get("prompt", ""), 80)
        parts = [f"Spawn {agent_type}" if agent_type else "Spawn agent"]
        if desc:
            parts.append(f"— {desc}")
        elif prompt_preview:
            parts.append(f"— {prompt_preview}")
        return _truncate(" ".join(parts))
    if tool_name == "Skill":
        skill = tool_input.get("skill", "")
        return f"Activate skill: {skill}"
    # Generic: summarize the input keys
    parts = []
    for key in ("query", "prompt", "pattern", "url", "skill"):
        if key in tool_input:
            parts.append(f"{key}={_truncate(str(tool_input[key]), 80)}")
    return _truncate(", ".join(parts)) if parts else tool_name


def build_observation(payload: dict) -> dict:
    """Assemble an observation record from a completed PostToolUse payload.

    Pure function -- reads only ``payload`` and performs no I/O, so the
    classification branches are unit-testable without a stdin/subprocess
    harness (mirrors the ``classify_event``/``build_summary``/
    ``extract_file_paths`` extraction pattern already in this file).

    A ``tool_name == "Skill"`` call is recorded as a first-class
    ``skill_activation`` event carrying a top-level ``skill_name``; every
    other tool stays a generic ``tool_use`` event. Both event types populate
    the identical envelope so the merge dedup key and all downstream readers
    stay valid.
    """
    tool_name = payload.get("tool_name", "")
    cwd = payload.get("cwd", ".")

    tool_input = payload.get("tool_input", {})
    if isinstance(tool_input, str):
        tool_input = {}

    file_paths = extract_file_paths(tool_input, tool_name)
    command = tool_input.get("command", "") if tool_name == "Bash" else ""
    classification = classify_event(tool_name, file_paths, command)
    summary = build_summary(tool_name, tool_input, classification)

    tool_response = payload.get("tool_response", {})
    has_error = isinstance(tool_response, dict) and tool_response.get("error")
    outcome = "failure" if has_error else "success"

    session_id = payload.get("session_id", "")
    agent_id = payload.get("agent_id", "") or session_id  # main agent uses session_id

    # Correlation: W3C trace-context IDs may be surfaced by a tool handler via
    # ``tool_response["additionalContext"]``. Missing/malformed additionalContext
    # degrades silently to empty strings (the common case -- no in-tree tool
    # currently populates these fields).
    additional_context = (
        tool_response.get("additionalContext", {}) if isinstance(tool_response, dict) else {}
    )
    if not isinstance(additional_context, dict):
        additional_context = {}
    trace_id = str(additional_context.get("trace_id") or "")
    span_id = str(additional_context.get("span_id") or "")
    parent_span_id = str(additional_context.get("parent_span_id") or "")

    event_type = "skill_activation" if tool_name == "Skill" else "tool_use"

    observation = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "agent_type": payload.get("agent_type", "main"),
        "agent_id": agent_id,
        "project": Path(cwd).name,
        "event_type": event_type,
        "tool_name": tool_name,
        "summary": summary,
        "file_paths": file_paths,
        "outcome": outcome,
        "classification": classification,
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
    }

    if tool_name == "Skill":
        observation["skill_name"] = tool_input.get("skill", "")

    return observation


def main() -> None:
    if is_disabled(DISABLE_OBSERVABILITY):
        return

    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(payload, dict):
        return  # well-formed but non-object JSON ([], null, "str", 123) -- no fields to read

    tool_name = payload.get("tool_name", "")
    if tool_name in BLOCKLIST:
        return

    cwd = payload.get("cwd", ".")
    ai_state_dir = Path(cwd) / ".ai-state"
    if not ai_state_dir.exists():
        return  # graceful degradation

    obs_path = ai_state_dir / "observations.jsonl"
    observation = build_observation(payload)
    append_observation(obs_path, observation)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
