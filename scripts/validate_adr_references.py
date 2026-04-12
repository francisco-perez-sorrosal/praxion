#!/usr/bin/env python3
"""Validate that every `affected_files:` entry in every ADR resolves on disk.

Reports orphan references (file listed in an ADR but missing from the
filesystem) as warnings. Exits non-zero if any orphan is found, so this can
be wired into CI or a pre-commit hook later.

Usage:
    python3 scripts/validate_adr_references.py           # scan and report
    python3 scripts/validate_adr_references.py --quiet   # only print orphans
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / ".ai-state" / "decisions"


def parse_affected_files(text: str) -> list[str]:
    """Extract file paths from an ADR's `affected_files` frontmatter field.

    Supports both inline-list (`["a", "b"]`) and block-list (`- a\n  - b`)
    YAML forms. Returns paths exactly as written in the ADR.
    """
    frontmatter = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not frontmatter:
        return []

    fm = frontmatter.group(1)
    inline = re.search(r"^affected_files:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if inline:
        return [
            p.strip().strip('"').strip("'")
            for p in inline.group(1).split(",")
            if p.strip()
        ]

    block = re.search(r"^affected_files:\s*\n((?:\s+-\s.*\n)+)", fm, re.MULTILINE)
    if block:
        return [
            line.split("-", 1)[1].strip().strip('"').strip("'")
            for line in block.group(1).splitlines()
        ]

    return []


def main() -> int:
    quiet = "--quiet" in sys.argv
    adrs = sorted(ADR_DIR.glob("[0-9]*.md"))
    orphans: list[tuple[str, str]] = []
    scanned = 0

    for adr in adrs:
        text = adr.read_text()
        for path in parse_affected_files(text):
            scanned += 1
            target = REPO_ROOT / path
            if not target.exists():
                orphans.append((adr.name, path))

    if not quiet:
        print(f"Scanned {scanned} affected_files references across {len(adrs)} ADRs")

    if orphans:
        print(f"\nOrphan references ({len(orphans)}):", file=sys.stderr)
        for adr_name, path in orphans:
            print(f"  {adr_name}: {path}", file=sys.stderr)
        return 1

    if not quiet:
        print("All references resolve on disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
