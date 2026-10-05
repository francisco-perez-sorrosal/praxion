"""The git and command adapters of the step-loop driver: the only module that touches the
repository or runs a command.

* **Git**: `commit_paths`, the commit by explicit path. A declared path (a file or a directory,
  spelled any way git accepts) is normalised once and expanded to the changed files under it;
  filtering, staging, the commit and the snapshots all work on those file names. A row already
  staged outside them is tolerated and stays staged, since a path-limited commit never takes it;
  the snapshot records it. After the commit its file set must equal the staged files and the tree
  outside them (staged rows included) must be unchanged; otherwise the disturbance is reported
  with both snapshots and nothing is unstaged, reset or restored for the caller. Outer-loop files (under
  `tests/acceptance/` or `tests/e2e/`, or named by any step's `Read-only:`) are withheld
  whatever the plan declares.
* **Runner**: the `Check:` command and the derived test scope. Each invocation the resolver
  lists runs and comes back on its own; merging them is the caller's job. No runner is asked to
  colour, and each command leads a process group that a timeout kills whole.

Every git call goes through `_git_runner.run_git`; from `commit_paths`, a git that cannot run is
`CommitInterrupted` and one that refuses a command is `CommitRefused`. Pathspecs are
`:(literal)` magic, not a global flag, which git would export to every hook the commit runs.
"""

from __future__ import annotations

import contextlib
import json
import os
import posixpath
import shlex
import signal
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from _git_runner import GIT_TIMEOUT_SECONDS, GitUnavailableError, run_git

OUTER_LOOP_PREFIXES = ("tests/acceptance/", "tests/e2e/")
# The commit runs the repository's hooks (about twenty, installing environments on a first
# run): a bound of its own, not the thirty seconds of plain plumbing.
COMMIT_TIMEOUT_SECONDS = 600.0
RUN_TIMEOUT_SECONDS = 540.0
RESOLVER_TIMEOUT_SECONDS = 60.0
KILL_GRACE_SECONDS = 5.0
FAILURE_TAIL_LINES = 20
RESOLVER = Path(__file__).resolve().with_name("resolve_test_scope.py")
_LITERAL_PATHSPEC = ":(literal)"
_NODE_SEPARATOR = "::"
_STATUS_PATH_OFFSET = 3  # porcelain v1: two status letters and a space precede the path
_UNTRACKED_DIRECTORY_MARK = "/"
_DELETED = "deleted"
_NOT_A_FILE = "not-a-file"
_NO_COLOUR_ENV = {"NO_COLOR": "1", "PY_COLORS": "0"}
_FORCED_COLOUR_VARS = ("FORCE_COLOR", "CLICOLOR_FORCE")

Entries = tuple[tuple[str, str], ...]


class GitCommandError(RuntimeError):
    """git ran and refused a command the driver needs to succeed."""


class OutsideRepoError(ValueError):
    """A declared path (or `Read-only:` entry) that leaves the repository."""


# --- The commit by explicit path ---------------------------------------------------------


@dataclass(frozen=True)
class TreeSnapshot:
    """The tree outside a set of files: (path, token) pairs, and the unstaged diff as a patch.

    Tokens: git's raw index row (`staged`), the worktree blob id (`unstaged`, `untracked`; the
    blob is computed, not stored, so the patch text restores no untracked file). The patch
    takes no part in equality.
    """

    staged: Entries
    unstaged: Entries
    untracked: Entries
    unstaged_diff: str = field(default="", compare=False)

    def paths_differing(self, other: TreeSnapshot) -> tuple[str, ...]:
        mine, theirs = self._tagged(), other._tagged()
        return tuple(sorted({path for _, path, _ in mine ^ theirs}))

    def patch_text(self) -> str:
        """The snapshot as text for `TREE_SNAPSHOT_<request>.patch`: hashes, and the diff."""
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
    """The commit holds exactly the files and the tree outside them is as it was."""

    sha: str
    files: tuple[str, ...]
    withheld: tuple[str, ...]


@dataclass(frozen=True)
class NothingToCommit:
    """None of the paths differs from HEAD once the outer-loop files are withheld."""

    withheld: tuple[str, ...]


@dataclass(frozen=True)
class CommitRefused:
    """The hooks, git or a lock refused (after the one re-stage retry when files moved).

    The declared files stay staged; the next attempt reads them as pre-staged until unstaged.
    """

    detail: str


@dataclass(frozen=True)
class CommitInterrupted:
    """git could not run to completion (the commit outlived its bound, or git vanished).

    The declared files stay staged, `index.lock` may be left behind (`index_locked`), and the
    hooks git started may still be running and writing. `after` is the snapshot taken then.
    """

    detail: str
    after: TreeSnapshot
    index_locked: bool


