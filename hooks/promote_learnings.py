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

from _hook_utils import record_gate_fire

# Source-of-truth for cleanup detection. hooks/cleanup_gate.sh mirrors this
# pattern for the PreToolUse fast-path; Python remains authoritative. Keep in
# sync when editing either side.
#
# The operand shape: an optional leading quote, an optional path prefix
# ending in "/", the literal ".ai-work", and an optional "/<rest>" -- so a
# bare `.ai-work`, a quoted `".ai-work/slug"`, and an absolute
# `/abs/path/.ai-work/slug` all count as targeting the directory, while a
# longer token like `.ai-workflow` does not (the trailing lookahead requires
# the operand to end at whitespace/end-of-string right after ".ai-work" or
# its "/<rest>" suffix).
#
# Deliberately narrow scope (see hooks/test_promote_learnings.py's
# false-negative table for the exhaustive, tested list of what this does
# NOT catch):
#   - "rm" only. `find ... -delete`, `rmdir`, and `trash` are not matched.
#     A prior revision covered `find ... -delete` too, but closing it
#     precisely requires shell-aware parsing this regex cannot do without
#     reintroducing a wildcard-match false positive (`.ai-work` found
#     inside an unrelated glob argument). Two prior "precision" fixes each
#     traded one false-positive/negative class for another (see
#     LEARNINGS.md, rw-9a9c268a) -- this scope is deliberately narrow rather
#     than chasing the next edge case.
#   - No quote-awareness. Distinguishing a real invocation from a mention
#     embedded in another command's quoted argument (`echo 'run rm -rf
#     .ai-work/x later'`) needs the same shell-aware parsing. This hook is
#     advisory (exits 0 unconditionally) and fail-open, so the cost of
#     either direction of imprecision is a spurious or missed reminder, not
#     lost data -- an acceptable trade for a regex over raw command text.
_AI_WORK_OPERAND = r"[\"']?(?:\S*/)?\.ai-work(?:/\S*)?[\"']?(?=\s|$)"

CLEANUP_PATTERNS = [
    # "rm" as its own shell word (preceded by start-of-string or a separator,
    # never mid-word as in "confirm"), targeting .ai-work as an operand.
    rf"(?:^|[;&|\s])rm\b(?:\s+\S+)*\s+{_AI_WORK_OPERAND}",
]

ENTRY_PREFIX = "- **["


def _is_cleanup_command(command: str) -> bool:
    """Check if the command targets .ai-work/ for deletion.

    A plain regex match over the raw command text -- no shell parsing, no
    quote tracking. See the CLEANUP_PATTERNS comment and the false-negative
    table in test_promote_learnings.py for the documented, tested scope.
    """
    return any(re.search(pattern, command) for pattern in CLEANUP_PATTERNS)


def _count_entries(content: str) -> int:
    """Count tagged entries (lines starting with '- **[') in LEARNINGS.md."""
    return sum(1 for line in content.splitlines() if line.strip().startswith(ENTRY_PREFIX))


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

    decision = _check_and_warn(payload.get("cwd", "."))
    try:
        record_gate_fire("promote_learnings", decision, session_id=payload.get("session_id", ""))
    except Exception:
        pass


def _check_and_warn(cwd: str) -> str:
    """Warn about unpromoted LEARNINGS.md entries about to be deleted. Returns the decision."""
    learnings = _find_learnings(cwd)
    if not learnings:
        return "pass"

    files_list = "\n".join(f"- {path}: {count} entries" for path, count in learnings)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"LEARNINGS.md files found with unpromoted content:\n"
                f"{files_list}\n\n"
                f"Consider promoting these insights to a permanent home "
                f"(an ADR, a doc, or a rule) before cleanup — they are about "
                f"to be deleted with .ai-work/."
            ),
        }
    }
    print(json.dumps(output))
    return "warn"


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
