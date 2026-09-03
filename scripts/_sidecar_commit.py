"""Per-mount commit serialization for sidecar placement.

Under sidecar placement every project checkout carries its own state mount, and
a mount is a real `git worktree` with an index of its own at
`<sidecar>/.git/worktrees/<name>/index`. The lock therefore hangs off that same
per-worktree directory rather than off the sidecar's shared `.git`: two
pipelines committing state in two project worktrees write two different index
files and must not wait on each other, while the committers that *do* share one
index -- the finalize-chain commit, the session-Stop commit, and a merge-back
writing the target mount -- serialize.

Three properties are load-bearing, and each is structural rather than
conventional:

**One lock, ever.** Nothing in this module acquires a second lock while holding
a first. `commit_paths` takes exactly one, and convergence -- which may merge
several branches into one mount in a single run -- takes the *target* mount's
lock once around the whole run and never a source's. A lock-ordering cycle is
therefore not representable here, rather than merely unlikely.

**Liveness, not age, separates a held lock from an abandoned one.** A holder's
record is written on acquisition and cleared on release, so a record surviving
without the `flock` means the writer died before its `finally` ran. An
age threshold would have to guess how long a legitimate commit may take, and
would report every slow-but-healthy committer as crashed.

**A contended commit defers; it does not raise.** Every caller here is a git
hook or a session boundary, where an escaping exception is a visible failure and
the work is not lost by waiting: the discipline is idempotent, so the next
trigger commits what this one skipped.

Every `git` invocation names its repository explicitly (`run_git`'s first
argument) and stages by explicit pathspec, so a committer can never sweep up
another committer's partial work.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import os
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO, Union

from _git_runner import git_output, run_git
from _sidecar_git import run_or_raise

LOCK_FILENAME = "praxion-sidecar-commit.lock"

# Long enough that the common contention -- a finalize-chain commit overlapping
# a Stop-hook commit, both sub-second -- resolves by waiting, short enough that
# a hook never feels stalled when the holder is genuinely stuck.
DEFAULT_TIMEOUT_SECONDS = 10.0

# `flock` offers no timed wait, so the bounded wait is a poll. The interval
# trades wake-ups against hand-off latency; at this value a typical hand-off
# costs a few milliseconds and a full 10s wait costs ~500 wake-ups.
POLL_INTERVAL_SECONDS = 0.02

_PORCELAIN_STATUS_WIDTH = 3
_RENAME_ARROW = " -> "


# -- States -------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Idle:
    """No committer holds the mount's lock and none left a record behind."""


@dataclasses.dataclass(frozen=True)
class Committing:
    """A live committer holds the lock; a caller should wait or defer."""

    holder_pid: int
    since: str


@dataclasses.dataclass(frozen=True)
class StaleLock:
    """A record outlived its holder -- the writer died before releasing.

    A distinct variant rather than a flag on `Committing`, because the two call
    for different actions: waiting is right for a live holder and useless for a
    dead one, which an operator should be told about instead.
    """

    holder_pid: int
    since: str


# `Union`, not `X | Y`: a runtime alias in that form needs 3.10, and this
# module ships into consumer git hooks that run on whatever `python3` the
# machine has. Every other union here is an annotation, deferred to a string
# by `from __future__ import annotations`, and so costs nothing at import.
SidecarCommit = Union[Idle, Committing, StaleLock]  # noqa: UP007


@dataclasses.dataclass(frozen=True)
class CommitResult:
    """What a commit attempt that held the lock actually did.

    `committed=False` with `sha=None` is the clean no-op: the pathspec named
    nothing that differed from HEAD, so no empty commit was created.
    """

    committed: bool
    sha: str | None
    staged: list[str]


@dataclasses.dataclass(frozen=True)
class CommitDeferred:
    """The lock was held past the caller's bound, so nothing was attempted.

    Not a failure: the caller's paths are still dirty in the mount and the next
    trigger commits them.
    """


@dataclasses.dataclass(frozen=True)
class LockHandle:
    """What the lock context yields -- enough for a caller to report itself."""

    path: Path
    pid: int
    since: str


