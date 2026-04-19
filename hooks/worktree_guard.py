#!/usr/bin/env python3
"""Worktree boundary guard -- blocks Write/Edit/NotebookEdit outside the session worktree.

PreToolUse hook that intercepts Write/Edit/NotebookEdit targeting an absolute
path. When the session runs inside a *linked* git worktree (not the main one),
any absolute target that resolves into a *different* git tree (a sibling
worktree or the main repo) is blocked with exit code 2. Targets under the
current worktree are allowed; non-git paths (e.g., ``~/.claude/settings.json``)
are allowed.

Rationale (captured from the concurrency-collab pipeline LEARNINGS):
    An implementer running inside ``.claude/worktrees/<name>/`` wrote
    ``rules/swe/adr-conventions.md`` to the main repo's path instead of the
    worktree copy, silently corrupting the main branch's tree. The agent's
    prompt resolved a bare relative path to an absolute main-repo path.

Behavior contract:
- **Fail-open**: any internal error (subprocess failure, path resolution
  error, JSON decode error) exits 0 so the hook never wedges work.
- **Opt-out**: set ``PRAXION_DISABLE_WORKTREE_GUARD=1`` in project settings'
  env block to disable the guard (mirrors other Praxion hook opt-outs).
- **Scope**: PreToolUse on ``Write|Edit|NotebookEdit``. Bash tool is handled
  elsewhere (``commit_gate.sh`` chain); this guard is path-based.
- **Silence on irrelevant paths**: relative file_path, non-worktree session,
  in-worktree target, and non-git target all exit 0 with no output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PREFIX = "[worktree-guard]"
GUARDED_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})
DISABLE_FLAG = "PRAXION_DISABLE_WORKTREE_GUARD"
SUBPROCESS_TIMEOUT_SECONDS = 3

_TRUTHY = frozenset({"1", "true", "yes"})


def _is_disabled() -> bool:
    return os.environ.get(DISABLE_FLAG, "").strip().lower() in _TRUTHY


def _log(msg: str) -> None:
    print(f"{PREFIX} {msg}", file=sys.stderr)


def _git(cwd: Path, *args: str) -> str | None:
    """Run ``git -C cwd <args>`` and return stdout; None on any failure."""
    try:
        result = subprocess.run(
            ("git", "-C", str(cwd), *args),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _resolve_session_worktree(cwd: Path) -> Path | None:
    """Return the session's worktree root if it is a *linked* worktree.

    Returns None when the session is in the main worktree (no boundary to
    enforce) or when git detection fails.
    """
    git_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir is None or common_dir is None:
        return None
    if Path(git_dir).resolve() == Path(common_dir).resolve():
        # Main worktree — no cross-boundary concern.
        return None
    toplevel = _git(cwd, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    return Path(toplevel).resolve()


def _is_within(candidate: Path, root: Path) -> bool:
    """True when ``candidate`` is ``root`` or lives under it (after resolve)."""
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        return False
    return True


def _nearest_existing_ancestor(path: Path) -> Path | None:
    """Walk up to find the first ancestor directory that exists on disk."""
    current = path.parent if path.parent != path else None
    while current is not None:
        if current.exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def _target_git_root(target_abs: Path) -> Path | None:
    """Return the git toplevel containing ``target_abs``; None if not in a repo."""
    probe_dir = (
        target_abs if target_abs.is_dir() else _nearest_existing_ancestor(target_abs)
    )
    if probe_dir is None:
        return None
    toplevel = _git(probe_dir, "rev-parse", "--show-toplevel")
    if toplevel is None:
        return None
    return Path(toplevel).resolve()


def _block(file_path: str, session_root: Path, target_root: Path) -> None:
    _log("BLOCKED: cross-worktree write")
    _log(f"  target:   {file_path}")
    _log(f"  session:  {session_root}")
    _log(f"  resolves in different git tree: {target_root}")
    _log("  Rewrite the path to stay within the session worktree, or")
    _log(f"  export {DISABLE_FLAG}=1 if this is intentional.")
    sys.exit(2)


def main() -> None:
    if _is_disabled():
        return

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return

    tool_name = payload.get("tool_name", "")
    if tool_name not in GUARDED_TOOLS:
        return

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path or not os.path.isabs(file_path):
        return

    cwd = Path(payload.get("cwd") or os.getcwd())
    session_root = _resolve_session_worktree(cwd)
    if session_root is None:
        return

    target_abs = Path(file_path).resolve()
    if _is_within(target_abs, session_root):
        return

    target_root = _target_git_root(target_abs)
    if target_root is None:
        # Outside any git tree (config/system path) — allow.
        return
    if target_root == session_root:
        # Symlink / path-normalization edge case — treat as allowed.
        return

    _block(file_path, session_root, target_root)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail-open: never block writes due to guard bugs.
        pass
