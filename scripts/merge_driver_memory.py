#!/usr/bin/env python3
"""Git custom merge driver for .ai-state/memory.json.

Called by git during merge when .gitattributes routes memory.json here.
Performs semantic JSON merge: union of entries, updated_at wins for
duplicate keys, session counts summed.

Usage (via git config, not called directly):
    git config merge.memory-json.name "Semantic memory.json merge"
    git config merge.memory-json.driver "python3 scripts/merge_driver_memory.py %O %A %B"

Arguments (provided by git):
    %O — ancestor (common base)
    %A — ours (current branch) — result must be written here
    %B — theirs (merging branch)

Exit codes:
    0 — merge succeeded, result written to %A
    1 — merge failed, manual resolution needed
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import reconcile functions from sibling script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from reconcile_ai_state import reconcile_memory  # noqa: E402

import json  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <ancestor> <ours> <theirs>", file=sys.stderr)
        return 1

    _ancestor_path, ours_path, theirs_path = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        ours_text = Path(ours_path).read_text(encoding="utf-8")
        theirs_text = Path(theirs_path).read_text(encoding="utf-8")
    except OSError as e:
        print(f"Cannot read input files: {e}", file=sys.stderr)
        return 1

    try:
        merged = reconcile_memory(ours_text, theirs_text)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Semantic merge failed: {e}", file=sys.stderr)
        return 1

    # Write result to ours path (git expects the result there)
    Path(ours_path).write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
