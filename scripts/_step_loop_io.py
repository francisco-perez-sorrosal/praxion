"""The git and command adapters of the step-loop driver.

The driver's pure modules decide; this one touches the repository and runs commands, and
nothing else in the driver does. Two halves:

* **Git**: which declared paths differ from HEAD, and `commit_paths`, the commit by explicit
  path. A commit may only change the paths it was given. Before staging, the tree outside
  those paths is snapshotted (the index rows, the unstaged edits and the untracked files);
  an index row already staged outside them is refused as a disturbed tree, since a path-limited
  commit leaves it staged and a later plain commit would sweep it in. After the commit, the
  commit's file set must equal the paths and the snapshot must be unchanged. A disturbance is
  reported with both snapshots; nothing is unstaged, reset or restored on the caller's behalf.
  Outer-loop paths (under `tests/acceptance/` or `tests/e2e/`, or named by any step's
  `Read-only:`) are withheld from the commit whatever the plan declares.
* **Runner**: the `Check:` command and the derived test scope. The resolver lists several
  invocations when the selected tests cannot share one process; each runs on its own and
  its output comes back on its own. Merging them into one run is the caller's job, never a
  concatenation of raw text. No runner is told to colour its output.

Every git call goes through `_git_runner.run_git`; a git that cannot run propagates as
`GitUnavailableError`, a git that refuses a command raises `GitCommandError`.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from _git_runner import run_git

OUTER_LOOP_PREFIXES = ("tests/acceptance/", "tests/e2e/")
RUN_TIMEOUT_SECONDS = 540.0
RESOLVER_TIMEOUT_SECONDS = 60.0
FAILURE_TAIL_LINES = 20
RESOLVER = Path(__file__).resolve().with_name("resolve_test_scope.py")
LITERAL_PATHSPECS = "--literal-pathspecs"
_NODE_BOUNDARIES = ("::", "[")
_UNTRACKED_DIRECTORY_MARK = "/"
_DELETED = "deleted"
_NOT_A_FILE = "not-a-file"
_NO_COLOUR_ENV = {"NO_COLOR": "1", "PY_COLORS": "0"}
_FORCED_COLOUR_VARS = ("FORCE_COLOR", "CLICOLOR_FORCE")

Entries = tuple[tuple[str, str], ...]


class GitCommandError(RuntimeError):
    """git ran and refused a command the driver needs to succeed."""


# --- The commit by explicit path ---------------------------------------------------------


@dataclass(frozen=True)
class TreeSnapshot:
    """The tree outside a pathspec: (path, token) pairs, and the unstaged diff as a patch.

    `staged` holds the index rows (token: git's raw row, with both blob ids), `unstaged` the
    modified tracked files (token: the worktree blob id) and `untracked` the new ones. The
    patch text is for a human restoring the tree; it takes no part in equality.
    """

    staged: Entries
    unstaged: Entries
    untracked: Entries
    unstaged_diff: str = field(default="", compare=False)

    def paths_differing(self, other: TreeSnapshot) -> tuple[str, ...]:
        mine, theirs = self._tagged(), other._tagged()
        return tuple(sorted({path for _, path, _ in mine ^ theirs}))

    def patch_text(self) -> str:
        """The snapshot as text for `TREE_SNAPSHOT_<request>.patch`."""
        lines = ["# staged outside the pathspec"]
        lines += [f"#   {path}  {row}" for path, row in self.staged]
        lines.append("# untracked outside the pathspec (path, blob id)")
        lines += [f"#   {path}  {blob}" for path, blob in self.untracked]
        lines.append("# unstaged diff outside the pathspec")
        return "\n".join(lines) + "\n" + self.unstaged_diff

    def _tagged(self) -> frozenset[tuple[str, str, str]]:
        kinds = (
            ("staged", self.staged),
            ("unstaged", self.unstaged),
            ("untracked", self.untracked),
        )
        return frozenset((kind, path, token) for kind, entries in kinds for path, token in entries)


@dataclass(frozen=True)
class Committed:
    """The commit holds exactly the paths and the tree outside them is as it was."""

    sha: str
    files: tuple[str, ...]
    withheld: tuple[str, ...]


@dataclass(frozen=True)
class NothingToCommit:
    """None of the paths differs from HEAD once the outer-loop paths are withheld."""

    withheld: tuple[str, ...]


@dataclass(frozen=True)
class CommitRefused:
    """The hooks (or git) refused the commit, after the one re-stage retry when files moved."""

    detail: str


@dataclass(frozen=True)
class TreeDisturbed:
    """The commit touched, or would touch, more than its paths.

    `sha` is the commit when one was made. `paths` names what moved outside the pathspec (or
    was already staged there); `before` and `after` are the two snapshots, equal when nothing
    was run.
    """

    before: TreeSnapshot
    after: TreeSnapshot
    paths: tuple[str, ...]
    sha: str | None


CommitOutcome = Union[Committed, NothingToCommit, CommitRefused, TreeDisturbed]  # noqa: UP007 -- runtime value, 3.9 floor


def commit_paths(
    repo: Path, paths: Iterable[str], message: str, read_only: Iterable[str] = ()
) -> CommitOutcome:
    """Commit `paths` (minus the outer-loop paths) with `message`, touching nothing else."""
    kept, withheld = split_outer_loop(paths, read_only)
    if not kept:
        return NothingToCommit(withheld)
    pathset = frozenset(kept)
    before = snapshot_outside(repo, pathset)
    if before.staged:
        staged = tuple(path for path, _ in before.staged)
        return TreeDisturbed(before, before, staged, None)
    _stage(repo, kept)
    expected = frozenset(_lines(_git(repo, "diff", "--cached", "--name-only", "-z", "--", *kept)))
    if not expected:
        return NothingToCommit(withheld)
    refused = _commit_with_retry(repo, message, kept)
    after = snapshot_outside(repo, pathset)
    if after != before:
        sha = _head_sha(repo) if refused is None else None
        return TreeDisturbed(before, after, before.paths_differing(after), sha)
    if refused is not None:
        return CommitRefused(refused)
    return _verified(repo, before, expected, withheld)


def paths_differing_from_head(repo: Path, paths: Iterable[str]) -> tuple[str, ...]:
    """The given paths that differ from HEAD: modified, staged, untracked or deleted."""
    wanted = tuple(paths)
    if not wanted:
        return ()
    status = _git(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        "--",
        *wanted,
    )
    changed = {entry[3:] for entry in _lines(status)}
    return tuple(path for path in wanted if path in changed)


def split_outer_loop(
    paths: Iterable[str], read_only: Iterable[str] = ()
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(kept, withheld): outer-loop paths leave the set whatever the plan declares.

    An entry names an outer-loop path as a path, `path::function` or a node id, or as a
    directory ending in a slash.
    """
    named = tuple(_entry_path(entry) for entry in read_only)
    withheld = tuple(p for p in paths if _is_outer_loop(p, named))
    kept = tuple(p for p in paths if p not in withheld)
    return kept, withheld


def snapshot_outside(repo: Path, pathspec: frozenset[str]) -> TreeSnapshot:
    """The index rows, unstaged edits and untracked files of every path not in `pathspec`."""
    raw = _lines(_git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev"))
    staged = tuple(sorted(zip(raw[1::2], raw[0::2])))  # noqa: B905 -- strict= is 3.10+
    modified = [p for p in _lines(_git(repo, "diff", "--name-only", "-z")) if p not in pathspec]
    others = _lines(_git(repo, "ls-files", "--others", "--exclude-standard", "-z"))
    untracked = [
        p for p in others if not p.endswith(_UNTRACKED_DIRECTORY_MARK) and p not in pathspec
    ]
    diff = _git(repo, "diff", "--binary", "--", *modified) if modified else ""
    return TreeSnapshot(
        staged=tuple((path, row) for path, row in staged if path not in pathspec),
        unstaged=_worktree_blobs(repo, modified),
        untracked=_worktree_blobs(repo, untracked),
        unstaged_diff=diff,
    )


def _entry_path(entry: str) -> str:
    cut = min((entry.find(mark) for mark in _NODE_BOUNDARIES if mark in entry), default=len(entry))
    return entry[:cut]


def _is_outer_loop(path: str, named: tuple[str, ...]) -> bool:
    if path.startswith(OUTER_LOOP_PREFIXES):
        return True
    return any(path == one or path.startswith(one.rstrip("/") + "/") for one in named)


def _stage(repo: Path, paths: tuple[str, ...]) -> None:
    _git(repo, "add", "--all", "--", *paths)


def _commit_with_retry(repo: Path, message: str, paths: tuple[str, ...]) -> str | None:
    """None on success, else git's own words. Hooks that rewrote files get one re-stage."""
    attempt = _try_commit(repo, message, paths)
    if attempt is not None and _lines(_git(repo, "diff", "--name-only", "-z", "--", *paths)):
        _stage(repo, paths)
        attempt = _try_commit(repo, message, paths)
    return attempt


def _try_commit(repo: Path, message: str, paths: tuple[str, ...]) -> str | None:
    done = _run(repo, "commit", "-m", message, "--", *paths)
    if done.returncode == 0:
        return None
    return _tail(done.stdout + done.stderr)


def _verified(
    repo: Path, snapshot: TreeSnapshot, expected: frozenset[str], withheld: tuple[str, ...]
) -> Union[Committed, TreeDisturbed]:  # noqa: UP007 -- runtime value, 3.9 floor
    """The commit just made, if its file set is exactly what was staged."""
    sha = _head_sha(repo)
    listing = _git(repo, "diff-tree", "--root", "-r", "--no-commit-id", "--name-only", "-z", sha)
    files = frozenset(_lines(listing))
    if files != expected:
        return TreeDisturbed(snapshot, snapshot, tuple(sorted(files ^ expected)), sha)
    return Committed(sha, tuple(sorted(files)), withheld)


def _head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "--verify", "HEAD").strip()


def _worktree_blobs(repo: Path, paths: list[str]) -> Entries:
    """Blob ids of the files as they are on disk; a file git cannot hash gets a marker."""
    marked = {p: _DELETED for p in paths if not os.path.lexists(repo / p)}
    marked |= {p: _NOT_A_FILE for p in paths if p not in marked and not (repo / p).is_file()}
    hashable = [p for p in paths if p not in marked]
    if hashable:  # a path holding a newline cannot ride --stdin-paths; none is expected
        ids = _git(
            repo, "hash-object", "--no-filters", "--stdin-paths", stdin="\n".join(hashable) + "\n"
        )
        marked |= dict(zip(hashable, ids.split()))  # noqa: B905 -- strict= is 3.10+
    return tuple(sorted(marked.items()))


def _run(repo: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """`git`, with every pathspec literal: a declared name is never a glob."""
    return run_git(repo, LITERAL_PATHSPECS, *args, stdin=stdin)


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    done = _run(repo, *args, stdin=stdin)
    if done.returncode != 0:
        raise GitCommandError(f"git {' '.join(args[:3])} failed: {_tail(done.stderr)}")
    return done.stdout


def _lines(nul_separated: str) -> list[str]:
    return [part for part in nul_separated.split("\0") if part]


def _tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-FAILURE_TAIL_LINES:])


