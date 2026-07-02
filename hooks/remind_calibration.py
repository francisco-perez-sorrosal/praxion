#!/usr/bin/env python3
"""Calibration reminder hook -- warns at commit time when calibration coverage lags.

PreToolUse hook that fires on `git commit` and nudges the operator when
task-completing commits have accumulated since the newest row in
.ai-state/calibration_log.md (see scripts/check_calibration_coverage.py).

Reuses check_calibration_coverage.compute_coverage() in-process -- no LLM
calls, no API keys required. Follows fail-open: always exits 0 (never blocks
commits).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Locate the sibling `scripts/` directory to import compute_coverage in-process.
# This is *plugin-internal code location* -- finding this hook's own sibling
# module inside the plugin's own checkout -- and is unrelated to resolving the
# *consumer* repo root below, which always comes from git (never __file__).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _repo_root import git_toplevel_from_cwd  # noqa: E402 (after sys.path injection)
from check_calibration_coverage import K_COMMITS, compute_coverage  # noqa: E402

GIT_COMMIT_RE = re.compile(r"git\s+commit")

# Matches the -m "<message>" or -m '<message>' argument of a pending commit.
_COMMIT_MESSAGE_RE = re.compile(r"""-m\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")

# Release automation (bump:) and ADR-finalize bookkeeping (chore(finalize)) are
# not task-completing work -- mirrors _EXCLUDED_PREFIXES in
# check_calibration_coverage.py.
_EXCLUDED_MESSAGE_PREFIXES = ("bump:", "chore(finalize)")

PREFIX = "[calibration-reminder]"
SUBPROCESS_TIMEOUT_SECONDS = 5


def _log(msg):
    """Log to stderr (visible to both Claude and user)."""
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _run_git(*args):
    """Run `git <args>` in the process's inherited cwd; return stripped stdout or None."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _pending_commit_message(command):
    """Extract the -m message body from a pending `git commit` command, or None."""
    match = _COMMIT_MESSAGE_RE.search(command)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _is_excluded_commit(message):
    """True if the pending commit message is release automation or finalize bookkeeping."""
    return any(message.startswith(prefix) for prefix in _EXCLUDED_MESSAGE_PREFIXES)


def _inside_linked_worktree():
    """True when the process cwd sits inside a linked (non-canonical) worktree."""
    git_dir = _run_git("rev-parse", "--git-dir")
    common_dir = _run_git("rev-parse", "--git-common-dir")
    if git_dir is None or common_dir is None:
        return False
    return Path(git_dir).resolve() != Path(common_dir).resolve()


def main():
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    command = payload.get("tool_input", {}).get("command", "")
    if not GIT_COMMIT_RE.search(command):
        return

    message = _pending_commit_message(command)
    if message is not None and _is_excluded_commit(message):
        return

    if _inside_linked_worktree():
        return

    repo_root = git_toplevel_from_cwd()
    if repo_root is None:
        return

    result = compute_coverage(repo_root)
    if result["covered"]:
        return

    _log(
        f"{result['uncalibrated_commits']} uncalibrated commit(s) since the newest "
        f".ai-state/calibration_log.md row (threshold: {K_COMMITS}). Append a row -- "
        "the Retrospective cell doubles as the micro-capture slot."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: never block commits due to hook errors
        pass
