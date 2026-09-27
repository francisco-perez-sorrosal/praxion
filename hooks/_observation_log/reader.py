"""Stdlib-only reader for the observation log.

This module never imports ``fcntl`` -- readers run on hosts (a script driven
from CI, a sentinel batch run) where the writer's exclusive-lock guarantee
does not apply and does not need to.

Nothing here is wired to a consumer yet -- migrating every reader onto these
functions is a later step's job. This step establishes the functions
themselves against the interfaces `SYSTEMS_PLAN.md` specifies, so that
migration is a mechanical swap rather than new design.
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
        text = path.read_text(encoding="utf-8")
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


def upcast(row: dict) -> dict:
    """Normalize a legacy row shape to its current equivalent.

    Identity passthrough for now -- this package's evolution contract names
    this function as the single place a legacy shape ever gets normalized
    (today, none exist); the first real upcast (a legacy helper `agent_stop`
    row presenting as `helper_stop`) lands in a later step.
    """
    return row


def recorded_mode(row: dict) -> Mode:
    """The ``Mode`` a row was written under.

    A missing ``log_mode`` key -- every row predating this package, and
    every row until a later step starts stamping it -- reads as ``FULL``,
    matching today's un-differentiated behavior.
    """
    try:
        return Mode(row.get("log_mode", Mode.FULL.value))
    except ValueError:
        return Mode.FULL
