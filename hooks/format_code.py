#!/usr/bin/env python3
"""Auto-format source files on Write/Edit.

PostToolUse hook that formats every written or edited file whose extension is
served by the ``_lang_tools`` registry. Reports what changed via stdout JSON so
Claude and the user see the fixes. Exits 0 unconditionally -- must never block
agent execution, and an unreachable formatter is a silent no-op.

Language support is registry-driven: adding an extension row to
``_lang_tools.LANG_TOOLS`` widens this hook with no change here.
"""

import json
import os
import subprocess
import sys

from _lang_tools import tool_for

FORMAT_TIMEOUT_SECONDS = 10


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    lang = tool_for(file_path)
    if lang is None:
        return

    if not os.path.isfile(file_path):
        return

    prefix = lang.resolve()
    if not prefix:
        return

    # Snapshot before formatting
    with open(file_path) as f:
        before = f.read()

    result = subprocess.run(
        lang.build_format_argv(prefix, file_path),
        capture_output=True,
        text=True,
        timeout=FORMAT_TIMEOUT_SECONDS,
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
        msg = f"[format hook] {lang.tool_name} formatted {basename} ({changed} lines changed)"
        if result.stderr.strip():
            msg += f"\n{result.stderr.strip()}"
        print(json.dumps({"additionalContext": msg}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
