#!/usr/bin/env python3
"""Code quality gate -- intercepts git commit to auto-fix and verify staged files.

PreToolUse hook that runs ruff format and ruff check --fix on staged Python
files before allowing a commit, and runs rustfmt --check on staged Rust files.
Auto-fixed Python files are re-staged. Reports all actions to stderr so Claude
and the user see what happened. Only blocks the commit (exit 2) if unfixable
violations remain in either language.

A Python file staged only in part (its working tree differs from the index) is
never auto-fixed or re-staged: re-adding it would sweep its unstaged changes
into the commit. Its staged content -- the bytes the commit will carry -- is
checked through ruff's stdin instead, and the gate blocks if that content is
not clean.

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

from _hook_utils import record_gate_fire
from _lang_tools import LANG_TOOLS, resolve_rust_edition, staged_files

GIT_COMMIT_RE = re.compile(r"git\s+commit")
PREFIX = "[quality gate]"


def _run(cmd, timeout=20, stdin=None):
    """Run a command, return (returncode, combined output)."""
    result = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return result.returncode, (result.stdout + result.stderr).strip()


def _partially_staged(files):
    """The subset of `files` whose working-tree copy differs from the staged copy.

    When git cannot answer, every file counts as partial: the gate then leaves
    the index alone rather than risk re-staging changes nobody staged.
    """
    rc, output = _run(["git", "diff", "--name-only", "--", *files], timeout=5)
    if rc != 0:
        return set(files)
    return set(output.splitlines())


def _staged_content_violations(ruff, files):
    """Check each file's staged blob through ruff's stdin; return violation texts."""
    violations = []
    for path in files:
        # Read the blob unstripped: its exact bytes are what the formatter judges.
        shown = subprocess.run(
            ["git", "show", f":{path}"], capture_output=True, text=True, timeout=5
        )
        if shown.returncode != 0:
            violations.append(f"{path}: staged content unreadable ({shown.stderr.strip()})")
            continue
        for label, cmd in (
            # --diff exits like --check and also shows what would change.
            ("Formatting", [*ruff, "format", "--diff", "--stdin-filename", path, "-"]),
            ("Linting", [*ruff, "check", "--stdin-filename", path, "-"]),
        ):
            rc, output = _run(cmd, stdin=shown.stdout)
            if rc != 0:
                violations.append(f"{label} (staged content of {path}):\n{output}")
    return violations


def _log(msg):
    """Log to stderr (visible to both Claude and user)."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _fix_restage_and_verify(ruff, files):
    """Auto-fix fully staged files, re-stage them, and return remaining violation texts.

    Only for files whose working tree equals the index: re-adding them stages
    the fixes and nothing else.
    """
    rc, output = _run([*ruff, "format", *files])
    if rc == 0 and output:
        _log(f"formatted: {output}")
    elif rc != 0:
        _log("ruff format applied fixes")

    rc, output = _run([*ruff, "check", "--fix", *files])
    if output:
        _log(f"lint auto-fix: {output}")

    subprocess.run(["git", "add", *files], capture_output=True, timeout=5)
    _log("re-staged fixed files")

    violations = []
    rc, output = _run([*ruff, "format", "--check", *files])
    if rc != 0:
        violations.append(f"Formatting:\n{output}")
    rc, output = _run([*ruff, "check", *files])
    if rc != 0:
        violations.append(f"Linting:\n{output}")
    return violations


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

    partial = [f for f in py_files if f in _partially_staged(py_files)]
    whole = [f for f in py_files if f not in partial]
    violations = _fix_restage_and_verify(ruff, whole) if whole else []
    if partial:
        _log(f"partially staged, checked as staged and left untouched: {', '.join(partial)}")
        violations += _staged_content_violations(ruff, partial)

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


def _group_by_edition(rs_files):
    """Group staged Rust files by their resolved `--edition`, preserving order.

    A workspace mid-migration can stage files from members declaring
    different editions in the same commit; resolving one file's edition and
    applying it to all of them misparses the others. Grouping means each
    group is checked under its own resolved edition.
    """
    groups: dict[str, list[str]] = {}
    for rs_file in rs_files:
        edition = resolve_rust_edition(rs_file)
        groups.setdefault(edition, []).append(rs_file)
    return groups


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

    violations = []
    for edition, files in _group_by_edition(rs_files).items():
        rc, output = _run([*rustfmt, "--edition", edition, "--check", *files])
        if rc != 0:
            violations.append(output)

    if not violations:
        _log("all Rust checks passed")
        return False

    _log("BLOCKED -- unfixable violations remain:")
    print(f"Formatting:\n{chr(10).join(violations)}", file=sys.stderr)
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
    blocked = python_blocked or rust_blocked

    try:
        record_gate_fire(
            "check_code_quality",
            "block" if blocked else "pass",
            session_id=payload.get("session_id", ""),
        )
    except Exception:
        pass

    if blocked:
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
