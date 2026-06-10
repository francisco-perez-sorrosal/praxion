#!/usr/bin/env python3
"""Export a Praxion rules bridge for Codex project-local hooks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FRONTMATTER_BOUNDARY = "---"
SKIP_RULE_FILES = {"CLAUDE.md", "README.md"}
HOOK_COMMAND_TEMPLATE = '/usr/bin/python3 "{hook_path}"'
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


def render_lookup_module() -> str:
    return """#!/usr/bin/env python3
\"\"\"Helpers for the generated Praxion Codex rules bridge.\"\"\"

from __future__ import annotations

import fnmatch
import json
import re
import shlex
from pathlib import Path, PurePosixPath


MANIFEST_PATH = Path(__file__).resolve().with_name("rules_manifest.json")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _rules_by_id(manifest: dict) -> dict[str, dict]:
    return {rule["id"]: rule for rule in manifest["rules"]}


def always_on_rules(manifest: dict) -> list[dict]:
    by_id = _rules_by_id(manifest)
    return [by_id[rule_id] for rule_id in manifest["always_on_rule_ids"]]


def path_scoped_rules(manifest: dict) -> list[dict]:
    by_id = _rules_by_id(manifest)
    return [by_id[rule_id] for rule_id in manifest["path_scoped_rule_ids"]]


def match_rules_for_paths(manifest: dict, paths: list[str]) -> list[dict]:
    matched: dict[str, dict] = {}
    candidates = [PurePosixPath(path) for path in paths if path]
    for rule in manifest["rules"]:
        globs = rule.get("path_globs", [])
        if not globs:
            continue
        for candidate in candidates:
            if any(candidate.match(glob) or fnmatch.fnmatch(candidate.as_posix(), glob) for glob in globs):
                matched[rule["id"]] = rule
                break
    return sorted(matched.values(), key=lambda item: item["relpath"])


def match_rules_for_prompt(manifest: dict, prompt: str) -> list[dict]:
    matched: dict[str, dict] = {}
    lowered = prompt.lower()
    tokens = set(re.findall(r"[a-z0-9_]+", lowered))
    for rule in path_scoped_rules(manifest):
        for keyword in rule.get("keywords", []):
            if keyword in tokens:
                matched[rule["id"]] = rule
                break
    return sorted(matched.values(), key=lambda item: item["relpath"])


def normalize_paths(raw_paths: list[str], cwd: str) -> list[str]:
    cwd_path = Path(cwd).resolve()
    relative: list[str] = []
    for item in raw_paths:
        if not item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = (cwd_path / path).resolve()
        try:
            relative.append(path.relative_to(cwd_path).as_posix())
        except ValueError:
            relative.append(path.as_posix())
    return sorted(set(relative))


