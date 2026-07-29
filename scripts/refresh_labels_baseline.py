#!/usr/bin/env python3
"""Refresh a project's `.github/labels.yml` `baseline:` block from the shipped
label-taxonomy manifest template, preserving the project's `additional:`
block (and any comments around either key) untouched.

Used by `/upgrade-project` when Praxion has added new label families since a
project's manifest was installed or last refreshed.

Usage: python scripts/refresh_labels_baseline.py <shipped-template-path> <project-manifest-path>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _find_key_line_index(lines: list[str], key: str) -> int:
    """Return the index of the top-level `<key>:` line."""
    pattern = re.compile(rf"^{re.escape(key)}:")
    for index, line in enumerate(lines):
        if pattern.match(line):
            return index
    raise ValueError(f"top-level key {key!r} not found")


def _leading_comment_start(lines: list[str], key_index: int) -> int:
    """Walk upward from `key_index` while the preceding line is a top-level
    (column-0) comment, returning the index of the first such comment line."""
    start = key_index
    while start > 0 and lines[start - 1].startswith("#"):
        start -= 1
    return start


def _is_top_level_line(line: str) -> bool:
    """A non-blank line starting at column 0 marks the next top-level key
    (or its leading comment) — the boundary of the current block."""
    return bool(line) and not line[0].isspace()


def _block_end(lines: list[str], key_index: int) -> int:
    """Return the index one past the last line belonging to the block that
    starts at `key_index` — the first subsequent top-level line, or EOF."""
    for index in range(key_index + 1, len(lines)):
        if _is_top_level_line(lines[index]):
            return index
    return len(lines)


def _extract_block(text: str, key: str) -> tuple[list[str], int, int]:
    """Return `(lines, block_start, block_end)` for the top-level `<key>:`
    block, including any contiguous comment lines immediately preceding it."""
    lines = text.split("\n")
    key_index = _find_key_line_index(lines, key)
    block_start = _leading_comment_start(lines, key_index)
    block_end = _block_end(lines, key_index)
    return lines, block_start, block_end


def refresh_baseline_block(shipped_template_text: str, project_manifest_text: str) -> str:
    """Replace the project manifest's `baseline:` block (plus its leading
    comment header) with the shipped template's, leaving every other line —
    including the `additional:` block and its own comments — untouched.

    Pure and deterministic: same inputs always produce the same output, and
    refreshing an already-current manifest a second time is a no-op.
    """
    shipped_lines, shipped_start, shipped_end = _extract_block(shipped_template_text, "baseline")
    project_lines, project_start, project_end = _extract_block(project_manifest_text, "baseline")

    result_lines = (
        project_lines[:project_start]
        + shipped_lines[shipped_start:shipped_end]
        + project_lines[project_end:]
    )
    return "\n".join(result_lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: read the shipped template and project manifest paths
    from argv, refresh the baseline block, and write the result back to the
    project manifest path in place."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(
            "usage: refresh_labels_baseline.py <shipped-template-path> <project-manifest-path>",
            file=sys.stderr,
        )
        return 1

    shipped_path = Path(args[0])
    project_path = Path(args[1])
    shipped_text = shipped_path.read_text(encoding="utf-8")
    project_text = project_path.read_text(encoding="utf-8")

    refreshed = refresh_baseline_block(shipped_text, project_text)
    project_path.write_text(refreshed, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
