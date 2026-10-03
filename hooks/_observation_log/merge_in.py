"""Merge-in: copy a worktree's log rows into the main checkout's log.

A worktree's log dies with ``git worktree remove``; this is the path that keeps
what it recorded. It is a *copy* path, not a recording path: every row keeps the
bytes it was stored with (so its ``project`` and ``log_mode`` are untouched, and
the row's identity is the same on both sides), the mode only decides whether to
copy at all, and the worktree's files are opened read-only and never changed.

Rows already in the main log are skipped by whole-row identity, counting the
main log's archives, so a merge is safe to repeat -- after the main log rotated,
or after the worktree kept recording. The rows that remain go in through
``writer.append_lines``, which takes the writer's lock and applies the size cap
and the retention policy to each one like any other append.
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Mapping
from pathlib import Path

from . import reader, writer
from .modes import Mode, resolve_mode

MERGED = "merged"
NOTHING_TO_MERGE = "nothing-to-merge"
RECORDING_OFF = "recording-off"
DEGRADED = "degraded"

# `outcome` is the sum type callers branch on; `reason` is None exactly when the
# outcome is not `degraded`, which only `_settled` and `_degraded` guarantee --
# no other site builds a report. `unreadable` names every worktree segment that
# could not be read (a segment, or an archive position missing between others).
# `worktree` is the worktree's state directory as passed in.
MergeReport = namedtuple(
    "MergeReport",
    ("worktree", "mode", "outcome", "copied", "skipped", "malformed", "unreadable", "reason"),
)

# What one pass over the worktree's segments found.
_Walk = namedtuple("_Walk", ("queued", "skipped", "malformed", "unreadable", "reasons"))


def merge_worktree_log(
    main_state_dir: Path, worktree_state_dir: Path, *, env: Mapping[str, str]
) -> MergeReport:
    """Copy into the main log every row of the worktree's log that it does not hold.

    ``env`` carries the recording mode (``off`` copies nothing). A worktree with
    no log has nothing to merge. Malformed lines are counted and left behind; an
    unreadable segment, an archive missing between others, or a main log that
    cannot be read or written makes the outcome ``degraded`` while every row that
    can be copied still is. Never raises for a problem in either log.
    """
    mode, _ = resolve_mode(env)
    if mode is Mode.OFF:
        return _settled(worktree_state_dir, mode, RECORDING_OFF)
    held, main_problem = _identities_held(main_state_dir)
    if main_problem is not None:
        return _degraded(worktree_state_dir, mode, (main_problem,))
    listing = reader.segment_listing(worktree_state_dir, archives=True)
    if not listing.segments:
        return _settled(worktree_state_dir, mode, NOTHING_TO_MERGE)
    walk = _walk_worktree(listing, held)
    written, append_error = writer.append_lines(reader.log_path(main_state_dir), walk.queued)
    reasons = walk.reasons + ((append_error,) if append_error else ())
    counts = {"copied": written, "skipped": walk.skipped, "malformed": walk.malformed}
    if reasons:
        return _degraded(worktree_state_dir, mode, reasons, unreadable=walk.unreadable, **counts)
    return _settled(worktree_state_dir, mode, MERGED, **counts)


def _identities_held(main_state_dir: Path) -> tuple[set[str], str | None]:
    """`(identities of every row the main log holds, None)`, or `(empty, why not)`.

    An unreadable main segment may hold the very rows a copy would duplicate, so
    one makes the whole merge degraded rather than risk a duplicate.
    """
    held: set[str] = set()
    listing = reader.segment_listing(main_state_dir, archives=True)
    for path in listing.segments:
        segment = reader.read_raw_segment(path)
        if segment.error is not None:
            return set(), f"the main log cannot be read ({path}: {segment.error})"
        held.update(reader.row_identity(row) for _, row in segment.entries)
    return held, None


def _walk_worktree(listing: reader.SegmentListing, held: set[str]) -> _Walk:
    """Queue the stored text of each row the main log lacks, oldest segment first.

    ``held`` grows as rows are queued, so a row repeated inside the worktree's
    own log is queued once.
    """
    queued: list[str] = []
    skipped = malformed = 0
    unreadable = [str(path) for path in listing.missing]
    reasons = [f"worktree archive is missing ({path})" for path in unreadable]
    for path in listing.segments:
        segment = reader.read_raw_segment(path)
        if segment.error is not None:
            unreadable.append(str(path))
            reasons.append(f"worktree segment cannot be read ({path}: {segment.error})")
            continue
        malformed += len(segment.malformed_lines)
        for text, row in segment.entries:
            identity = reader.row_identity(row)
            if identity in held:
                skipped += 1
                continue
            held.add(identity)
            queued.append(text)
    return _Walk(queued, skipped, malformed, tuple(unreadable), tuple(reasons))


def _settled(
    worktree: Path,
    mode: Mode,
    outcome: str,
    *,
    copied: int = 0,
    skipped: int = 0,
    malformed: int = 0,
) -> MergeReport:
    """A report for a merge that met no problem: never carries a reason."""
    return MergeReport(worktree, mode, outcome, copied, skipped, malformed, (), None)


def _degraded(
    worktree: Path,
    mode: Mode,
    reasons: tuple[str, ...],
    *,
    copied: int = 0,
    skipped: int = 0,
    malformed: int = 0,
    unreadable: tuple[str, ...] = (),
) -> MergeReport:
    """A report for a merge that met a problem: always carries a reason."""
    return MergeReport(
        worktree, mode, DEGRADED, copied, skipped, malformed, unreadable, "; ".join(reasons)
    )
