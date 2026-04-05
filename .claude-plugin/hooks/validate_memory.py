"""SubagentStop hook: block subagent completion when significant work was done
without calling remember().

Scans the agent transcript for Write/Edit tool calls and for remember()
calls. If the agent made substantial edits but never persisted learnings,
blocks completion (exit 2) with a stderr message.

Synchronous hook (async: false). Uses exit 2 + stderr for blocking.
Exit 0 unconditionally on second invocation or when thresholds are not met.
"""

from __future__ import annotations

import json
import sys

# Read-only agents that should never be blocked for memory
EXEMPT_AGENTS = frozenset(
    {
        "Explore",
        "i-am:sentinel",
        "i-am:doc-engineer",
        "Plan",
    }
)

MIN_EDITS_FOR_SIGNIFICANT = 5
REMEMBER_TOOL_SUBSTRING = "remember"
SIGNIFICANT_TOOLS = frozenset({"Write", "Edit"})


def _scan_transcript(transcript_path: str) -> tuple[int, int, bool]:
    """Scan transcript for work and remember() indicators.

    Returns (edit_count, remember_count, wrote_learnings).
    """
    edit_count = 0
    remember_count = 0
    wrote_learnings = False

    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    turn = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if turn.get("type") != "assistant":
                    continue

                message = turn.get("message", {})
                content = message.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if block.get("type") != "tool_use":
                        continue

                    name = block.get("name", "")
                    tool_input = block.get("input", {})

                    if name in SIGNIFICANT_TOOLS:
                        edit_count += 1
                        file_path = tool_input.get("file_path", "")
                        if "LEARNINGS" in file_path:
                            wrote_learnings = True

                    if REMEMBER_TOOL_SUBSTRING in name.lower():
                        remember_count += 1
    except OSError:
        pass

    return edit_count, remember_count, wrote_learnings


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    agent_type = payload.get("agent_type", "")

    # Exempt read-only or documentation agents
    if agent_type in EXEMPT_AGENTS:
        return

    transcript_path = payload.get("agent_transcript_path")
    if not transcript_path:
        return

    edit_count, remember_count, wrote_learnings = _scan_transcript(transcript_path)

    significant_work = edit_count >= MIN_EDITS_FOR_SIGNIFICANT

    if significant_work and remember_count == 0:
        detail = f"{edit_count} file edits"
        if wrote_learnings:
            detail += " including LEARNINGS.md"

        message = (
            f"[validate-memory] Agent [{agent_type}] did significant work "
            f"({detail}) but never called remember(). Before completing, "
            f"evaluate whether you discovered gotchas, patterns, or conventions "
            f"worth persisting. Call remember() for cross-session insights, "
            f"then finish. If nothing is worth remembering, you can complete again."
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
