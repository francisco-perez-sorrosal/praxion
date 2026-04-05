"""Stop hook: block session end when significant work was done without remember().

Scans the transcript for tool usage patterns (edits, reads, searches,
agent delegation) and for remember() calls. If the session did substantial
work but never persisted learnings to memory, blocks the stop (exit 2).

Synchronous hook (async: false). Uses exit 2 + stderr for blocking.
On second attempt (stop_hook_active), re-scans the transcript — only
passes through if remember() was actually called or on the second block
to prevent infinite loops.
"""

from __future__ import annotations

import json
import sys

from _hook_utils import REMEMBER_PROMPT, scan_transcript


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    is_retry = payload.get("stop_hook_active", False)

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return

    stats = scan_transcript(transcript_path)

    if stats.remember_count > 0:
        return

    if not stats.has_significant_work:
        return

    # Second attempt and still no remember() — let through to avoid infinite loop
    if is_retry:
        return

    message = (
        f"[memory-gate] You did significant work ({stats.work_summary}) but never "
        f"called remember(). You MUST call the mcp__plugin_i-am_memory__remember "
        f"tool now before stopping. {REMEMBER_PROMPT}"
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
