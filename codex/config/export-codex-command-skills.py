#!/usr/bin/env python3
"""Export Praxion slash commands to Codex skill wrappers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FRONTMATTER_BOUNDARY = "---"
SKIP_COMMAND_FILES = {"CLAUDE.md", "README.md"}


class CommandParseError(ValueError):
    """Raised when a command file cannot be converted safely."""


def parse_frontmatter_command(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_BOUNDARY:
        raise CommandParseError(f"{path} is missing YAML frontmatter")

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_BOUNDARY:
            end_index = index
            break
    if end_index is None:
        raise CommandParseError(f"{path} has unterminated YAML frontmatter")

    metadata = parse_simple_yaml(lines[1:end_index], path)
    body = "\n".join(lines[end_index + 1 :]).strip() + "\n"
    return metadata, body


def parse_simple_yaml(lines: list[str], path: Path) -> dict[str, str]:
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
            raise CommandParseError(f"{path}: unsupported frontmatter line: {line!r}")

        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if raw_value in {">", ">-", "|", "|-"}:
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

        if raw_value.startswith("'") and raw_value.endswith("'"):
            metadata[key] = raw_value[1:-1].replace("''", "'")
        elif raw_value.startswith('"') and raw_value.endswith('"'):
            metadata[key] = raw_value[1:-1]
        else:
            metadata[key] = raw_value
        index += 1

    if not metadata.get("description"):
        raise CommandParseError(f"{path}: missing required frontmatter key: description")
    return metadata


def yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_codex_command_skill(
    command_name: str,
    metadata: dict[str, str],
    source_path: Path,
) -> str:
    description = metadata["description"]
    argument_hint = metadata.get("argument-hint", "")

    lines = [
        "---",
        f"name: praxion-command-{command_name}",
        f"description: {yaml_single_quote(description)}",
        "---",
        "",
        f"# /{command_name}",
        "",
        "This is a Codex command-skill wrapper for a Praxion slash command.",
        "",
        f"Before running this workflow, read the canonical command definition at `{source_path.as_posix()}` and follow it as the authoritative source.",
        "Do not treat this wrapper as a fork; it exists only to expose Praxion commands through Codex's documented skill activation surface.",
        "",
        "Preserve the original slash-command semantics:",
        "",
        f"- Invoke this workflow when the user asks for `/{command_name}` or names `praxion-command-{command_name}`.",
        "- Treat any user text after the command name as `$ARGUMENTS`.",
        "- Derive `$1`, `$2`, and later positional arguments by splitting `$ARGUMENTS` on shell-style whitespace.",
        "- Treat Claude `allowed-tools` frontmatter as the command's intended tool boundary; in Codex, use available equivalent tools and respect the active sandbox and approval policy.",
        "- Interpret command-body `!` shell snippets and `@` file references as instructions to gather that context with Codex tools before executing the workflow.",
        "- Keep all substantive behavior in the canonical command file; update `commands/*.md` in Praxion when command behavior changes.",
    ]
    if argument_hint:
        lines.extend(["", f"Argument hint: `{argument_hint}`"])
    lines.append("")
    return "\n".join(lines)


def export_command_skills(repo_root: Path, out_dir: Path) -> list[Path]:
    commands_dir = repo_root / "commands"
    if not commands_dir.is_dir():
        raise CommandParseError(f"Commands directory not found: {commands_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in sorted(commands_dir.glob("*.md")):
        if source_path.name in SKIP_COMMAND_FILES:
            continue
        metadata, _body = parse_frontmatter_command(source_path)
        command_name = source_path.stem
        target_dir = out_dir / f"praxion-command-{command_name}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "SKILL.md"
        target_path.write_text(
            render_codex_command_skill(command_name, metadata, source_path.resolve()),
            encoding="utf-8",
        )
        written.append(target_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_command_skills(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
