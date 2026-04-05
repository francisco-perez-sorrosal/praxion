"""SessionStart + SubagentStart hook: inject memory and decision context.

Fires at both SessionStart (main agent) and SubagentStart (subagents),
ensuring every agent sees curated memory and architectural decisions
from the first turn. Detects the event type from the payload and sets
hookEventName accordingly.

Two independent data sources, combined into a single additionalContext:

1. Memory context -- reads .ai-state/memory.json with LOCK_SH, formats
   active entries as Markdown-KV with importance-based tiering and
   agent-type-aware category prioritization.

2. Decision context -- reads .ai-state/decisions/DECISIONS_INDEX.md,
   parses the markdown table, filters to accepted/proposed ADRs, and
   formats as rich semantic lines. Soft-capped at ADR_SOFT_CAP chars.

ADRs get first priority in the shared MAX_INJECT_CHARS budget --
architectural decisions are hard constraints that should never be
dropped. Memory fills the remaining space, with its own importance
tiering handling budget pressure gracefully. Either source can be
missing -- the hook degrades silently, emitting whichever context
is available.

Synchronous hook (async: false). Exit 0 unconditionally -- must never
block agent creation.
"""

from __future__ import annotations

import fcntl
import json
import sys
from pathlib import Path

# -- Constants ----------------------------------------------------------------

MAX_INJECT_CHARS = 8000
ADR_SOFT_CAP = 2000  # soft cap for ADR content; trimmed when many ADRs exist

# Section headers and join separator — budgeted so content doesn't overshoot
_ADR_HEADER = "## Decision Context (auto-injected)\n\n"
_MEM_HEADER = "## Memory Context (auto-injected)\n\n"
_SECTION_JOIN = "\n\n"
# Reserved overhead when both sections are present
_MAX_OVERHEAD = len(_ADR_HEADER) + len(_MEM_HEADER) + len(_SECTION_JOIN)

IMPORTANCE_TIER_1 = 7  # always inject
IMPORTANCE_TIER_2 = 4  # inject if budget allows
# tier 3 (1-3): search-only, never injected

# DECISIONS_INDEX.md table column positions (0-based, after splitting on "|")
_ADR_COL_ID = 0
_ADR_COL_TITLE = 1
_ADR_COL_STATUS = 2
_ADR_COL_CATEGORY = 3
_ADR_COL_DATE = 4
_ADR_COL_TAGS = 5
_ADR_COL_SUMMARY = 6
_ADR_EXPECTED_COLS = 7

_ADR_INJECTABLE_STATUSES = frozenset({"accepted", "proposed"})

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


def _build_tiered_output(
    entries: list[dict], agent_type: str, budget: int = MAX_INJECT_CHARS
) -> str:
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
    HEADER_ESTIMATE = 35  # "## <category> (NN entries)\n" ~ 35 chars
    FOOTER_RESERVE = 60  # reserve for truncation footer if needed

    for entry in tier1 + tier2:
        line = _format_entry_line(entry)
        line_cost = len(line) + 1  # +1 for newline
        if entry["category"] not in seen_categories:
            line_cost += HEADER_ESTIMATE  # account for new category header
        if char_count + line_cost > budget - FOOTER_RESERVE:
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


# -- ADR (Architecture Decision Record) injection -----------------------------


def _read_decisions_index(index_path: Path) -> str | None:
    """Read DECISIONS_INDEX.md. Returns raw text or None on any error."""
    try:
        if not index_path.exists():
            return None
        text = index_path.read_text(encoding="utf-8")
        return text if text.strip() else None
    except OSError:
        return None


