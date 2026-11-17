"""Whether a `record` call of a request is running: an OS lock held for the call's whole run.

`record` holds `fcntl.flock` on `<task>/gate/<request>/record.lock` from start to end
(`holding_record`), so a second `record` of the same request and the Stop guard's probe
(`record_in_flight`) can see it. Liveness is the lock itself: the kernel releases it when the
holder exits, however it exits, so a crashed call never leaves a record that reads as running.
The file's content, `{"pid", "started"}`, only names the holder in a refusal.

A call removes the file as it lets go, so a refused or finished `record` leaves no file behind,
unless the removal fails or the file at the path is another call's by then (it removes only its
own). The holder unlinks before it closes, and a call that takes the lock keeps it only while
the file at the path is still the one it locked (else it opens the new one): two calls can never
each hold a lock, one on the removed file and one on its successor.

The probe takes the same lock for an instant, so a `record` that starts at that instant retries
for `WAIT_SECONDS` before it refuses. The descriptor is not inherited (PEP 446, the default of
`os.open`): a gate run the call leaves detached must not keep the lock alive after it.

Stdlib-only and 3.9-safe at runtime; POSIX only (`fcntl`).
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOCK_FILE = "record.lock"
WAIT_SECONDS = 1.0  # longer than any probe holds the lock, far shorter than a record runs
RETRY_SECONDS = 0.05
_FILE_MODE = 0o644
_HOLDER_MAX_BYTES = 4096  # far above the few dozen bytes `_write_holder` writes


class RecordRunningError(Exception):
    """Another `record` of the request holds its lock; `holder_pid` is None when unreadable."""

    def __init__(self, request: str, holder_pid: int | None) -> None:
        holder = "an unknown process" if holder_pid is None else f"process {holder_pid}"
        super().__init__(f"a record of {request} is already running in {holder}")
        self.request, self.holder_pid = request, holder_pid


@contextmanager
def holding_record(
    run_dir: Path,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[None]:
    """Hold the request's record lock for the body, or raise `RecordRunningError` when another
    call still holds it after `WAIT_SECONDS`. The request is `run_dir`'s name."""
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = run_dir / LOCK_FILE
    descriptor = _acquire(lock, clock() + WAIT_SECONDS, clock, sleep)
    try:
        _write_holder(descriptor)
        yield
    finally:
        try:
            _remove_own_file(lock, descriptor)  # before the close: who locks it sees it gone
        finally:
            os.close(descriptor)  # closing the only descriptor releases the lock


def _remove_own_file(lock: Path, descriptor: int) -> None:
    """Remove the file at `lock` only while it is the one `descriptor` holds: a file made there
    since is another call's. A removal that fails leaves the file, which the next call reuses; it
    must not turn a record that has done its work into an error."""
    try:
        if _still_at(lock, descriptor):
            lock.unlink()
    except OSError:
        pass


def record_in_flight(run_dir: Path) -> bool:
    """Whether a `record` of the request holds its lock now. Never creates the file; a probe
    that cannot look (no file, an error) reads as no record in flight."""
    try:
        descriptor = os.open(run_dir / LOCK_FILE, os.O_RDONLY)
    except OSError:
        return False
    try:
        return not _try_lock(descriptor)
    except OSError:
        return False
    finally:
        os.close(descriptor)


# --- The lock --------------------------------------------------------------------------------


def _acquire(
    lock: Path, deadline: float, clock: Callable[[], float], sleep: Callable[[float], None]
) -> int:
    """A descriptor of `lock` holding its lock, the file still at the path."""
    while True:
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, _FILE_MODE)
        if _try_lock(descriptor):
            if _still_at(lock, descriptor):
                return descriptor
            os.close(descriptor)  # its holder removed it as it let go: open the one at the path
            continue
        holder = _holder_pid(descriptor)
        os.close(descriptor)
        if clock() >= deadline:
            raise RecordRunningError(lock.parent.name, holder)
        sleep(RETRY_SECONDS)


def _still_at(lock: Path, descriptor: int) -> bool:
    """Whether the locked file is the one at the path, not one its holder removed meanwhile."""
    try:
        at_path = os.stat(lock)
    except FileNotFoundError:
        return False
    held = os.fstat(descriptor)
    return (held.st_dev, held.st_ino) == (at_path.st_dev, at_path.st_ino)


def _try_lock(descriptor: int) -> bool:
    """Take the exclusive lock without waiting: True when taken, False when another holds it.
    The probe's caller releases it by closing the descriptor."""
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _write_holder(descriptor: int) -> None:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    holder = json.dumps({"pid": os.getpid(), "started": started}).encode()
    os.ftruncate(descriptor, 0)
    os.pwrite(descriptor, holder, 0)


def _holder_pid(descriptor: int) -> int | None:
    """The pid the holder wrote; None while it has not written it or when it does not parse."""
    try:
        content = json.loads(os.pread(descriptor, _HOLDER_MAX_BYTES, 0).decode())
    except (OSError, ValueError):
        return None
    pid = content.get("pid") if isinstance(content, dict) else None
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None
