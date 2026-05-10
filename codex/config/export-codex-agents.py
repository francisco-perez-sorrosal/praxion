#!/usr/bin/env python3
"""Export Praxion Markdown agents to Codex custom-agent TOML files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path


FRONTMATTER_BOUNDARY = "---"
SKIP_AGENT_FILES = {"CLAUDE.md", "README.md"}

# Keep the agent wrapper on current Codex model families while preserving the
# canonical Praxion routing table as the source of truth for which agents get
# which tier. The exporter translates the tier into the current Codex model
# family rather than copying Claude aliases into Codex config.
CODEX_MODEL_SETTINGS_BY_TIER = {
    "high": {"model": "gpt-5.5", "model_reasoning_effort": "high"},
    "medium": {"model": "gpt-5.4", "model_reasoning_effort": "medium"},
    "low": {"model": "gpt-5.4-mini", "model_reasoning_effort": "low"},
}


class AgentParseError(ValueError):
    """Raised when an agent file cannot be converted safely."""


def load_model_routes(repo_root: Path) -> dict[str, dict[str, object]]:
    exporter_path = repo_root / "codex" / "config" / "export-codex-pipeline-adapter.py"
    spec = importlib.util.spec_from_file_location(
        "export_codex_pipeline_adapter", exporter_path
    )
    if spec is None or spec.loader is None:
        raise AgentParseError(f"Unable to load routing exporter from {exporter_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    routes = module.export_model_routing(repo_root)["agent_routes"]
    return {route["agent"]: route for route in routes}


def split_frontmatter_agent(path: Path) -> tuple[list[str], dict[str, str], str]:
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

    frontmatter_lines = lines[1:end_index]
    metadata = parse_simple_yaml(frontmatter_lines, path)
    body = "\n".join(lines[end_index + 1 :]).strip() + "\n"
    return frontmatter_lines, metadata, body


def parse_frontmatter_agent(path: Path) -> tuple[dict[str, str], str]:
    """Compatibility wrapper for callers that only need metadata and body."""

    _frontmatter_lines, metadata, body = split_frontmatter_agent(path)
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

        if raw_value.startswith("'") and raw_value.endswith("'"):
            metadata[key] = raw_value[1:-1].replace("''", "'")
        elif raw_value.startswith('"') and raw_value.endswith('"'):
            metadata[key] = raw_value[1:-1]
        else:
            metadata[key] = raw_value
        index += 1

    for required in ("name", "description"):
        if not metadata.get(required):
            raise AgentParseError(
                f"{path}: missing required frontmatter key: {required}"
            )
    return metadata


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_frontmatter_capsule(frontmatter_lines: list[str]) -> str:
    frontmatter_block = "\n".join(
        [FRONTMATTER_BOUNDARY, *frontmatter_lines, FRONTMATTER_BOUNDARY]
    )
    return "\n".join(
        [
            "Praxion agent contract:",
            "",
            "The YAML block below preserves the canonical Claude frontmatter contract.",
            "Treat it as authoritative for tool scope, permission mode, memory, hooks,",
            "skills, max turns, background execution, and any other source-only settings.",
            "",
            "```yaml",
            frontmatter_block,
            "```",
        ]
    )


def render_developer_instructions(
    name: str,
    source_path: Path,
    frontmatter_lines: list[str],
) -> str:
    capsule = render_frontmatter_capsule(frontmatter_lines)
    return "\n".join(
        [
            f"You are a Codex wrapper for the Praxion `{name}` agent.",
            "",
            f"Before doing task work, read the canonical agent definition at `{source_path.as_posix()}` and follow it as the authoritative source.",
            "The top-level TOML `model` settings are translated from Praxion's routing table; the canonical source remains the routing authority.",
            "Do not treat this wrapper as a fork; the source file remains authoritative.",
            "",
            "Also apply the Praxion behavioral contract: Surface Assumptions, Register Objection, Stay Surgical, Simplicity First.",
            "",
            capsule,
            "",
            "Do not duplicate the canonical agent body here. Read it from the source file when you need the full workflow narrative.",
        ]
    )


def render_codex_agent(
    metadata: dict[str, str],
    source_path: Path,
    frontmatter_lines: list[str],
    routing: dict[str, object],
) -> str:
    description = metadata["description"]
    codex_adapter = routing.get("codex_adapter", {})
    tier = str(codex_adapter.get("codex_tier", ""))
    model_settings = CODEX_MODEL_SETTINGS_BY_TIER.get(tier)
    if model_settings is None:
        raise AgentParseError(
            f"{source_path}: missing Codex model settings for routing tier: {tier}"
        )
    developer_instructions = render_developer_instructions(
        metadata["name"], source_path, frontmatter_lines
    )

    return "\n".join(
        [
            "# Generated by Praxion Codex exporter.",
            f"name = {toml_string(metadata['name'])}",
            f"description = {toml_string(description)}",
            f"model = {toml_string(model_settings['model'])}",
            f"model_reasoning_effort = {toml_string(model_settings['model_reasoning_effort'])}",
            f"developer_instructions = {toml_string(developer_instructions)}",
            "",
        ]
    )


def export_agents(repo_root: Path, out_dir: Path) -> list[Path]:
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        raise AgentParseError(f"Agents directory not found: {agents_dir}")

    routes = load_model_routes(repo_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in sorted(agents_dir.glob("*.md")):
        if source_path.name in SKIP_AGENT_FILES:
            continue
        frontmatter_lines, metadata, _body = split_frontmatter_agent(source_path)
        routing = routes.get(metadata["name"])
        if routing is None:
            raise AgentParseError(
                f"{source_path}: missing Codex routing entry for agent: {metadata['name']}"
            )
        target_path = out_dir / f"{metadata['name']}.toml"
        target_path.write_text(
            render_codex_agent(
                metadata, source_path.resolve(), frontmatter_lines, routing
            ),
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