def looks_like_path_fragment(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if any(ch in token for ch in ("*", "?", "[")):
        return True
    if "/" in token or token.startswith("."):
        return True
    if re.search(r"\\.[A-Za-z0-9_]{1,8}$", token):
        return True
    return False


def extract_paths_from_command(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return [token for token in tokens if looks_like_path_fragment(token)]


def extract_paths_from_prompt(prompt: str) -> list[str]:
    raw = re.findall(r"(?:\\.{1,2}/|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*(?:\\.[A-Za-z0-9_]{1,8})?", prompt)
    return [token for token in raw if looks_like_path_fragment(token)]


def format_context(label: str, rules: list[dict]) -> str:
    if not rules:
        return ""
    lines = [f"[Praxion rules bridge] {label}"]
    for rule in rules:
        lines.append(f"- {rule['title']} — {rule['source_path']}")
    lines.append("Canonical Praxion rule files above remain the source of truth. Read them before acting.")
    return "\\n".join(lines)

"""


def render_hook_runtime_module(repo_root: Path) -> str:
    repo_root_str = repo_root.resolve().as_posix()
    return (
        """#!/usr/bin/env python3
\"\"\"Runtime helpers for generated Praxion Codex hook wrappers.\"\"\"

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path("""
        + repr(repo_root_str)
        + """)
PROJECT_SETTINGS_PATH = Path(".codex") / "praxion" / "settings.json"
_LEGACY_ADDITIONAL_CONTEXT_EVENTS = frozenset(
    {"SessionStart", "PostToolUse", "UserPromptSubmit"}
)


def payload_has_ai_state(raw_payload: str) -> bool:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        return False
    cwd = str(payload.get("cwd", "") or "")
    return bool(cwd) and Path(cwd, ".ai-state").is_dir()


def payload_cwd(raw_payload: str) -> str | None:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        return None
    cwd = str(payload.get("cwd", "") or "")
    if not cwd or not Path(cwd).is_dir():
        return None
    return cwd


def load_project_env(raw_payload: str) -> dict[str, str]:
    cwd = payload_cwd(raw_payload)
    if not cwd:
        return {}
    settings_path = Path(cwd) / PROJECT_SETTINGS_PATH
    if not settings_path.exists():
        return {}
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    env = payload.get("env")
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items()}


def run_canonical_hook(
    relative_path: str,
    raw_payload: str,
    env_updates: dict[str, str] | None = None,
) -> int:
    return run_canonical_command([sys.executable, relative_path], raw_payload, env_updates)


def run_canonical_command(
    command: list[str],
    raw_payload: str,
    env_updates: dict[str, str] | None = None,
) -> int:
    env = os.environ.copy()
    if env_updates:
        env.update(env_updates)
    project_env = load_project_env(raw_payload)
    if project_env:
        env.update(project_env)
    resolved = [
        str(REPO_ROOT / part)
        if part.startswith(("hooks/", "scripts/"))
        else part
        for part in command
    ]
    result = subprocess.run(
        resolved,
        input=raw_payload,
        text=True,
        capture_output=True,
        env=env,
        cwd=payload_cwd(raw_payload),
        check=False,
    )
    if result.stdout:
        sys.stdout.write(normalize_hook_stdout(raw_payload, result.stdout))
    if result.stderr:
        sys.stderr.write(result.stderr)
    return int(result.returncode)


def normalize_hook_stdout(raw_payload: str, stdout: str) -> str:
    if not stdout.strip():
        return stdout
    try:
        payload = json.loads(raw_payload or "{}")
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return stdout
    if not isinstance(output, dict) or "hookSpecificOutput" in output:
        return stdout
    event_name = str(payload.get("hook_event_name", "") or "")
    if event_name not in _LEGACY_ADDITIONAL_CONTEXT_EVENTS:
        return stdout
    additional_context = output.get("additionalContext")
    if not isinstance(additional_context, str):
        return stdout
    normalized: dict[str, object] = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": additional_context,
        }
    }
    for key in (
        "continue",
        "decision",
        "reason",
        "stopReason",
        "suppressOutput",
        "systemMessage",
    ):
        if key in output:
            normalized[key] = output[key]
    return json.dumps(normalized)
"""
    )


def render_hook_script(kind: str) -> str:
    if kind == "session-start":
        imports = """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from rules_lookup import always_on_rules, format_context, load_manifest  # noqa: E402

"""
        body = """
def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    manifest = load_manifest()
    rules = always_on_rules(manifest)
    context = format_context("Always-on Praxion rules for this project:", rules)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0
"""
    elif kind == "user-prompt-submit":
        imports = """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

"""
        body = """
def main() -> int:
    from rules_lookup import (
        extract_paths_from_prompt,
        format_context,
        load_manifest,
        match_rules_for_paths,
        match_rules_for_prompt,
        normalize_paths,
    )

    payload = json.loads(sys.stdin.read() or "{}")
    manifest = load_manifest()
    prompt = payload.get("prompt", "")
    cwd = payload.get("cwd", "")
    rules = []
    if cwd:
        prompt_paths = extract_paths_from_prompt(prompt)
        if prompt_paths:
            rules = match_rules_for_paths(manifest, normalize_paths(prompt_paths, cwd))
    if not rules:
        rules = match_rules_for_prompt(manifest, prompt)
    if not rules:
        return 0
    context = format_context("Prompt-matched Praxion rules to consult for this turn:", rules)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0
"""
    elif kind == "pre-tool-use":
        imports = """#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from rules_lookup import extract_paths_from_command, format_context, load_manifest, looks_like_path_fragment, match_rules_for_paths, normalize_paths  # noqa: E402

"""
        body = """
MUTATING_TOOL_NAMES = {"Edit", "MultiEdit", "NotebookEdit", "Write", "apply_patch", "ApplyPatch"}
READ_ONLY_TOOL_NAMES = {"Glob", "Grep", "LS", "Read"}