class LockTimeout(Exception):  # noqa: N818 -- the name callers catch, fixed by its consumers
    """The mount's lock stayed held for the whole bounded wait."""


class GitCommandError(RuntimeError):
    """A `git` command ran against the mount and exited non-zero.

    Raised rather than swallowed so a refusal with a cause the caller must see
    -- an unconfigured commit identity, a mount mid-merge -- surfaces as itself
    instead of as a silent clean no-op.
    """


# -- Lock path ----------------------------------------------------------------


def lock_path_for(mount: Path) -> Path:
    """Return the lock path for `mount`, inside that mount's own git dir.

    Read from the mount's `.git` pointer file rather than asked of `git`: this
    runs on hook paths where a subprocess per call is the dominant cost, and the
    pointer file is a stable, documented one-line format.
    """
    return _worktree_git_dir(mount) / LOCK_FILENAME


def _worktree_git_dir(mount: Path) -> Path:
    """Resolve the real git directory a `git worktree` checkout points at."""
    pointer = Path(mount) / ".git"
    if pointer.is_dir():
        # Not a linked worktree but a plain repository: its git dir is the
        # directory itself, which keeps the lock per-index there too.
        return pointer
    for line in pointer.read_text(encoding="utf-8").splitlines():
        if line.startswith("gitdir:"):
            recorded = Path(line.removeprefix("gitdir:").strip())
            # git may record the path relative to the checkout holding the
            # pointer file (`worktree add --relative-paths`).
            return recorded if recorded.is_absolute() else (Path(mount) / recorded).resolve()
    raise ValueError(f"{pointer} is not a git worktree pointer file")


# -- Reporting ----------------------------------------------------------------


def read_lock_state(mount: Path) -> SidecarCommit:
    """Classify the mount's lock without ever acquiring or clearing it.

    Reporting only -- `doctor`'s row. Nothing here reclaims a stale lock,
    because nothing needs to: `flock` is released by the kernel when the
    holder's descriptor closes, so the next acquirer simply succeeds and
    overwrites the dead record.

    That release-on-death guarantee is a local-POSIX-filesystem property. On NFS
    or SMB, `flock` may be emulated, downgraded to advisory-only, or simply
    unreliable, and this classification degrades with it -- a live holder can
    read back as `StaleLock`. A sidecar lives under `~/.praxion` by design, so
    the mount and its git dir are local; a deliberately network-hosted sidecar is
    outside what this reports faithfully.
    """
    path = lock_path_for(mount)
    if not path.exists():
        return Idle()
    record = _read_record(path)
    if record is None:
        return Idle()
    holder_pid, since = record
    if _lock_is_held(path):
        return Committing(holder_pid=holder_pid, since=since)
    # The record survives only when a `finally` did not run, so an unheld lock
    # with a record is an abandoned one. That holds even when the recorded pid
    # is alive today: the kernel released the flock at process death, and a
    # reused pid names a different process entirely.
    return StaleLock(holder_pid=holder_pid, since=since)


