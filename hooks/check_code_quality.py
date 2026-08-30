#!/usr/bin/env python3
"""Code quality gate -- intercepts git commit to auto-fix and verify staged files.

PreToolUse hook that runs ruff format and ruff check --fix on staged Python
files before allowing a commit, and runs rustfmt --check on staged Rust files.
Auto-fixed Python files are re-staged. Reports all actions to stderr so Claude
and the user see what happened. Only blocks the commit (exit 2) if unfixable
violations remain in either language.

Clippy is deliberately excluded from the Rust check -- it is a merge-stage
concern, not a commit-gate one (a multi-second clippy run here would train
people to disable the gate). The Rust check is staged-file-scoped
(`rustfmt --check <files>`), never `cargo fmt --all`, so one legacy
unformatted file elsewhere in the project never blocks an unrelated commit.

Follows fail-open: internal errors exit 0 (never blocks commits due to own bugs).
"""

import json
import re
import subprocess
import sys

from _lang_tools import LANG_TOOLS, resolve_rust_edition, staged_files

GIT_COMMIT_RE = re.compile(r"git\s+commit")
PREFIX = "[quality gate]"


def _run(cmd, timeout=20):
    """Run a command, return (returncode, combined output)."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.returncode, (result.stdout + result.stderr).strip()


def _log(msg):
    """Log to stderr (visible to both Claude and user)."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _check_staged_python_files():
    """Auto-fix and verify staged Python files. Returns True iff the commit should block."""
    py_files = staged_files(".py")
    if not py_files:
        return False

    ruff = LANG_TOOLS[".py"].resolve()
    if not ruff:
        _log("ruff not found, skipping quality checks")
        return False

    _log(f"checking {len(py_files)} staged Python file(s): {', '.join(py_files)}")

    # Auto-fix: format
    rc, output = _run([*ruff, "format", *py_files])
    if rc == 0 and output:
        _log(f"formatted: {output}")
    elif rc != 0:
        _log("ruff format applied fixes")

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

    if not violations:
        _log("all checks passed")
        return False

    _log("BLOCKED -- unfixable violations remain:")
    for v in violations:
        print(v, file=sys.stderr)
    print(
        "\nFix these manually, stage the files, then retry the commit.",
        file=sys.stderr,
    )
    return True


def _check_staged_rust_files():
    """Verify staged Rust files are rustfmt-clean. Returns True iff the commit should block.

    Staged-file-scoped (`rustfmt --check`) -- never `cargo fmt --all` -- so a
    legacy unformatted file elsewhere in the project never blocks a commit
    that doesn't touch it. No auto-fix: unlike ruff, this gate only verifies.
    """
    rs_files = staged_files(".rs")
    if not rs_files:
        return False

    rustfmt = LANG_TOOLS[".rs"].resolve()
    if not rustfmt:
        _log("rustfmt not found, skipping Rust quality checks")
        return False

    _log(f"checking {len(rs_files)} staged Rust file(s): {', '.join(rs_files)}")

    edition = resolve_rust_edition(rs_files[0])
    rc, output = _run([*rustfmt, "--edition", edition, "--check", *rs_files])
    if rc == 0:
        _log("all Rust checks passed")
        return False

    _log("BLOCKED -- unfixable violations remain:")
    print(f"Formatting:\n{output}", file=sys.stderr)
    print(
        "\nFix these manually (`cargo fmt`), stage the files, then retry the commit.",
        file=sys.stderr,
    )
    return True


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return

    python_blocked = _check_staged_python_files()
    rust_blocked = _check_staged_rust_files()

    if python_blocked or rust_blocked:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
