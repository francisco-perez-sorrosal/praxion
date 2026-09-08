#!/usr/bin/env python3
"""Drop `memory: user` frontmatter from agents with zero WAL memory-write evidence (P1.8).

Explicit allowlist -- no heuristics. The list is derived from
`scripts/query_memory_write_evidence.py` run against the main checkout's WAL:
keep on any `praxion:*` agent with fewer than 5 recorded spawns (insufficient
sample) or >=1 recorded memory-write row under either marker filter; drop only
where spawns >= 5 AND writes == 0 under both filters. See
`.ai-work/process-economy-phase1/LEARNINGS.md § Decisions Made` for the
re-add-on-evidence rule.

Idempotent: skips a file that no longer carries a `memory:` line.

Usage:
    python3 scripts/strip_memory_frontmatter.py          # apply
    python3 scripts/strip_memory_frontmatter.py --check  # verify, exit 1 if stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit allowlist -- agents with >=5 recorded spawns and 0 recorded
# memory-write rows (both "agent-memory" and "/memory/" marker filters) in
# the main checkout's WAL as of 2026-09-08.
DROP_MEMORY_FRONTMATTER = [
    "agents/context-engineer.md",
    "agents/doc-engineer.md",
    "agents/implementation-planner.md",
    "agents/implementer.md",
    "agents/researcher.md",
    "agents/systems-architect.md",
    "agents/test-engineer.md",
]

MEMORY_LINE_RE = re.compile(r"^memory: user\n", re.MULTILINE)


def strip() -> list[Path]:
    touched = []
    for rel in DROP_MEMORY_FRONTMATTER:
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        new_text, n = MEMORY_LINE_RE.subn("", text, count=1)
        if n:
            path.write_text(new_text, encoding="utf-8")
            touched.append(path)
    return touched


def check() -> list[str]:
    violations = []
    for rel in DROP_MEMORY_FRONTMATTER:
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        if re.search(r"^memory: user$", text, re.MULTILINE):
            violations.append(f"{path}: still carries 'memory: user' frontmatter")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only, do not write")
    args = parser.parse_args()

    if args.check:
        violations = check()
        if violations:
            print(f"FAIL: {len(violations)} agent(s) still carry the dropped memory: field:")
            for v in violations:
                print(f"  - {v}")
            return 1
        print(f"OK: all {len(DROP_MEMORY_FRONTMATTER)} listed agents have no memory: frontmatter.")
        return 0

    touched = strip()
    print(f"Dropped 'memory: user' from {len(touched)} agent file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
