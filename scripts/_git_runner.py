"""Shared `git` subprocess primitive for `scripts/`.

Twelve private `_git`/`_run_git` helpers had grown independently across
`scripts/` and `hooks/`, and no two shared a contract: some took a `repo_root`,
others closed over a module-level constant; some caught
`(OSError, subprocess.SubprocessError)`, others only `FileNotFoundError`; and
**half passed no `timeout` at all**. The split was populational, not random --
the `hooks/` helpers all carried a timeout because a hang there is immediately
visible in a blocking harness, while the advisory `scripts/` ones did not,
because a hang there just looks slow.

`finalize_adrs.py` sat on the wrong side of that split while running on the
*blocking* post-merge hook path, where a hung or credential-prompting `git`
would stall ADR finalize with no bound at all. That crossover is why this
module exists: **the timeout is the load-bearing property, not the
deduplication.** Body-hash duplication detection is structurally blind here --
the helpers were a behavioural fork, not copies.

The second load-bearing property arrived the same way: every helper here names
its repository, and none of them scrubbed the repository-scoping variables git
exports to hooks -- so a hook-triggered call silently acted on the *hook's*
repository instead of the named one. See `REPOSITORY_SCOPING_ENV_VARS`.

The contract generalizes `adr_health._git` and `check_metrics_freshness._git`,
the two helpers that were already correct:

    run_git(repo_root, *args)     -> CompletedProcess[str]; raises GitUnavailableError
    git_output(repo_root, *args)  -> stripped stdout, or None on any failure

`run_git` is the base: it distinguishes "git ran and returned non-zero" (a
`CompletedProcess` the caller inspects) from "git could not run at all"
(`GitUnavailableError`). `git_output` is the swallow-everything convenience for
callers that already treat both as "no answer". A caller that must stay loud
when git is *absent* -- a gate, for instance, where a silent `None` would
report a false all-clear -- uses `run_git` and lets the error propagate.

`GitUnavailableError` subclasses `OSError` deliberately: a caller that already
wrote `except OSError` to catch a missing `git` binary keeps working unchanged,
and a *timeout* (`subprocess.TimeoutExpired`, which is not an `OSError`) now
lands in that same handler instead of escaping as a new exception type.

Sibling-imported the same way as `_repo_root` and `_script_cli`, so it resolves
through the `install_claude.sh` symlink without needing a link of its own. Not
executable, so the installer's `-f && -x` filter leaves it off `PATH` --
correct, since it is a library and not a user-facing tool.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

# Every `git` call these scripts make is local plumbing -- rev-parse, log,
# ls-tree, show, mv, add -- so 30s is far past any legitimate runtime and is
# only ever reached by a genuine hang (an index lock, a credential prompt on a
# non-interactive hook path).
GIT_TIMEOUT_SECONDS = 30.0

# Git exports these to every hook it runs, scoped to the repository whose hook
# is firing -- and it exports `GIT_INDEX_FILE` and `GIT_DIR` *relative*
# (`.git/index`, `.git`). A `run_git(other_repo, ...)` call inheriting them
# resolves `.git/index` under `other_repo`, so any repository whose `.git` is a
# worktree *pointer file* dies with `fatal: .git/index: index file open failed:
# Not a directory`. That is precisely the shape of a sidecar state mount, and
# it broke the whole post-commit convergence channel: merge-back read the
# failure as a merge conflict and finalize_adrs silently declined to promote.
#
# So a runner that takes its repository as an argument must never let an
# inherited environment redirect it: `repo_root` is the caller's stated intent
# and outranks whatever the ambient process was scoped to. Only the
# repository-scoping variables are removed -- identity (`GIT_AUTHOR_*`,
# `GIT_COMMITTER_*`), config (`GIT_CONFIG_*`), `GIT_SSH*` and everything else
# a caller or a test fixture deliberately sets are left intact.
REPOSITORY_SCOPING_ENV_VARS = (
    "GIT_INDEX_FILE",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_NAMESPACE",
)


def _unscoped_environ() -> dict[str, str] | None:
    """`os.environ` minus the repository-scoping variables, or `None`.

    `None` means "nothing to scrub" and is passed straight to `subprocess.run`,
    which then inherits the parent environment as before -- so off the hook
    path this costs one membership test per variable and copies nothing.
    """
    present = [name for name in REPOSITORY_SCOPING_ENV_VARS if name in os.environ]
    if not present:
        return None
    env = dict(os.environ)
    for name in present:
        del env[name]
    return env


class GitUnavailableError(OSError):
    """`git` could not be run to completion.

    Raised for a missing binary, a timeout, or any other OS-level failure to
    execute -- never for a `git` command that ran and exited non-zero, which is
    a `CompletedProcess` with a non-zero `returncode`.
    """


def run_git(
    repo_root: Path | str,
    *args: str,
    timeout: float = GIT_TIMEOUT_SECONDS,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `repo_root` under a bounded timeout.

    `stdin`, when given, is fed to git on standard input -- for the plumbing
    that reads a patch or an object body from it (`patch-id`, `hash-object --stdin`).

    Returns the `CompletedProcess` whatever the exit code; raises
    `GitUnavailableError` when git could not run to completion.

    `timeout` is keyword-only and cannot be disabled: `None` or a non-positive
    value raises `ValueError` rather than silently restoring the unbounded
    behaviour this module exists to remove.

    Decoding is pinned to UTF-8 with `errors="replace"` so a diff carrying
    invalid bytes yields U+FFFD rather than crashing a hook mid-flight.

    The child environment is stripped of the repository-scoping git variables
    (see `REPOSITORY_SCOPING_ENV_VARS`) so `repo_root` is the only thing that
    decides which repository the command acts on.
    """
    if timeout is None or timeout <= 0:
        raise ValueError(f"git timeout must be a positive number of seconds, got {timeout!r}")
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            env=_unscoped_environ(),
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitUnavailableError(
            f"git {' '.join(args)} exceeded the {timeout}s timeout in {repo_root}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitUnavailableError(
            f"git {' '.join(args)} could not be run in {repo_root}: {exc}"
        ) from exc


def git_output(
    repo_root: Path | str,
    *args: str,
    timeout: float = GIT_TIMEOUT_SECONDS,
    logger: logging.Logger | None = None,
    stdin: str | None = None,
) -> str | None:
    """Return `git <args>` stdout stripped, or `None` when git cannot answer.

    `None` covers all three no-answer cases: git could not run, git exited
    non-zero, or stdout was empty. Callers that must distinguish them use
    `run_git` directly.

    `logger`, when supplied, receives a DEBUG line naming the failing command,
    its exit code, and its stderr -- the diagnostic three of the migrated
    callers already emitted privately.
    """
    try:
        result = run_git(repo_root, *args, timeout=timeout, stdin=stdin)
    except GitUnavailableError as exc:
        if logger is not None:
            logger.debug("%s", exc)
        return None
    if result.returncode != 0:
        if logger is not None:
            logger.debug(
                "git %s failed (rc=%s): %s",
                " ".join(args),
                result.returncode,
                result.stderr.strip(),
            )
        return None
    return result.stdout.strip() or None
