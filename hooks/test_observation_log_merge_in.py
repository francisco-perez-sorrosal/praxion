"""Merge-in copies a worktree's log rows into the main log, once each, unchanged.

A worktree's rows are copied by their stored text, skipping any row the main log
(archives included) already holds, so a merge can be repeated after the main log
rotated or the worktree kept recording. The worktree's files are only ever read.
A log that cannot be read or written is reported with the counts of what was
copied; it never raises. Unreadable segments are modelled as a directory standing
where the file should be, which fails the same way for every user, root included.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hooks._observation_log import merge_in, reader, retention, writer
from hooks._observation_log.merge_in import (
    DEGRADED,
    MERGED,
    NOTHING_TO_MERGE,
    RECORDING_OFF,
    merge_worktree_log,
)
from hooks._observation_log.retention import archive_path

STANDARD = {"PRAXION_OBSERVATION_LOG": "standard"}


@pytest.fixture
def main_state(tmp_path: Path) -> Path:
    return tmp_path / "main" / ".ai-state"


@pytest.fixture
def worktree_state(tmp_path: Path) -> Path:
    return tmp_path / "worktree" / ".ai-state"


def _row(n: int, **fields) -> dict:
    return {"event_type": "agent_start", "timestamp": f"2026-10-0{n}T00:00:00Z", "n": n, **fields}


def _lines(rows: list[dict]) -> bytes:
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def _seed(state: Path, rows: list[dict], *, archives: dict[int, list[dict]] | None = None) -> None:
    """Write `rows` to the active log and each position of `archives` beside it."""
    state.mkdir(parents=True, exist_ok=True)
    reader.log_path(state).write_bytes(_lines(rows))
    for position, archived in (archives or {}).items():
        archive_path(reader.log_path(state), position).write_bytes(_lines(archived))


def _history(state: Path) -> list[dict]:
    return reader.read_rows(state, archives=True)


def _main_bytes(state: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(state.iterdir())} if state.is_dir() else {}


def _stamped_files(state: Path) -> dict[str, tuple[bytes, int]]:
    """Every file's bytes and modification time: what a read-only pass must leave."""
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(state.iterdir())}


def _merge(main_state: Path, worktree_state: Path, env=STANDARD):
    return merge_worktree_log(main_state, worktree_state, env=env)


# -- what is copied ------------------------------------------------------------------------


def test_every_worktree_row_the_main_log_lacks_is_copied_and_the_counts_say_so(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [_row(1)])
    _seed(worktree_state, [_row(2), _row(1), _row(3)])

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied, report.skipped, report.malformed) == (MERGED, 2, 1, 0)
    assert report.reason is None
    assert _history(main_state) == [_row(1), _row(2), _row(3)]


def test_rows_are_copied_oldest_segment_first(main_state: Path, worktree_state: Path) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(3)], archives={1: [_row(2)], 2: [_row(1)]})

    _merge(main_state, worktree_state)

    assert _history(main_state) == [_row(1), _row(2), _row(3)]


def test_a_row_is_copied_as_stored_with_its_project_and_mode_untouched(
    main_state: Path, worktree_state: Path
) -> None:
    stored = (
        '{"z":1,  "project":"pipeline-a", "log_mode":"full",'
        ' "event_type":"gate_fire", "summary":"café   end"}'
    )
    legacy = '{"event_type": "agent_stop", "project": "pipeline-a"}'
    _seed(main_state, [])
    worktree_state.mkdir(parents=True)
    reader.log_path(worktree_state).write_text(f"{stored}\n{legacy}\n", encoding="utf-8")

    _merge(main_state, worktree_state)

    copied = reader.log_path(main_state).read_text(encoding="utf-8")
    assert copied == f"{stored}\n{legacy}\n"


@pytest.mark.parametrize("mode", ["full", "standard"])
def test_rows_recorded_under_any_mode_are_copied_whichever_mode_is_in_effect(
    main_state: Path, worktree_state: Path, mode: str
) -> None:
    other = {"log_mode": "full" if mode == "standard" else "standard"}
    _seed(main_state, [])
    _seed(worktree_state, [_row(1, **other), _row(2)])

    report = _merge(main_state, worktree_state, {"PRAXION_OBSERVATION_LOG": mode})

    assert (report.mode.value, report.copied) == (mode, 2)


