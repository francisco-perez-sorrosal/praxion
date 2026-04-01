"""Watch .ai-work/<task-slug>/PROGRESS.md for new progress lines and convert to events."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from watchfiles import awatch

from task_chronograph_mcp.events import Event, EventStore, EventType

PROGRESS_FILENAME = "PROGRESS.md"

# Format: [TIMESTAMP] [AGENT] Phase N/M: phase-name -- summary #label1 #key=value
PROGRESS_LINE_PATTERN = re.compile(
    r"\[([^\]]+)\]\s+\[([^\]]+)\]\s+Phase\s+(\d+)/(\d+):\s+(\S+)\s+--\s+(.+)"
)


def parse_progress_line(line: str) -> Event | None:
    """Parse a PROGRESS.md line into an Event.

    Expected format:
        [TIMESTAMP] [AGENT] Phase N/M: phase-name -- summary text #label1 #key=value

    Returns None for malformed lines that do not match the expected format.
    """
    match = PROGRESS_LINE_PATTERN.match(line.strip())
    if not match:
        return None

    timestamp_str, agent_name, phase_str, total_str, phase_name, rest = match.groups()

    labels, summary = _parse_labels_and_summary(rest)
    timestamp = _parse_timestamp(timestamp_str)

    return Event(
        event_type=EventType.PHASE_TRANSITION,
        agent_type=agent_name,
        timestamp=timestamp,
        phase=int(phase_str),
        total_phases=int(total_str),
        phase_name=phase_name,
        message=summary,
        labels=labels,
    )


def _parse_labels_and_summary(rest: str) -> tuple[dict[str, str], str]:
    """Separate hashtag labels from summary text.

    Labels are hashtag-prefixed tokens at the end of the line:
      - ``#tag`` becomes ``{"tag": ""}``
      - ``#key=value`` becomes ``{"key": "value"}``
    Everything before the first hashtag token is summary text.
    """
    labels: dict[str, str] = {}
    summary_parts: list[str] = []

    for word in rest.split():
        if word.startswith("#"):
            tag = word[1:]
            if "=" in tag:
                key, value = tag.split("=", 1)
                labels[key] = value
            else:
                labels[tag] = ""
        else:
            summary_parts.append(word)

    return labels, " ".join(summary_parts)


def _parse_timestamp(timestamp_str: str) -> datetime:
    """Parse an ISO-format timestamp, falling back to now on failure."""
    try:
        return datetime.fromisoformat(timestamp_str)
    except ValueError:
        return datetime.now(UTC)


async def watch_progress_file(path: Path, store: EventStore) -> None:
    """Watch a directory tree for PROGRESS.md changes and convert new lines to events.

    Watches `.ai-work/` and all task-scoped subdirectories (e.g.,
    `.ai-work/<task-slug>/PROGRESS.md`).  Tracks line counts per file so
    multiple concurrent pipelines are handled independently.

    The watcher skips lines that existed before it started (no history replay).
    New lines are parsed and, if valid, added to the store as phase-transition events.
    """
    line_counts: dict[Path, int] = {}

    # Seed counts for any pre-existing PROGRESS.md files (root + subdirs)
    for progress_file in path.rglob(PROGRESS_FILENAME):
        try:
            line_counts[progress_file] = len(progress_file.read_text().splitlines())
        except (OSError, UnicodeDecodeError):
            line_counts[progress_file] = 0

    async for changes in awatch(path):
        for _change_type, changed_path in changes:
            if Path(changed_path).name != PROGRESS_FILENAME:
                continue
            changed = Path(changed_path)
            try:
                lines = changed.read_text().splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            last = line_counts.get(changed, 0)
            new_lines = lines[last:]
            line_counts[changed] = len(lines)

            for line in new_lines:
                event = parse_progress_line(line)
                if event is not None:
                    store.add(event)
