"""Stdlib-only reader for the observation log.

This module never imports ``fcntl`` -- readers run on hosts (a script driven
from CI, a sentinel batch run) where the writer's exclusive-lock guarantee
does not apply and does not need to.

Every code reader of the log goes through these functions; a module that
names the log file directly instead is caught by
`hooks/test_observation_log_private_reader.py`. Segment discovery lives in
`segment_listing()` alone, so the retention policy extends one function.

Hot-path constraint: the writer imports this module, so everything here stays
on modules the writer already loads (no ``dataclasses``, runtime ``typing``,
``subprocess``, ...); values are namedtuples.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

from . import retention
from .modes import Mode

LOG_FILENAME = "observations.jsonl"

# `(path, rows, malformed_lines, error)`. `error` is `None` or a named reason
# ("missing", "unreadable: ..."), in which case `rows` is empty.
# `malformed_lines` carries 1-based line numbers -- both P03's "line N:
# unparseable" report and the cost collector's malformed-line count derive
# from this one field.
SegmentRead = namedtuple("SegmentRead", ("path", "rows", "malformed_lines", "error"))

# `(path, entries, malformed_lines, error)`: `SegmentRead`'s shape for a copier.
# `entries` is a tuple of `(text, row)`: the stored line without its newline and
# the object it parses to, never upcast, so a copy is byte-faithful.
RawSegmentRead = namedtuple("RawSegmentRead", ("path", "entries", "malformed_lines", "error"))

# `(segments, missing, error)`. `segments` holds the paths that exist: archives by
# descending position (oldest first), then the active log. `missing` holds the
# archive paths absent between position 1 and the highest position present --
# a gap is history lost, never the end of it. The two never overlap. `error` is
# None, or "unreadable: <state dir>: <why>" when the directory could not be
# scanned for archives: the listing is then incomplete, which is different from
# a directory that holds none, and a caller that copies or counts must say so.
SegmentListing = namedtuple("SegmentListing", ("segments", "missing", "error"), defaults=(None,))

# `row_time` of a row with no readable time: later than any real instant, so a
# time-ordered sort puts it after the rest. Compare it, never subtract from it.
UNTIMED = datetime.max.replace(tzinfo=timezone.utc)

_IDENTITY_DIGEST_BYTES = 16  # blake2b-128: collisions are not a concern at log scale


def log_path(ai_state_dir: Path) -> Path:
    """The active log path for ``ai_state_dir``."""
    return ai_state_dir / LOG_FILENAME


def segment_listing(ai_state_dir: Path, *, archives: bool) -> SegmentListing:
    """The log's segments for ``ai_state_dir``, oldest first, and any gaps.

    With ``archives`` False this is the active log alone and no directory is
    listed, so the hot path and the active-only readers cost what they always
    did. With it True every numbered archive is found by name -- one directory
    scan -- including a position above the retention policy's count.

    A directory that cannot be entered or scanned is never reported as holding
    no log: the active path stays listed (its read then names the reason) and a
    failed scan sets ``error``. Only a path that is not there, or is no
    directory, holds nothing.
    """
    active = log_path(ai_state_dir)
    newest = (active,) if _may_exist(active) else ()
    if not archives:
        return SegmentListing(segments=newest, missing=())
    present, error = _archives_by_position(ai_state_dir)
    if not present:
        return SegmentListing(segments=newest, missing=(), error=error)
    positions = range(max(present), 0, -1)
    return SegmentListing(
        segments=tuple(present[p] for p in positions if p in present) + newest,
        missing=tuple(retention.archive_path(active, p) for p in positions if p not in present),
        error=error,
    )


def _may_exist(path: Path) -> bool:
    """False only when ``path`` is certainly not there.

    Stats the path itself: ``Path.exists()`` reads a permission error as "not
    there" from Python 3.14 on, which would turn an unreadable state directory
    into one with no log.
    """
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def _archives_by_position(ai_state_dir: Path) -> tuple[dict[int, Path], str | None]:
    """`(every numbered archive in ai_state_dir by position, None)`.

    A directory that is not there, or is no directory, has none; any other
    failure to scan returns what was found (nothing) with the reason.
    """
    found: dict[int, Path] = {}
    try:
        with os.scandir(ai_state_dir) as entries:
            for entry in entries:
                path = ai_state_dir / entry.name
                position = retention.archive_position(path, LOG_FILENAME)
                if position is not None:
                    found[position] = path
    except (FileNotFoundError, NotADirectoryError):
        return {}, None
    except OSError as exc:
        return {}, f"unreadable: {ai_state_dir}: {exc}"
    return found, None


def segments(ai_state_dir: Path, *, archives: bool) -> tuple[Path, ...]:
    """Existing log segments for ``ai_state_dir``, oldest first."""
    return segment_listing(ai_state_dir, archives=archives).segments


def read_segment(path: Path) -> SegmentRead:
    """Stream one segment file, upcasting each row. Never raises.

    A missing or unreadable file yields an empty ``SegmentRead`` naming the
    reason. A line that fails to parse as a JSON object is counted into
    ``malformed_lines`` by its 1-based line number and excluded from
    ``rows`` -- never silently dropped, never fatal to the rest of the read.
    """
    entries, malformed, error = _scan_segment(path)
    rows = tuple(upcast(row) for _, row in entries)
    return SegmentRead(path=path, rows=rows, malformed_lines=malformed, error=error)


def read_raw_segment(path: Path) -> RawSegmentRead:
    """Stream one segment file as stored text plus parsed row, never upcast.

    For copying and identity: ``read_segment`` shows the vocabulary readers
    share, this shows what the file holds. Same tagged errors, same line
    numbering, never raises.
    """
    entries, malformed, error = _scan_segment(path)
    return RawSegmentRead(path=path, entries=entries, malformed_lines=malformed, error=error)


def _scan_segment(path: Path) -> tuple[tuple, tuple[int, ...], str | None]:
    """`(entries, malformed_lines, error)` for one segment, never raising.

    A line is what text-mode file iteration yields, never `str.splitlines()`,
    which also breaks at U+0085, U+2028, U+2029 and other separators a
    JSON-valid row may carry raw. Memory is bounded by the longest line.
    """
    entries: list[tuple[str, dict]] = []
    malformed: list[int] = []
    try:
        # errors="replace": a torn multi-byte sequence must cost one malformed
        # line, never the whole segment (strict decoding raises ValueError).
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row = _parse_row(line)
                if row is None:
                    malformed.append(line_no)
                else:
                    entries.append((line.removesuffix("\n"), row))
    except FileNotFoundError:
        return (), (), "missing"
    except OSError as exc:
        return (), (), f"unreadable: {exc}"
    return tuple(entries), tuple(malformed), None


def _parse_row(line: str) -> dict | None:
    """The JSON object ``line`` holds, or ``None`` when it holds none."""
    try:
        row = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    return row if isinstance(row, dict) else None


def row_identity(row: dict) -> str:
    """The identity of ``row`` as stored: two rows are one event exactly when equal.

    A hash of the row's canonical JSON -- key order never matters, any field
    does. Compute it over the row from `read_raw_segment`, never an upcast
    one, so a copied row and its original agree.
    """
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # surrogatepass: a row may hold an escaped lone surrogate ("\ud83d" is valid
    # JSON, and the form json.dumps writes); strict encoding would raise on it.
    digest = hashlib.blake2b(
        canonical.encode("utf-8", "surrogatepass"), digest_size=_IDENTITY_DIGEST_BYTES
    )
    return digest.hexdigest()


def row_time(row: dict) -> datetime:
    """When ``row`` was recorded, as an aware ``datetime``; the one timestamp parser.

    A naive stamp is read as UTC. A row with no readable time answers
    ``UNTIMED``, so ``sorted(rows, key=row_time)`` orders the dated rows and
    leaves the rest after them in their original order (the sort is stable).
    """
    stamp = row.get("timestamp")
    if not isinstance(stamp, str):
        return UNTIMED
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"  # `fromisoformat` takes "Z" only from Python 3.11
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return UNTIMED
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def read_rows(ai_state_dir: Path, *, archives: bool = False) -> list[dict]:
    """Every row across the requested segments, oldest to newest.

    Fail-open convenience: a missing or unreadable segment contributes no
    rows rather than raising.
    """
    rows: list[dict] = []
    for path in segments(ai_state_dir, archives=archives):
        rows.extend(read_segment(path).rows)
    return rows


def tail_rows(path: Path, max_bytes: int) -> list[dict]:
    """Parsed rows from the last complete JSONL lines of ``path``.

    Reads at most ``max_bytes`` from the end of the file. When the window
    starts mid-file the first line may be a truncated fragment, so it is
    discarded. Any OSError (missing file, unreadable path) degrades to an
    empty list.
    """
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            window = min(size, max_bytes)
            handle.seek(size - window)
            chunk = handle.read(window)
    except OSError:
        return []
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if window < size and lines:
        lines = lines[1:]  # drop the fragment the window cut in half

    rows: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(row, dict):
            rows.append(upcast(row))
    return rows


# A stop whose usage came from either transcript belongs to a real agent,
# whatever its correlation verdict says.
_TRANSCRIPT_USAGE_SOURCES = frozenset({"subagent-transcript", "parent-transcript"})

# Usage fields a stop row fills from a transcript.
_TOKEN_FIELDS = ("tokens_in", "tokens_out", "cache_read", "cache_create")

# The keys a `helper_stop` row carries; an upcast legacy row is cut to these.
_HELPER_STOP_KEYS = ("timestamp", "session_id", "agent_id", "project", "event_type", "log_mode")


def upcast(row: dict) -> dict:
    """Normalize a legacy row shape to its current equivalent.

    The single place a legacy shape is ever normalized, so every reader sees
    one vocabulary. Only legacy rows -- those without a `log_mode` key -- are
    candidates: every row the owner writer appends carries that key and was
    classified at write time, so it passes through unchanged, including an
    `unobserved-agent` stop with no usage whose own transcript exists.

    Today there is one rule: a legacy `agent_stop` row self-reporting
    `start_correlation: unobserved-agent` and carrying no usage at all was a
    harness helper call, not an agent -- it is presented as the slim
    `helper_stop` row the stop path now writes directly. Any other row
    passes through unchanged.

    "No usage at all" means no transcript `usage_source` *and* no token
    field populated. A legacy row with token counts but no source label
    stays `agent_stop`: such rows are helpers carrying the parent session's
    cumulative usage, but their content cannot tell them from a real agent
    whose start went unobserved, so the rule stays conservative.
    """
    if (
        "log_mode" not in row
        and row.get("event_type") == "agent_stop"
        and row.get("start_correlation") == "unobserved-agent"
        and row.get("usage_source") not in _TRANSCRIPT_USAGE_SOURCES
        and all(row.get(field) is None for field in _TOKEN_FIELDS)
    ):
        helper = {key: row[key] for key in _HELPER_STOP_KEYS if key in row}
        helper["event_type"] = "helper_stop"
        return helper
    return row


def recorded_mode(row: dict) -> Mode:
    """The ``Mode`` a row was written under.

    Every row `writer.record`/`record_tool_call` appends now carries
    ``log_mode``. A missing key -- every row predating this package, plus
    the prose-written `recovery` rows that bypass the writer entirely --
    reads as ``FULL``, matching the un-differentiated behavior those rows
    were always recorded under.
    """
    try:
        return Mode(row.get("log_mode", Mode.FULL.value))
    except ValueError:
        return Mode.FULL
