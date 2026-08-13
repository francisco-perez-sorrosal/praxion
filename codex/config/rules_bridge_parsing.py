#!/usr/bin/env python3
"""Rule parsing and manifest building for the Praxion Codex rules bridge exporter."""

from __future__ import annotations

import re
from pathlib import Path

FRONTMATTER_BOUNDARY = "---"
SKIP_RULE_FILES = {"CLAUDE.md", "README.md"}

STOPWORDS = {
    "a",
    "an",
    "artifact",
    "artifacts",
    "and",
    "are",
    "be",
    "by",
    "code",
    "conventions",
    "docs",
    "file",
    "files",
    "for",
    "from",
    "in",
    "is",
    "md",
    "path",
    "paths",
    "of",
    "on",
    "or",
    "output",
    "protocol",
    "rule",
    "rules",
    "style",
    "styles",
    "the",
    "to",
    "with",
    "work",
    "writing",
    "yaml",
}
CLAUDE_ONLY_PATTERNS = [
    r"\bClaude Code\b",
    r"\bAnthropic\b",
    r"~\/\.claude",
    r"\.claude\/",
    r"\bCLAUDE_CODE_[A-Z_]+\b",
    r"\bopus\b",
    r"\bsonnet\b",
    r"\bhaiku\b",
    r"\bremember\(",
    r"\brecall\(",
    r"\bbrowse_index\(",
    r"\bsession_start\(",
    r"\bSubagentStart\b",
    r"\bSubagentStop\b",
    r"\bPreCompact\b",
    r"\bPostCompact\b",
    r"claude-ecosystem",
]


class RuleParseError(ValueError):
    """Raised when a Praxion rule cannot be converted safely."""


def parse_rule(path: Path, repo_root: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    metadata: dict[str, object] = {}
    body_lines = lines
    if lines and lines[0].strip() == FRONTMATTER_BOUNDARY:
        end_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == FRONTMATTER_BOUNDARY:
                end_index = index
                break
        if end_index is None:
            raise RuleParseError(f"{path} has unterminated YAML frontmatter")
        metadata = parse_rule_frontmatter(lines[1:end_index], path)
        body_lines = lines[end_index + 1 :]

    title = extract_title(body_lines, path)
    summary = extract_summary(body_lines)
    relpath = path.relative_to(repo_root).as_posix()
    path_globs = [str(item) for item in metadata.get("paths", [])]
    scope = "path_scoped" if path_globs else "always_on"
    codex_metadata = metadata.get("codex", {})
    portability = resolve_codex_portability(relpath, title, body_lines, codex_metadata)
    codex_load = resolve_codex_load(scope, portability, codex_metadata)
    return {
        "id": relpath.removesuffix(".md").replace("/", "::"),
        "relpath": relpath,
        "source_path": str(path.resolve().as_posix()),
        "scope": scope,
        "path_globs": path_globs,
        "title": title,
        "summary": summary,
        "keywords": sorted(build_keywords(relpath, title, path_globs)),
        "codex_load": codex_load,
        "codex_portability": portability,
    }


def parse_rule_frontmatter(lines: list[str], path: Path) -> dict[str, object]:
    metadata: dict[str, object] = {}
    index = 0
    key_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s*(.*))?$")

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")):
            index += 1
            continue

        match = key_pattern.match(line)
        if not match:
            raise RuleParseError(f"{path}: unsupported frontmatter line: {line!r}")

        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if key == "paths":
            paths: list[str] = []
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line and not next_line.startswith((" ", "\t", "-")):
                    break
                stripped_next = next_line.strip()
                if stripped_next.startswith("- "):
                    value = stripped_next[2:].strip()
                    paths.append(strip_yaml_string(value))
                index += 1
            metadata["paths"] = paths
            continue

        if key == "codex":
            codex_metadata: dict[str, str] = {}
            if raw_value:
                codex_metadata["portability"] = strip_yaml_string(raw_value)
                metadata["codex"] = codex_metadata
                index += 1
                continue
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line and not next_line.startswith((" ", "\t")):
                    break
                stripped_next = next_line.strip()
                if not stripped_next or stripped_next.startswith("#"):
                    index += 1
                    continue
                submatch = key_pattern.match(stripped_next)
                if not submatch:
                    raise RuleParseError(
                        f"{path}: unsupported codex frontmatter line: {next_line!r}"
                    )
                subkey, subvalue = submatch.group(1), (submatch.group(2) or "").strip()
                codex_metadata[subkey] = strip_yaml_string(subvalue)
                index += 1
            metadata["codex"] = codex_metadata
            continue

        metadata[key] = strip_yaml_string(raw_value)
        index += 1

    return metadata


