#!/usr/bin/env python3
"""Calibration reminder hook -- commit-time AND Stop-time calibration nudges.

Two independent trigger paths share this script:

1. **Commit-time** (PreToolUse on `git commit`, pre-existing): reuses
   check_calibration_coverage.compute_coverage() in-process and warns when
   task-completing commits have accumulated since the newest row in
   .ai-state/calibration_log.md.
2. **Stop-time** (new): at most once per session, nudges when the session made a
   qualifying edit but left calibration_log.md untouched -- see `_handle_stop`.

Both emit via `hookSpecificOutput.additionalContext` on stdout (never stderr --
stderr at exit 0 is shown only in verbose mode and never reaches the model). No LLM
calls, no API keys required. Follows fail-open: always exits 0 (never blocks).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from _hook_utils import record_gate_fire

# Locate the sibling `scripts/` directory to import in-process. This is
# *plugin-internal code location* -- finding this hook's own sibling module inside
# the plugin's own checkout -- and is unrelated to resolving the *consumer* repo
# root below, which always comes from git (never __file__).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from _git_runner import GitUnavailableError, run_git  # noqa: E402 (after sys.path injection)
from _repo_root import git_toplevel_from_cwd  # noqa: E402
from check_calibration_coverage import (  # noqa: E402
    CALIBRATION_LOG_REL,
    K_COMMITS,
    compute_coverage,
)

GIT_COMMIT_RE = re.compile(r"git\s+commit")

STOP_HOOK_NAME = "remind_calibration_stop"

# Tools whose row on this session's WAL constitutes "made an edit this session".
_QUALIFYING_TOOL_NAMES = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# A qualifying-edit path under any of these prefixes does not count -- pipeline/
# repo-management churn, not the kind of work a calibration row should track.
_EXCLUDED_PATH_PREFIXES = (".ai-state/", ".ai-work/", ".claude/")

# Matches the -m "<message>" or -m '<message>' argument of a pending commit.
_COMMIT_MESSAGE_RE = re.compile(r"""-m\s+(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")

# Release automation (bump:) and ADR-finalize bookkeeping (chore(finalize)) are
# not task-completing work -- mirrors _EXCLUDED_PREFIXES in
# check_calibration_coverage.py.
_EXCLUDED_MESSAGE_PREFIXES = ("bump:", "chore(finalize)")

PREFIX = "[calibration-reminder]"
SUBPROCESS_TIMEOUT_SECONDS = 5


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


def _emit(hook_event_name: str, message: str) -> None:
    """Print the structured additionalContext payload the model actually sees."""
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": hook_event_name, "additionalContext": message}}
        )
    )


def main():
    raw = sys.stdin.read()

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    if payload.get("hook_event_name") == "Stop":
        _handle_stop(payload)
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

    decision, warning = _check_and_warn(repo_root)
    if warning:
        _emit("PreToolUse", warning)
    try:
        record_gate_fire("remind_calibration", decision, session_id=payload.get("session_id", ""))
    except Exception:
        pass


def _check_and_warn(repo_root: Path) -> tuple[str, str]:
    """Return (decision, warning) -- warning is "" when the calibration log is covered."""
    result = compute_coverage(repo_root)
    if result["covered"]:
        return "pass", ""

    warning = (
        f"{PREFIX} {result['uncalibrated_commits']} uncalibrated commit(s) since the newest "
        f".ai-state/calibration_log.md row (threshold: {K_COMMITS}). Append a row -- "
        "the Retrospective cell doubles as the micro-capture slot."
    )
    return "warn", warning


# -- Stop-time reminder ---------------------------------------------------------------


def _read_wal_rows(obs_path: Path) -> list[dict]:
    """Read every JSONL row from a session-scoped WAL, skipping malformed lines."""
    if not obs_path.exists():
        return []
    try:
        text = obs_path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _is_excluded_path(path: str, repo_root: Path) -> bool:
    """True for bookkeeping directories and for files outside this repo.

    The capture hooks record absolute paths; a relative one is taken as repo-relative.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(repo_root.resolve())
        except ValueError:
            return True
    relative = candidate.as_posix().removeprefix("./")
    return any(relative.startswith(prefix) for prefix in _EXCLUDED_PATH_PREFIXES)


def _is_qualifying_edit_row(row: dict, session_id: str, repo_root: Path) -> bool:
    if row.get("session_id") != session_id or row.get("event_type") != "tool_use":
        return False
    if row.get("tool_name") not in _QUALIFYING_TOOL_NAMES:
        return False
    return any(not _is_excluded_path(p, repo_root) for p in row.get("file_paths") or [])


def _already_reminded_this_session(rows: list[dict], session_id: str) -> bool:
    return any(
        row.get("event_type") == "gate_fire"
        and row.get("hook") == STOP_HOOK_NAME
        and row.get("session_id") == session_id
        for row in rows
    )


def _session_touched_calibration_log(rows: list[dict], session_id: str) -> bool:
    return any(
        row.get("session_id") == session_id
        and row.get("event_type") == "tool_use"
        and row.get("tool_name") in _QUALIFYING_TOOL_NAMES
        and any(p.endswith(CALIBRATION_LOG_REL) for p in row.get("file_paths") or [])
        for row in rows
    )


def _calibration_log_changed_vs_head(repo_root: Path) -> bool:
    """True when the working tree diverges from HEAD, or when git cannot answer."""
    try:
        result = run_git(repo_root, "diff", "--quiet", "HEAD", "--", CALIBRATION_LOG_REL)
    except GitUnavailableError:
        return True
    return result.returncode != 0


def _handle_stop(payload: dict) -> None:
    """At most once per session: nudge when work was done but the log was not."""
    if payload.get("stop_hook_active"):
        return
    session_id = str(payload.get("session_id") or "")
    if not session_id or _inside_linked_worktree():
        return

    repo_root = git_toplevel_from_cwd()
    # Only projects that keep a calibration log are asked to append to it.
    if repo_root is None or not (repo_root / CALIBRATION_LOG_REL).is_file():
        return

    obs_path = repo_root / ".ai-state" / "observations.jsonl"
    rows = _read_wal_rows(obs_path)
    if _already_reminded_this_session(rows, session_id):
        return
    if not any(_is_qualifying_edit_row(row, session_id, repo_root) for row in rows):
        return
    if _calibration_log_changed_vs_head(repo_root) or _session_touched_calibration_log(
        rows, session_id
    ):
        return

    _emit(
        "Stop",
        f"{PREFIX} this session edited files but .ai-state/calibration_log.md is "
        "unchanged. If a task-completing pipeline finished, append a calibration "
        "row before ending -- the Retrospective cell doubles as the micro-capture slot.",
    )
    try:
        record_gate_fire(STOP_HOOK_NAME, "warn", session_id=session_id, project_dir=repo_root)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail-open: never block commits due to hook errors
        pass
