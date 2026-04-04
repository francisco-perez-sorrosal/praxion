"""SubagentStop hook: detect when agents write LEARNINGS.md without calling remember().

Parses the agent transcript to check whether memory tools were used.
Warns the parent agent if LEARNINGS.md was written but no remember()
was called. Async hook (async: true) — never blocks.

Exit 0 unconditionally — must never block agent completion.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _scan_transcript(transcript_path: str) -> tuple[bool, bool]:
    """Scan a JSONL transcript for memory writes and LEARNINGS.md writes.

    Returns (called_remember, wrote_learnings).
    """
    called_remember = False
    wrote_learnings = False

    path = Path(transcript_path)
    if not path.exists():
        return called_remember, wrote_learnings

    try:
        with path.open(encoding="utf-8") as f:
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

                    if "memory" in name and "remember" in name:
                        called_remember = True

                    if name in ("Write", "Edit"):
                        file_path = tool_input.get("file_path", "")
                        if "LEARNINGS" in file_path:
                            wrote_learnings = True
    except OSError:
        pass

    return called_remember, wrote_learnings


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    transcript_path = payload.get("agent_transcript_path")
    if not transcript_path:
        return

    called_remember, wrote_learnings = _scan_transcript(transcript_path)

    if wrote_learnings and not called_remember:
        agent_type = payload.get("agent_type", "unknown")
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": (
                    f"Note: Agent [{agent_type}] wrote to LEARNINGS.md but did not call "
                    f"remember(). Consider promoting cross-session insights to memory "
                    f"before cleanup."
                ),
            },
        }
        print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
