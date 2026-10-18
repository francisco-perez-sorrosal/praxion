"""The liveness mode of the kernel manifest checker: spawns of adopted roles that left no kernel row.

`check_kernel_manifest.py --liveness` judges an observation log instead of the kernels: each
first `agent_start` of a role at trial or switched (by the plugin's ledger) must have a matching
`kernel_injected` row, the only sign that the spawn hook ran for it. `liveness_report` is the
pure judgement; `check_liveness` reads the log and the ledger's history and hands it the rows and
what it learned of each segment. A segment the read could not take whole (missing from the archive
positions, unreadable, or holding a line that does not parse) and that falls inside the judged
window makes the report unknown: it is named, every finding from the rest is still listed, and the
report is never clean. The command line, which renders the report, stays in `check_kernel_manifest`.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import kernel_ledger as kl
import kernel_ledger_history as kh
import kernel_model as km

# hooks/_observation_log is the one reader of the observation log; it sits beside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _observation_log import reader, retention  # noqa: E402 (after sys.path injection)

AGENT_PREFIX = "praxion:"  # the agent type of this plugin's agents, as the log records it
SPAWN_ROW = "agent_start"
KERNEL_ROW = "kernel_injected"
MISSING = "missing"  # why an archive position the log has a gap at is lost
STATE_DIR = ".ai-state"


@dataclass(frozen=True)
class SegmentFact:
    """What the read learned of one log segment, whether or not it could take it whole."""

    path: Path
    last_append: datetime | None  # when the segment last grew; None when that cannot be told
    problem: str | None  # why it was not read whole (a missing archive included); None when it was


@dataclass(frozen=True)
class LostSegment:
    """A segment inside the judged window that the read could not take whole."""

    path: Path
    reason: str


@dataclass(frozen=True)
class LivenessReport:
    """What the liveness check judged and found: a clean report states how much it judged.

    `lost` non-empty makes the report unknown: the findings are those of the segments read, and
    a spawn the lost segments held is neither judged nor cleared.
    """

    judged: int  # spawns of adopted roles at or after their record's start
    adopted: int  # roles at trial or switched in the ledger read
    findings: tuple[km.Finding, ...]
    unplaced: tuple[str, ...] = ()  # roles a plugin root without history cannot place
    lost: tuple[LostSegment, ...] = ()


def check_liveness(root: Path, plugin_root: Path, since: str | None) -> LivenessReport:
    """Spawns in the observation log under `root` that left no kernel row, by the plugin's ledger."""
    placed = kh.placed_adoptions(plugin_root)
    bound = None if since is None else kh.commit_time(root, since)
    rows, segments = _read_log(root)
    report = liveness_report(placed.adoptions, rows, bound, segments)
    return dataclasses.replace(report, unplaced=placed.unplaced)


def liveness_report(
    adoptions: Mapping[str, kl.Adoption],
    rows: Sequence[Mapping[str, object]],
    since: datetime | None = None,
    segments: Sequence[SegmentFact] = (),
) -> LivenessReport:
    """Each spawn of an adopted role, from its record's start and from `since`, judged for its row.

    A spawn is an agent's first `agent_start`; a later one is a resume and is never judged. Only
    this plugin's agents (`praxion:<role>`) count; the role is what follows the prefix. Rows are
    matched by agent id, so one row serves exactly the spawn that wrote it. `segments`, oldest
    first, say which segments were not read whole; those inside the judged window are reported.
    """
    delivered = {row.get("agent_id") for row in rows if row.get("event_type") == KERNEL_ROW}
    judged = _judged_spawns(adoptions, rows, since)
    findings = tuple(
        km.Finding(
            "liveness-missing-row",
            f"role {role}",
            f"agent {agent_id} started at {row.get('timestamp')} and left no {KERNEL_ROW} row",
        )
        for agent_id, role, row in judged
        if agent_id not in delivered
    )
    lost = _lost_inside(_window_start(adoptions, since), segments)
    return LivenessReport(len(judged), len(adoptions), findings, lost=lost)


def _window_start(adoptions: Mapping[str, kl.Adoption], since: datetime | None) -> datetime | None:
    """Where the judged window opens: the earliest instant any adopted role is judged from."""
    return min((_judged_from(adoption, since) for adoption in adoptions.values()), default=None)


def _lost_inside(
    window_start: datetime | None, segments: Sequence[SegmentFact]
) -> tuple[LostSegment, ...]:
    """The segments not read whole whose last append is not before the window opens.

    Segments are ordered oldest first and a segment never grows after a newer one began, so one
    whose own time is unknown (a missing archive, a failed stat) is no later than the nearest
    newer segment with a known time; with none, it may reach into the window.
    """
    if window_start is None:
        return ()
    lost: list[LostSegment] = []
    newer: datetime | None = None
    for segment in reversed(segments):
        latest = segment.last_append or newer
        if segment.problem and (latest is None or latest >= window_start):
            lost.append(LostSegment(segment.path, segment.problem))
        newer = latest
    return tuple(reversed(lost))


def _judged_spawns(
    adoptions: Mapping[str, kl.Adoption],
    rows: Sequence[Mapping[str, object]],
    since: datetime | None,
) -> list[tuple[object, str, Mapping[str, object]]]:
    spawns: dict[object, Mapping[str, object]] = {}
    for row in rows:
        if row.get("event_type") == SPAWN_ROW:
            spawns.setdefault(row.get("agent_id"), row)
    judged = []
    for agent_id, row in spawns.items():
        role = _adopted_role(row, adoptions)
        if role is not None and reader.row_time(dict(row)) >= _judged_from(adoptions[role], since):
            judged.append((agent_id, role, row))
    return judged


def _judged_from(adoption: kl.Adoption, since: datetime | None) -> datetime:
    return adoption.since if since is None else max(adoption.since, since)


def _adopted_role(row: Mapping[str, object], adoptions: Collection[str]) -> str | None:
    agent_type = row.get("agent_type")
    if not isinstance(agent_type, str) or not agent_type.startswith(AGENT_PREFIX):
        return None
    role = agent_type.removeprefix(AGENT_PREFIX)
    return role if role in adoptions else None


def _read_log(root: Path) -> tuple[list[dict], list[SegmentFact]]:
    """The rows of every segment under `root` that could be read, and what each segment was."""
    state_dir = root / STATE_DIR
    listing = reader.segment_listing(state_dir, archives=True)
    if listing.error:
        raise km.KernelModelError(
            f"{state_dir}: the observation log cannot be listed: {listing.error}"
        )
    if not listing.segments:
        raise km.KernelModelError(f"no observation log under {state_dir}: nothing to judge")
    rows: list[dict] = []
    facts = [SegmentFact(path, None, MISSING) for path in listing.missing]
    for path in listing.segments:
        segment = reader.read_segment(path)
        rows.extend(segment.rows)
        facts.append(SegmentFact(path, _last_append(path), _problem(segment)))
    facts.sort(key=lambda fact: -_archive_position(fact.path))
    return rows, facts


def _problem(segment: reader.SegmentRead) -> str | None:
    if segment.error:
        return segment.error
    if segment.malformed_lines:
        return f"unparseable lines {list(segment.malformed_lines)}"
    return None


def _archive_position(path: Path) -> int:
    """How far back a segment is kept: the active log 0, the newest archive 1."""
    return retention.archive_position(path, reader.LOG_FILENAME) or 0


def _last_append(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
