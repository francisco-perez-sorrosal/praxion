#!/usr/bin/env python3
"""Auto-format Python files on Write/Edit.

PostToolUse hook that runs ruff format after every Python file write or edit.
Reports what changed via stdout JSON so Claude and the user see the fixes.
Exits 0 unconditionally -- must never block agent execution.
"""

import json
import os
import shutil
import subprocess
import sys


def _find_ruff():
    """Find ruff executable. Returns command list or None."""
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uv"):
        return ["uv", "run", "ruff"]
    if shutil.which("pixi"):
        return ["pixi", "run", "ruff"]
    return None


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return

    if not os.path.isfile(file_path):
        return

    ruff = _find_ruff()
    if not ruff:
        return

    # Snapshot before formatting
    with open(file_path) as f:
        before = f.read()

    result = subprocess.run(
        [*ruff, "format", file_path],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Check if file changed
    with open(file_path) as f:
        after = f.read()

    if before != after:
        basename = os.path.basename(file_path)
        # Count changed lines for a concise summary
        before_lines = set(before.splitlines())
        after_lines = set(after.splitlines())
        changed = len(before_lines.symmetric_difference(after_lines))
        msg = f"[format hook] ruff formatted {basename} ({changed} lines changed)"
        if result.stderr.strip():
            msg += f"\n{result.stderr.strip()}"
        print(json.dumps({"additionalContext": msg}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