def _read_record(path: Path) -> tuple[int, str] | None:
    """Parse `pid\\nsince\\n`, or `None` when the file carries no live record."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 2 or not lines[0].strip().isdigit():
        return None
    return int(lines[0].strip()), lines[1].strip()


def _lock_is_held(path: Path) -> bool:
    """Probe without blocking; release immediately if the probe won."""
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


# -- The lock -----------------------------------------------------------------


@contextlib.contextmanager
def mount_lock(
    mount: Path,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[LockHandle]:
    """Hold `mount`'s commit lock for the duration of the context.

    Raises `LockTimeout` when the lock stays held for the whole bounded wait;
    releases -- and clears its record -- in a `finally`, so an exception inside
    the context cannot leave the mount looking permanently locked.

    Mutual exclusion here is `fcntl.flock`, which is reliable on local POSIX
    filesystems and *not* guaranteed on NFS or SMB, where it may be emulated or
    advisory-only. A sidecar is local by design (`~/.praxion`); a network-hosted
    one would weaken this to a convention rather than an enforced lock.
    """
    path = lock_path_for(mount)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        _acquire_within(handle, path, timeout_seconds, clock)
        record = _write_record(handle, path)
        try:
            yield record
        finally:
            _clear_record(handle)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _acquire_within(
    handle: TextIO, path: Path, timeout_seconds: float, clock: Callable[[], float]
) -> None:
    """Poll for the lock until `timeout_seconds` of `clock` have elapsed."""
    deadline = clock() + timeout_seconds
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            pass
        if clock() >= deadline:
            raise LockTimeout(f"{path} stayed held for {timeout_seconds}s")
        time.sleep(POLL_INTERVAL_SECONDS)


def _write_record(handle: TextIO, path: Path) -> LockHandle:
    """Record who holds the lock and since when, replacing any dead record."""
    pid = os.getpid()
    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    handle.truncate(0)
    handle.write(f"{pid}\n{since}\n")
    handle.flush()
    return LockHandle(path=path, pid=pid, since=since)


def _clear_record(handle: TextIO) -> None:
    """Erase the record so a completed commit never reads back as abandoned."""
    handle.truncate(0)
    handle.flush()


# -- Committing ---------------------------------------------------------------


def commit_paths(
    mount: Path,
    paths: Sequence[str],
    message: str,
    *,
    lock: AbstractContextManager[object] | None = None,
) -> CommitResult | CommitDeferred:
    """Stage exactly `paths` in `mount` and commit them under the mount's lock.

    `lock` lets a caller supply an already-configured context manager -- a
    shorter bound, or a lock it already holds for a wider operation. The default
    takes this mount's lock, and it is the only lock this call ever takes.

    Refuses an empty pathspec: staging nothing would either commit nothing or,
    with a whole-tree fallback, sweep up another committer's work -- and a
    caller that meant "commit the residue" already has `residue_paths`.
    """
    if not paths:
        raise ValueError("commit_paths needs at least one path; refusing an empty paths list")
    guard = mount_lock(mount) if lock is None else lock
    try:
        with guard:
            return _stage_and_commit(mount, list(paths), message)
    except LockTimeout:
        return CommitDeferred()


def _stage_and_commit(mount: Path, paths: list[str], message: str) -> CommitResult:
    """Under the lock: stage the pathspec, then commit only if it changed HEAD."""
    run_or_raise(mount, GitCommandError, "add", "--", *paths)
    if _index_matches_head(mount):
        return CommitResult(committed=False, sha=None, staged=[])
    run_or_raise(mount, GitCommandError, "commit", "-m", message)
    return CommitResult(committed=True, sha=git_output(mount, "rev-parse", "HEAD"), staged=paths)


def _index_matches_head(mount: Path) -> bool:
    """True when nothing is staged -- the clean no-op, not a failure."""
    return run_git(mount, "diff", "--cached", "--quiet").returncode == 0


def residue_paths(mount: Path) -> list[str]:
    """List every dirty path in `mount`, ready to be handed to `commit_paths`.

    The Stop-hook commit derives its pathspec from here rather than staging the
    whole tree, which is what keeps two committers from staging each other's
    half-written work.

    Raises `GitCommandError` when `git status` itself fails -- a corrupted `.git`
    pointer, a mount mid-repair, a held index lock. Returning `[]` there would
    make a broken mount indistinguishable from a clean one, and the caller would
    log a successful no-op over a mount it never actually read.
    """
    # Deliberately `run_git` rather than `git_output`: the latter strips the
    # whole output, and porcelain's status column is leading whitespace on an
    # unstaged line -- stripping it shifts every path left by one character and
    # silently eats the leading dot of a `.ai-state/` path.
    status = run_or_raise(mount, GitCommandError, "status", "--porcelain")
    return [_porcelain_path(line) for line in status.stdout.splitlines() if line.strip()]


def _porcelain_path(line: str) -> str:
    """Strip the two-column status prefix, and take a rename's new path."""
    path = line[_PORCELAIN_STATUS_WIDTH:]
    if _RENAME_ARROW in path:
        path = path.split(_RENAME_ARROW, 1)[1]
    return path.strip().strip('"')
