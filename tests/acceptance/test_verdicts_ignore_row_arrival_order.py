"""A verdict over the log does not depend on when a merged row arrived.

Merge-in appends a worktree's rows after rows the main checkout recorded later.
The spawn tally, the lifecycle-pairing check and pipeline recovery reach the
same verdict over the same rows whether they sit in time order or in arrival
order (merged rows last). Each scenario reads one checkout twice, rewriting
only the order of its log's lines between the reads.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from tests.acceptance.drivers.history_readers import (
    comparable_pairing,
    lifecycle_pairing,
    pipeline_checkout,
    recovery,
)
from tests.acceptance.drivers.log_rows import agent_start, agent_stop, session_start, tool_write
from tests.acceptance.drivers.log_segments import active_log, append_rows, now_iso, state_dir_of
from tests.acceptance.drivers.observation_harness import new_checkout
from tests.acceptance.drivers.spawn_tally import spawn_count

CHECKOUT = "order-repo"
IMPLEMENTER = "praxion:implementer"


def _write_in_order(checkout: Path, rows: list[dict]) -> None:
    log = active_log(state_dir_of(checkout))
    log.unlink(missing_ok=True)
    append_rows(state_dir_of(checkout), rows)


def _report_without_sources(tmp_path: Path, checkout: Path) -> dict | None:
    tally = spawn_count(checkout, CHECKOUT, scratch=tmp_path / "tally")
    return (
        None if tally.report is None else {k: v for k, v in tally.report.items() if k != "sources"}
    )


def test_the_spawn_tally_report_does_not_depend_on_row_arrival_order(tmp_path: Path) -> None:
    checkout = new_checkout(tmp_path / CHECKOUT)
    merged = [agent_start("a1", at="2026-09-20T10:00:00+00:00", project=CHECKOUT)]
    recorded_here = [agent_start("a1", at="2026-09-20T12:00:00+00:00", project=CHECKOUT)]
    _write_in_order(checkout, merged + recorded_here)
    in_time_order = _report_without_sources(tmp_path, checkout)
    _write_in_order(checkout, recorded_here + merged)

    in_arrival_order = _report_without_sources(tmp_path, checkout)

    assert in_arrival_order == in_time_order


def test_lifecycle_pairing_verdict_does_not_depend_on_row_arrival_order(tmp_path: Path) -> None:
    checkout = new_checkout(tmp_path / CHECKOUT)
    merged = [
        agent_start("a-wt", at="2026-09-20T10:00:00+00:00", project="wt", session_id="wt-session"),
        tool_write("a-wt", "/wt/src/x.py", at="2026-09-20T10:01:00+00:00", session_id="wt-session"),
    ]
    recorded_here = [
        session_start("main-session", at="2026-09-21T10:00:00+00:00", project=CHECKOUT),
        agent_start(
            "a-main", at="2026-09-21T10:01:00+00:00", project=CHECKOUT, session_id="main-session"
        ),
        agent_stop(
            "a-main", at="2026-09-21T10:02:00+00:00", project=CHECKOUT, session_id="main-session"
        ),
    ]
    _write_in_order(checkout, merged + recorded_here)
    in_time_order = comparable_pairing(lifecycle_pairing(checkout))
    _write_in_order(checkout, recorded_here + merged)

    in_arrival_order = comparable_pairing(lifecycle_pairing(checkout))

    assert in_arrival_order == in_time_order


def test_recovery_verdict_does_not_depend_on_row_arrival_order(tmp_path: Path) -> None:
    pipeline = pipeline_checkout(tmp_path / "pipeline")
    earlier, later = now_iso(-timedelta(days=2)), now_iso(-timedelta(days=1))
    merged = [
        tool_write("ag1", pipeline.file("src/a.py"), at=earlier),
        agent_stop("ag1", at=earlier, project="pipeline", agent_type=IMPLEMENTER),
    ]
    recorded_here = [tool_write("ag2", pipeline.file("src/b.py"), at=later)]
    _write_in_order(pipeline.checkout, merged + recorded_here)
    in_time_order = recovery(pipeline)
    _write_in_order(pipeline.checkout, recorded_here + merged)

    in_arrival_order = recovery(pipeline)

    assert in_arrival_order == in_time_order
