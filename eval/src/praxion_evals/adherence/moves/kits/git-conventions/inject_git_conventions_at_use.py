#!/usr/bin/env python3
"""PreToolUse hook of the git-conventions lean arm: the whole rule, before a staging or committing command.

Reads the rule file from the plugin tree this script sits in and emits its body (frontmatter
stripped, no added line) as the tool call's additional context. It fires for `git add`,
`git stage` and `git commit` only, alone or chained in one call; `git stash` and
`git checkout --` are not matched, which is why the kernel keeps their lines resident.

It honours the project's rule disable list under the rule's own id, as the session-start
injection does, so the lean arm never re-enables a rule a project turned off.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

RULE_PATH = "rules/swe/vcs/git-conventions.md"
RULE_ID = "swe/vcs/git-conventions"
DISABLE_FLAG = "PRAXION_DISABLE_RULE_INJECTION"
TRUTHY = frozenset({"1", "true", "yes"})
PROJECT_CONFIG = Path(".claude") / "praxion-rules.yaml"
SUPPORTED_SCHEMA_VERSION = 1

_SEGMENT_BREAK = re.compile(r"&&|\|\||[;|\n]")
_STAGING_OR_COMMITTING = re.compile(
    r"(?:\S+=\S*\s+)*git\s+(?:-[Cc]\s+\S+\s+)*(?:add|stage|commit)\b"
)
_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def stages_or_commits(command: str) -> bool:
    """Whether any command of a chained call is `git add`, `git stage` or `git commit`."""
    segments = (segment.strip() for segment in _SEGMENT_BREAK.split(command))
    return any(_STAGING_OR_COMMITTING.match(segment) for segment in segments)


def disabled_by(patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(RULE_ID, pattern) for pattern in patterns)


def rule_body(rule_text: str) -> str:
    return _FRONTMATTER.sub("", rule_text, count=1).lstrip("\n")


def project_disable_patterns(project: Path) -> list[str]:
    """The project's `disable:` list; a missing, unreadable or unsupported file disables nothing."""
    config = project / PROJECT_CONFIG
    if not config.is_file():
        return []
    if yaml is None:
        _warn(f"{config} not read: PyYAML is not available")
        return []
    try:
        data: Any = yaml.safe_load(config.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        _warn(f"{config} not read: {error}")
        return []
    if not isinstance(data, dict):
        return []
    version = data.get("version", SUPPORTED_SCHEMA_VERSION)
    if isinstance(version, int) and version > SUPPORTED_SCHEMA_VERSION:
        return []
    listed = data.get("disable", [])
    return [str(pattern) for pattern in listed] if isinstance(listed, list) else []


def context_for(payload: Any, plugin_root: Path, environ: Mapping[str, str]) -> str | None:
    """The text to hand the session for this tool call, or None when nothing is owed."""
    if environ.get(DISABLE_FLAG, "").strip().lower() in TRUTHY:
        return None
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not stages_or_commits(command):
        return None
    project = Path(payload.get("cwd") or Path.cwd())
    if disabled_by(project_disable_patterns(project)):
        return None
    try:
        return rule_body((plugin_root / RULE_PATH).read_text(encoding="utf-8"))
    except OSError as error:
        _warn(f"the rule file is not readable: {error}")
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0  # a hook never blocks the call it watches
    text = context_for(payload, Path(__file__).resolve().parent.parent, os.environ)
    if text is not None:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}
        print(json.dumps(output))
    return 0


def _warn(message: str) -> None:
    print(f"[git-conventions hook] {message}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