# --- The runner --------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandRun:
    """One command's output (stdout then stderr). `problem` is set iff it never exited."""

    argv: tuple[str, ...]
    cwd: str
    output: str
    returncode: int | None
    problem: str | None = None

    def __post_init__(self) -> None:
        if (self.returncode is None) != (self.problem is not None):
            raise ValueError("a run has a return code or a problem, never both and never neither")


@dataclass(frozen=True)
class ScopeRuns:
    """The derived scope: the resolver's decision and each invocation's own run."""

    decision: str
    runs: tuple[CommandRun, ...]


@dataclass(frozen=True)
class ScopeUnresolved:
    """The resolver itself failed (exit 2 means: run the full suite) or answered no JSON."""

    resolver: CommandRun


def run_check(repo: Path, command: str, timeout: float = RUN_TIMEOUT_SECONDS) -> CommandRun:
    """Run a step's `Check:` command (split like a shell would, run without one)."""
    return run_command(tuple(shlex.split(command)), repo, timeout)


def run_derived_scope(
    repo: Path, changed: Iterable[str], timeout: float = RUN_TIMEOUT_SECONDS
) -> Union[ScopeRuns, ScopeUnresolved]:  # noqa: UP007 -- runtime value, 3.9 floor
    """Resolve the test scope for `changed` and run every invocation it lists."""
    ask = (sys.executable, str(RESOLVER), "--repo-root", str(repo), "--changed", *changed, "--json")
    resolver = run_command(ask, repo, RESOLVER_TIMEOUT_SECONDS)
    plan = _read_plan(resolver)
    if plan is None:
        return ScopeUnresolved(resolver)
    invocations = [i for pocket in plan["pockets"] for i in pocket["invocations"]]
    runs = tuple(run_command(tuple(i["argv"]), repo / i["cwd"], timeout) for i in invocations)
    return ScopeRuns(str(plan["decision"]), runs)


def run_command(argv: tuple[str, ...], cwd: Path, timeout: float) -> CommandRun:
    """Run `argv` under a timeout with colour off; a run that cannot finish says why."""
    try:
        done = subprocess.run(
            argv, cwd=str(cwd), env=_no_colour_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        partial = _text(exc.stdout) + _text(exc.stderr)
        return CommandRun(argv, str(cwd), partial, None, f"timed out after {timeout:g}s")
    except OSError as exc:
        return CommandRun(argv, str(cwd), "", None, f"could not start: {exc}")
    return CommandRun(argv, str(cwd), done.stdout + done.stderr, done.returncode)


def _read_plan(resolver: CommandRun) -> dict | None:
    if resolver.returncode != 0:
        return None
    try:
        plan = json.loads(resolver.output)
    except json.JSONDecodeError:
        return None
    return plan if isinstance(plan, dict) and "pockets" in plan else None


def _no_colour_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _FORCED_COLOUR_VARS}
    return {**env, **_NO_COLOUR_ENV}


def _text(captured: str | bytes | None) -> str:
    if isinstance(captured, bytes):
        return captured.decode("utf-8", errors="replace")
    return captured or ""
