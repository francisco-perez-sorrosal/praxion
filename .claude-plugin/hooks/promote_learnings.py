"""PreToolUse hook: warn before LEARNINGS.md cleanup.

Fires on Bash commands that might delete .ai-work/ directories.
Scans for LEARNINGS.md files and surfaces promotion candidates.
Synchronous hook (async: false) -- shows warning before proceeding.
Exit 0 unconditionally.
"""

import json
import re
import sys
from pathlib import Path

CLEANUP_PATTERNS = [
    r"rm\s+.*\.ai-work",
    r"clean.work",
]

ENTRY_PREFIX = "- **["


def _is_cleanup_command(command: str) -> bool:
    """Check if the command targets .ai-work/ for deletion."""
    return any(re.search(p, command) for p in CLEANUP_PATTERNS)


def _count_entries(content: str) -> int:
    """Count tagged entries (lines starting with '- **[') in LEARNINGS.md."""
    return sum(
        1 for line in content.splitlines() if line.strip().startswith(ENTRY_PREFIX)
    )


def _find_learnings(cwd: str) -> list[tuple[str, int]]:
    """Find LEARNINGS.md files with unpromoted entries under .ai-work/."""
    ai_work = Path(cwd) / ".ai-work"
    if not ai_work.exists():
        return []

    results = []
    for learnings_file in ai_work.rglob("LEARNINGS.md"):
        try:
            content = learnings_file.read_text(encoding="utf-8")
            entry_count = _count_entries(content)
            if entry_count > 0:
                rel_path = learnings_file.relative_to(Path(cwd))
                results.append((str(rel_path), entry_count))
        except OSError:
            continue

    return results


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return

    tool_name = payload.get("tool_name", "")
    if tool_name != "Bash":
        return

    command = payload.get("tool_input", {}).get("command", "")
    if not _is_cleanup_command(command):
        return

    cwd = payload.get("cwd", ".")
    learnings = _find_learnings(cwd)
    if not learnings:
        return

    files_list = "\n".join(f"- {path}: {count} entries" for path, count in learnings)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"LEARNINGS.md files found with unpromoted content:\n"
                f"{files_list}\n\n"
                f"Consider running `/cajalogic dream` or calling `remember()` "
                f"for cross-session insights before cleanup."
            ),
        }
    }
    print(json.dumps(output))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