def test_two_rows_that_differ_in_any_field_are_both_copied(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [_row(1, agent_id="a1", tool_name="Read")])
    _seed(
        worktree_state,
        [_row(1, agent_id="a2", tool_name="Read"), _row(1, agent_id="a1", tool_name="Grep")],
    )

    report = _merge(main_state, worktree_state)

    assert (report.copied, report.skipped) == (2, 0)


def test_a_row_repeated_inside_the_worktree_log_is_copied_once(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1), _row(1)])

    report = _merge(main_state, worktree_state)

    assert (report.copied, report.skipped) == (1, 1)


def test_key_order_and_spacing_do_not_make_two_rows_different(
    main_state: Path, worktree_state: Path
) -> None:
    main_state.mkdir(parents=True)
    reader.log_path(main_state).write_text('{"a":1,"b":2}\n', encoding="utf-8")
    worktree_state.mkdir(parents=True)
    reader.log_path(worktree_state).write_text('{ "b": 2, "a": 1 }\n', encoding="utf-8")

    report = _merge(main_state, worktree_state)

    assert (report.copied, report.skipped) == (0, 1)


# -- repeating a merge ---------------------------------------------------------------------


def test_a_second_merge_copies_nothing_and_leaves_the_main_log_alone(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1), _row(2)])
    _merge(main_state, worktree_state)
    before = _main_bytes(main_state)

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied, report.skipped) == (MERGED, 0, 2)
    assert _main_bytes(main_state) == before


def test_a_merge_after_the_main_log_rotated_copies_nothing(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1), _row(2)])
    _merge(main_state, worktree_state)
    log = reader.log_path(main_state)
    log.rename(archive_path(log, 1))
    log.write_bytes(_lines([_row(9)]))

    report = _merge(main_state, worktree_state)

    assert (report.copied, report.skipped) == (0, 2)


def test_rows_the_worktree_recorded_after_an_earlier_merge_are_copied_by_the_next(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1)])
    _merge(main_state, worktree_state)
    with open(reader.log_path(worktree_state), "ab") as handle:
        handle.write(_lines([_row(2)]))

    report = _merge(main_state, worktree_state)

    assert (report.copied, report.skipped) == (1, 1)
    assert _history(main_state) == [_row(1), _row(2)]


# -- the other outcomes --------------------------------------------------------------------


def test_a_worktree_with_no_log_has_nothing_to_merge_and_creates_nothing_in_main(
    main_state: Path, worktree_state: Path
) -> None:
    worktree_state.mkdir(parents=True)
    _seed(main_state, [_row(1)])
    before = _main_bytes(main_state)

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied, report.reason) == (NOTHING_TO_MERGE, 0, None)
    assert _main_bytes(main_state) == before


def test_a_worktree_with_no_state_directory_has_nothing_to_merge(
    main_state: Path, worktree_state: Path
) -> None:
    report = _merge(main_state, worktree_state)

    assert report.outcome == NOTHING_TO_MERGE
    assert not main_state.exists()


@pytest.mark.parametrize(
    "env",
    [{"PRAXION_OBSERVATION_LOG": "off"}, {"PRAXION_DISABLE_OBSERVABILITY": "1"}],
    ids=["mode-off", "legacy-kill-switch"],
)
def test_under_the_off_mode_nothing_is_copied_and_the_report_says_so(
    main_state: Path, worktree_state: Path, env: dict
) -> None:
    _seed(main_state, [_row(1)])
    _seed(worktree_state, [_row(2)])
    before = _main_bytes(main_state)

    report = _merge(main_state, worktree_state, env)

    assert (report.outcome, report.mode.value, report.copied) == (RECORDING_OFF, "off", 0)
    assert report.reason is None
    assert _main_bytes(main_state) == before


def test_malformed_lines_are_counted_and_left_behind_without_degrading_the_merge(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1)])
    with open(reader.log_path(worktree_state), "ab") as handle:
        handle.write(b'{not json\n["an", "array"]\n')

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied, report.malformed, report.reason) == (MERGED, 1, 2, None)
    assert _history(main_state) == [_row(1)]


