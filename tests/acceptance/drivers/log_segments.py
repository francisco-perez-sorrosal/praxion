"""Driver for the observation log's segments: the active log and its archives.

A scenario finds the segments the way any outside observer can: every file
in the state directory whose name begins with the log's name, ordered by last
modification, oldest first (a rotation renames, so each archive keeps the time
of its last append and the active log is always the newest). It never builds
an archive name by hand; the one archive name it uses is the single archive the
earlier scheme wrote, which the specification names. It never imports the log's
owner package and never spells the log's file name: the names come from the
harness driver, so the owner's single-reader gates keep holding.

Rotation is driven the way it happens in a session: the active log is filled
with padding rows up to the writer's size cap, then a hook appends a row.
Padding rows are plain JSON objects with `event_type: "padding"`, a generation
number and a sequence number, so a scenario can tell which rotation moved which
rows where without knowing how the writer does it.

Assumed boundary, unbound until a binding step names it: the retention policy
(how many archives it keeps, the span of history it targets, and where the
owner keeps the archive at a given position). Each unbound function raises
with the assumption in words.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.acceptance.drivers.observation_harness import ARCHIVE_NAME, LOG_NAME, STATE_DIR, Session

LEGACY_ARCHIVE_NAME = ARCHIVE_NAME
# The writer's size cap at the base commit (10 MiB). A binding step restates it
# if the retention policy moves the cap.
SIZE_CAP_BYTES = 10 * 1024 * 1024

_PAD = "x" * 900


# -- The retention policy: an assumed boundary ------------------------------


def retention_archive_count() -> int:
    """How many archives the retention policy keeps (more than one, per the spec)."""
    raise NotImplementedError(
        "unbound: the retention policy's archive count, read from the one named place "
        "where the policy is stated, has not been bound to this driver yet"
    )


def retention_history_target() -> timedelta:
    """The span of history the retention policy is meant to cover."""
    raise NotImplementedError(
        "unbound: the retention policy's history target, read from the one named place "
        "where the policy is stated, has not been bound to this driver yet"
    )


def archive_position_path(state_dir: Path, position: int) -> Path:
    """Where the owner keeps the archive at `position` (1 is the newest)."""
    raise NotImplementedError(
        "unbound: where the log's owner keeps the archive at a given position of the "
        "archive sequence has not been bound to this driver yet"
    )


# -- The size cap: existing surface --------------------------------------------


def require_archive_positions(count: int) -> None:
    """Skip a scenario that needs `count` archive positions when the policy keeps fewer."""
    kept = retention_archive_count()
    if kept < count:
        import pytest

        pytest.skip(f"the retention policy keeps {kept} archives; this scenario needs {count}")


def size_cap() -> int:
    """The active log's size cap."""
    return SIZE_CAP_BYTES


# -- The owner's listing ---------------------------------------------------------


def state_dir_of(checkout: Path) -> Path:
    return checkout / STATE_DIR


def active_log(state_dir: Path) -> Path:
    return state_dir / LOG_NAME


def listed_segments(state_dir: Path) -> tuple[Path, ...]:
    """Every segment, archives included, oldest first; existing files only."""
    if not state_dir.is_dir():
        return ()
    found = [p for p in state_dir.iterdir() if p.is_file() and p.name.startswith(LOG_NAME)]
    return tuple(sorted(found, key=lambda p: (p.stat().st_mtime_ns, p.name == LOG_NAME)))


def listed_archives(state_dir: Path) -> tuple[Path, ...]:
    """The archives in the owner's listing, oldest first (the active log left out)."""
    return tuple(p for p in listed_segments(state_dir) if p.name != LOG_NAME)


def files_beside_log(state_dir: Path) -> tuple[Path, ...]:
    """Every file in the state directory whose name starts with the log's stem."""
    return tuple(
        sorted(p for p in state_dir.iterdir() if p.name.startswith(LOG_NAME.split(".")[0]))
    )


# -- Reading segments ------------------------------------------------------------