def _parse_index_rows(content: str) -> list[dict]:
    """Parse the markdown table in DECISIONS_INDEX.md into a list of ADR dicts.

    Skips header, separator, metadata, and malformed rows. Filters to
    accepted/proposed status only.
    """
    rows: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        # Skip header row and separator row
        if line.startswith("| ID") or line.startswith("|-"):
            continue

        # Split on "|", strip the empty first/last elements from leading/trailing "|"
        cols = [c.strip() for c in line.split("|")]
        # Remove empty strings from leading/trailing "|"
        if cols and cols[0] == "":
            cols = cols[1:]
        if cols and cols[-1] == "":
            cols = cols[:-1]

        if len(cols) < _ADR_EXPECTED_COLS:
            continue

        status = cols[_ADR_COL_STATUS].lower()
        if status not in _ADR_INJECTABLE_STATUSES:
            continue

        rows.append(
            {
                "id": cols[_ADR_COL_ID],
                "title": cols[_ADR_COL_TITLE],
                "status": status,
                "category": cols[_ADR_COL_CATEGORY],
                "date": cols[_ADR_COL_DATE],
                "tags": cols[_ADR_COL_TAGS],
                "summary": cols[_ADR_COL_SUMMARY],
            }
        )
    return rows


def _format_adr_line(row: dict) -> str:
    """Format a single ADR row in rich semantic format."""
    return f"- **{row['id']}** {row['title']} ({row['status']}): {row['summary']} [{row['tags']}]"


def _build_adr_output(rows: list[dict], budget: int) -> str:
    """Format ADR rows into injectable Markdown, respecting the character budget.

    Adds entries one by one until min(budget, ADR_SOFT_CAP) is reached.
    When budget is ample and total content fits under the soft cap, all entries
    are included without truncation.
    """
    if not rows:
        return ""

    effective_cap = min(budget, ADR_SOFT_CAP)
    footer_reserve = 60  # reserve for truncation footer if needed
    lines: list[str] = []
    char_count = 0
    included = 0

    for row in rows:
        line = _format_adr_line(row)
        line_cost = len(line) + 1  # +1 for newline
        if char_count + line_cost > effective_cap - footer_reserve:
            break
        lines.append(line)
        char_count += line_cost
        included += 1

    if not lines:
        return ""

    result = "\n".join(lines)

    omitted = len(rows) - included
    if omitted > 0:
        result += f"\n\n... and {omitted} more decisions (see .ai-state/decisions/)"

    return result


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    cwd = payload.get("cwd", ".")
    agent_type = _resolve_agent_type(payload)

    # Reserve space for section headers and join separator so content stays
    # within MAX_INJECT_CHARS when wrapped with headers.
    content_budget = MAX_INJECT_CHARS - _MAX_OVERHEAD

    # -- ADR context (first priority: architectural decisions are hard constraints)
    adr_body = ""
    index_path = Path(cwd) / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
    index_content = _read_decisions_index(index_path)
    if index_content is not None:
        adr_rows = _parse_index_rows(index_content)
        if adr_rows:
            adr_body = _build_adr_output(adr_rows, budget=content_budget)

    # -- Memory context (fills remaining budget after decisions) ---------------
    memory_body = ""
    memory_path = Path(cwd) / ".ai-state" / "memory.json"
    if memory_path.exists():
        data = _read_with_lock(memory_path)
        if data is not None:
            memories = data.get("memories", {})
            if memories:
                entries = _collect_active_entries(memories)
                if entries:
                    remaining = content_budget - len(adr_body)
                    if remaining > 0:
                        memory_body = _build_tiered_output(
                            entries, agent_type, budget=remaining
                        )

    # -- Combine and emit -----------------------------------------------------
    sections = []
    if adr_body:
        sections.append(f"{_ADR_HEADER}{adr_body}")
    if memory_body:
        sections.append(f"{_MEM_HEADER}{memory_body}")

    # Memory obligation footer — the only reliable injection point for agents
    _OBLIGATION = (
        "---\n"
        "**Memory obligation**: Before completing, evaluate whether you "
        "discovered a gotcha, pattern, convention, or architectural insight "
        "that future agents should know. If yes, call "
        "`remember(category, key, value, tags, importance, summary, type)`. "
        "This is not optional — the memory gate will block session completion "
        "if significant work was done without any remember() calls."
    )
    sections.append(_OBLIGATION)

    context = _SECTION_JOIN.join(sections)
    if not context:
        return

    # Detect event type: SubagentStart payloads have agent_type,
    # SessionStart payloads do not. hookEventName must match the
    # triggering event or additionalContext is silently ignored.
    is_subagent = bool(payload.get("agent_type"))
    event_name = "SubagentStart" if is_subagent else "SessionStart"

    output = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
