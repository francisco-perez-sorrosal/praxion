#!/usr/bin/env python3
"""Collect a commit's test suite in a depth-1 clone, the way CI checks it out.

CI clones at depth 1. A test that reads git history while it is being collected (a parametrize
list built from `git diff <base>`, a module constant from `git rev-parse HEAD~1`) raises before
any skip applies, so the whole suite fails there and nowhere else: every local run has the
history. This check clones the committed `--ref` at depth 1 into a temporary directory and runs
the collection command inside it, so the failure shows before the merge instead of after the push.

Usage:
    check_shallow_collection.py [--repo-root DIR] [--ref REF] [--cwd SUBDIR] [-- COMMAND...]

The default command is this interpreter's `pytest --collect-only -q`; give another after `--`
(for example a pocket's own interpreter). Only committed state is checked: the clone holds `--ref`,
never the working tree. Every `GIT_*` variable is removed from the command's environment, so a
`GIT_DIR` inherited from a git hook cannot lend the clone the source repository's history.

Exit codes: 0 the suite collects at depth 1 / 1 it does not (the command's output tail is printed)
/ 2 usage or infrastructure error (no repository, an unresolvable ref, a failed clone, a command
that cannot start). The repository root is `--repo-root` or the git toplevel of the current
directory, never this file's location: managed projects run it through a `~/.local/bin` link.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_COMMAND = (sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider")
PYTEST_NO_TESTS_COLLECTED = 5  # pytest's own exit status: nothing to collect is not a failure
TAIL_LINES = 40
GIT_TIMEOUT_SECONDS = 120
COLLECT_TIMEOUT_SECONDS = 900


class CheckError(Exception):
    """An input or infrastructure failure: the check could not run, so it never reads as clean."""


@dataclass(frozen=True)
class Collection:
    sha: str
    returncode: int
    output: str


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        repo = _repo_root(args.repo_root)
        sha = _resolve_commit(repo, args.ref)
        collection = _collect_at_depth_one(
            repo, sha, args.cwd, tuple(args.command) or DEFAULT_COMMAND
        )
    except CheckError as error:
        print(f"check_shallow_collection: {error}", file=sys.stderr)
        return 2
    _report(collection, dirty=_has_uncommitted_changes(repo))
    return 0 if _collected(collection.returncode) else 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", help="repository to check (default: the git toplevel here)")
    parser.add_argument(
        "--ref", default="HEAD", help="commit, branch or tag to clone (default HEAD)"
    )
    parser.add_argument("--cwd", default=".", help="directory inside the clone to collect from")
    parser.add_argument("command", nargs="*", help="collection command, after `--`")
    return parser.parse_args(argv)


def _collected(returncode: int) -> bool:
    return returncode in (0, PYTEST_NO_TESTS_COLLECTED)


def _report(collection: Collection, *, dirty: bool) -> None:
    short = collection.sha[:8]
    if _collected(collection.returncode):
        print(f"shallow collection: clean at depth 1 ({short})")
    else:
        tail = "\n".join(collection.output.splitlines()[-TAIL_LINES:])
        print(f"shallow collection: FAILED at depth 1 ({short}), exit {collection.returncode}")
        print(tail)
    if dirty:
        print("note: uncommitted changes are not checked; the clone holds the committed ref only")


# -- git and process adapters -------------------------------------------------------------------


def _git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckError(f"git {' '.join(args)} failed: {error}") from error


def _repo_root(given: str | None) -> Path:
    start = Path(given) if given else Path.cwd()
    probe = _git(start, "rev-parse", "--show-toplevel")
    if probe.returncode != 0:
        raise CheckError(f"not a git repository: {start}")
    return Path(probe.stdout.strip())


def _resolve_commit(repo: Path, ref: str) -> str:
    probe = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if probe.returncode != 0:
        raise CheckError(f"cannot resolve ref {ref!r} to a commit in {repo}")
    return probe.stdout.strip()


def _has_uncommitted_changes(repo: Path) -> bool:
    status = _git(repo, "status", "--porcelain", "--untracked-files=no")
    return status.returncode == 0 and bool(status.stdout.strip())


def _collect_at_depth_one(
    repo: Path, sha: str, subdir: str, command: tuple[str, ...]
) -> Collection:
    with tempfile.TemporaryDirectory(prefix="shallow-collection-") as scratch:
        clone = Path(scratch) / "clone"
        _shallow_clone(repo, sha, clone)
        workdir = clone / subdir
        if not workdir.is_dir():
            raise CheckError(f"--cwd {subdir!r} is not a directory at {sha[:8]}")
        try:
            run = subprocess.run(
                list(command),
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=COLLECT_TIMEOUT_SECONDS,
                env=_git_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CheckError(f"collection command could not run: {error}") from error
        return Collection(sha=sha, returncode=run.returncode, output=run.stdout + run.stderr)


def _shallow_clone(repo: Path, sha: str, clone: Path) -> None:
    """A clone holding `sha` alone: a `file://` fetch honours depth, where a local path ignores it."""
    steps = (
        ("init", "-q", str(clone)),
        ("-C", str(clone), "fetch", "-q", "--depth", "1", "--no-tags", repo.as_uri(), sha),
        ("-C", str(clone), "checkout", "-q", "--detach", "FETCH_HEAD"),
    )
    for step in steps:
        result = subprocess.run(
            ["git", *step],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=_git_env(),
        )
        if result.returncode != 0:
            raise CheckError(f"depth-1 clone of {sha[:8]} failed: {result.stderr.strip()}")


if __name__ == "__main__":
    sys.exit(main())
