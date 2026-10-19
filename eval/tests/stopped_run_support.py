"""The stopped run the continuation tests share: eight task shapes that stopped on three lean
failures in a row, and the builders that plant it. ``test_adherence_continue_run.py`` keeps the
fixtures that build it once per module and copy it per test. Moved unchanged from that module to
keep it under the size ceiling; the helpers it imports lost their leading underscore."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from praxion_evals.adherence import results
from praxion_evals.adherence.infra_stop import EvidenceTail, Launched, StopReason
from praxion_evals.adherence.lineage import InfraStopped, RunEnding, ending_to_json
from praxion_evals.adherence.model import Errored, SessionRecord
from tests.adherence_run_support import ROLE, Script, run_small
from tests.conftest import use_full_first, use_paid_script, use_unswitched_checkout

EIGHT_TASKS = ["--required-pairs", "8"]  # with the small run's zero slack: eight planned tasks
STOPPING_KIND, STOPPING_TAIL = "exit_nonzero", "fatal: the session channel closed unexpectedly"
STOPPED = "stopped.json"
# The planned position of each task shape, as the planner reads them.
(COMPLETE, LEAN_BEFORE_STREAK, LEAN_ONLY, FULL_ONLY) = (0, 1, 2, 3)
(LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED) = (4, 5, 6, 7)
LAUNCHED_AGAIN = (LEAN_IN_STREAK, BOTH_IN_STREAK, REFUSED, NEVER_LAUNCHED)


# ---------------------------------------------------------------------------
# A stopped run in eight shapes, and its continuation
# ---------------------------------------------------------------------------


def failed_as(record: SessionRecord, kind: str = STOPPING_KIND, tail: str = STOPPING_TAIL):
    status = Errored(kind, "the session failed", tails=EvidenceTail(tail, ""))  # type: ignore[arg-type]
    return replace(record, status=status)


def shaped(ran: dict[tuple[int, str], SessionRecord]) -> list[SessionRecord]:
    """The eight task shapes in planned order; ``ran`` is each (position, arm)'s measured record."""
    return [
        ran[(COMPLETE, "full")],
        ran[(COMPLETE, "lean")],
        ran[(LEAN_BEFORE_STREAK, "full")],
        *[failed_as(ran[(LEAN_BEFORE_STREAK, "lean")])] * 2,
        ran[(LEAN_ONLY, "full")],
        *[failed_as(ran[(LEAN_ONLY, "lean")], "no_result_event", "")] * 2,
        *[failed_as(ran[(FULL_ONLY, "full")], "envelope_unparseable", "")] * 2,
        ran[(FULL_ONLY, "lean")],
        failed_as(ran[(REFUSED, "full")], "launch_refused", ""),
        failed_as(ran[(REFUSED, "lean")], "launch_refused", ""),
        ran[(LEAN_IN_STREAK, "full")],
        *[failed_as(ran[(LEAN_IN_STREAK, "lean")])] * 2,
        *[failed_as(ran[(BOTH_IN_STREAK, "full")])] * 2,
        failed_as(ran[(BOTH_IN_STREAK, "lean")]),
    ]


def rewritten(tmp_path: Path, run: results.RunResults, ending: RunEnding, sessions=None):
    extra = {**run.run.extra, "ending": ending_to_json(ending)}
    rewritten = replace(run, run=replace(run.run, extra=extra), sessions=sessions or run.sessions)
    results.write_atomic(tmp_path / STOPPED, rewritten)
    return rewritten


def stopped_in_eight_shapes(tmp_path: Path, *options: str) -> results.RunResults:
    """A run of eight tasks that stopped on three lean failures in a row, seen in both arms."""
    run = run_small(tmp_path, *EIGHT_TASKS, *options, name=STOPPED)[1]
    planned = run.run.extra["tasks"][ROLE]
    ran = {(planned.index(r.setup.task_id), r.setup.arm): r for r in run.sessions}
    streak = [(LEAN_IN_STREAK, 1), (LEAN_IN_STREAK, 2), (BOTH_IN_STREAK, 1)]
    stop = StopReason(
        STOPPING_KIND,
        EvidenceTail(STOPPING_TAIL, "").masked(),
        ROLE,
        "lean",
        tuple(Launched(planned[at], "lean", attempt) for at, attempt in streak),
        "both-arms",
    )
    return rewritten(tmp_path, run, InfraStopped(stop), shaped(ran))


def build_stopped(tmp_path_factory: pytest.TempPathFactory, *, seeded_order: bool) -> Path:
    where = tmp_path_factory.mktemp("stopped")
    with pytest.MonkeyPatch.context() as patch:
        use_paid_script(patch, Script())
        if not seeded_order:
            use_full_first(patch)
        use_unswitched_checkout(patch)
        stopped_in_eight_shapes(where)
    return where
