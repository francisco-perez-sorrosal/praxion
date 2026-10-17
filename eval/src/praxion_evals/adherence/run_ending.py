"""How one part of a run ends, and what the part that continues it starts from.

A part of a run ends ``Finished``, ``InfraStopped``, ``SpendRefused`` or ``Interrupted``
(``lineage.RunEnding``); ``finalized`` writes that ending, whether the part is complete and when it
finished into its results.

A continuation is a later part of the same declared run. Each part's results file holds only the
sessions that part launched; the earlier parts keep theirs, so a recorded session is carried over by
the lineage, never copied or redrawn. A ``Continuation`` is what a new part writes before its first
session: the run it continues, the lineage of parts before it with the stop that ended each, the
declared run's whole plan (not just the tasks this part launches again) and the launch orders drawn
so far, so a later continuation reads them from the latest part alone.

Everything here is pure: the caller supplies the time and writes the file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, assert_never

from praxion_evals.adherence.infra_stop import StopReason
from praxion_evals.adherence.lineage import (
    Closed,
    Finished,
    InfraStopped,
    Interrupted,
    Legacy,
    RunEnding,
    SpendRefused,
    ending_of,
    ending_to_json,
)
from praxion_evals.adherence.model import Errored
from praxion_evals.adherence.results import RunResults

# ---------------------------------------------------------------------------
# The end of a part
# ---------------------------------------------------------------------------


def finalized(
    recorded: RunResults, stop: StopReason | None, interrupted: bool, now: datetime
) -> RunResults:
    """``recorded`` with its ending, its completeness and its finishing time.

    Complete means: no refused launch, every arm built and proven, no session left in error, not
    stopped and not interrupted.
    """
    latest = {(r.setup.role, r.setup.arm, r.setup.task_id): r.status for r in recorded.sessions}
    unbuilt = any(not a["built"] for per_arm in recorded.arms.values() for a in per_arm.values())
    complete = (
        not interrupted
        and not recorded.run.refused_launches
        and not unbuilt
        and not any(isinstance(status, Errored) for status in latest.values())
        and stop is None
    )
    extra = {
        **recorded.run.extra,
        "ending": ending_to_json(part_ending(recorded, stop, interrupted)),
        "finished_at": now.isoformat(),
    }
    return replace(recorded, run=replace(recorded.run, complete=complete, extra=extra))


def part_ending(recorded: RunResults, stop: StopReason | None, interrupted: bool) -> RunEnding:
    if interrupted:
        return Interrupted()
    if stop is not None:
        return InfraStopped(stop)
    if recorded.run.refused_launches:
        return SpendRefused(refused_tasks(recorded))
    return Finished()


def refused_tasks(recorded: RunResults) -> tuple[str, ...]:
    """The tasks whose session the cap refused, in order, each once."""
    refused = (
        r.setup.task_id
        for r in recorded.sessions
        if isinstance(r.status, Errored) and r.status.kind == "launch_refused"
    )
    return tuple(dict.fromkeys(refused))


def stop_summary(ending: RunEnding) -> str:
    """The words a lineage names the end of one of its parts by."""
    match ending:
        case InfraStopped(reason=reason):
            return (
                f"{len(reason.sessions)} {reason.arm} sessions in a row ended in {reason.kind}"
                " with the same evidence"
            )
        case SpendRefused():
            return "the spend cap refused a launch"
        case Interrupted():
            return "the operator interrupted it"
        case Finished():
            return "it finished its plan"
        case Closed(reason=reason):
            return f"closed: {reason}"
        case Legacy():
            return "recorded before runs recorded how they ended"
        case _:
            assert_never(ending)


# ---------------------------------------------------------------------------
# What a continuation starts from
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Continuation:
    """The parts a new part continues, oldest first (``(run id, how it ended)``), the declared
    run's planned task ids by role, and the launch orders its parts drew, by role then task."""

    parts: tuple[tuple[str, RunEnding], ...]
    tasks: Mapping[str, tuple[str, ...]]
    launch_orders: Mapping[str, Mapping[str, tuple[str, ...]]]

    def __post_init__(self) -> None:
        if not self.parts:
            raise ValueError("a continuation continues at least one part")

    @classmethod
    def of(cls, parts: Sequence[RunResults]) -> Continuation:
        """The continuation of the lineage ``parts`` (oldest first): the plan of the first part,
        the launch orders the latest one recorded."""
        first, latest = parts[0].run.extra, parts[-1].run.extra
        return cls(
            parts=tuple((part.run.id, ending_of(part)) for part in parts),
            tasks={role: tuple(ids) for role, ids in first["tasks"].items()},
            launch_orders={
                role: {task: tuple(order) for task, order in per_task.items()}
                for role, per_task in latest.get("launch_order", {}).items()
            },
        )

    def extra(self, run_id: str) -> dict[str, Any]:
        """The entries the part ``run_id`` records about the run it continues (its ``run`` keys)."""
        lineage = [{"run_id": part, "stop": stop_summary(ending)} for part, ending in self.parts]
        return {
            "continues": self.parts[-1][0],
            "lineage": [*lineage, {"run_id": run_id, "stop": None}],
            "tasks": {role: list(ids) for role, ids in self.tasks.items()},
            "launch_order": {
                role: {task: list(order) for task, order in per_task.items()}
                for role, per_task in self.launch_orders.items()
            },
        }