def _extract_paths(value: object, key_hint: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            paths.extend(_extract_paths(nested, key))
        return paths
    if isinstance(value, list):
        for item in value:
            paths.extend(_extract_paths(item, key_hint))
        return paths
    if isinstance(value, str):
        if key_hint == "command":
            paths.extend(extract_paths_from_command(value))
        elif key_hint in {"file_path", "path", "paths", "glob", "pattern"}:
            if looks_like_path_fragment(value):
                paths.append(value)
        for marker in re.findall(r"\\*\\*\\* (?:Add|Update|Delete) File: ([^\\n]+)", value):
            paths.append(marker.strip())
    return paths


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    tool_name = str(payload.get("tool_name", ""))
    if tool_name in READ_ONLY_TOOL_NAMES:
        return 0
    if tool_name and tool_name not in MUTATING_TOOL_NAMES:
        return 0

    manifest = load_manifest()
    cwd = payload.get("cwd", "")
    raw_paths = _extract_paths(payload.get("tool_input", {}))
    if not raw_paths or not cwd:
        return 0
    rules = match_rules_for_paths(manifest, normalize_paths(raw_paths, cwd))
    if not rules:
        return 0
    context = format_context("File-scoped Praxion rules to consult before this tool action:", rules)
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0
"""
    if kind in {"session-start", "user-prompt-submit", "pre-tool-use"}:
        return (
            imports
            + body
            + """

if __name__ == "__main__":
    raise SystemExit(main())
"""
        )
    if kind == "decisions-session-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import payload_has_ai_state, run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    if not payload_has_ai_state(raw):
        return 0
    return run_canonical_hook("hooks/inject_decisions.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-session-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    surface_status = run_canonical_hook("hooks/measure_context_surface.py", raw)
    return surface_status or lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-stop":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/send_event.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    capture_status = run_canonical_hook("hooks/capture_memory.py", raw)
    return capture_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "process-framing-user-prompt-submit":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/inject_process_framing.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "subagent-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def _normalize_task_payload(raw: str) -> str:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw
    if payload.get("tool_name") == "Task":
        payload["tool_name"] = "Agent"
        return json.dumps(payload)
    return raw


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/inject_subagent_context.py", _normalize_task_payload(raw))


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "worktree-guard-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/worktree_guard.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-quality-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/commit_gate.sh", "hooks/check_code_quality.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-adr-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/commit_gate.sh", "hooks/remind_adr.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "cleanup-learnings-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(["hooks/cleanup_gate.sh", "hooks/promote_learnings.py"], raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "commit-id-citation-pre-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_command


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_command(
        ["hooks/commit_gate.sh", "scripts/check_id_citation_discipline.py"],
        raw,
    )


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "format-python-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/format_python.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "detect-duplication-post-tool-use":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/detect_duplication.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-subagent-start":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "observability-subagent-stop":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    status = run_canonical_hook("hooks/send_event.py", raw)
    lifecycle_status = run_canonical_hook("hooks/capture_session.py", raw)
    return lifecycle_status or status


if __name__ == "__main__":
    raise SystemExit(main())
"""
    elif kind == "precompact-state":
        return """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_DIR = Path(__file__).resolve().parents[1] / "praxion"
sys.path.insert(0, str(HELPER_DIR))

from hook_runtime import run_canonical_hook


def main() -> int:
    raw = sys.stdin.read()
    return run_canonical_hook("hooks/precompact_state.py", raw)


if __name__ == "__main__":
    raise SystemExit(main())
"""
    else:
        raise ValueError(f"unsupported hook kind: {kind}")


def render_hook_registrations() -> dict[str, object]:
    def command(name: str, project_root: str) -> str:
        hook_path = Path(project_root) / ".codex" / "hooks" / name
        return HOOK_COMMAND_TEMPLATE.format(hook_path=hook_path.as_posix())

    project_root = "__PRAXION_PROJECT_ROOT__"
    return {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-session-start.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: loading always-on rules",
                        }
                    ],
                },
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-decisions-session-start.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: injecting decision context",
                        }
                    ],
                },
                {
                    "matcher": "startup|resume|clear",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-session-start.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing session start",
                        }
                    ],
                },
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-observability-stop.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing session stop",
                        }
                    ],
                },
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-user-prompt-submit.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: routing prompt-scoped rules",
                        }
                    ],
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-process-framing-user-prompt-submit.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: injecting process framing",
                        }
                    ],
                },
            ],
            "PreToolUse": [
                {
                    "matcher": "Agent|Task",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-subagent-pre-tool-use.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: injecting subagent contract",
                        }
                    ],
                },
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-commit-quality-pre-tool-use.py", project_root
                            ),
                            "timeout": 30,
                            "statusMessage": "Praxion: checking commit quality",
                        },
                        {
                            "type": "command",
                            "command": command("praxion-commit-adr-pre-tool-use.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: checking ADR reminder",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-cleanup-learnings-pre-tool-use.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: checking learnings cleanup",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-commit-id-citation-pre-tool-use.py",
                                project_root,
                            ),
                            "timeout": 20,
                            "statusMessage": "Praxion: checking id citations",
                        },
                    ],
                },
                {
                    "matcher": "Edit|MultiEdit|NotebookEdit|Write|apply_patch|ApplyPatch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-worktree-guard-pre-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: checking worktree boundary",
                        }
                    ],
                },
                {
                    "matcher": "Edit|MultiEdit|NotebookEdit|Write|apply_patch|ApplyPatch",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-pre-tool-use.py", project_root),
                            "timeout": 30,
                            "statusMessage": "Praxion: routing file-scoped rules",
                        }
                    ],
                },
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-pre-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing tool start",
                        }
                    ],
                },
            ],
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-post-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing tool result",
                        }
                    ],
                },
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-format-python-post-tool-use.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: formatting Python",
                        },
                        {
                            "type": "command",
                            "command": command(
                                "praxion-detect-duplication-post-tool-use.py",
                                project_root,
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: detecting duplication",
                        },
                    ],
                },
            ],
            "SubagentStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-subagent-start.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing subagent start",
                        }
                    ],
                }
            ],
            "SubagentStop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command(
                                "praxion-observability-subagent-stop.py", project_root
                            ),
                            "timeout": 15,
                            "statusMessage": "Praxion: capturing subagent stop",
                        }
                    ],
                },
            ],
            "PreCompact": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command("praxion-precompact-state.py", project_root),
                            "timeout": 15,
                            "statusMessage": "Praxion: snapshotting pipeline state",
                        }
                    ],
                }
            ],
        }
    }