# -- a log that cannot be read or written --------------------------------------------------


def test_an_unreadable_worktree_segment_is_named_and_every_other_row_is_still_copied(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [], archives={1: [_row(1), _row(2)]})
    active = reader.log_path(worktree_state)
    active.unlink()
    active.mkdir()

    report = _merge(main_state, worktree_state)

    assert report.outcome == DEGRADED
    assert report.copied == 2
    assert report.unreadable == (str(active),)
    assert str(active) in report.reason


def test_an_archive_missing_between_the_worktrees_segments_is_named_as_unreadable(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(3)], archives={1: [_row(2)], 3: [_row(1)]})
    absent = archive_path(reader.log_path(worktree_state), 2)

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied) == (DEGRADED, 3)
    assert report.unreadable == (str(absent),)
    assert "missing" in report.reason


def test_an_unreadable_main_segment_copies_nothing_because_duplicates_cannot_be_ruled_out(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [_row(1)])
    unreadable = archive_path(reader.log_path(main_state), 1)
    unreadable.mkdir()
    _seed(worktree_state, [_row(2)])
    before = reader.log_path(main_state).read_bytes()

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied) == (DEGRADED, 0)
    assert str(unreadable) in report.reason
    assert reader.log_path(main_state).read_bytes() == before


def test_a_failed_append_is_reported_with_the_rows_that_did_land(
    main_state: Path, worktree_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(1), _row(2), _row(3)])
    monkeypatch.setattr(
        merge_in.writer, "append_lines", lambda log, lines: (2, "append failed after 2 rows")
    )

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied, report.skipped) == (DEGRADED, 2, 0)
    assert report.reason == "append failed after 2 rows"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a read-only directory")
def test_an_unwritable_main_state_directory_degrades_and_the_worktree_log_stays_intact(
    main_state: Path, worktree_state: Path
) -> None:
    main_state.mkdir(parents=True)
    _seed(worktree_state, [_row(1)])
    before = _stamped_files(worktree_state)
    main_state.chmod(0o555)
    try:
        report = _merge(main_state, worktree_state)
    finally:
        main_state.chmod(0o755)

    assert (report.outcome, report.copied) == (DEGRADED, 0)
    assert report.reason
    assert _stamped_files(worktree_state) == before


# -- the main log's rules apply to merged rows ---------------------------------------------


def test_merged_rows_that_carry_the_main_log_past_its_cap_rotate_it_like_any_append(
    main_state: Path, worktree_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_row(n) for n in range(1, 8)]
    row_bytes = len(json.dumps(rows[0])) + 1
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 3 * row_bytes)
    _seed(main_state, [])
    _seed(worktree_state, rows)

    report = _merge(main_state, worktree_state)

    assert (report.outcome, report.copied) == (MERGED, 7)
    assert _history(main_state) == rows
    archives = reader.segment_listing(main_state, archives=True).segments
    assert len(archives) == 3
    assert archives[0].stat().st_size == 3 * row_bytes


def test_merging_more_rows_than_the_archives_hold_drops_only_the_oldest_like_a_rotation(
    main_state: Path, worktree_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_row(n) for n in range(1, 10)]
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 1)
    monkeypatch.setattr(retention, "ARCHIVE_COUNT", 2)
    _seed(main_state, [])
    _seed(worktree_state, rows)

    _merge(main_state, worktree_state)

    kept = reader.segment_listing(main_state, archives=True).segments
    assert [p.name.rpartition(".")[2] for p in kept] == ["2", "1", "jsonl"]


# -- the worktree is only read -------------------------------------------------------------


@pytest.mark.parametrize("damaged", [False, True], ids=["healthy", "partly-unreadable"])
def test_the_worktrees_files_are_left_byte_for_byte_and_untouched(
    main_state: Path, worktree_state: Path, damaged: bool
) -> None:
    _seed(main_state, [])
    _seed(worktree_state, [_row(3)], archives={1: [_row(2)], 3: [_row(1)]} if damaged else {1: []})
    before = _stamped_files(worktree_state)

    _merge(main_state, worktree_state)

    assert _stamped_files(worktree_state) == before