@dataclass(frozen=True)
class TreeDisturbed:
    """The commit touched more than its files: `paths` names what moved, `sha` the commit
    if one was made, `before`/`after` the snapshots.
    """

    before: TreeSnapshot
    after: TreeSnapshot
    paths: tuple[str, ...]
    sha: str | None


CommitOutcome = Union[  # noqa: UP007 -- runtime value, 3.9 floor
    Committed, NothingToCommit, CommitRefused, CommitInterrupted, TreeDisturbed
]


@dataclass(frozen=True)
class _Job:
    paths: tuple[str, ...]
    withheld: tuple[str, ...]
    message: str
    before: TreeSnapshot
    timeout: float


def commit_paths(
    repo: Path,
    paths: Iterable[str],
    message: str,
    read_only: Iterable[str] = (),
    commit_timeout: float = COMMIT_TIMEOUT_SECONDS,
) -> CommitOutcome:
    """Commit the changed files under `paths` (minus the outer-loop files), touching no other."""
    kept, withheld = split_outer_loop(paths_differing_from_head(repo, paths), read_only, repo)
    if not kept:
        return NothingToCommit(withheld)
    before = snapshot_outside(repo, frozenset(kept))
    return _commit_and_judge(repo, _Job(kept, withheld, message, before, commit_timeout))


def paths_differing_from_head(repo: Path, paths: Iterable[str]) -> tuple[str, ...]:
    """The files under the given paths (directories expand) that differ from HEAD, sorted."""
    wanted = tuple(normalise_path(p, repo) for p in paths)
    if not wanted:
        return ()
    status = _git(
        repo,
        *("status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"),
        "--",
        *_specs(wanted),
    )
    return tuple(sorted({entry[_STATUS_PATH_OFFSET:] for entry in _lines(status)}))


def normalise_path(raw: str, root: Path | None = None) -> str:
    """The repo-relative, `normpath`-clean form of a path (absolute ones relate to `root`).

    A path that leaves the repository raises `OutsideRepoError`.
    """
    relative = raw
    if root is not None and os.path.isabs(raw):  # the shorter relpath is the one that stays inside
        relative = min((os.path.relpath(raw, base) for base in (root, root.resolve())), key=len)
    clean = posixpath.normpath(relative)
    if clean.startswith("/") or clean == ".." or clean.startswith("../"):
        raise OutsideRepoError(f"{raw!r} is outside the repository")
    return clean