def export_rules_bridge(repo_root: Path, out_dir: Path) -> list[Path]:
    codex_dir = out_dir
    praxion_dir = codex_dir / "praxion"
    hooks_dir = codex_dir / "hooks"
    praxion_dir.mkdir(parents=True, exist_ok=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(repo_root)
    written: list[Path] = []

    manifest_path = praxion_dir / "rules_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written.append(manifest_path)

    lookup_path = praxion_dir / "rules_lookup.py"
    lookup_path.write_text(render_lookup_module(), encoding="utf-8")
    written.append(lookup_path)

    runtime_path = praxion_dir / "hook_runtime.py"
    runtime_path.write_text(render_hook_runtime_module(repo_root), encoding="utf-8")
    written.append(runtime_path)

    for hook_name, kind in [
        ("praxion-session-start.py", "session-start"),
        ("praxion-decisions-session-start.py", "decisions-session-start"),
        ("praxion-observability-session-start.py", "observability-session-start"),
        ("praxion-observability-stop.py", "observability-stop"),
        ("praxion-user-prompt-submit.py", "user-prompt-submit"),
        (
            "praxion-process-framing-user-prompt-submit.py",
            "process-framing-user-prompt-submit",
        ),
        ("praxion-subagent-pre-tool-use.py", "subagent-pre-tool-use"),
        ("praxion-commit-quality-pre-tool-use.py", "commit-quality-pre-tool-use"),
        ("praxion-commit-adr-pre-tool-use.py", "commit-adr-pre-tool-use"),
        ("praxion-cleanup-learnings-pre-tool-use.py", "cleanup-learnings-pre-tool-use"),
        (
            "praxion-commit-id-citation-pre-tool-use.py",
            "commit-id-citation-pre-tool-use",
        ),
        ("praxion-worktree-guard-pre-tool-use.py", "worktree-guard-pre-tool-use"),
        ("praxion-pre-tool-use.py", "pre-tool-use"),
        ("praxion-observability-pre-tool-use.py", "observability-pre-tool-use"),
        ("praxion-observability-post-tool-use.py", "observability-post-tool-use"),
        ("praxion-format-python-post-tool-use.py", "format-python-post-tool-use"),
        (
            "praxion-detect-duplication-post-tool-use.py",
            "detect-duplication-post-tool-use",
        ),
        ("praxion-observability-subagent-start.py", "observability-subagent-start"),
        ("praxion-observability-subagent-stop.py", "observability-subagent-stop"),
        ("praxion-precompact-state.py", "precompact-state"),
    ]:
        hook_path = hooks_dir / hook_name
        hook_path.write_text(render_hook_script(kind), encoding="utf-8")
        written.append(hook_path)

    registrations_path = praxion_dir / "hook_registrations.json"
    registrations_path.write_text(
        json.dumps(render_hook_registrations(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(registrations_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    written = export_rules_bridge(args.repo_root.resolve(), args.out_dir.resolve())
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
