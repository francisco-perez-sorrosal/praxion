"""The log's retention policy, in one named place.

The writer shifts archives by these rules and the reader finds them by the same
names, so this module is the only builder and the only parser of an archive's
name: ``<log name>.<position>``, position 1 the newest. A position above
``ARCHIVE_COUNT`` is *surplus* -- still read as history, never written by
rotation.

Hot-path constraint: the writer imports the reader, which imports this module,
so it stays on ``datetime.timedelta`` and ``pathlib`` and imports neither of its
siblings.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

# The active log rotates when it reaches this size.
SIZE_CAP_BYTES = 10 * 1024 * 1024  # 10 MiB

# Archives kept beside the active log. Must stay at least 2: "more than one
# archive" is the point of the policy, and a test enforces it. Five segments
# cover about 35 weeks of a `full` log and about 70 of a `standard` one, both
# past HISTORY_TARGET; the log-health check judges the figure at run time.
ARCHIVE_COUNT = 5

# The span of history the archives are meant to cover.
HISTORY_TARGET = timedelta(weeks=26)


def archive_path(log_path: Path, position: int) -> Path:
    """Where the archive at ``position`` lives beside ``log_path``."""
    if position < 1:
        raise ValueError(f"an archive position starts at 1, got {position}")
    return log_path.with_name(f"{log_path.name}.{position}")


def archive_position(path: Path, log_name: str) -> int | None:
    """The position ``path`` holds as an archive of ``log_name``, or ``None``.

    Accepts exactly the names ``archive_path`` writes: a canonical decimal
    position, so ``.01``, ``.0`` and a backup suffix are not archives.
    """
    prefix = f"{log_name}."
    name = path.name
    if not name.startswith(prefix):
        return None
    digits = name[len(prefix) :]
    if not (digits.isascii() and digits.isdigit()) or digits.startswith("0"):
        return None
    return int(digits)
