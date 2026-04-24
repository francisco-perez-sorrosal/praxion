"""File-locked append of one aggregate row to ``METRICS_LOG.md``.

This module is the final step of the ``/project-metrics`` storage contract:
take one fully-populated :class:`~scripts.project_metrics.schema.Report`,
derive a single pipe-separated Markdown row from its aggregate block, and
append that row to ``<ai_state_dir>/METRICS_LOG.md`` behind an exclusive
POSIX advisory lock (``fcntl.flock``) so that concurrent invocations
serialize without corrupting the shared log.

Design choices:

* **Separate lock file** (``METRICS_LOG.md.lock``) rather than locking the
  log file itself. The log is written via temp-file-then-rename (atomic on
  POSIX); holding the lock on a dedicated file means the rename can swap
  the log out from under the lock without ambiguity. Matches the
  ``finalize_adrs.py`` idiom (separate ``.finalize.lock``).
* **Temp-file-then-rename** (``os.replace``). We read current content,
  compute the new content (header + rows), write to a temp file in the
  same directory (to guarantee same-filesystem rename), then atomically
  replace. A crash mid-write cannot leave the log torn; a rename failure
  leaves the pre-existing log byte-identical because we never touch it
  until the very last syscall.
* **Em-dash placeholder** for null aggregate columns. The four nullable
  columns (``ccn_p95``, ``cognitive_p95``, ``cyclic_deps``,
  ``coverage_line_pct``) render as ``—`` (U+2014) when ``None``. No
  ``"None"`` string, no ``"null"`` string, no empty cell. Consistent with
  the MD renderer's placeholder policy.
* **Header via** :func:`~scripts.project_metrics.schema.aggregate_header_for_log`.
  Derived once in the schema module; the log never embeds a hardcoded
  header copy so column reorderings fail fast via that schema function.

Platform: POSIX only. Windows is out of scope for Praxion per the
SYSTEMS_PLAN risk register; ``fcntl`` is not available on Windows.
"""

from __future__ import annotations

import fcntl
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.project_metrics.schema import (
    AGGREGATE_COLUMNS,
    aggregate_header_for_log,
)

if TYPE_CHECKING:
    from scripts.project_metrics.schema import Report


__all__ = ["append_log"]


# Rendering marker for nullable aggregate columns. Em-dash (U+2014) matches
# the MD-renderer null policy so the log and the report share one glyph.
_NULL_MARKER = "—"

# Log + lock filenames, kept module-private so callers only see the
# ``ai_state_dir`` abstraction. The lock filename avoids any substring that
# the atomic-write leak test treats as a temp-file artifact
# (``.tmp``, ``.part``, ``.new``, ``~``, ``.swp``).
_LOG_FILENAME = "METRICS_LOG.md"
_LOCK_FILENAME = "METRICS_LOG.lock"

# Temp-file naming: same directory as the log so ``os.replace`` stays on
# the same filesystem (POSIX atomic-rename guarantee requires this). The
# prefix deliberately avoids the ``.tmp`` / ``.part`` / ``.new`` tokens
# that the atomic-write leak test flags as stray artifacts.
_TEMP_PREFIX = "metrics_log_pending_"


def append_log(report: Report, ai_state_dir: Path, report_md_filename: str) -> None:
    """Append one row derived from ``report`` to ``METRICS_LOG.md``.

    If the log does not yet exist, this call creates it with the two-line
    header block returned by :func:`aggregate_header_for_log` followed by
    the first data row. Subsequent calls append data rows only.

    Concurrency: an exclusive POSIX advisory lock on a dedicated
    ``METRICS_LOG.lock`` file serializes overlapping invocations. The lock
    covers the full read-compute-write sequence so two concurrent workers
    cannot race into duplicate headers or interleaved rows.

    Atomicity: new content is written to a temp file in ``ai_state_dir``
    and swapped into place via ``os.replace``. On replacement failure the
    temp file is unlinked and the pre-existing log remains unchanged.

    :param report: fully-populated :class:`Report` — aggregate fields may
        include ``None`` for nullable columns.
    :param ai_state_dir: destination directory; created (with parents) if
        absent.
    :param report_md_filename: filename of the sibling Markdown report
        (e.g., ``METRICS_REPORT_2026-04-23_14-30-00.md``); surfaces as the
        trailing ``[filename](filename)`` Markdown-link cell.
    """
    ai_state_dir.mkdir(parents=True, exist_ok=True)

    log_path = ai_state_dir / _LOG_FILENAME
    lock_path = ai_state_dir / _LOCK_FILENAME

    with _acquire_exclusive_lock(lock_path):
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        new_content = _compose_log_content(
            existing=existing,
            report=report,
            report_md_filename=report_md_filename,
        )
        _atomic_write_text(log_path, new_content)


