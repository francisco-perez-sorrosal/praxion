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

Declared limit: the main log's identity index is read outside the writer's
lock, so a rotation during that read, or a second merge-in of the same
worktree running at once, can append a row the main log already held -- one
extra copy, never a lost row (tech-debt ledger, merge-in identity race).
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Mapping, Sequence
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
_Walk = namedtuple(
    "_Walk", ("queued", "identities", "skipped", "malformed", "unreadable", "reasons")
)


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
    return merge_worktree_logs(main_state_dir, [worktree_state_dir], env=env)[0]


def merge_worktree_logs(
    main_state_dir: Path, worktree_state_dirs: Sequence[Path], *, env: Mapping[str, str]
) -> tuple[MergeReport, ...]:
    """One report per worktree, in order, each as ``merge_worktree_log`` reports it.

    The main log's row identities are read once, on the first worktree that has
    rows to offer, and shared by the rest: a worktree with no log never costs a
    read of the main log, and a run over many worktrees reads it once, not once
    per worktree. Each worktree sees the rows the one before it copied.
    """
    mode, _ = resolve_mode(env)
    main = _MainIdentities(main_state_dir)
    return tuple(_merge_guarded(main, state_dir, mode) for state_dir in worktree_state_dirs)


def holds_log(worktree_state_dir: Path) -> bool:
    """Whether a merge of this worktree has anything to look at.

    False only when the directory listed cleanly and holds no segment. One that
    cannot be listed counts as holding a log, so it becomes a ``degraded`` merge
    with a reason, never a silent skip.
    """
    return _has_log(reader.segment_listing(worktree_state_dir, archives=True))


def _has_log(listing: reader.SegmentListing) -> bool:
    return bool(listing.segments) or listing.error is not None


class _MainIdentities:
    """The identity of every row the main log holds, read on first use.

    Shared by the worktrees of one run, so the set is what the next worktree is
    checked against. It holds only rows that are in the main log: after a failed
    append the caller takes back the rows that never landed, or a later worktree
    holding the same row would skip it and the row would be in no log.
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self._read: tuple[set[str], str | None] | None = None

    def held(self) -> tuple[set[str], str | None]:
        """`(identities, None)`, or `(empty, why the main log cannot be trusted)`.

        A failure to build the index is remembered, so every later worktree is
        degraded with the same reason instead of repeating a read that failed.
        """
        if self._read is None:
            try:
                self._read = _identities_held(self.state_dir)
            except Exception as exc:  # noqa: BLE001 -- a merge reports a fault, never raises
                self._read = (set(), _internal_error(exc))
        return self._read


def _internal_error(exc: Exception) -> str:
    return f"internal error: {type(exc).__name__}: {exc}"


def _merge_guarded(main: _MainIdentities, worktree_state_dir: Path, mode: Mode) -> MergeReport:
    """``_merge_one``, with any exception turned into this worktree's own ``degraded`` report."""
    try:
        return _merge_one(main, worktree_state_dir, mode)
    except Exception as exc:  # noqa: BLE001 -- one worktree's fault must not stop the run
        return _degraded(worktree_state_dir, mode, (_internal_error(exc),))


def _merge_one(main: _MainIdentities, worktree_state_dir: Path, mode: Mode) -> MergeReport:
    if mode is Mode.OFF:
        return _settled(worktree_state_dir, mode, RECORDING_OFF)
    listing = reader.segment_listing(worktree_state_dir, archives=True)
    if not _has_log(listing):
        return _settled(worktree_state_dir, mode, NOTHING_TO_MERGE)
    held, main_problem = main.held()
    if main_problem is not None:
        return _degraded(worktree_state_dir, mode, (main_problem,))
    walk = _walk_worktree(listing, held)
    written, append_error = writer.append_lines(reader.log_path(main.state_dir), walk.queued)
    held.difference_update(walk.identities[written:])
    reasons = walk.reasons + ((append_error,) if append_error else ())
    counts = {"copied": written, "skipped": walk.skipped, "malformed": walk.malformed}
    if reasons:
        return _degraded(worktree_state_dir, mode, reasons, unreadable=walk.unreadable, **counts)
    return _settled(worktree_state_dir, mode, MERGED, **counts)


def _identities_held(main_state_dir: Path) -> tuple[set[str], str | None]:
    """`(identities of every row the main log holds, None)`, or `(empty, why not)`.

    An unreadable main segment, or a main directory that cannot be listed for
    archives, may hold the very rows a copy would duplicate, so either makes the
    whole merge degraded rather than risk a duplicate.
    """
    held: set[str] = set()
    listing = reader.segment_listing(main_state_dir, archives=True)
    if listing.error is not None:
        return set(), f"the main log cannot be read ({listing.error})"
    for path in listing.segments:
        segment = reader.read_raw_segment(path)
        if segment.error is not None:
            return set(), f"the main log cannot be read ({path}: {segment.error})"
        held.update(reader.row_identity(row) for _, row in segment.entries)
    return held, None


def _walk_worktree(listing: reader.SegmentListing, held: set[str]) -> _Walk:
    """Queue the stored text of each row the main log lacks, oldest segment first.

    ``held`` grows as rows are queued, so a row repeated inside the worktree's
    own log is queued once; ``identities`` is the queued rows' identities in
    queue order, so the caller can take back the ones that never landed.
    """
    queued: list[str] = []
    identities: list[str] = []
    skipped = malformed = 0
    unreadable = [str(path) for path in listing.missing]
    reasons = [f"worktree archive is missing ({path})" for path in unreadable]
    if listing.error is not None:
        reasons.append(f"worktree log cannot be listed ({listing.error})")
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
            identities.append(identity)
    return _Walk(queued, identities, skipped, malformed, tuple(unreadable), tuple(reasons))


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
