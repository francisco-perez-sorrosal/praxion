#!/usr/bin/env python3
"""ADR reminder hook -- warns when architectural files are committed without an ADR.

PreToolUse hook that checks staged files for architectural changes (CLAUDE.md,
agents, skills, rules, commands, hooks, workflows) and emits a warning if no
ADR file in .ai-state/decisions/ was modified in the same session.

Pure file-path matching -- no LLM calls, no API keys required.
Follows fail-open: always exits 0 (never blocks commits).
"""

import json
import os
import re
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"git\s+commit")
PREFIX = "[adr-reminder]"
SUBPROCESS_TIMEOUT_SECONDS = 5

# Glob patterns for files considered architectural.
# Uses ** for recursive directory matching and * for single-segment matching.
ARCHITECTURAL_PATTERNS = [
    "CLAUDE.md",
    "**/CLAUDE.md",
    "agents/*.md",
    "skills/*/SKILL.md",
    "rules/**/*.md",
    "commands/*.md",
    ".claude-plugin/hooks/**",
    ".claude-plugin/plugin.json",
    ".github/workflows/**",
]

ADR_DIRECTORY = os.path.join(".ai-state", "decisions")

# Pre-compiled regex patterns from ARCHITECTURAL_PATTERNS for correct
# path-segment-aware matching (fnmatch treats * as matching / on Unix).
_COMPILED_PATTERNS = None


def _log(msg):
    """Log to stderr (visible to both Claude and user)."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _staged_files():
    """Get list of staged files (excluding deleted)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=d"],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


def _glob_to_regex(pattern):
    """Convert a glob pattern to a regex with correct path-segment semantics.

    * matches any characters except /  (single segment)
    ** matches any characters including /  (zero or more segments)
    """
    result = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ** — match any path segments (including zero)
                result.append(".*")
                i += 2
                # Skip trailing / after ** if present
                if i < len(pattern) and pattern[i] == "/":
                    result.append("(?:/)?")
                    i += 1
                continue
            # * — match within a single segment (no /)
            result.append("[^/]*")
        elif char == "?":
            result.append("[^/]")
        elif char == ".":
            result.append(r"\.")
        else:
            result.append(re.escape(char))
        i += 1
    return re.compile("^" + "".join(result) + "$")


def _get_compiled_patterns():
    """Lazily compile ARCHITECTURAL_PATTERNS into regex patterns."""
    global _COMPILED_PATTERNS  # noqa: PLW0603
    if _COMPILED_PATTERNS is None:
        _COMPILED_PATTERNS = [_glob_to_regex(p) for p in ARCHITECTURAL_PATTERNS]
    return _COMPILED_PATTERNS


def _matches_architectural_pattern(filepath):
    """Check if a file path matches any architectural pattern."""
    for regex in _get_compiled_patterns():
        if regex.match(filepath):
            return True
    return False


def _has_adr_file_in_staged(staged_files):
    """Check if any staged file is an ADR in .ai-state/decisions/."""
    for filepath in staged_files:
        normalized = filepath.replace("\\", "/")
        adr_prefix = ADR_DIRECTORY.replace("\\", "/")
        if normalized.startswith(adr_prefix + "/") and normalized.endswith(".md"):
            return True
    return False


def _has_recent_adr_commit():
    """Check if an ADR was committed in the current HEAD (most recent commit)."""
    result = subprocess.run(
        [
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "HEAD",
            "--",
            f"{ADR_DIRECTORY}/",
        ],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return False
    adr_files = [f for f in result.stdout.strip().splitlines() if f.endswith(".md")]
    return len(adr_files) > 0


def main():
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return

    staged_files = _staged_files()
    if not staged_files:
        return

    architectural_files = [f for f in staged_files if _matches_architectural_pattern(f)]
    if not architectural_files:
        return

    # Check if an ADR was touched (staged or recently committed)
    if _has_adr_file_in_staged(staged_files):
        return
    if _has_recent_adr_commit():
        return

    # Architectural files changed without an ADR
    _log("Architectural files modified without an ADR.")
    _log(f"  Changed: {', '.join(architectural_files)}")
    _log("  Consider creating one in .ai-state/decisions/")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: never block commits due to hook errors
        pass
