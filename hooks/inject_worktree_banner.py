#!/usr/bin/env python3
"""SessionStart hook: warn when the session opens inside a linked git worktree.

When a Claude Code session starts with its working directory inside a *linked*
git worktree (typically ``.claude/worktrees/<name>/``), this hook injects a
banner naming the worktree root and the canonical (main) checkout, so the agent
does not accidentally create or edit files in the parent checkout.

It is the proactive complement to ``worktree_guard.py`` (a PreToolUse hook that
*blocks* cross-worktree writes with exit code 2): the guard is the backstop that
catches the mistake; this banner is the heads-up that keeps the agent from
forming the intent in the first place.

Behavior contract:
- **Fail-open**: any internal error (subprocess failure, JSON decode, path
  resolution) exits 0 with no output -- a SessionStart hook must never wedge
  session creation.
- **Opt-out**: ``PRAXION_DISABLE_WORKTREE_BANNER=1`` in project settings' env
  block disables the banner (mirrors the ``PRAXION_DISABLE_*`` convention used
  by the other Praxion hooks).
- **Silent in the common case**: when the session is in the main worktree (or
  not in a git repo at all), the hook exits 0 with no output.

Scope notes:
- **SessionStart-only.** ``SubagentStart`` ``additionalContext`` is silently
  ignored by Claude Code, and ``EnterWorktree`` mid-session does not re-fire
  SessionStart -- subagents spawned after an ``EnterWorktree`` rely on
  ``worktree_guard.py`` for the boundary guarantee. Carrying this banner via
  ``inject_subagent_context.py`` (PreToolUse(Agent) ``updatedInput``) is a
  possible future enhancement, intentionally out of scope here.
- **Small duplication with ``worktree_guard.py`` is deliberate.** Both worktree
  hooks are self-contained -- there are only two. If a third worktree hook ever
  appears, extract a ``hooks/_worktree_utils`` module then.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

DISABLE_FLAG = "PRAXION_DISABLE_WORKTREE_BANNER"
SUBPROCESS_TIMEOUT_SECONDS = 3

_LIFECYCLE_REF = (
    "skills/software-planning/references/"
    "coordination-details.md#pipeline-worktree-lifecycle"
)


def _git(cwd: Path, *args: str) -> str | None:
    """Run ``git -C cwd <args>`` and return stripped stdout; None on any failure."""
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


def _linked_worktree_root(cwd: Path) -> Path | None:
    """Return the session's worktree root iff it is a *linked* worktree.

    Returns None when the session is in the main worktree (nothing to warn
    about) or when git detection fails.
    """
    git_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    common_dir = _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if git_dir is None or common_dir is None:
        return None
    if Path(git_dir).resolve() == Path(common_dir).resolve():
        return None  # main worktree -- no boundary to announce
    toplevel = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(toplevel).resolve() if toplevel else None


def _main_checkout_root(cwd: Path) -> Path | None:
    """Return the main worktree's root via ``git worktree list --porcelain``.

    The first ``worktree <path>`` line of the porcelain output is always the
    main worktree. Returns None on any failure.
    """
    listing = _git(cwd, "worktree", "list", "--porcelain")
    if not listing:
        return None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree ") :].strip()).resolve()
    return None


def _build_banner(worktree_root: Path, main_root: Path | None) -> str:
    """Render the worktree-orientation banner injected into the agent's context."""
    canonical = (
        f"`{main_root}`" if main_root else "the main checkout (run `git worktree list`)"
    )
    return (
        "## Worktree session (auto-injected)\n\n"
        f"⚠️ You are operating **inside a git worktree** at "
        f"`{worktree_root}`. The canonical checkout is {canonical} -- **do not "
        "create or edit files outside this worktree.** A `PreToolUse` guard "
        "(`worktree_guard.py`) blocks cross-worktree writes, but stay inside "
        "this tree by default rather than leaning on it.\n\n"
        "- `.ai-work/` here is gitignored and worktree-local.\n"
        "- `.ai-state/` changes are committed on this worktree's branch and "
        f"reconciled into the base branch at `/merge-worktree` (see `{_LIFECYCLE_REF}`).\n"
        "- Run `pwd` if you're unsure which checkout you're in."
    )


def _emit(context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )


def main() -> None:
    # Drain stdin even though we may not need it -- the hook framework can
    # SIGPIPE on its write end if the pipe is left unread.
    raw = sys.stdin.read()
    if is_disabled(DISABLE_FLAG):
        return
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())
    worktree_root = _linked_worktree_root(cwd)
    if worktree_root is None:
        return
    _emit(_build_banner(worktree_root, _main_checkout_root(cwd)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block session creation
