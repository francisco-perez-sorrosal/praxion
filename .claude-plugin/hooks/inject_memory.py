"""SubagentStart hook: inject memory context into every agent.

Reads .ai-state/memory.json directly, formats active entries as
Markdown-KV with importance-based tiering and agent-type-aware category
prioritization.  Synchronous hook (async: false) -- completes in <50ms.

Concurrency: acquires LOCK_SH on .ai-state/memory.lock before reading
memory.json, so concurrent writers (via MCP server) do not see partial
reads.

Exit 0 unconditionally -- must never block agent creation.
"""

from __future__ import annotations

import fcntl
import json
import sys
from pathlib import Path

# -- Constants ----------------------------------------------------------------

MAX_INJECT_CHARS = 8000

IMPORTANCE_TIER_1 = 7  # always inject
IMPORTANCE_TIER_2 = 4  # inject if budget allows
# tier 3 (1-3): search-only, never injected

AGENT_CATEGORY_PRIORITIES: dict[str, list[str]] = {
    "implementer": [
        "learnings",
        "tools",
        "project",
        "user",
        "assistant",
        "relationships",
    ],
    "test-engineer": [
        "learnings",
        "tools",
        "project",
        "user",
        "assistant",
        "relationships",
    ],
    "systems-architect": [
        "project",
        "learnings",
        "user",
        "tools",
        "assistant",
        "relationships",
    ],
    "researcher": [
        "learnings",
        "project",
        "user",
        "tools",
        "assistant",
        "relationships",
    ],
    "promethean": [
        "project",
        "learnings",
        "relationships",
        "user",
        "tools",
        "assistant",
    ],
    "verifier": [
        "learnings",
        "project",
        "tools",
        "user",
        "assistant",
        "relationships",
    ],
    "sentinel": [
        "project",
        "learnings",
        "tools",
        "user",
        "assistant",
        "relationships",
    ],
    "context-engineer": [
        "project",
        "learnings",
        "tools",
        "user",
        "assistant",
        "relationships",
    ],
    "_default": [
        "learnings",
        "project",
        "user",
        "tools",
        "assistant",
        "relationships",
    ],
}


def _resolve_agent_type(payload: dict) -> str:
    """Extract agent type from payload, falling back to _default."""
    agent_type = payload.get("agent_type", "")
    if agent_type and agent_type in AGENT_CATEGORY_PRIORITIES:
        return agent_type

    # Try to derive from agent description
    description = payload.get("description", "").lower()
    for known_type in AGENT_CATEGORY_PRIORITIES:
        if known_type != "_default" and known_type in description:
            return known_type

    return "_default"


def _collect_active_entries(memories: dict) -> list[dict]:
    """Collect active (non-invalidated, non-superseded) entries with metadata."""
    entries = []
    for category, cat_entries in memories.items():
        if not isinstance(cat_entries, dict):
            continue
        for key, entry in cat_entries.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("invalid_at") is not None:
                continue
            if entry.get("status") == "superseded":
                continue
            entries.append(
                {
                    "category": category,
                    "key": key,
                    "importance": entry.get("importance", 5),
                    "summary": entry.get("summary", ""),
                    "value": entry.get("value", ""),
                    "tags": entry.get("tags", []),
                }
            )
    return entries


def _format_entry_line(entry: dict) -> str:
    """Format a single entry as a Markdown-KV line."""
    summary = entry["summary"]
    if not summary:
        value = entry["value"]
        summary = value[:100].rsplit(" ", 1)[0] if len(value) > 100 else value
    tags = entry["tags"]
    tag_str = f" [{', '.join(tags)}]" if tags else ""
    return f"- **{entry['key']}**: {summary}{tag_str}"


def _build_tiered_output(entries: list[dict], agent_type: str) -> str:
    """Build Markdown output respecting importance tiers and character budget.

    Tier 1 (importance >= 7): always injected, sorted by category priority.
    Tier 2 (importance 4-6): injected if budget allows, sorted by category priority.
    Tier 3 (importance 1-3): search-only, never injected.
    """
    priority_order = AGENT_CATEGORY_PRIORITIES.get(
        agent_type, AGENT_CATEGORY_PRIORITIES["_default"]
    )
    category_rank = {cat: idx for idx, cat in enumerate(priority_order)}

    def sort_key(entry: dict) -> tuple[int, int]:
        cat_rank = category_rank.get(entry["category"], len(priority_order))
        return (cat_rank, -entry["importance"])

    tier1 = [e for e in entries if e["importance"] >= IMPORTANCE_TIER_1]
    tier2 = [
        e for e in entries if IMPORTANCE_TIER_2 <= e["importance"] < IMPORTANCE_TIER_1
    ]

    tier1.sort(key=sort_key)
    tier2.sort(key=sort_key)

    # Build output respecting budget (including category header costs)
    selected: list[dict] = []
    char_count = 0
    seen_categories: set[str] = set()
    # Estimate header cost: "## <category> (NN entries)\n" ~ 35 chars per category
    HEADER_ESTIMATE = 35

    for entry in tier1 + tier2:
        line = _format_entry_line(entry)
        line_cost = len(line) + 1  # +1 for newline
        if entry["category"] not in seen_categories:
            line_cost += HEADER_ESTIMATE  # account for new category header
        if char_count + line_cost > MAX_INJECT_CHARS:
            break
        selected.append(entry)
        char_count += line_cost
        seen_categories.add(entry["category"])

    if not selected:
        return ""

    # Group selected entries by category for output (dict preserves insertion order)
    grouped: dict[str, list[str]] = {}
    for entry in selected:
        cat = entry["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(_format_entry_line(entry))

    sections = []
    for cat, lines in grouped.items():
        sections.append(f"## {cat} ({len(lines)} entries)")
        sections.extend(lines)

    result = "\n".join(sections)

    # Add truncation footer if entries were dropped
    total_active = len(tier1) + len(tier2)
    if len(selected) < total_active:
        omitted = total_active - len(selected)
        result += f"\n\n... and {omitted} more entries (use search to find them)"

    return result


def _read_with_lock(memory_path: Path) -> dict | None:
    """Read memory.json with a shared lock for concurrent safety.

    Returns the parsed data dict, or None if the file cannot be read.
    """
    lock_path = memory_path.parent / "memory.lock"

    lock_fd = None
    try:
        lock_path.touch(exist_ok=True)
        lock_fd = lock_path.open("r")
        fcntl.flock(lock_fd, fcntl.LOCK_SH)
    except OSError:
        # Lock file can't be created/opened -- proceed without lock (best effort)
        pass

    try:
        data = json.loads(memory_path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except OSError:
                pass


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    cwd = payload.get("cwd", ".")
    memory_path = Path(cwd) / ".ai-state" / "memory.json"

    if not memory_path.exists():
        return

    data = _read_with_lock(memory_path)
    if data is None:
        return

    memories = data.get("memories", {})
    if not memories:
        return

    entries = _collect_active_entries(memories)
    if not entries:
        return

    agent_type = _resolve_agent_type(payload)
    markdown = _build_tiered_output(entries, agent_type)
    if not markdown:
        return

    context = f"## Memory Context (auto-injected)\n\n{markdown}"

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
