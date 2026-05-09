#!/usr/bin/env python3
"""Export Praxion skills to Codex skill wrappers with full descriptions."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


FRONTMATTER_BOUNDARY = "---"
SKIP_SKILL_FILES = {"CLAUDE.md", "README.md"}


class SkillParseError(ValueError):
    """Raised when a skill file cannot be converted safely."""


def parse_frontmatter_skill(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_BOUNDARY:
        raise SkillParseError(f"{path} is missing YAML frontmatter")

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_BOUNDARY:
            end_index = index
            break
    if end_index is None:
        raise SkillParseError(f"{path} has unterminated YAML frontmatter")

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
            raise SkillParseError(f"{path}: unsupported frontmatter line: {line!r}")

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

        metadata[key] = raw_value.strip('"').strip("'")
        index += 1

    for required in ("name", "description"):
        if not metadata.get(required):
            raise SkillParseError(f"{path}: missing required frontmatter key: {required}")
    return metadata


def yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_codex_skill(metadata: dict[str, str], source_path: Path) -> str:
    name = metadata["name"]
    description = metadata["description"]

    return "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {yaml_single_quote(description)}",
            "---",
            "",
            f"# {name}",
            "",
            "This is a Codex skill wrapper for Praxion.",
            "",
            f"Before using this skill, read the canonical skill definition at `{source_path.as_posix()}` and follow it as the authoritative source.",
            "Do not treat this wrapper as a fork; it exists only to expose Codex startup metadata.",
            "",
        ]
    )


def export_skills(repo_root: Path, out_dir: Path) -> list[Path]:
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        raise SkillParseError(f"Skills directory not found: {skills_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in sorted(skills_dir.glob("*/SKILL.md")):
        if source_path.name in SKIP_SKILL_FILES:
            continue
        metadata, _body = parse_frontmatter_skill(source_path)
        target_dir = out_dir / metadata["name"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "SKILL.md"
        relative_source = source_path.relative_to(repo_root)
        target_path.write_text(
            render_codex_skill(metadata, relative_source),
            encoding="utf-8",
        )
        written.append(target_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_skills(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
