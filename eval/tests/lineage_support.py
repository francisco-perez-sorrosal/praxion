"""What the lineage, ending and continuation tests share: a stop, a closed run, a part on disk,
and the identity a run was measured on."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from praxion_evals.adherence import results
from praxion_evals.adherence.infra_stop import (
    Launched,
    StopReason,
)
from praxion_evals.adherence.lineage import (
    Closed,
    InfraStopped,
    ReadTip,
    RunEnding,
    ending_to_json,
)
from praxion_evals.adherence.run_identity import MeasuredIdentity
from tests.test_adherence_results import declared, run_results

CREDIT_TAIL = "\nCredit balance is too low"


def infra_stop(scope: str = "both-arms") -> InfraStopped:
    sessions = tuple(Launched(f"task-{n}", "lean", 1) for n in range(3))
    reason = StopReason("result_error", CREDIT_TAIL, "researcher", "lean", sessions, scope)  # type: ignore[arg-type]
    return InfraStopped(reason)


def closed_ending(stopped: Any = None) -> Closed:
    return Closed(
        "no credit left", "2026-10-17T09:00:00Z", {"C1": "clear"}, stopped or infra_stop()
    )


def write_part(
    directory: Path, run_id: str, continues: str | None = None, ending: RunEnding | None = None
) -> None:
    extra: dict[str, Any] = {} if continues is None else {"continues": continues}
    if ending is not None:
        extra["ending"] = ending_to_json(ending)
    results.write_atomic(directory / f"{run_id}.json", run_results([], run_id=run_id, extra=extra))


SEED = 7


def identity(tree: str = "tree-a", **changes: Any) -> MeasuredIdentity:
    held: dict[str, Any] = {
        "tree": tree,
        "model": "claude-opus-5-5",
        "seed": SEED,
        "tasks": {"researcher": ("task-0", "task-1")},
        "launch_orders": {},
        "declared": declared(),
        "roles": {},
    }
    return MeasuredIdentity(**{**held, **changes})


def read_tip(ending: RunEnding | None = None, continued_by: str | None = None) -> ReadTip:
    extra = {} if ending is None else {"ending": ending_to_json(ending)}
    return ReadTip(run_results([], run_id="run-a", extra=extra), identity(), continued_by)
