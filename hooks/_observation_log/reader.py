"""Stdlib-only reader for the observation log.

This module never imports ``fcntl`` -- readers run on hosts (a script driven
from CI, a sentinel batch run) where the writer's exclusive-lock guarantee
does not apply and does not need to.

Every code reader of the log goes through these functions; a module that
names the log file directly instead is caught by
`hooks/test_observation_log_private_reader.py`. Segment discovery lives in
`segments()` alone, so a future retention policy extends one function.
"""

from __future__ import annotations

import json
import os
from collections import namedtuple
from pathlib import Path

from .modes import Mode

LOG_FILENAME = "observations.jsonl"

# `(path, rows, malformed_lines, error)`. `error` is `None` or a named reason
# ("missing", "unreadable: ..."), in which case `rows` is empty.
# `malformed_lines` carries 1-based line numbers -- both P03's "line N:
# unparseable" report and the cost collector's malformed-line count derive
# from this one field.
SegmentRead = namedtuple("SegmentRead", ("path", "rows", "malformed_lines", "error"))


def log_path(ai_state_dir: Path) -> Path:
    """The active log path for ``ai_state_dir``."""
    return ai_state_dir / LOG_FILENAME


def segments(ai_state_dir: Path, *, archives: bool) -> tuple[Path, ...]:
    """Existing log segments for ``ai_state_dir``, oldest first.

    The ``.1`` archive (when ``archives`` is True and the file exists) comes
    before the active file. This is the one place a future rotation policy
    extends to N archives.
    """
    active = log_path(ai_state_dir)
    paths: list[Path] = []
    if archives:
        archive = Path(f"{active}.1")
        if archive.exists():
            paths.append(archive)
    if active.exists():
        paths.append(active)
    return tuple(paths)


def read_segment(path: Path) -> SegmentRead:
    """Stream one segment file, upcasting each row. Never raises.

    A missing or unreadable file yields an empty ``SegmentRead`` naming the
    reason. A line that fails to parse as a JSON object is counted into
    ``malformed_lines`` by its 1-based line number and excluded from
    ``rows`` -- never silently dropped, never fatal to the rest of the read.
    """
    try:
        # errors="replace": a torn multi-byte sequence must cost one malformed
        # line, never the whole segment (strict decoding raises ValueError).
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return SegmentRead(path=path, rows=(), malformed_lines=(), error="missing")
    except OSError as exc:
        return SegmentRead(path=path, rows=(), malformed_lines=(), error=f"unreadable: {exc}")

    rows: list[dict] = []
    malformed: list[int] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            malformed.append(line_no)
            continue
        if isinstance(row, dict):
            rows.append(upcast(row))
        else:
            malformed.append(line_no)
    return SegmentRead(path=path, rows=tuple(rows), malformed_lines=tuple(malformed), error=None)


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
    one vocabulary. Today there is one rule: an `agent_stop` row written
    before `helper_stop` existed, self-reporting `start_correlation:
    unobserved-agent` and carrying no usage at all, was a harness helper
    call, not an agent -- it is presented as the slim `helper_stop` row the
    stop path now writes directly. Any other row passes through unchanged.

    "No usage at all" means no transcript `usage_source` *and* no token
    field populated: rows written before `usage_source` existed carry real
    token counts with no source label, and those are agents.
    """
    if (
        row.get("event_type") == "agent_stop"
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
