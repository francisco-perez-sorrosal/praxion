#!/usr/bin/env python3
"""SessionStart hook: self-heal Praxion's git hook chain.

A package manager's ``prepare`` script (husky's on ``npm install``, lefthook's
``install``) can re-point ``core.hooksPath`` away from Praxion's wrapper
directory without any Praxion code path running -- git itself is what git
hooks would otherwise repair, so the finalize hook chain (``dec-356``'s
self-delivering repair channel) structurally cannot reach this failure. This
hook is the channel that can: it fires on every session start, restoring the
chain when a wrapper directory is found but no longer wired.

Carries no sidecar concept -- P1's own SessionStart work is a separate hook,
keeping this milestone independently mergeable.

Behavior contract:
- **Fail-open**: any internal error (subprocess failure, JSON decode, path
  resolution) exits 0 with no output -- a SessionStart hook must never wedge
  session creation.
- **Opt-out**: ``PRAXION_DISABLE_HOOK_CHAIN_HEAL=1`` in project settings' env
  block disables the heal entirely (mirrors the ``PRAXION_DISABLE_*``
  convention).
- **Fast-exit, no subprocess**: for the overwhelming majority of sessions
  (no Praxion wrapper directory ever installed), this hook returns after a
  handful of pure filesystem reads -- ``lstat``/``read`` only, never a
  ``git`` subprocess call. ``install_git_hooks.py --heal`` (the one
  subprocess this hook can run) fires only once the wrapper directory is
  confirmed present.
- **At most one line of output**, and only when the heal actually wrote
  something -- a no-op heal (chain already current) is silent.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from _hook_utils import is_disabled

DISABLE_FLAG = "PRAXION_DISABLE_HOOK_CHAIN_HEAL"
WRAPPER_DIRNAME = "praxion-hooks"
SUBPROCESS_TIMEOUT_SECONDS = 15


def _fast_common_dir(cwd: Path) -> Path | None:
    """Resolve the git COMMON directory via pure filesystem reads.

    Mirrors what ``git rev-parse --git-common-dir`` reports, for the two
    shapes a session's cwd can be: the main worktree (``.git`` is a
    directory -- the common dir IS that directory) or a linked worktree
    (``.git`` is a file naming the per-worktree gitdir, whose own
    ``commondir`` file names the real common directory). Returns None on any
    unexpected shape rather than guessing -- the caller then simply performs
    no heal this session, which is always safe.
    """
    git_entry = cwd / ".git"
    try:
        entry_stat = os.lstat(git_entry)
    except OSError:
        return None
    if stat.S_ISDIR(entry_stat.st_mode):
        return git_entry
    if not stat.S_ISREG(entry_stat.st_mode):
        return None
    try:
        content = git_entry.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    worktree_gitdir = Path(content.split(":", 1)[1].strip())
    if not worktree_gitdir.is_absolute():
        worktree_gitdir = (cwd / worktree_gitdir).resolve()
    try:
        common_rel = (worktree_gitdir / "commondir").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    common = Path(common_rel)
    if not common.is_absolute():
        common = (worktree_gitdir / common_rel).resolve()
    return common


def _existing_wrapper_dir(cwd: Path) -> Path | None:
    """Return the wrapper directory path iff it exists on disk. No subprocess."""
    common_dir = _fast_common_dir(cwd)
    if common_dir is None:
        return None
    wrapper_dir = common_dir / WRAPPER_DIRNAME
    try:
        os.lstat(wrapper_dir)
    except OSError:
        return None
    return wrapper_dir


def _resolve_plugin_root() -> Path:
    plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root_str:
        return Path(plugin_root_str)
    return Path(__file__).resolve().parent.parent


def _run_heal(cwd: Path, plugin_root: Path) -> str | None:
    """Invoke ``install_git_hooks.py --heal``; return its one-line summary
    iff the run performed a write, else None. Any failure is swallowed."""
    script = plugin_root / "scripts" / "install_git_hooks.py"
    if not script.is_file():
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--heal", "--plugin-root", str(plugin_root), "--json"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or not payload.get("changed"):
        return None
    messages = payload.get("messages") or []
    return messages[0] if messages else "git hook chain restored"


def _emit(context: str) -> None:
    print(
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        )
    )


def main() -> None:
    # Drain stdin even when unused -- the hook framework can SIGPIPE on its
    # write end if the pipe is left unread.
    raw = sys.stdin.read()
    if is_disabled(DISABLE_FLAG):
        return
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    cwd = Path(payload.get("cwd") or os.getcwd())

    wrapper_dir = _existing_wrapper_dir(cwd)
    if wrapper_dir is None:
        return  # fast-exit: no Praxion wrapper directory -- nothing to heal

    summary = _run_heal(cwd, _resolve_plugin_root())
    if summary:
        _emit(f"praxion: git hook chain self-heal -- {summary}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block session creation
