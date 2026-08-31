#!/usr/bin/env python3
"""Regenerate DECISIONS_INDEX.md from ADR file frontmatter.

Reads all ADR files in .ai-state/decisions/, extracts YAML frontmatter,
and generates a markdown index table sorted by ID.

Usage:
    python scripts/regenerate_adr_index.py                 # write the index
    python scripts/regenerate_adr_index.py --check          # read-only: diff, no write
    python scripts/regenerate_adr_index.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _repo_root import is_plugin_cache_path
from _repo_root import resolve_repo_root as _resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent
DECISIONS_DIR = SCRIPT_DIR.parent / ".ai-state" / "decisions"
INDEX_PATH = DECISIONS_DIR / "DECISIONS_INDEX.md"


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver."""
    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR)


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


def _narrowing_ids(raw_superseded_in_part_by: str) -> list[str]:
    """Parse the (already-inline-normalized) `superseded_in_part_by` value into ids."""
    if not raw_superseded_in_part_by:
        return []
    if raw_superseded_in_part_by.startswith("[") and raw_superseded_in_part_by.endswith("]"):
        inner = raw_superseded_in_part_by[1:-1]
        if not inner.strip():
            return []
        return [item.strip().strip('"').strip("'") for item in inner.split(",")]
    return [raw_superseded_in_part_by]


def format_status_cell(status: str, raw_superseded_in_part_by: str) -> str:
    """`accepted (narrowed by dec-NNN[, dec-MMM...])` when the record is narrowed."""
    narrowing_ids = _narrowing_ids(raw_superseded_in_part_by)
    if not narrowing_ids:
        return status
    return f"{status} (narrowed by {', '.join(narrowing_ids)})"


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
        status = format_status_cell(adr["status"], adr.get("superseded_in_part_by", ""))
        category = adr["category"]
        date = adr["date"]
        tags = format_tags(adr.get("tags", ""))
        summary = adr["summary"]

        lines.append(
            f"| {adr_id} | {title} | {status} | {category} | {date} | {tags} | {summary} |"
        )

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser. Unknown flags exit 2 without touching the index."""
    parser = argparse.ArgumentParser(
        description="Regenerate DECISIONS_INDEX.md from ADR file frontmatter.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root to operate against (defaults to the resolved repo root).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only: regenerate the index in memory and diff against the "
        "committed file. Exits 0 if identical, 1 with a summary if stale. "
        "Never writes.",
    )
    return parser


def _run_check(index_content: str, adr_count: int) -> int:
    """Diff freshly generated content against the committed file. No writes."""
    on_disk = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.is_file() else None
    if on_disk == index_content:
        print(f"{INDEX_PATH} is up to date ({adr_count} entries).")
        return 0
    print(f"{INDEX_PATH} is stale ({adr_count} entries in source of truth).", file=sys.stderr)
    print("Run without --check to regenerate.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> None:
    """Entry point: collect ADRs, then either check (read-only) or write the index."""
    args = _build_arg_parser().parse_args(argv)

    root = resolve_repo_root(args.repo_root)
    if is_plugin_cache_path(root):
        print(
            f"refusing to regenerate index against a plugin-cache path: {root}",
            file=sys.stderr,
        )
        sys.exit(1)
    apply_repo_root(root)
    adrs = collect_adrs()
    index_content = generate_index(adrs)

    if args.check:
        sys.exit(_run_check(index_content, len(adrs)))

    INDEX_PATH.write_text(index_content, encoding="utf-8")
    print(f"Generated {INDEX_PATH} with {len(adrs)} entries.")


if __name__ == "__main__":
    main()
