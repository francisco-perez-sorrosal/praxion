"""Which checkouts a repository has: its main working tree and every linked worktree.

The one place that asks git. Cross-checkout consumers (the spawn counter, the
log-health check, the merge-in trigger) take their list from here, so they agree
on what a checkout is and what it is called.

Runs ``git``, so nothing on the per-tool-call hook path may import this module;
the owner writer and reader never do.
"""

from __future__ import annotations

import os
import subprocess
from collections import namedtuple
from pathlib import Path

from .location import STATE_DIRNAME

# `name` is the root directory's basename -- the convention `location.locate`
# gives a row's `project` -- so a worktree's name and the `project` of the rows
# it recorded agree. `head` is the commit its working tree is at.
Checkout = namedtuple("Checkout", ("root", "state_dir", "name", "is_main", "head"))

# `(checkouts, error)`. Either `error` is None and the main checkout comes first,
# or `error` names why git could not answer and `checkouts` is empty: a failed
# listing is never an empty repository.
CheckoutListing = namedtuple("CheckoutListing", ("checkouts", "error"))

# Local plumbing only: past this, git is hung (a lock, a prompt on a hook path).
GIT_TIMEOUT_SECONDS = 10

# Git hands these to every hook it runs, scoped (and relative) to the repository
# whose hook is firing; a call that names another repository must not inherit
# them. Everything else a caller sets (identity, config, ssh) is left alone. The
# same list lives in `scripts/_git_runner.py`, which hooks cannot import.
_REPOSITORY_SCOPING_ENV_VARS = (
    "GIT_INDEX_FILE",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_NAMESPACE",
)


def repository_checkouts(repo_root: Path) -> CheckoutListing:
    """The checkouts of the repository ``repo_root`` belongs to, main checkout first.

    ``repo_root`` may be any of them. A linked worktree whose directory is gone
    (git has not pruned it yet) is dropped. Never raises.
    """
    completed, error = _git(repo_root, "worktree", "list", "--porcelain")
    if completed is None:
        return CheckoutListing((), error)
    if completed.returncode != 0:
        return CheckoutListing((), f"git worktree list failed: {completed.stderr.strip()}")
    entries = _parse_porcelain(completed.stdout)
    if not entries or entries[0].bare:
        return CheckoutListing((), "the repository has no main working tree to read")
    checkouts = tuple(
        _checkout(entry, is_main=index == 0)
        for index, entry in enumerate(entries)
        if index == 0 or Path(entry.root).is_dir()
    )
    return CheckoutListing(checkouts, None)


def contains(main_root: Path, commit: str) -> bool:
    """Whether ``commit`` is part of the history of the HEAD of ``main_root``.

    A commit git does not know, or a failure to ask, reads as not contained: the
    caller then leaves that worktree for the explicit merge command.
    """
    completed, _ = _git(main_root, "merge-base", "--is-ancestor", commit, "HEAD")
    return completed is not None and completed.returncode == 0


_PorcelainEntry = namedtuple("_PorcelainEntry", ("root", "head", "bare"))


def _parse_porcelain(text: str) -> list[_PorcelainEntry]:
    """The entries of ``git worktree list --porcelain``: blank-line separated
    blocks of ``key value`` lines, the first block the main working tree."""
    entries = []
    for block in text.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" in fields:
            entries.append(
                _PorcelainEntry(fields["worktree"], fields.get("HEAD", ""), "bare" in fields)
            )
    return entries


def _checkout(entry: _PorcelainEntry, *, is_main: bool) -> Checkout:
    root = Path(entry.root)
    return Checkout(root, root / STATE_DIRNAME, root.name, is_main, entry.head)


def _git(repo_root: Path, *args: str):
    """`(completed process, None)`, or `(None, reason)` when git could not be run."""
    env = {k: v for k, v in os.environ.items() if k not in _REPOSITORY_SCOPING_ENV_VARS}
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, f"git {args[0]} timed out after {GIT_TIMEOUT_SECONDS} s"
    except OSError as exc:
        return None, f"git could not be run in {repo_root}: {exc}"
    return completed, None
