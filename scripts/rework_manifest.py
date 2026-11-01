#!/usr/bin/env python3
"""Deterministic substrate for REWORK_MANIFEST.md generation.

Pure functions with no I/O — filesystem interaction happens in the calling
layer (verifier Phase 12.5).  These three functions are the single source
of truth for the row-ID formula, JSON block extraction, and table rendering.
"""

from __future__ import annotations

import hashlib
import json
import re

_COLUMNS = ["#", "Worktree", "Agent", "Severity", "Tier", "Class", "Headline"]

_FIELD_MAP = {
    "#": "row_number",
    "Worktree": "worktree_name",
    "Agent": "target_agent",
    "Severity": "severity",
    "Tier": "recommended_tier",
    "Class": "class",
    "Headline": "headline",
}

_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def compute_row_id(report_id: str, cluster_signature: str) -> str:
    """Return ``rw-<sha1(report_id + cluster_signature)[:8]>``."""
    digest = hashlib.sha1((report_id + cluster_signature).encode()).hexdigest()
    return f"rw-{digest[:8]}"


def parse_json_blocks(manifest_text: str) -> list[dict]:
    """Extract per-row fenced JSON blocks; skip malformed blocks silently."""
    rows: list[dict] = []
    for match in _JSON_BLOCK_RE.finditer(manifest_text):
        try:
            rows.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return rows


def render_table_from_rows(rows: list[dict]) -> str:
    """Render a markdown table + per-row JSON blocks from row dicts.

    The rendered output round-trips through ``parse_json_blocks`` losslessly.
    """
    header = "| " + " | ".join(_COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in _COLUMNS) + " |"
    table_lines = [header, separator]
    for idx, row in enumerate(rows, start=1):
        cells: list[str] = []
        for col in _COLUMNS:
            if col == "#":
                cells.append(str(idx))
            else:
                value = row.get(_FIELD_MAP[col], "")
                cells.append(f"`{value}`" if col == "Worktree" else str(value))
        table_lines.append("| " + " | ".join(cells) + " |")

    block_lines: list[str] = ["\n## Row details"]
    for idx, row in enumerate(rows, start=1):
        worktree = row.get("worktree_name", f"row-{idx}")
        block_lines.append(f"\n### Row {idx} — {worktree}\n")
        block_lines.append("```json")
        block_lines.append(json.dumps(row, indent=2))
        block_lines.append("```")

    return "\n".join(table_lines) + "\n" + "\n".join(block_lines) + "\n"
