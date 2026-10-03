"""A rotation keeps earlier archives, never loses a row, and costs nothing below the cap.

When a hook appends to a log that has reached its size cap, the active log becomes
the newest archive and every older archive moves one position older; only an
archive beyond the policy's count is removed, and only the oldest. The single
archive the earlier scheme wrote survives the first rotation unchanged. A
rotation the filesystem refuses still records the row and loses none. Below the
cap the recording hook does no extra file work, and a rotation renames segments
without reading or rewriting a row.

Scenarios fill the active log with numbered padding rows (one generation per
rotation) and read the segments back through the owner's listing, oldest first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.file_work_probe import probing_harness
from tests.acceptance.drivers.log_rows import agent_start
from tests.acceptance.drivers.log_segments import (
    LEGACY_ARCHIVE_NAME,
    active_log,
    append_rows,
    archive_generations,
    fill_to_cap,
    history_rows,
    identity,
    listed_archives,
    listed_segments,
    retention_archive_count,
    rotate,
    rotate_times,
    running_as_root,
    session_ids_in,
    state_dir_of,
)
from tests.acceptance.drivers.observation_harness import HookHarness, Session, new_checkout
from tests.acceptance.drivers.spawn_tally import spawn_count

CHECKOUT = "retention-repo"
SESSION_ID = "5e551011-0000-4000-8000-0000000a0001"
REFUSED_SESSION = "5e551011-0000-4000-8000-0000000a00f1"
LATER_SESSION = "5e551011-0000-4000-8000-0000000a00f2"
LEGACY_AGENT = "a65ec99bc016c1ca0"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return new_checkout(tmp_path / CHECKOUT)


@pytest.fixture
def session(tmp_path: Path, checkout: Path) -> Session:
    return Session(HookHarness(tmp_path / "harness"), SESSION_ID, checkout)


def _legacy_archive(checkout: Path) -> Path:
    """The single archive the earlier scheme left, holding a spawn recorded then."""
    archive = state_dir_of(checkout) / LEGACY_ARCHIVE_NAME
    append_rows(
        state_dir_of(checkout),
        [agent_start(LEGACY_AGENT, at="2026-08-30T23:31:50.032601+00:00", project=CHECKOUT)],
        segment=archive,
    )
    return archive


# -- Several archives are kept ----------------------------------------------------


def test_two_rotations_keep_both_archives_oldest_first(checkout: Path, session: Session) -> None:
    rotate_times(session, state_dir_of(checkout), 2)

    assert archive_generations(state_dir_of(checkout)) == [{1}, {2}]


def test_rotations_up_to_the_policy_count_keep_every_archive(
    checkout: Path, session: Session
) -> None:
    kept = retention_archive_count()

    rotate_times(session, state_dir_of(checkout), kept)

    assert archive_generations(state_dir_of(checkout)) == [{g} for g in range(1, kept + 1)]


def test_a_rotation_beyond_the_policy_count_removes_only_the_oldest_archive(
    checkout: Path, session: Session
) -> None:
    kept = retention_archive_count()

    rotate_times(session, state_dir_of(checkout), kept + 1)

    assert archive_generations(state_dir_of(checkout)) == [{g} for g in range(2, kept + 2)]


# -- The archive written before this change is kept -------------------------------


def test_the_legacy_archive_survives_the_first_rotation_unchanged_as_the_next_older_archive(
    checkout: Path, session: Session
) -> None:
    legacy_bytes = _legacy_archive(checkout).read_bytes()

    rotate(session, state_dir_of(checkout), 1)

    archives = listed_archives(state_dir_of(checkout))
    assert [a.read_bytes() == legacy_bytes for a in archives] == [True, False]
    assert archive_generations(state_dir_of(checkout)) == [set(), {1}]


def test_the_spawn_tally_still_reads_the_legacy_archive_after_the_first_rotation(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    _legacy_archive(checkout)
    rotate(session, state_dir_of(checkout), 1)
    session.resume(LEGACY_AGENT)

    tally = spawn_count(checkout, CHECKOUT, scratch=tmp_path / "tally")

    assert (tally.spawns, tally.resumes) == (1, 1), tally.describe()


# -- A rotation that fails part-way loses no row -----------------------------------


@pytest.mark.skipif(running_as_root(), reason="root ignores a read-only directory")
def test_a_rotation_the_state_directory_refuses_still_records_the_row_and_loses_none(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    state = state_dir_of(checkout)
    session.session_start()
    padded = fill_to_cap(state, 1)
    refused = Session(session.harness, REFUSED_SESSION, checkout)
    state.chmod(0o555)
    try:
        refused.session_start()
    finally:
        state.chmod(0o755)

    padding_seqs = [r["seq"] for r in history_rows(state) if r.get("event_type") == "padding"]
    assert sorted(padding_seqs) == list(range(padded)), "a padding row was lost or duplicated"
    assert session_ids_in(state).count(REFUSED_SESSION) == 1


@pytest.mark.skipif(running_as_root(), reason="root ignores a read-only directory")
def test_a_refused_rotation_completes_at_a_later_rotation(
    tmp_path: Path, checkout: Path, session: Session
) -> None:
    state = state_dir_of(checkout)
    session.session_start()
    fill_to_cap(state, 1)
    state.chmod(0o555)
    try:
        Session(session.harness, REFUSED_SESSION, checkout).session_start()
    finally:
        state.chmod(0o755)

    Session(session.harness, LATER_SESSION, checkout).session_start()

    assert archive_generations(state) == [{1}]
    assert session_ids_in(state).count(LATER_SESSION) == 1


# -- Recording below the cap costs what it cost before -----------------------------


def _write_call(session: Session, target: Path) -> None:
    """A completed Write call: a file-changing tool call, recorded in every mode but off."""
    target.write_text("changed\n", encoding="utf-8")
    tool_use_id = session.new_tool_use_id()
    tool_input = {"file_path": str(target), "content": "changed\n"}
    session.tool_event(
        "PostToolUse", "Write", tool_input, tool_use_id, tool_response={"filePath": str(target)}
    )


def test_below_the_cap_the_recording_hook_touches_no_archive_lists_no_state_directory_and_starts_no_process(
    tmp_path: Path, checkout: Path
) -> None:
    probe = probing_harness(tmp_path / "probe")
    session = Session(probe.harness, SESSION_ID, checkout)
    _legacy_archive(checkout)
    rotate(session, state_dir_of(checkout), 1)
    archives = set(listed_archives(state_dir_of(checkout))) | {
        state_dir_of(checkout) / LEGACY_ARCHIVE_NAME
    }
    probe.reset()

    _write_call(session, checkout / "notes.txt")

    work = probe.work().by("capture_observations.py")
    assert work.opened({active_log(state_dir_of(checkout))}), "the probe saw no recording append"
    assert work.opened(archives) == []
    assert work.listed(state_dir_of(checkout)) == []
    assert work.processes_started() == []


def test_a_rotation_renames_segments_without_reading_or_rewriting_any_row(
    tmp_path: Path, checkout: Path
) -> None:
    probe = probing_harness(tmp_path / "probe")
    session = Session(probe.harness, SESSION_ID, checkout)
    state = state_dir_of(checkout)
    legacy = identity(_legacy_archive(checkout))
    fill_to_cap(state, 1)
    former_active = identity(active_log(state))
    former_bytes = active_log(state).read_bytes()
    probe.reset()

    _write_call(session, checkout / "notes.txt")

    archives = listed_archives(state)
    newest = archives[-1]
    assert newest.stat().st_ino == former_active.inode, "the active log was copied, not renamed"
    assert newest.read_bytes().startswith(former_bytes), "rows of the former active log changed"
    assert [identity(a) for a in archives[:-1]] == [legacy], "an older archive was rewritten"
    reads = (
        probe.work().by("capture_observations.py").opened_for_reading(set(listed_segments(state)))
    )
    assert reads == []
