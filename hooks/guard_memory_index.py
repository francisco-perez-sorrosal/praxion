#!/usr/bin/env python3
"""PreToolUse gate: a Write or Edit to a memory index may add only one-line pointers.

Claude Code loads a memory index (``MEMORY.md``) into every session, and an
agent's own index into every spawn of that agent, so an index line that turns
into a status paragraph is paid for on every start. This hook computes what the
pending Write or Edit would leave in the index and refuses it when the write
*adds* a line over 150 characters, adds content that is not a pointer, or grows
the index past the harness load limit. Lines already there never block a write,
so an index carrying old debt still takes a conforming new entry. The refusal
reason carries the convention, so the agent learns it at the moment it applies.

Which files count: ``<config>/projects/<project>/memory/MEMORY.md`` (a
project's auto-memory) and any ``agent-memory/<agent>/MEMORY.md`` (an agent's
own memory, user or project scope). ``<config>`` is ``$CLAUDE_CONFIG_DIR`` or
``~/.claude``. Every other path returns before the checker is imported.

The rules live in ``scripts/check_memory_index.py``, which ships with this hook
in the plugin, so it is imported from this file's location. Fail-open: any
internal error allows the write.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

INDEX_NAME = "MEMORY.md"
CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"


def is_memory_index(path: Path, config: Path) -> bool:
    """True for a project auto-memory index under `config`, or any agent-memory index."""
    if path.name != INDEX_NAME:
        return False
    if path.parent.parent.name == "agent-memory":
        return True
    project_memory = path.parent.name == "memory" and path.parent.parent.parent.name == "projects"
    return project_memory and path.resolve().is_relative_to(config.resolve())


def _after(tool_name: str, tool_input: dict, before: str) -> str | None:
    """The index text the pending write would leave, or None when it cannot be known."""
    if tool_name == "Write":
        return tool_input.get("content")
    if tool_name == "Edit":
        old, new = tool_input.get("old_string"), tool_input.get("new_string")
        if old is None or new is None or old not in before:
            return None
        return (
            before.replace(old, new)
            if tool_input.get("replace_all")
            else before.replace(old, new, 1)
        )
    return None


def main() -> None:
    payload = json.loads(sys.stdin.read())
    tool_input = payload.get("tool_input") or {}
    path = Path(tool_input.get("file_path") or "")
    config = Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")
    if not is_memory_index(path, config):
        return

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from check_memory_index import CONVENTION, gate_messages

    before = path.read_text(encoding="utf-8") if path.is_file() else ""
    after = _after(payload.get("tool_name", ""), tool_input, before)
    if after is None:
        return
    messages = gate_messages(before, after)
    if not messages:
        return
    reason = f"{CONVENTION} This write would add:\n" + "\n".join(f"- {m}" for m in messages)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
