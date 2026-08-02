#!/usr/bin/env python3
"""
Export repo commands/*.md to Cursor-compatible .cursor/commands/*.md.

Cursor slash commands are plain Markdown (no YAML frontmatter). This script
strips frontmatter from commands/*.md and writes the body to .cursor/commands/,
optionally prepending Description and Arguments from frontmatter.
Source of truth remains commands/*.md; run from repo root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def split_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Frontmatter is between first --- and second ---."""
    if not content.strip().startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_block = parts[1]
    fm = {}
    for line in fm_block.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.+)$", line.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1].replace('\\"', '"')
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1].replace("\\'", "'")
            fm[key] = val
    return fm, parts[2].lstrip("\n")


def export_commands(repo_root: Path, out_dir: Path) -> None:
    """Read commands/*.md, write plain .cursor/commands/*.md."""
    commands_dir = repo_root / "commands"
    if not commands_dir.is_dir():
        sys.exit("commands/ not found")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Remove stale exports (commands deleted from repo)
    source_names = {p.name for p in commands_dir.glob("*.md") if p.name.lower() != "readme.md"}
    for existing in out_dir.glob("*.md"):
        if existing.name not in source_names:
            existing.unlink()
            print(f"  Removed stale: {existing.name}")

    for path in sorted(commands_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8")
        fm, body = split_frontmatter(text)
        description = fm.get("description", "")
        argument_hint = fm.get("argument-hint", "")

        lines = []
        if description:
            lines.append(f"**Description:** {description}\n")
        if argument_hint:
            lines.append(f"**Arguments:** {argument_hint}\n")
        if lines:
            lines.append("---\n")
        lines.append(body)

        out_path = out_dir / path.name
        out_path.write_text("".join(lines), encoding="utf-8")
        print(f"  {path.name} -> {out_path}")


def main() -> None:
    repo_root = (
        Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent.parent
    )
    out_dir = (
        Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else repo_root / ".cursor" / "commands"
    )
    export_commands(repo_root, out_dir)


if __name__ == "__main__":
    main()
