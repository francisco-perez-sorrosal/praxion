#!/usr/bin/env python3
"""Regenerate DECISIONS_INDEX.md from ADR file frontmatter.

Reads all ADR files in .ai-state/decisions/, extracts YAML frontmatter,
and generates a markdown index table sorted by ID.

Usage: python scripts/regenerate_adr_index.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DECISIONS_DIR = SCRIPT_DIR.parent / ".ai-state" / "decisions"
INDEX_PATH = DECISIONS_DIR / "DECISIONS_INDEX.md"


def _git_toplevel_from_cwd() -> Path | None:
    """Resolve the repo root from the process CWD via git.

    A bare `git rev-parse --show-toplevel` (no `cwd` override) returns the
    consumer's repo even when this script runs from a symlinked plugin cache,
    where `Path(__file__).resolve()` would follow the symlink to the plugin.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return Path(out) if out else None


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root: explicit `--repo-root` > git-root > script-relative."""
    if cli_repo_root:
        return Path(cli_repo_root).resolve()
    git_root = _git_toplevel_from_cwd()
    if git_root is not None:
        return git_root.resolve()
    return SCRIPT_DIR.parent


def apply_repo_root(root: Path) -> None:
    """Rebind the module-level path constants to a resolved repo root."""
    global DECISIONS_DIR, INDEX_PATH
    DECISIONS_DIR = root / ".ai-state" / "decisions"
    INDEX_PATH = DECISIONS_DIR / "DECISIONS_INDEX.md"


# Match files like 001-slug.md, 012-another-slug.md
ADR_FILENAME_PATTERN = re.compile(r"^\d{3}-.+\.md$")

FRONTMATTER_DELIMITER = "---"

REQUIRED_FIELDS = ("id", "title", "status", "category", "date", "summary", "tags")

INDEX_HEADER = """# Decisions Index

Auto-generated from ADR frontmatter. Do not edit manually.
Regenerate: `python scripts/regenerate_adr_index.py`

| ID | Title | Status | Category | Date | Tags | Summary |
|----|-------|--------|----------|------|------|---------|"""


def parse_frontmatter(content: str) -> dict[str, str]:
    """Extract YAML frontmatter as key-value pairs using simple line parsing.

    Handles scalar values (strings, unquoted values), inline lists [a, b, c],
    and block-style lists (key: followed by indented "- item" lines).
    Block lists are normalized to the inline-bracket form so downstream
    formatters can treat both shapes uniformly. Does not depend on PyYAML.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}

    frontmatter_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_DELIMITER:
            break
        frontmatter_lines.append(line)
    else:
        return {}

    result: dict[str, str] = {}
    block_key: str | None = None
    block_items: list[str] = []

    def flush_block() -> None:
        nonlocal block_key, block_items
        if block_key is not None and block_items:
            result[block_key] = "[" + ", ".join(f'"{item}"' for item in block_items) + "]"
        block_key = None
        block_items = []

    for line in frontmatter_lines:
        block_item = re.match(r"^\s+-\s*(.+)$", line)
        if block_item and block_key is not None:
            item = block_item.group(1).strip()
            if (item.startswith('"') and item.endswith('"')) or (
                item.startswith("'") and item.endswith("'")
            ):
                item = item[1:-1]
            block_items.append(item)
            continue

        match = re.match(r"^(\w[\w_]*)\s*:\s*(.*)$", line)
        if match:
            flush_block()
            key = match.group(1)
            value = match.group(2).strip()
            if value == "":
                block_key = key
                continue
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            result[key] = value

    flush_block()
    return result


def format_tags(raw_tags: str) -> str:
    """Format a YAML list value into a readable comma-separated string.

    Handles both inline lists [a, b, c] and bare values.
    """
    if raw_tags.startswith("[") and raw_tags.endswith("]"):
        inner = raw_tags[1:-1]
        items = [item.strip().strip('"').strip("'") for item in inner.split(",")]
        return ", ".join(items)
    return raw_tags


def collect_adrs() -> list[dict[str, str]]:
    """Read all ADR files and return parsed frontmatter sorted by ID."""
    if not DECISIONS_DIR.is_dir():
        return []

    adrs: list[dict[str, str]] = []
    for path in sorted(DECISIONS_DIR.iterdir()):
        if not ADR_FILENAME_PATTERN.match(path.name):
            continue

        content = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(content)

        missing = [f for f in REQUIRED_FIELDS if f not in frontmatter]
        if missing:
            print(
                f"Warning: {path.name} missing required fields: {', '.join(missing)}",
                file=sys.stderr,
            )
            continue

        adrs.append(frontmatter)

    return adrs


def generate_index(adrs: list[dict[str, str]]) -> str:
    """Generate the full index markdown content."""
    lines = [INDEX_HEADER]

    for adr in adrs:
        adr_id = adr["id"]
        title = adr["title"]
        status = adr["status"]
        category = adr["category"]
        date = adr["date"]
        tags = format_tags(adr.get("tags", ""))
        summary = adr["summary"]

        lines.append(
            f"| {adr_id} | {title} | {status} | {category} | {date} | {tags} | {summary} |"
        )

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _parse_repo_root_arg() -> str | None:
    """Extract `--repo-root <path>` from argv, if present."""
    if "--repo-root" in sys.argv:
        idx = sys.argv.index("--repo-root")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return None


def main() -> None:
    """Entry point: collect ADRs, generate index, write to file."""
    apply_repo_root(resolve_repo_root(_parse_repo_root_arg()))
    adrs = collect_adrs()
    index_content = generate_index(adrs)
    INDEX_PATH.write_text(index_content, encoding="utf-8")

    print(f"Generated {INDEX_PATH} with {len(adrs)} entries.")


if __name__ == "__main__":
    main()
