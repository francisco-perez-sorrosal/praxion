"""SessionStart hook: inject Architecture Decision Record (ADR) context.

Reads ``.ai-state/decisions/DECISIONS_INDEX.md``, parses the markdown table,
filters to accepted/proposed ADRs, and injects the most recently authored
decisions as ``additionalContext`` at SessionStart. Architectural decisions
are hard constraints that should surface to every agent at the start of work.

This logic previously lived inside ``inject_memory.py``, where it shared a
character budget with memory injection and was gated behind the memory
kill-switch. It now stands alone so decision context survives independently
of any memory backend.

Behavior contract:
- Fail-open: any error exits 0 with no output; never blocks SessionStart.
- Kill-switch: ``PRAXION_DISABLE_DECISION_INJECTION=1`` disables injection.
- Degrades silently when the index is missing or holds no injectable rows.

Synchronous hook (async: false). Exit 0 unconditionally -- must never
block session creation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from _hook_utils import is_disabled

# -- Constants ----------------------------------------------------------------

DISABLE_FLAG = "PRAXION_DISABLE_DECISION_INJECTION"

ADR_SOFT_CAP = 2000  # char budget for injected decision context
_ADR_HEADER = "## Decision Context (auto-injected)\n\n"

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

    # Inject the most recently authored decisions first: they are the ones most
    # likely to constrain current work. Rows arrive in index order (oldest
    # dec-NNN first), so the soft cap would otherwise surface only the earliest
    # decisions. Sort by (date, id) descending before applying the cap.
    rows = sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True)

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


def _emit_additional_context(context: str) -> None:
    """Emit additionalContext for SessionStart.

    SubagentStart additionalContext is silently ignored by Claude Code --
    use PreToolUse(Agent) with updatedInput for subagent context injection.
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


def main() -> None:
    # Drain stdin even when disabled -- stdin must be consumed or the hook
    # framework may SIGPIPE on its write end.
    try:
        raw = sys.stdin.read()
    except OSError:
        raw = ""

    if is_disabled(DISABLE_FLAG):
        return

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()

    index_path = Path(cwd) / ".ai-state" / "decisions" / "DECISIONS_INDEX.md"
    index_content = _read_decisions_index(index_path)
    if index_content is None:
        return

    rows = _parse_index_rows(index_content)
    if not rows:
        return

    body = _build_adr_output(rows, budget=ADR_SOFT_CAP)
    if not body:
        return

    _emit_additional_context(f"{_ADR_HEADER}{body}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
