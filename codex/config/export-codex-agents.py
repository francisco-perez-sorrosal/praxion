#!/usr/bin/env python3
"""Export Praxion Markdown agents to Codex custom-agent TOML files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FRONTMATTER_BOUNDARY = "---"
SKIP_AGENT_FILES = {"CLAUDE.md", "README.md"}


class AgentParseError(ValueError):
    """Raised when an agent file cannot be converted safely."""


def parse_frontmatter_agent(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_BOUNDARY:
        raise AgentParseError(f"{path} is missing YAML frontmatter")

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_BOUNDARY:
            end_index = index
            break
    if end_index is None:
        raise AgentParseError(f"{path} has unterminated YAML frontmatter")

    metadata = parse_simple_yaml(lines[1:end_index], path)
    body = "\n".join(lines[end_index + 1 :]).strip() + "\n"
    return metadata, body


def parse_simple_yaml(lines: list[str], path: Path) -> dict[str, str]:
    """Parse the YAML subset used by Praxion agent frontmatter.

    This avoids adding a PyYAML dependency for an installer/export helper.
    It supports scalar values and folded block scalars (`>` / `>-`).
    """

    metadata: dict[str, str] = {}
    index = 0
    key_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")

    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            index += 1
            continue

        match = key_pattern.match(line)
        if not match:
            raise AgentParseError(f"{path}: unsupported frontmatter line: {line!r}")

        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if raw_value in {">", ">-"}:
            block: list[str] = []
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line and not next_line.startswith((" ", "\t")):
                    break
                block.append(next_line.strip())
                index += 1
            metadata[key] = " ".join(part for part in block if part).strip()
            continue

        metadata[key] = raw_value.strip('"').strip("'")
        index += 1

    for required in ("name", "description"):
        if not metadata.get(required):
            raise AgentParseError(f"{path}: missing required frontmatter key: {required}")
    return metadata


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_codex_agent(metadata: dict[str, str], source_path: Path) -> str:
    name = metadata["name"]
    description = metadata["description"]
    developer_instructions = (
        "You are a Codex wrapper for the Praxion "
        f"`{name}` agent. Before doing task work, read the canonical agent "
        f"definition at `{source_path.as_posix()}` and follow it as your "
        "primary role instructions. Also apply the Praxion behavioral "
        "contract: Surface Assumptions, Register Objection, Stay Surgical, "
        "Simplicity First. Do not treat this wrapper as a fork of the agent; "
        "the source file is authoritative."
    )

    return "\n".join(
        [
            f"name = {toml_string(name)}",
            f"description = {toml_string(description)}",
            f"developer_instructions = {toml_string(developer_instructions)}",
            "",
        ]
    )


def export_agents(repo_root: Path, out_dir: Path) -> list[Path]:
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        raise AgentParseError(f"Agents directory not found: {agents_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in sorted(agents_dir.glob("*.md")):
        if source_path.name in SKIP_AGENT_FILES:
            continue
        metadata, _body = parse_frontmatter_agent(source_path)
        target_path = out_dir / f"{metadata['name']}.toml"
        relative_source = source_path.relative_to(repo_root)
        target_path.write_text(
            render_codex_agent(metadata, relative_source),
            encoding="utf-8",
        )
        written.append(target_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_agents(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