def test_the_report_names_a_reason_exactly_when_it_is_degraded(
    main_state: Path, worktree_state: Path
) -> None:
    _seed(main_state, [_row(1)])
    _seed(worktree_state, [_row(2)])
    healthy = _merge(main_state, worktree_state)
    off = _merge(main_state, worktree_state, {"PRAXION_OBSERVATION_LOG": "off"})
    nothing = _merge(main_state, main_state.parent / "elsewhere" / ".ai-state")
    archive_path(reader.log_path(main_state), 1).mkdir()
    degraded = _merge(main_state, worktree_state)

    reports = (healthy, off, nothing, degraded)

    assert [r.outcome for r in reports] == [MERGED, RECORDING_OFF, NOTHING_TO_MERGE, DEGRADED]
    assert [r.reason is not None for r in reports] == [False, False, False, True]


# -- several worktrees in one run ----------------------------------------------------------


def _merge_all(main_state: Path, worktree_states: list[Path], env=STANDARD):
    return merge_in.merge_worktree_logs(main_state, worktree_states, env=env)


def test_each_worktree_in_a_run_is_checked_against_the_rows_the_one_before_copied(
    main_state: Path, tmp_path: Path
) -> None:
    _seed(main_state, [_row(1)])
    first, second = tmp_path / "first" / ".ai-state", tmp_path / "second" / ".ai-state"
    _seed(first, [_row(2), _row(3)])
    _seed(second, [_row(3), _row(4)])

    reports = _merge_all(main_state, [first, second])

    assert [(r.outcome, r.copied, r.skipped) for r in reports] == [(MERGED, 2, 0), (MERGED, 1, 1)]
    assert sorted(row["n"] for row in _history(main_state)) == [1, 2, 3, 4]


def test_the_main_log_is_read_once_for_a_run_and_not_at_all_when_no_worktree_has_a_log(
    main_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(main_state, [_row(1)])
    withlog = [tmp_path / name / ".ai-state" for name in ("a", "b", "c")]
    for n, state in enumerate(withlog, start=2):
        _seed(state, [_row(n)])
    reads = []
    real = merge_in._identities_held
    monkeypatch.setattr(
        merge_in, "_identities_held", lambda state: reads.append(state) or real(state)
    )

    _merge_all(main_state, [tmp_path / "none" / ".ai-state"])
    assert reads == []

    _merge_all(main_state, withlog)
    assert reads == [main_state]


def test_a_worktree_with_no_log_is_not_degraded_by_an_unreadable_main_log(
    main_state: Path, tmp_path: Path
) -> None:
    _seed(main_state, [_row(1)])
    archive_path(reader.log_path(main_state), 1).mkdir()
    withlog = tmp_path / "withlog" / ".ai-state"
    _seed(withlog, [_row(2)])

    empty, degraded = _merge_all(main_state, [tmp_path / "none" / ".ai-state", withlog])

    assert (empty.outcome, degraded.outcome) == (NOTHING_TO_MERGE, DEGRADED)


def test_a_row_a_failed_append_never_landed_is_still_copied_from_the_next_worktree(
    main_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(main_state, [])
    first, second = tmp_path / "first" / ".ai-state", tmp_path / "second" / ".ai-state"
    _seed(first, [_row(1), _row(2)])
    _seed(second, [_row(2)])
    real = merge_in.writer.append_lines
    calls = []

    def fails_after_one_row(log, lines):
        calls.append(list(lines))
        return (
            (real(log, lines[:1])[0], "append failed after 1 row")
            if len(calls) == 1
            else real(log, lines)
        )

    monkeypatch.setattr(merge_in.writer, "append_lines", fails_after_one_row)

    first_report, second_report = _merge_all(main_state, [first, second])

    assert (first_report.outcome, first_report.copied) == (DEGRADED, 1)
    assert (second_report.outcome, second_report.copied, second_report.skipped) == (MERGED, 1, 0)
    assert sorted(row["n"] for row in _history(main_state)) == [1, 2]