def rows_of(segment: Path) -> list[dict]:
    """Every row of one segment; a line that is not a JSON object fails loudly."""
    rows = []
    for number, line in enumerate(segment.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{segment}:{number} is not whole JSON: {line[:120]!r}") from exc
        assert isinstance(row, dict), f"{segment}:{number} is not a JSON object"
        rows.append(row)
    return rows


def history_rows(state_dir: Path) -> list[dict]:
    """Every row of every listed segment, in listing order."""
    return [row for segment in listed_segments(state_dir) for row in rows_of(segment)]


def generations_in(segment: Path) -> set[int]:
    return {row["generation"] for row in rows_of(segment) if row.get("event_type") == "padding"}


def archive_generations(state_dir: Path) -> list[set[int]]:
    """Per listed archive, oldest first, the padding generations it holds."""
    return [generations_in(archive) for archive in listed_archives(state_dir)]


def session_ids_in(state_dir: Path, event_type: str = "session_start") -> list[str]:
    """Session ids of every `event_type` row across the listed segments, with repeats."""
    return [
        r.get("session_id") for r in history_rows(state_dir) if r.get("event_type") == event_type
    ]


@dataclass(frozen=True)
class FileIdentity:
    """Which file a path names and whether its bytes were rewritten."""

    inode: int
    mtime_ns: int
    size: int
    sha256: str


def identity(path: Path) -> FileIdentity:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return FileIdentity(stat.st_ino, stat.st_mtime_ns, stat.st_size, digest)


def contents(state_dir: Path) -> dict[str, bytes]:
    """Name -> bytes of every file beside the log."""
    return {p.name: p.read_bytes() for p in files_beside_log(state_dir)}


# -- Writing rows and rotating ---------------------------------------------------


def now_iso(offset: timedelta = timedelta(0)) -> str:
    return (datetime.now(UTC) + offset).isoformat()


def append_lines(state_dir: Path, lines: list[str], *, segment: Path | None = None) -> None:
    """Append literal lines to the active log (or to `segment`), as an earlier writer left them."""
    state_dir.mkdir(parents=True, exist_ok=True)
    target = segment or active_log(state_dir)
    with target.open("a", encoding="utf-8") as handle:
        handle.write("".join(f"{line}\n" for line in lines))


def append_rows(state_dir: Path, rows: list[dict], *, segment: Path | None = None) -> None:
    append_lines(state_dir, [json.dumps(row) for row in rows], segment=segment)


def padding_lines(generation: int, count: int, *, at: str, project: str) -> list[str]:
    return [
        json.dumps(
            {
                "timestamp": at,
                "session_id": f"padding-{generation}",
                "project": project,
                "event_type": "padding",
                "generation": generation,
                "seq": seq,
                "pad": _PAD,
            }
        )
        for seq in range(count)
    ]


def fill_to_cap(
    state_dir: Path,
    generation: int,
    *,
    at: str | None = None,
    project: str = "padding",
    extra_bytes: int = 0,
) -> int:
    """Append padding rows until the active log has reached the size cap (plus `extra_bytes`).

    Returns how many padding rows were appended.
    """
    log = active_log(state_dir)
    size = log.stat().st_size if log.exists() else 0
    one = len(padding_lines(generation, 1, at=at or now_iso(), project=project)[0]) + 1
    missing = size_cap() + extra_bytes - size
    count = max(1, -(-missing // one))
    append_lines(state_dir, padding_lines(generation, count, at=at or now_iso(), project=project))
    return count


def rotate(session: Session, state_dir: Path, generation: int, *, at: str | None = None) -> None:
    """Fill the active log to the cap, then let a session start append to it."""
    fill_to_cap(state_dir, generation, at=at)
    session.session_start()


def rotate_times(
    session: Session,
    state_dir: Path,
    times: int,
    *,
    at: str | None = None,
    oldest_at: str | None = None,
) -> None:
    """Rotate `times` times; the first generation's padding may carry its own time."""
    for generation in range(1, times + 1):
        stamp = oldest_at if generation == 1 and oldest_at is not None else at
        rotate(session, state_dir, generation, at=stamp)


def make_unreadable(path: Path) -> None:
    path.chmod(0o000)


def make_readable(path: Path) -> None:
    path.chmod(0o644)


def running_as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0