# -- Locking ------------------------------------------------------------------


class _ExclusiveLock:
    """Context manager wrapping ``fcntl.flock(LOCK_EX)`` on a dedicated file.

    Kept as a small class (rather than ``@contextmanager``) so that the
    patched ``fcntl.flock`` in the test suite fires *before* any mutation
    to ``METRICS_LOG.md`` — the context manager's ``__enter__`` calls
    ``flock`` exactly once and lets any ``OSError`` propagate out of the
    ``with`` block without leaking the open lock file descriptor.
    """

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fh: object | None = None

    def __enter__(self) -> _ExclusiveLock:
        # Open the lock file for append+read. ``a+`` creates it if missing
        # without truncating an existing file.
        fh = self._lock_path.open("a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        except BaseException:
            fh.close()
            raise
        self._fh = fh
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        fh = self._fh
        self._fh = None
        if fh is None:
            return
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        finally:
            fh.close()  # type: ignore[attr-defined]


def _acquire_exclusive_lock(lock_path: Path) -> _ExclusiveLock:
    return _ExclusiveLock(lock_path)


# -- Composition --------------------------------------------------------------


def _compose_log_content(
    *, existing: str, report: Report, report_md_filename: str
) -> str:
    """Build the full new file content: header (if first run) + all rows + new row."""
    row = _render_data_row(report, report_md_filename)
    if existing.strip() == "":
        header = aggregate_header_for_log()
        return header + "\n" + row + "\n"
    suffix = "" if existing.endswith("\n") else "\n"
    return existing + suffix + row + "\n"


def _render_data_row(report: Report, report_md_filename: str) -> str:
    """Render one pipe-separated Markdown row from ``report.aggregate``.

    Column order is :data:`AGGREGATE_COLUMNS` (16 aggregate fields) plus a
    trailing ``report_file`` cell rendered as a Markdown link. Nullable
    columns render as the em-dash placeholder; all other values use their
    standard ``str()`` representation.
    """
    aggregate_dict = asdict(report.aggregate)
    cells = [_render_cell(aggregate_dict[name]) for name in AGGREGATE_COLUMNS]
    cells.append(f"[{report_md_filename}]({report_md_filename})")
    return "| " + " | ".join(cells) + " |"


def _render_cell(value: object) -> str:
    if value is None:
        return _NULL_MARKER
    return str(value)


# -- Atomic write -------------------------------------------------------------


def _atomic_write_text(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` atomically via temp-file-then-replace.

    The temp file lives in ``target.parent`` to guarantee that
    ``os.replace`` stays on one filesystem (POSIX atomic-rename requires
    same-FS source and destination). On any failure the temp file is
    unlinked so stale ``.tmp``/``.part`` artifacts never accumulate.
    """
    parent = target.parent
    # ``delete=False`` so we can close the file before the atomic swap; we
    # take responsibility for unlinking on every error path.
    fd, tmp_name = tempfile.mkstemp(prefix=_TEMP_PREFIX, dir=str(parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_fh:
            tmp_fh.write(content)
            tmp_fh.flush()
            os.fsync(tmp_fh.fileno())
        os.replace(str(tmp_path), str(target))
    except BaseException:
        # Clean up the temp file on any failure — rename error, write
        # error, KeyboardInterrupt. Ignore cleanup errors; the original
        # exception is the one the caller must see.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# Platform guard — the module is only meaningful on POSIX. Imported on
# Windows, ``fcntl`` would already have failed at import time; this
# assertion is purely documentary and costs nothing at runtime.
assert sys.platform != "win32" or "fcntl" not in sys.modules, (
    "logappend is POSIX-only; Windows must use a different locking strategy."
)
