#!/usr/bin/env python3
"""Renders the static Python helper modules written into the generated .codex/praxion/ directory."""

from __future__ import annotations

from pathlib import Path


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
