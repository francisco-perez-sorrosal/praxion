"""Append-only JSONL observation store for tool and lifecycle events.

Provides thread/process-safe appends via fcntl.LOCK_EX on a sidecar lock file.
Reads tolerate partial last lines (append-only JSONL guarantee).
"""

from __future__ import annotations

import contextlib
import fcntl
import json
from datetime import UTC, datetime
from pathlib import Path

# -- Constants ----------------------------------------------------------------

DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MiB rotation threshold
DEFAULT_QUERY_LIMIT = 100
MAX_SESSION_OBSERVATIONS = 10_000

ROTATION_TIMESTAMP_FORMAT = "%Y-%m-%d"


# -- ObservationStore ---------------------------------------------------------


class ObservationStore:
    """Append-only JSONL observation store for tool and lifecycle events.

    Each observation is a single JSON line. Appends are process-safe via
    an exclusive lock on a sidecar `observations.lock` file.
    """

    def __init__(self, file_path: Path | str) -> None:
        self._path = Path(file_path)
        self._lock_path = self._path.parent / "observations.lock"

    # -- Write ----------------------------------------------------------------

    def append(self, observation: dict) -> None:
        """Append a single observation as a JSONL line.

        Thread/process safe via LOCK_EX on the sidecar lock file.
        Creates parent directories and the file if they do not exist.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        with self._exclusive_lock():
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(observation, separators=(",", ":")) + "\n")
                f.flush()

    # -- Read -----------------------------------------------------------------

    def query(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        session_id: str | None = None,
        tool_filter: str | None = None,
        classification: str | None = None,
        event_type: str | None = None,
        limit: int = DEFAULT_QUERY_LIMIT,
    ) -> list[dict]:
        """Read and filter observations from the JSONL file.

        Returns up to *limit* matching observations in chronological order
        (oldest first). Malformed JSON lines are silently skipped.
        """
        observations = self._read_all()

        filtered: list[dict] = []
        for obs in observations:
            if not _matches(
                obs,
                since=since,
                until=until,
                session_id=session_id,
                tool_filter=tool_filter,
                classification=classification,
                event_type=event_type,
            ):
                continue
            filtered.append(obs)

        # Apply limit (from the end to get the most recent when over-limit)
        if len(filtered) > limit:
            filtered = filtered[-limit:]
        return filtered

    def session_observations(self, session_id: str) -> list[dict]:
        """All observations for a specific session."""
        return self.query(session_id=session_id, limit=MAX_SESSION_OBSERVATIONS)

    # -- Maintenance ----------------------------------------------------------

    def rotate_if_needed(self, max_bytes: int = DEFAULT_MAX_BYTES) -> str | None:
        """Rotate the file if it exceeds *max_bytes*.

        Renames the current file to ``observations.YYYY-MM-DD.jsonl``
        and returns the rotated filename, or ``None`` if no rotation occurred.
        """
        if not self._path.exists():
            return None

        if self._path.stat().st_size <= max_bytes:
            return None

        timestamp = datetime.now(UTC).strftime(ROTATION_TIMESTAMP_FORMAT)
        rotated_name = f"observations.{timestamp}.jsonl"
        rotated_path = self._path.parent / rotated_name

        # Avoid overwriting an existing rotation from the same day
        counter = 1
        while rotated_path.exists():
            rotated_name = f"observations.{timestamp}.{counter}.jsonl"
            rotated_path = self._path.parent / rotated_name
            counter += 1

        with self._exclusive_lock():
            self._path.rename(rotated_path)

        return rotated_name

    def count(self) -> int:
        """Count total observations in the file."""
        return len(self._read_all())

    def count_sessions(self) -> int:
        """Count distinct session_id values across all observations.

        Streams the JSONL file; missing file or empty file returns 0.
        Malformed lines are skipped. O(N) over the active file only
        (rotation is not walked).
        """
        if not self._path.exists():
            return 0
        seen: set[str] = set()
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obs = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = obs.get("session_id")
                if sid:
                    seen.add(sid)
        return len(seen)

    def file_size(self) -> int:
        """Return file size in bytes, or 0 if the file does not exist."""
        if not self._path.exists():
            return 0
        return self._path.stat().st_size

    # -- Internal -------------------------------------------------------------

    @contextlib.contextmanager
    def _exclusive_lock(self):
        """Acquire an exclusive lock on the sidecar lock file."""
        self._lock_path.touch(exist_ok=True)
        lock_fd = self._lock_path.open("w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

    def _read_all(self) -> list[dict]:
        """Read all valid JSONL lines from the file.

        Malformed lines (including partial last lines from concurrent writes)
        are silently skipped.
        """
        if not self._path.exists():
            return []

        observations: list[dict] = []
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    observations.append(json.loads(line))
        return observations


# -- Filter helpers -----------------------------------------------------------


def _matches(
    obs: dict,
    *,
    since: str | None,
    until: str | None,
    session_id: str | None,
    tool_filter: str | None,
    classification: str | None,
    event_type: str | None,
) -> bool:
    """Return True if the observation matches all non-None filters."""
    if since is not None and obs.get("timestamp", "") < since:
        return False
    if until is not None and obs.get("timestamp", "") > until:
        return False
    if session_id is not None and obs.get("session_id") != session_id:
        return False
    if tool_filter is not None and obs.get("tool_name") != tool_filter:
        return False
    if classification is not None and obs.get("classification") != classification:
        return False
    if event_type is not None and obs.get("event_type") != event_type:
        return False
    return True
