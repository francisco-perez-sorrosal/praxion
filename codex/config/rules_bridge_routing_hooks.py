#!/usr/bin/env python3
"""Renders the Codex hook wrapper scripts that route Praxion rules by path or prompt."""

from __future__ import annotations

ROUTING_KINDS = frozenset({"session-start", "user-prompt-submit", "pre-tool-use"})


def render_routing_hook_script(kind: str) -> str:
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
    else:
        raise ValueError(f"unsupported routing hook kind: {kind}")
    return (
        imports
        + body
        + """

if __name__ == "__main__":
    raise SystemExit(main())
"""
    )
