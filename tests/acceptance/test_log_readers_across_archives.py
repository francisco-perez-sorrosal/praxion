"""Readers see the history the archives keep, each at its own reach.

Whole-history readers (the spawn tally) read every retained archive and the
active log, oldest first; a damaged archive is named and the tally is never
reported complete over it. Pipeline recovery sees every row inside its age
window whichever segment holds it, and none older. Active-only and tail readers
see exactly the active log, as before.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.acceptance.drivers.history_readers import (
    comparable_pairing,
    lifecycle_pairing,
    localization,
    pipeline_checkout,
    recovery,
)
from tests.acceptance.drivers.log_rows import agent_start, agent_stop, tool_write
from tests.acceptance.drivers.log_segments import (
    active_log,
    append_rows,
    listed_archives,
    make_unreadable,
    now_iso,
    require_archive_positions,
    rotate,
    rotate_times,
    running_as_root,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session, new_checkout
from tests.acceptance.drivers.spawn_tally import Tally, spawn_count

CHECKOUT = "history-repo"
SESSION_ID = "5e551011-0000-4000-8000-0000000b0001"
SPAWNED = "a0ldest0000000001"
IMPLEMENTER = "praxion:implementer"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return new_checkout(tmp_path / CHECKOUT)


@pytest.fixture
def session(tmp_path: Path, checkout: Path) -> Session:
    return Session(HookHarness(tmp_path / "harness"), SESSION_ID, checkout)


def _tally(tmp_path: Path, checkout: Path) -> Tally:
    return spawn_count(checkout, CHECKOUT, scratch=tmp_path / "tally", budget=99)


def _spawn_then_rotate(checkout: Path, session: Session, rotations: int) -> None:
    """A spawn recorded before the first of `rotations` rotations, so it sits in the oldest archive."""
    append_rows(state_dir_of(checkout), [agent_start(SPAWNED, at=now_iso(), project=CHECKOUT)])
    rotate_times(session, state_dir_of(checkout), rotations)


def _not_complete(tally: Tally) -> bool:
    return not (tally.exit_code == 0 and tally.report and tally.report.get("verdict") == "within")


def _named(tally: Tally, segment: Path) -> bool:
    return str(segment) in tally.stderr or str(segment) in json.dumps(tally.report)


# -- Whole-history readers -----------------------------------------------------------


def test_a_spawn_in_the_oldest_retained_archive_resumed_in_the_active_log_counts_once(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    _spawn_then_rotate(checkout, session, 2)
    session.resume(SPAWNED, IMPLEMENTER)

    tally = _tally(tmp_path, checkout)

    assert (tally.spawns, tally.resumes) == (1, 1), tally.describe()


@pytest.mark.skipif(running_as_root(), reason="root reads a chmod-000 file")
def test_the_spawn_tally_names_an_unreadable_archive_and_does_not_report_complete(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    _spawn_then_rotate(checkout, session, 2)
    archives = listed_archives(state_dir_of(checkout))
    assert len(archives) == 2, f"two rotations should keep two archives, found {archives}"
    make_unreadable(archives[0])

    tally = _tally(tmp_path, checkout)

    assert _named(tally, archives[0]), tally.describe()
    assert _not_complete(tally), tally.describe()


def test_the_spawn_tally_names_a_missing_archive_between_two_present_ones_and_does_not_report_complete(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    require_archive_positions(3)
    _spawn_then_rotate(checkout, session, 3)
    missing = listed_archives(state_dir_of(checkout))[1]
    missing.unlink()

    tally = _tally(tmp_path, checkout)

    assert _named(tally, missing), tally.describe()
    assert _not_complete(tally), tally.describe()


# -- The recovery window -------------------------------------------------------------


def _recorded_step_work(state: Path, files: tuple[str, str], *, at: str) -> None:
    """An implementer that wrote the first of `files` and stopped, at `at`."""
    append_rows(
        state,
        [
            tool_write("ag1", files[0], at=at),
            agent_stop("ag1", at=at, project="pipeline", agent_type=IMPLEMENTER),
        ],
    )


def test_a_recent_agent_stop_pushed_into_an_older_archive_is_still_seen_by_recovery(
    tmp_path: Path,
) -> None:
    pipeline = pipeline_checkout(tmp_path / "pipeline")
    state = state_dir_of(pipeline.checkout)
    _recorded_step_work(state, (pipeline.file("src/a.py"), ""), at=now_iso(-timedelta(hours=1)))
    rotate_times(
        Session(HookHarness(tmp_path / "harness"), SESSION_ID, pipeline.checkout), state, 3
    )

    seen = localization(recovery(pipeline))

    assert seen == {"correlated_agent_ids": ["ag1"], "agent_stop_seen": True}


def test_an_agent_stop_older_than_the_window_in_an_archive_is_not_considered(
    tmp_path: Path,
) -> None:
    pipeline = pipeline_checkout(tmp_path / "pipeline")
    state = state_dir_of(pipeline.checkout)
    _recorded_step_work(state, (pipeline.file("src/a.py"), ""), at=now_iso(-timedelta(days=30)))
    rotate_times(
        Session(HookHarness(tmp_path / "harness"), SESSION_ID, pipeline.checkout), state, 2
    )

    seen = localization(recovery(pipeline))

    assert seen["correlated_agent_ids"] == [], seen
    assert seen["agent_stop_seen"] is not True, seen


def test_an_agent_stop_older_than_the_window_in_the_active_log_is_not_considered(
    tmp_path: Path,
) -> None:
    pipeline = pipeline_checkout(tmp_path / "pipeline")
    state = state_dir_of(pipeline.checkout)
    _recorded_step_work(state, (pipeline.file("src/a.py"), ""), at=now_iso(-timedelta(days=30)))

    seen = localization(recovery(pipeline))

    assert seen["correlated_agent_ids"] == [], seen
    assert seen["agent_stop_seen"] is not True, seen


def test_a_window_the_caller_sets_bounds_every_segment(tmp_path: Path) -> None:
    pipeline = pipeline_checkout(tmp_path / "pipeline")
    state = state_dir_of(pipeline.checkout)
    _recorded_step_work(state, (pipeline.file("src/a.py"), ""), at=now_iso(-timedelta(days=4)))
    rotate_times(
        Session(HookHarness(tmp_path / "harness"), SESSION_ID, pipeline.checkout), state, 2
    )

    within_default = localization(recovery(pipeline))["agent_stop_seen"]
    within_two_days = localization(recovery(pipeline, max_age_days=2))["agent_stop_seen"]

    assert (within_default, within_two_days is True) == (True, False)


# -- Active-only and tail readers ------------------------------------------------------


def _unpaired_rows(at: str) -> list[dict]:
    """An agent that ran a tool and never stopped: the lifecycle check warns if it reads these."""
    return [
        agent_start("a-archived", at=at, project=CHECKOUT, session_id="archived-session"),
        tool_write(
            "a-archived", "/x/src/z.py", at=at, project=CHECKOUT, session_id="archived-session"
        ),
    ]


def test_lifecycle_pairing_gives_the_same_verdict_whether_or_not_archives_hold_other_rows(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    state = state_dir_of(checkout)
    append_rows(state, _unpaired_rows("2026-09-20T10:00:00+00:00"))
    rotate(session, state, 1)
    append_rows(state, _unpaired_rows("2026-09-21T10:00:00+00:00"))
    rotate(session, state, 2)
    without_archives = new_checkout(tmp_path / "same-active-log")
    active_log(state_dir_of(without_archives)).write_bytes(active_log(state).read_bytes())

    with_archives_verdict = comparable_pairing(lifecycle_pairing(checkout))

    assert with_archives_verdict == comparable_pairing(lifecycle_pairing(without_archives))
