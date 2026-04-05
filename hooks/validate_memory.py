"""SubagentStop hook: block subagent completion when significant work was done
without calling remember().

Scans the agent transcript for tool usage patterns and for remember()
calls. If the agent did substantial work but never persisted learnings,
blocks completion (exit 2) with a stderr message.

Synchronous hook (async: false). Uses exit 2 + stderr for blocking.
On retry, re-scans — only passes if remember() was called or to break
infinite loops.
"""

from __future__ import annotations

import json
import sys

from _hook_utils import REMEMBER_PROMPT, scan_transcript

# Read-only agents that should never be blocked for memory
EXEMPT_AGENTS = frozenset(
    {
        "Explore",
        "i-am:sentinel",
        "i-am:doc-engineer",
        "Plan",
    }
)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    agent_type = payload.get("agent_type", "")

    if agent_type in EXEMPT_AGENTS:
        return

    transcript_path = payload.get("agent_transcript_path")
    if not transcript_path:
        return

    is_retry = bool(payload.get("stop_hook_active"))

    stats = scan_transcript(transcript_path)

    if not stats.has_unmemorized_work:
        return

    # Second attempt and still no remember() — let through to avoid infinite loop
    if is_retry:
        return

    message = (
        f"[validate-memory] Agent [{agent_type}] did significant work "
        f"({stats.work_summary}) but never called remember(). You MUST call the "
        f"mcp__plugin_i-am_memory__remember tool now before completing. "
        f"{REMEMBER_PROMPT}"
    )
    print(
        json.dumps({"decision": "block", "reason": message}),
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open