def split_outer_loop(
    paths: Iterable[str], read_only: Iterable[str] = (), root: Path | None = None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(kept, withheld), both normalised: outer-loop files leave the set whatever the plan says.

    `paths` are files (`commit_paths` expands directories first). A `Read-only:` entry is a
    path, a directory or `path::node`, cut at the first `::` only, so `weird[1].txt` is a path.
    """
    named = tuple(normalise_path(entry.split(_NODE_SEPARATOR, 1)[0], root) for entry in read_only)
    clean = tuple(normalise_path(p, root) for p in paths)
    withheld = tuple(p for p in clean if _is_outer_loop(p, named))
    return tuple(p for p in clean if p not in withheld), withheld


def snapshot_outside(repo: Path, files: frozenset[str]) -> TreeSnapshot:
    """The index rows, unstaged edits and untracked files of every path not in `files`."""
    raw = _lines(_git(repo, "diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev"))
    staged = tuple(sorted(zip(raw[1::2], raw[0::2])))  # noqa: B905 -- strict= is 3.10+
    modified = [p for p in _lines(_git(repo, "diff", "--name-only", "-z")) if p not in files]
    others = _lines(_git(repo, "ls-files", "--others", "--exclude-standard", "-z"))
    untracked = [p for p in others if not p.endswith(_UNTRACKED_DIRECTORY_MARK) and p not in files]
    diff = _git(repo, "diff", "--binary", "--", *_specs(modified)) if modified else ""
    return TreeSnapshot(
        staged=tuple((path, row) for path, row in staged if path not in files),
        unstaged=_worktree_blobs(repo, modified),
        untracked=_worktree_blobs(repo, untracked),
        unstaged_diff=diff,
    )


def _commit_and_judge(repo: Path, job: _Job) -> CommitOutcome:
    try:
        _stage(repo, job.paths)
        staged = _git(
            repo, "diff", "--cached", "--name-only", "--no-renames", "-z", "--", *_specs(job.paths)
        )
        expected = frozenset(_lines(staged))
        refused = _commit_with_retry(repo, job) if expected else None
    except GitCommandError as exc:
        return CommitRefused(str(exc))
    except GitUnavailableError as exc:
        after = snapshot_outside(repo, frozenset(job.paths))
        return CommitInterrupted(str(exc), after, _index_locked(repo))
    if not expected:
        return NothingToCommit(job.withheld)
    after = snapshot_outside(repo, frozenset(job.paths))
    if after != job.before:
        sha = _head_sha(repo) if refused is None else None
        return TreeDisturbed(job.before, after, job.before.paths_differing(after), sha)
    if refused is not None:
        return CommitRefused(refused)
    return _verified(repo, job, expected)


def _is_outer_loop(path: str, named: tuple[str, ...]) -> bool:
    if (path + "/").startswith(OUTER_LOOP_PREFIXES):
        return True
    return any(path == one or path.startswith(one + "/") for one in named)


def _specs(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(_LITERAL_PATHSPEC + path for path in paths)


def _stage(repo: Path, paths: tuple[str, ...]) -> None:
    """Stage what exists in the work tree or the index; a deletion or move already staged
    (`git rm`, `git mv`) names a path in neither, which `git add` refuses and needs nothing."""
    indexed = frozenset(_lines(_git(repo, "ls-files", "--cached", "-z", "--", *_specs(paths))))
    present = [p for p in paths if p in indexed or os.path.lexists(repo / p)]
    if present:
        _git(repo, "add", "--all", "--", *_specs(present))


def _commit_with_retry(repo: Path, job: _Job) -> str | None:
    """None on success, else git's own words. Hooks that rewrote files get one re-stage."""
    attempt = _try_commit(repo, job)
    if attempt is not None and _lines(
        _git(repo, "diff", "--name-only", "-z", "--", *_specs(job.paths))
    ):
        _stage(repo, job.paths)
        attempt = _try_commit(repo, job)
    return attempt


def _try_commit(repo: Path, job: _Job) -> str | None:
    done = _run(repo, "commit", "-m", job.message, "--", *_specs(job.paths), timeout=job.timeout)
    if done.returncode == 0:
        return None
    return _tail(done.stdout + done.stderr)


def _verified(repo: Path, job: _Job, expected: frozenset[str]) -> Union[Committed, TreeDisturbed]:  # noqa: UP007 -- runtime value, 3.9 floor
    """The commit just made, if its file set is exactly what was staged."""
    sha = _head_sha(repo)
    listing = _git(
        repo,
        "diff-tree",
        "--root",
        "-r",
        "--no-renames",
        "--no-commit-id",
        "--name-only",
        "-z",
        sha,
    )
    files = frozenset(_lines(listing))
    if files != expected:
        return TreeDisturbed(job.before, job.before, tuple(sorted(files ^ expected)), sha)
    return Committed(sha, tuple(sorted(files)), job.withheld)


def _head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "--verify", "HEAD").strip()


def _index_locked(repo: Path) -> bool:
    done = run_git(repo, "rev-parse", "--git-path", "index.lock")
    return done.returncode == 0 and (repo / done.stdout.strip()).exists()


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


def _run(
    repo: Path, *args: str, stdin: str | None = None, timeout: float = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str]:
    return run_git(repo, *args, stdin=stdin, timeout=timeout)


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
    """Run `argv` under a timeout with colour off; a run that cannot finish says why.

    The command leads its own process group and a timeout kills the whole group: a
    `uv run pytest` or a shell wrapper must not leave workers editing the tree after the
    driver has reported the run as over or been interrupted.
    """
    try:
        proc = subprocess.Popen(
            argv, cwd=str(cwd), env=_no_colour_env(), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            start_new_session=True,
        )  # fmt: skip
    except OSError as exc:
        return CommandRun(argv, str(cwd), "", None, f"could not start: {exc}")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        out, err = _kill_group(proc)
        return CommandRun(argv, str(cwd), out + err, None, f"timed out after {timeout:g}s")
    except BaseException:  # an interrupt must not leave the runner editing the tree
        _kill_group(proc)
        raise
    return CommandRun(argv, str(cwd), out + err, proc.returncode)


def _kill_group(proc: subprocess.Popen[str]) -> tuple[str, str]:
    """Kill the command's whole process group; what it had printed comes back."""
    with contextlib.suppress(ProcessLookupError):  # the group may already be gone
        os.killpg(proc.pid, signal.SIGKILL)
    try:
        return proc.communicate(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:  # a descendant left the group and holds the pipes
        return "", ""


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
