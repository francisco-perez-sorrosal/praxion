#!/usr/bin/env python3
"""Install/check/uninstall Praxion-managed Codex MCP config."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


STATE_VERSION = 1
CONFIG_DIR_NAME = ".codex"
CONFIG_FILE_NAME = "config.toml"
STATE_RELATIVE_PATH = Path("praxion/mcp_state.json")
PROJECT_DOC_FALLBACK_KEY = "project_doc_fallback_filenames"
CLAUDE_FALLBACK_FILENAME = "CLAUDE.md"


@dataclass(frozen=True)
class ServerConfig:
    command: str
    args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]


def codex_dir(project_root: Path) -> Path:
    return project_root / CONFIG_DIR_NAME


def config_path(project_root: Path) -> Path:
    return codex_dir(project_root) / CONFIG_FILE_NAME


def state_path(project_root: Path) -> Path:
    return codex_dir(project_root) / STATE_RELATIVE_PATH


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def load_plugin_mcp_servers(repo_root: Path) -> dict[str, ServerConfig]:
    manifest_path = repo_root / ".claude-plugin" / "plugin.json"
    manifest = load_json(manifest_path)
    plugin_root = repo_root.as_posix()

    servers: dict[str, ServerConfig] = {}
    for name, payload in (manifest.get("mcpServers") or {}).items():
        command = str(payload["command"]).replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)
        args = tuple(
            str(arg).replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)
            for arg in payload.get("args", [])
        )
        env = tuple(
            sorted(
                (
                    str(key),
                    str(value).replace("${CLAUDE_PLUGIN_ROOT}", plugin_root),
                )
                for key, value in (payload.get("env") or {}).items()
            )
        )
        servers[str(name)] = ServerConfig(command=command, args=args, env=env)
    return servers


def toml_quote(value: str) -> str:
    return json.dumps(value)


def toml_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(toml_quote(value) for value in values) + "]"


def render_server_block(name: str, server: ServerConfig) -> str:
    lines = [
        f"[mcp_servers.{name}]",
        f"command = {toml_quote(server.command)}",
        f"args = {toml_list(server.args)}",
    ]
    if server.env:
        lines.append("")
        lines.append(f"[mcp_servers.{name}.env]")
        for key, value in server.env:
            lines.append(f"{key} = {toml_quote(value)}")
    return "\n".join(lines).rstrip() + "\n"


TABLE_HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*$")


@dataclass(frozen=True)
class TableSection:
    start_line: int
    parts: tuple[str, ...]


def split_toml_dotted_key(raw: str) -> tuple[str, ...]:
    parts: list[str] = []
    index = 0
    text = raw.strip()

    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break

        if text[index] == '"':
            end = index + 1
            escaped = False
            while end < len(text):
                char = text[end]
                if char == '"' and not escaped:
                    break
                if char == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                end += 1
            if end >= len(text) or text[end] != '"':
                raise ValueError(f"Malformed TOML dotted key: {raw}")
            parts.append(json.loads(text[index : end + 1]))
            index = end + 1
        else:
            end = index
            while end < len(text) and text[end] not in ". ":
                end += 1
            token = text[index:end].strip()
            if not token:
                raise ValueError(f"Malformed TOML dotted key: {raw}")
            parts.append(token)
            index = end

        while index < len(text) and text[index].isspace():
            index += 1
        if index < len(text):
            if text[index] != ".":
                raise ValueError(f"Malformed TOML dotted key: {raw}")
            index += 1

    return tuple(parts)


def parse_table_sections(text: str) -> list[TableSection]:
    lines = text.splitlines(keepends=True)
    sections: list[TableSection] = []
    for index, line in enumerate(lines):
        match = TABLE_HEADER_RE.match(line)
        if match is None:
            continue
        sections.append(
            TableSection(start_line=index, parts=split_toml_dotted_key(match.group(1)))
        )
    return sections


def server_name_for_table(parts: tuple[str, ...]) -> str | None:
    if len(parts) < 2 or parts[0] != "mcp_servers":
        return None
    return parts[1]


def normalize_config_text(text: str) -> str:
    stripped = text.strip("\n")
    if not stripped:
        return ""
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped + "\n"


TOP_LEVEL_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(toml_quote(value) for value in values) + "]"


def find_top_level_assignment_span(text: str, key: str) -> tuple[int, int, str] | None:
    lines = text.splitlines(keepends=True)
    section_started = False
    index = 0

    while index < len(lines):
        line = lines[index]
        if TABLE_HEADER_RE.match(line):
            section_started = True
        if section_started:
            index += 1
            continue

        match = TOP_LEVEL_ASSIGNMENT_RE.match(line)
        if match is None or match.group(1) != key:
            index += 1
            continue

        end_index = index + 1
        bracket_balance = line.split("=", 1)[1].split("#", 1)[0].count(
            "["
        ) - line.split("=", 1)[1].split("#", 1)[0].count("]")
        while bracket_balance > 0 and end_index < len(lines):
            next_line = lines[end_index]
            bracket_balance += next_line.split("#", 1)[0].count("[")
            bracket_balance -= next_line.split("#", 1)[0].count("]")
            end_index += 1

        return index, end_index, "".join(lines[index:end_index])

    return None


def remove_top_level_assignment(text: str, key: str) -> tuple[str, str | None]:
    span = find_top_level_assignment_span(text, key)
    if span is None:
        return normalize_config_text(text), None

    start_index, end_index, removed = span
    lines = text.splitlines(keepends=True)
    kept = "".join(lines[:start_index] + lines[end_index:])
    return normalize_config_text(kept), removed


def set_top_level_assignment(text: str, key: str, rendered_value: str) -> str:
    cleaned_text, _removed = remove_top_level_assignment(text, key)
    line = f"{key} = {rendered_value}\n"
    if not cleaned_text:
        return line

    lines = cleaned_text.splitlines(keepends=True)
    insert_at = len(lines)
    for index, existing_line in enumerate(lines):
        if TABLE_HEADER_RE.match(existing_line):
            insert_at = index
            break

    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1

    updated = lines[:insert_at] + [line] + lines[insert_at:]
    return normalize_config_text("".join(updated))


def merge_project_doc_fallbacks(parsed: dict) -> list[str]:
    existing = parsed.get(PROJECT_DOC_FALLBACK_KEY)
    if isinstance(existing, list):
        merged = [str(item) for item in existing]
    else:
        merged = []
    if CLAUDE_FALLBACK_FILENAME not in merged:
        merged.append(CLAUDE_FALLBACK_FILENAME)
    return merged


def remove_server_blocks(
    text: str, server_names: set[str]
) -> tuple[str, dict[str, str | None]]:
    if not text:
        return "", {name: None for name in server_names}

    lines = text.splitlines(keepends=True)
    sections = parse_table_sections(text)
    removed: dict[str, str | None] = {name: None for name in server_names}
    keep_ranges: list[tuple[int, int]] = []
    cursor = 0
    index = 0

    while index < len(sections):
        section = sections[index]
        server_name = server_name_for_table(section.parts)
        if server_name not in server_names:
            index += 1
            continue

        end_index = index + 1
        while end_index < len(sections):
            next_server = server_name_for_table(sections[end_index].parts)
            if next_server != server_name:
                break
            end_index += 1

        start_line = section.start_line
        end_line = (
            sections[end_index].start_line if end_index < len(sections) else len(lines)
        )
        keep_ranges.append((cursor, start_line))
        if removed[server_name] is None:
            removed[server_name] = "".join(lines[start_line:end_line]).rstrip() + "\n"
        cursor = end_line
        index = end_index

    keep_ranges.append((cursor, len(lines)))
    kept = "".join("".join(lines[start:end]) for start, end in keep_ranges)
    return normalize_config_text(kept), removed


def append_server_blocks(text: str, blocks: list[str]) -> str:
    rendered_blocks = [block.rstrip("\n") for block in blocks if block]
    if not rendered_blocks:
        return normalize_config_text(text)

    existing = text.rstrip("\n")
    addition = "\n\n".join(rendered_blocks)
    if existing:
        return existing + "\n\n" + addition + "\n"
    return addition + "\n"


def load_state(project_root: Path) -> dict | None:
    path = state_path(project_root)
    if not path.exists():
        return None
    return load_json(path)


def save_state(project_root: Path, state: dict) -> None:
    dump_json(state_path(project_root), state)


def unlink_state(project_root: Path) -> None:
    path = state_path(project_root)
    if path.exists():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass


def ensure_valid_toml(text: str, path: Path) -> dict:
    if not text.strip():
        return {}
    try:
        return tomllib.loads(text)
    except (
        tomllib.TOMLDecodeError
    ) as exc:  # pragma: no cover - parse details vary by Python
        raise RuntimeError(f"Invalid Codex config TOML at {path}: {exc}") from exc


def read_config_text(project_root: Path) -> str:
    path = config_path(project_root)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_config_text(project_root: Path, text: str) -> None:
    path = config_path(project_root)
    normalized = normalize_config_text(text)
    if not normalized:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized, encoding="utf-8")


def normalize_server_payload(payload: dict | None) -> ServerConfig | None:
    if payload is None:
        return None
    env = payload.get("env") or {}
    return ServerConfig(
        command=str(payload.get("command", "")),
        args=tuple(str(arg) for arg in payload.get("args", [])),
        env=tuple(sorted((str(key), str(value)) for key, value in env.items())),
    )


def expected_blocks_for_repo(repo_root: Path, server_order: list[str]) -> list[str]:
    expected = load_plugin_mcp_servers(repo_root)
    return [render_server_block(name, expected[name]) for name in server_order]


def install(repo_root: Path, project_root: Path) -> None:
    current_text = read_config_text(project_root)
    parsed = ensure_valid_toml(current_text, config_path(project_root))

    expected = load_plugin_mcp_servers(repo_root)
    server_order = list(expected)
    cleaned_text, removed_blocks = remove_server_blocks(current_text, set(server_order))
    cleaned_text, removed_fallback_assignment = remove_top_level_assignment(
        cleaned_text, PROJECT_DOC_FALLBACK_KEY
    )

    state = load_state(project_root)
    if state is None:
        state = {
            "version": STATE_VERSION,
            "original_blocks": {
                name: removed_blocks.get(name) for name in server_order
            },
            "original_project_doc_fallback_assignment": removed_fallback_assignment,
            "project_root": project_root.as_posix(),
            "repo_root": repo_root.as_posix(),
        }
    else:
        state.setdefault("version", STATE_VERSION)
        state.setdefault("original_blocks", {})
        state.setdefault(
            "original_project_doc_fallback_assignment", removed_fallback_assignment
        )
        state.setdefault("project_root", project_root.as_posix())
        state.setdefault("repo_root", repo_root.as_posix())
        for name in server_order:
            state["original_blocks"].setdefault(name, removed_blocks.get(name))

    new_text = set_top_level_assignment(
        cleaned_text,
        PROJECT_DOC_FALLBACK_KEY,
        toml_array(merge_project_doc_fallbacks(parsed)),
    )
    new_text = append_server_blocks(
        new_text,
        [render_server_block(name, expected[name]) for name in server_order],
    )
    write_config_text(project_root, new_text)
    save_state(project_root, state)


def uninstall(repo_root: Path, project_root: Path) -> None:
    state = load_state(project_root)
    if state is None:
        return

    current_text = read_config_text(project_root)
    ensure_valid_toml(current_text, config_path(project_root))

    original_blocks = state.get("original_blocks", {})
    original_fallback_assignment = state.get(
        "original_project_doc_fallback_assignment", None
    )

    server_names = set(str(name) for name in original_blocks)
    server_names.update(load_plugin_mcp_servers(repo_root))
    cleaned_text, _removed_blocks = remove_server_blocks(current_text, server_names)
    cleaned_text, _removed_fallback_assignment = remove_top_level_assignment(
        cleaned_text, PROJECT_DOC_FALLBACK_KEY
    )
    if original_fallback_assignment:
        cleaned_text = set_top_level_assignment(
            cleaned_text,
            PROJECT_DOC_FALLBACK_KEY,
            original_fallback_assignment.split("=", 1)[1].strip(),
        )
    restored_blocks = [
        original_blocks[name] for name in original_blocks if original_blocks[name]
    ]
    write_config_text(project_root, append_server_blocks(cleaned_text, restored_blocks))
    unlink_state(project_root)


def check(repo_root: Path, project_root: Path) -> tuple[bool, list[str]]:
    path = config_path(project_root)
    problems: list[str] = []
    if not path.exists():
        return False, [f"Codex project MCP config missing: {path}"]

    text = path.read_text(encoding="utf-8")
    parsed = ensure_valid_toml(text, path)
    state = load_state(project_root)
    if state is None:
        problems.append(f"Praxion Codex MCP state missing: {state_path(project_root)}")

    expected = load_plugin_mcp_servers(repo_root)
    actual_servers = parsed.get("mcp_servers") or {}
    for name, server in expected.items():
        actual = normalize_server_payload(actual_servers.get(name))
        if actual is None:
            problems.append(f"Codex project MCP server missing: {name}")
            continue
        if actual != server:
            problems.append(f"Codex project MCP server is stale: {name}")

    fallback_filenames = parsed.get(PROJECT_DOC_FALLBACK_KEY) or []
    if CLAUDE_FALLBACK_FILENAME not in fallback_filenames:
        problems.append(
            "Codex project config missing Praxion project-doc fallback: CLAUDE.md"
        )

    return not problems, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument(
        "--mode", choices={"install", "check", "uninstall"}, required=True
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    project_root = args.project_root.resolve()

    if args.mode == "install":
        install(repo_root, project_root)
        return 0

    if args.mode == "uninstall":
        uninstall(repo_root, project_root)
        return 0

    ok, problems = check(repo_root, project_root)
    for problem in problems:
        print(problem)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
