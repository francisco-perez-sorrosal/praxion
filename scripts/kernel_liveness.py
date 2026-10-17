"""The liveness mode of the kernel manifest checker: spawns of adopted roles that left no kernel row.

`check_kernel_manifest.py --liveness` judges an observation log instead of the kernels: each
first `agent_start` of a role at trial or switched (by the plugin's ledger) must have a matching
`kernel_injected` row, the only sign that the spawn hook ran for it. `liveness_report` is the
pure judgement; `check_liveness` reads the log and the ledger's history and hands it the rows.
The command line, which renders the report, stays in `check_kernel_manifest`.
"""

from __future__ import annotations

import dataclasses
import sys
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import kernel_ledger as kl
import kernel_ledger_history as kh
import kernel_model as km

# hooks/_observation_log is the one reader of the observation log; it sits beside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _observation_log import reader  # noqa: E402 (after sys.path injection)

AGENT_PREFIX = "praxion:"  # the agent type of this plugin's agents, as the log records it
SPAWN_ROW = "agent_start"
KERNEL_ROW = "kernel_injected"
STATE_DIR = ".ai-state"


@dataclass(frozen=True)
class LivenessReport:
    """What the liveness check judged and found: a clean report states how much it judged."""

    judged: int  # spawns of adopted roles at or after their record's start
    adopted: int  # roles at trial or switched in the ledger read
    findings: tuple[km.Finding, ...]
    unplaced: tuple[str, ...] = ()  # roles a plugin root without history cannot place


def check_liveness(root: Path, plugin_root: Path, since: str | None) -> LivenessReport:
    """Spawns in the observation log under `root` that left no kernel row, by the plugin's ledger."""
    placed = kh.placed_adoptions(plugin_root)
    bound = None if since is None else kh.commit_time(root, since)
    report = liveness_report(placed.adoptions, _observation_rows(root), bound)
    return dataclasses.replace(report, unplaced=placed.unplaced)


def liveness_report(
    adoptions: Mapping[str, kl.Adoption],
    rows: Sequence[Mapping[str, object]],
    since: datetime | None = None,
) -> LivenessReport:
    """Each spawn of an adopted role, from its record's start and from `since`, judged for its row.

    A spawn is an agent's first `agent_start`; a later one is a resume and is never judged. Only
    this plugin's agents (`praxion:<role>`) count; the role is what follows the prefix. Rows are
    matched by agent id, so one row serves exactly the spawn that wrote it.
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
    return LivenessReport(len(judged), len(adoptions), findings)


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


def _observation_rows(root: Path) -> list[dict]:
    """Every row of the log under `root`, read strictly: a lost row could hide a violation."""
    state_dir = root / STATE_DIR
    listing = reader.segment_listing(state_dir, archives=True)
    if listing.error:
        raise km.KernelModelError(
            f"{state_dir}: the observation log cannot be listed: {listing.error}"
        )
    if not listing.segments:
        raise km.KernelModelError(f"no observation log under {state_dir}: nothing to judge")
    rows: list[dict] = []
    for path in listing.segments:
        segment = reader.read_segment(path)
        if segment.error or segment.malformed_lines:
            problem = segment.error or f"unparseable lines {list(segment.malformed_lines)}"
            raise km.KernelModelError(
                f"{path}: the observation log is not readable whole: {problem}"
            )
        rows.extend(segment.rows)
    return rows
