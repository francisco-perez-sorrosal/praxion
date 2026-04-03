"""SubagentStart hook: inject memory context into every agent.

Reads .ai-state/memory.json directly, formats active entries as
Markdown-KV, and injects via additionalContext. Synchronous hook
(async: false) — completes in <50ms.

Exit 0 unconditionally — must never block agent creation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _format_markdown_kv(memories: dict) -> str:
    """Format memory entries as Markdown-KV grouped by category."""
    sections = []
    for category in sorted(memories):
        entries = memories[category]
        if not entries:
            continue

        active = {}
        for key, entry in entries.items():
            if entry.get("invalid_at") is not None:
                continue
            if entry.get("status") == "superseded":
                continue
            active[key] = entry

        if not active:
            continue

        lines = [f"## {category} ({len(active)} entries)"]
        for key in sorted(active):
            entry = active[key]
            summary = entry.get("summary", "")
            if not summary:
                value = entry.get("value", "")
                summary = value[:100].rsplit(" ", 1)[0] if len(value) > 100 else value
            tags = entry.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- **{key}**: {summary}{tag_str}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    cwd = payload.get("cwd", ".")
    memory_path = Path(cwd) / ".ai-state" / "memory.json"

    if not memory_path.exists():
        return

    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    memories = data.get("memories", {})
    if not memories:
        return

    markdown = _format_markdown_kv(memories)
    if not markdown:
        return

    context = f"## Memory Context (auto-injected)\n\n{markdown}"

    output = {"hookSpecificOutput": {"additionalContext": context}}
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
