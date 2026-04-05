#!/usr/bin/env python3
"""Memory enforcement gate -- blocks commits when significant work was done
without calling remember().

PreToolUse hook gated by commit_gate.sh. Scans the transcript for work
patterns and remember() calls. If significant work was done without any
remember() calls, blocks the commit via exit 2 so the agent must call
remember() before proceeding.

This closes the gap between SubagentStop (which enforces memory on subagents)
and Stop (which enforces memory at session end). The commit is a natural
checkpoint for "I'm done with this work phase" and the right place to
enforce memory persistence.

Exit code semantics (Claude Code hooks):
  exit 0 -- allow the action; stdout JSON (hookSpecificOutput) is processed
  exit 2 -- block the action; stdout is IGNORED, stderr is fed back to agent

Pure transcript scanning -- no LLM calls, no API keys required.
Blocks via exit 2 on PreToolUse (supported since Claude Code v2.1.90).
"""

import json
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__file__))

from _hook_utils import REMEMBER_PROMPT, scan_transcript  # noqa: E402

GIT_COMMIT_RE = re.compile(r"git\s+commit")
PREFIX = "[memory-gate:commit]"


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return

    stats = scan_transcript(transcript_path)

    if stats.remember_count > 0:
        return

    if not stats.has_significant_work:
        return

    print(
        f"{PREFIX} You did significant work ({stats.work_summary}) but "
        f"haven't called remember() yet. You MUST call "
        f"mcp__plugin_i-am_memory__remember now before committing.\n"
        f"{REMEMBER_PROMPT}",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open
