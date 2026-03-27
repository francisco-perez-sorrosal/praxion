#!/usr/bin/env python3
"""Code quality gate -- intercepts git commit to auto-fix and verify staged Python files.

PreToolUse hook that runs ruff format and ruff check --fix on staged Python
files before allowing a commit. Auto-fixed files are re-staged. Reports all
actions to stderr so Claude and the user see what happened. Only blocks the
commit (exit 2) if unfixable violations remain.

Follows fail-open: internal errors exit 0 (never blocks commits due to own bugs).
"""

import json
import re
import shutil
import subprocess
import sys

GIT_COMMIT_RE = re.compile(r"git\s+commit")
PREFIX = "[quality gate]"


def _find_ruff():
    """Find ruff executable. Returns command list or None."""
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uv"):
        return ["uv", "run", "ruff"]
    if shutil.which("pixi"):
        return ["pixi", "run", "ruff"]
    return None


def _staged_python_files():
    """Get list of staged .py files (excluding deleted)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=d", "--", "*.py"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f]


def _run(cmd, timeout=20):
    """Run a command, return (returncode, combined output)."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, (result.stdout + result.stderr).strip()


def _log(msg):
    """Log to stderr (visible to both Claude and user)."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return

    py_files = _staged_python_files()
    if not py_files:
        return

    ruff = _find_ruff()
    if not ruff:
        _log("ruff not found, skipping quality checks")
        return

    _log(f"checking {len(py_files)} staged Python file(s): {', '.join(py_files)}")

    # Auto-fix: format
    rc, output = _run([*ruff, "format", *py_files])
    if rc == 0 and output:
        _log(f"formatted: {output}")
    elif rc != 0:
        _log(f"ruff format applied fixes")

    # Auto-fix: lint
    rc, output = _run([*ruff, "check", "--fix", *py_files])
    if output:
        _log(f"lint auto-fix: {output}")

    # Re-stage fixed files
    subprocess.run(["git", "add", *py_files], capture_output=True, timeout=5)
    _log("re-staged fixed files")

    # Verify: check if unfixable violations remain
    violations = []

    rc, output = _run([*ruff, "format", "--check", *py_files])
    if rc != 0:
        violations.append(f"Formatting:\n{output}")

    rc, output = _run([*ruff, "check", *py_files])
    if rc != 0:
        violations.append(f"Linting:\n{output}")

    if violations:
        _log("BLOCKED -- unfixable violations remain:")
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "\nFix these manually, stage the files, then retry the commit.",
            file=sys.stderr,
        )
        sys.exit(2)

    _log("all checks passed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
