"""Stop hook: block session end when significant work was done without remember().

Scans the transcript for Write/Edit/Agent tool calls and for remember()
calls. If the session did substantial work but never persisted learnings
to memory, blocks the stop (exit 2) with a stderr message prompting the
agent to call remember().

Synchronous hook (async: false). Uses exit 2 + stderr for blocking.
Checks stop_hook_active to prevent infinite loops.
"""

from __future__ import annotations

import json
import sys

# Thresholds — tune these based on experience
MIN_EDITS_FOR_SIGNIFICANT = 3
REMEMBER_TOOL_SUBSTRING = "remember"
SIGNIFICANT_TOOLS = frozenset({"Write", "Edit"})
DELEGATION_TOOLS = frozenset({"Agent"})


def _scan_transcript(transcript_path: str) -> tuple[int, int, bool]:
    """Scan transcript for work indicators.

    Returns (edit_count, remember_count, spawned_agents).
    """
    edit_count = 0
    remember_count = 0
    spawned_agents = False

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

                    if name in SIGNIFICANT_TOOLS:
                        edit_count += 1
                    elif name in DELEGATION_TOOLS:
                        spawned_agents = True
                    elif REMEMBER_TOOL_SUBSTRING in name.lower():
                        remember_count += 1
    except OSError:
        pass

    return edit_count, remember_count, spawned_agents


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    # Prevent infinite loops — second invocation after a block
    if payload.get("stop_hook_active"):
        return

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return

    edit_count, remember_count, spawned_agents = _scan_transcript(transcript_path)

    significant_work = edit_count >= MIN_EDITS_FOR_SIGNIFICANT or spawned_agents

    if significant_work and remember_count == 0:
        detail = []
        if edit_count > 0:
            detail.append(f"{edit_count} file edits")
        if spawned_agents:
            detail.append("agent delegation")
        work_summary = ", ".join(detail)

        message = (
            f"[memory-gate] You did significant work this session ({work_summary}) "
            f"but never called remember(). Before finishing, review what you learned "
            f"and call remember(category, key, value, tags, importance, summary, type) "
            f"for any gotchas, patterns, conventions, or insights that future agents "
            f"should know. If nothing is worth remembering, you can stop again."
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
        pass  # fail-open — never crash the session
