"""Which files a ``git commit`` about to run would record, resolved from a hook payload.

The same-call staging helpers behind ``scripts/check_id_citation_discipline.py``:
a PreToolUse hook fires before any command in the Bash call runs, so the staged
set alone misses a file that ``git add x && git commit`` stages. Stdlib-only and
3.9-safe.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from _git_runner import run_git

# Env signal the commit-gate wrapper exports; authoritative that stdin carries a
# commit payload, so any git failure under it is contention, never "not a repo".
_PAYLOAD_ENV = "PRAXION_COMMIT_PAYLOAD"

_COMMIT_ALL_FLAG = re.compile(r"(?:^|\s)(?:-a|--all|-[a-zA-Z]*a[a-zA-Z]*)(?:\s|$)")

# Shell operators that separate the commands of one Bash call.
# Declared limit: `|`, `&`, `$(...)`, `xargs` and wrapper shells are not split on (td-528).
_COMMAND_SEPARATOR = re.compile(r"&&|\|\||;|\n")
# `git add` flags that stage every change in the working tree; `:/` is the
# pathspec for the repository root, so it matches them from any subdirectory.
_ADD_WHOLE_TREE = frozenset({"-A", "--all"})


def _same_call_add_pathspecs(command: str) -> list[str] | None:
    """Pathspecs a `git add` earlier in the same Bash call will stage.

    The PreToolUse hook fires before any command in the call runs, so a file
    that `git add x && git commit` stages is not in the index yet and a
    staged-set scope would miss it. Returns the pathspecs named by every
    `git add` that precedes the first `git commit` (``[":/"]``, the repository
    root, for `-A`/`--all`), or ``None`` when no such `git add` exists. A
    `git add` after the commit stages nothing the commit records, so it is
    ignored.
    """
    pathspecs: list[str] = []
    found = False
    for segment in _COMMAND_SEPARATOR.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if tokens[:2] == ["git", "commit"]:
            break
        if tokens[:2] != ["git", "add"]:
            continue
        found = True
        args = tokens[2:]
        if any(arg in _ADD_WHOLE_TREE for arg in args):
            pathspecs.append(":/")
        pathspecs.extend(arg for arg in args if not arg.startswith("-"))
    return pathspecs if found else None


def _pathspec_changed_names(cwd: Path, pathspecs: list[str]) -> list[str]:
    """Repo-relative names of modified or untracked files matching ``pathspecs``,
    resolved from ``cwd`` the way the `git add` itself would resolve them."""
    names: list[str] = []
    changed = _git(cwd, "diff", "--name-only", "--diff-filter=ACMR", "-z", "--", *pathspecs)
    untracked = _git(
        cwd, "ls-files", "--others", "--exclude-standard", "-z", "--full-name", "--", *pathspecs
    )
    if changed is not None:
        names.extend(n for n in changed.stdout.split("\0") if n)
    if untracked is not None:
        names.extend(n for n in untracked.stdout.split("\0") if n)
    return names


_GIT_RETRIES = 3
_GIT_RETRY_SLEEP = 0.1


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run a git command, retrying transient failures (index-lock contention).

    Concurrent git activity in the same worktree — a sibling agent committing,
    a finalize hook firing — can make an index-reading command fail for a
    moment. Retrying a few times absorbs that; a persistent failure returns
    ``None`` so the caller can choose a safe response rather than misread it.
    """
    for attempt in range(_GIT_RETRIES):
        try:
            # Through the shared runner: this gate fires on every `git commit`,
            # so it always runs with git's repository-scoping variables in the
            # environment -- exported *relative*, which silently re-targets any
            # call naming a different repository than the firing hook's.
            result = run_git(cwd, *args)
        except OSError:
            # git could not be run to completion (resource pressure, transient
            # exec failure, the runner's timeout -- GitUnavailableError is an
            # OSError). Treat as a failed call so the caller falls to its
            # pass-safe path rather than crashing the gate.
            result = None
        if result is not None and result.returncode == 0:
            return result
        if attempt + 1 < _GIT_RETRIES:
            time.sleep(_GIT_RETRY_SLEEP)
    return None


def _git_changed_names(repo_root: Path, *diff_args: str) -> list[str]:
    result = _git(repo_root, "diff", "--name-only", "--diff-filter=ACMR", "-z", *diff_args)
    if result is None:
        return []
    return [name for name in result.stdout.split("\0") if name]


class _ScopeUnavailable:
    """Marker: hook mode is in effect but the commit scope could not be computed."""


def hook_scope_files(
    payload: dict, default_root: Path
) -> tuple[Path, list[Path]] | type[_ScopeUnavailable] | None:
    """Resolve the file set a ``git commit`` about to run would actually record.

    Invoked as a PreToolUse hook the script receives the tool payload on stdin
    and no ``--files``. The commit's scope is the staged set, plus the
    tracked-but-unstaged modifications when the command carries ``-a``/``--all``
    (``-am`` included). Three outcomes: the scoped file list; ``None`` when the
    payload's directory is not inside a git repository (a genuine non-hook
    caller — the full scan is right); and ``_ScopeUnavailable`` when we are in a
    git repo but scoping failed even after retries — the caller must pass rather
    than full-scan, because gating a commit on the whole tree's pre-existing
    violations is never the right hook behaviour.
    """
    tool_input = payload.get("tool_input") or {}
    command = str(tool_input.get("command", ""))
    cwd = Path(str(payload.get("cwd") or default_root))
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top is None:
        # The commit-gate wrapper only fires on a real `git commit`, so when its
        # env signal is present a git failure is never "not a repo" — it is
        # contention, and a whole-repo scan would wrongly gate the commit on
        # unrelated pre-existing violations. Return the pass-safe marker.
        if os.environ.get(_PAYLOAD_ENV):
            return _ScopeUnavailable
        # Direct CLI: distinguish "not a repo" (full scan is correct) from a
        # transient error inside a repo with one quick probe.
        try:
            probe = run_git(cwd, "rev-parse", "--is-inside-work-tree")
        except OSError:
            return None
        if probe.returncode != 0:
            return None
        return _ScopeUnavailable
    if not top.stdout.strip():
        return None
    repo_root = Path(top.stdout.strip()).resolve()
    names = _git_changed_names(repo_root, "--cached")
    if _COMMIT_ALL_FLAG.search(command):
        names.extend(_git_changed_names(repo_root))
    pathspecs = _same_call_add_pathspecs(command)
    if pathspecs:
        names.extend(_pathspec_changed_names(cwd, pathspecs))
    return repo_root, [repo_root / name for name in dict.fromkeys(names)]