def strip_yaml_string(value: str) -> str:
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def extract_title(lines: list[str], path: Path) -> str:
    for line in lines:
        if line.startswith("## "):
            return line[3:].strip()
    raise RuleParseError(f"{path}: missing level-2 title heading")


def extract_summary(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if stripped.startswith("## "):
            continue
        if stripped.startswith(("- ", "* ")):
            if not paragraphs:
                return stripped[2:].strip()
            continue
        if stripped.startswith(("```", "|", "#")):
            continue
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current).strip())
    return paragraphs[0] if paragraphs else ""


def build_keywords(relpath: str, title: str, globs: list[str]) -> set[str]:
    tokens: set[str] = set()
    for source in [relpath, title, *globs]:
        for token in re.findall(r"[A-Za-z0-9_]+", source.lower()):
            if token in STOPWORDS or len(token) < 3:
                continue
            tokens.add(token)
    alias_map = {
        "readme": {"readme"},
        "diagram": {"diagram", "architecture", "mermaid"},
        "dashboard": {"dashboard", "nextjs"},
        "testing": {"test", "tests", "pytest", "spec"},
        "staleness": {"skill", "skills", "skill_md"},
        "agent": {"agent", "agents"},
        "command": {"command", "commands"},
        "rule": {"rule", "rules"},
        "html": {"html", "jinja", "template"},
        "citation": {"citation", "traceability"},
        "gpu": {"gpu", "training", "experiments", "runs"},
        "eval": {"eval", "evaluation", "training", "metrics"},
        "git": {"git", "commit", "branch"},
        "pr": {"pr", "pull", "review"},
    }
    for token, aliases in alias_map.items():
        if token in tokens:
            tokens.update(aliases)
    return tokens


def infer_codex_portability(relpath: str, title: str, body_lines: list[str]) -> str:
    combined = "\n".join([relpath, title, *body_lines])
    for pattern in CLAUDE_ONLY_PATTERNS:
        if re.search(pattern, combined):
            return "claude_only"
    return "portable"


def resolve_codex_portability(
    relpath: str, title: str, body_lines: list[str], codex_metadata: dict[str, object]
) -> str:
    value = str(codex_metadata.get("portability", "auto")).strip().lower()
    if value in {"", "auto"}:
        return infer_codex_portability(relpath, title, body_lines)
    if value in {"portable", "claude_only"}:
        return value
    raise RuleParseError(
        f"{relpath}: unsupported codex.portability {value!r}; expected auto, portable, or claude_only"
    )


def resolve_codex_load(scope: str, portability: str, codex_metadata: dict[str, object]) -> str:
    value = str(codex_metadata.get("load", "auto")).strip().lower()
    if value in {"", "auto"}:
        if portability != "portable":
            return "exclude"
        return "path_scoped" if scope == "path_scoped" else "always_on"
    if value in {"always_on", "path_scoped", "exclude"}:
        if portability != "portable" and value != "exclude":
            raise RuleParseError(
                f"codex.load={value!r} requires codex.portability=portable for this rule"
            )
        return value
    raise RuleParseError(
        f"unsupported codex.load {value!r}; expected auto, always_on, path_scoped, or exclude"
    )


def build_manifest(repo_root: Path) -> dict[str, object]:
    rules_dir = repo_root / "rules"
    if not rules_dir.is_dir():
        raise RuleParseError(f"Rules directory not found: {rules_dir}")

    rules: list[dict[str, object]] = []
    for source_path in sorted(rules_dir.rglob("*.md")):
        if source_path.name in SKIP_RULE_FILES:
            continue
        rules.append(parse_rule(source_path, repo_root))

    always_on = [rule for rule in rules if rule["codex_load"] == "always_on"]
    path_scoped = [rule for rule in rules if rule["codex_load"] == "path_scoped"]
    return {
        "generated_by": "Praxion Codex rules bridge exporter",
        "praxion_root": str(repo_root.resolve().as_posix()),
        "codex_portable_always_on_rule_ids": [rule["id"] for rule in always_on],
        "rules": rules,
        "always_on_rule_ids": [rule["id"] for rule in always_on],
        "path_scoped_rule_ids": [rule["id"] for rule in path_scoped],
    }
