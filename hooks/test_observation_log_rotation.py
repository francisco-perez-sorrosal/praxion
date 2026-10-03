"""Rotation shifts numbered archives, and a fault part-way through costs no history.

At the size cap the writer frees position 1 by moving each archive one position
older, then renames the active log into it. The shift stops at the lowest free
position, so a gap left by an earlier fault is closed instead of pushing the oldest
archive out; only with every position taken is the archive at the last position
overwritten. These tests drive the shift with the cap patched down to a few
bytes, inject a refused rename at every position of the shift (the one thing a
real directory cannot be made to do on demand), and check that the next rotation
leaves exactly what a clean one would have.

They also cover the batched append a copier uses: pre-serialized rows, appended
in lock holds of bounded size, rotating between rows.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hooks._observation_log import retention, writer
from hooks._observation_log.retention import archive_path

LOG_NAME = "observations.jsonl"
ACTIVE = b"active\n"
NEW_ROW = {"event": "new"}
NEW_LINE = b'{"event":"new"}\n'
LATER_ROW = {"event": "later"}
LATER_LINE = b'{"event":"later"}\n'


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The active log, with the cap patched so any non-empty log is at it."""
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 1)
    return tmp_path / ".ai-state" / LOG_NAME


def _archive_tag(position: int) -> bytes:
    return f"archive {position}\n".encode()


def _seed(log: Path, positions: list[int]) -> None:
    """The active log plus one tagged archive at each of `positions`."""
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(ACTIVE)
    for position in positions:
        archive_path(log, position).write_bytes(_archive_tag(position))


def _archives(log: Path, highest: int) -> dict[int, bytes]:
    """The bytes held at each occupied position from 1 to `highest`."""
    return {
        position: archive_path(log, position).read_bytes()
        for position in range(1, highest + 1)
        if archive_path(log, position).exists()
    }


def _in_position_order(log: Path, highest: int) -> list[bytes]:
    """The archives read newest to oldest, skipping free positions."""
    return list(_archives(log, highest).values())


def _generation(number: int) -> bytes:
    return f"generation {number}\n".encode()


def _rotate_generations(log: Path, generations: int) -> None:
    """Rotate once per generation, each time from an active log holding only that generation."""
    for number in range(generations):
        log.write_bytes(_generation(number))
        writer.append_observation(log, NEW_ROW)


def _refuse_renames_onto(monkeypatch: pytest.MonkeyPatch, refused: Path) -> None:
    """Make the one rename whose destination is `refused` fail, as a full disk would."""
    real_replace = os.replace

    def replace(src, dst):
        if Path(dst) == refused:
            raise OSError(f"injected: rename onto {refused.name} refused")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)


# -- A clean shift --------------------------------------------------------------


def test_below_the_cap_nothing_moves_and_no_archive_position_is_examined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    _seed(log, [1])
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", len(ACTIVE) + 1)
    examined: list[str] = []
    real_lstat = os.lstat

    def lstat(path, *args, **kwargs):
        examined.append(str(path))
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    writer.append_observation(log, NEW_ROW)

    assert log.read_bytes() == ACTIVE + NEW_LINE
    assert _archives(log, retention.ARCHIVE_COUNT) == {1: _archive_tag(1)}
    assert [p for p in examined if Path(p).name.startswith(f"{LOG_NAME}.")] == []


def test_the_log_rotates_when_it_reaches_the_cap_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    _seed(log, [])
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", len(ACTIVE))

    writer.append_observation(log, NEW_ROW)

    assert log.read_bytes() == NEW_LINE
    assert _archives(log, retention.ARCHIVE_COUNT) == {1: ACTIVE}


def test_one_byte_below_the_cap_the_log_does_not_rotate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    _seed(log, [])
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", len(ACTIVE) + 1)

    writer.append_observation(log, NEW_ROW)

    assert log.read_bytes() == ACTIVE + NEW_LINE
    assert _archives(log, retention.ARCHIVE_COUNT) == {}


def test_the_legacy_archive_becomes_position_two_byte_for_byte(log: Path) -> None:
    _seed(log, [1])
    legacy = archive_path(log, 1)
    legacy_inode = legacy.stat().st_ino

    writer.append_observation(log, NEW_ROW)

    moved = archive_path(log, 2)
    assert moved.read_bytes() == _archive_tag(1)
    assert moved.stat().st_ino == legacy_inode, "the legacy archive was copied, not renamed"
    assert archive_path(log, 1).read_bytes() == ACTIVE
    assert log.read_bytes() == NEW_LINE


def test_a_full_set_of_positions_drops_only_the_oldest(log: Path) -> None:
    count = retention.ARCHIVE_COUNT
    _seed(log, list(range(1, count + 1)))

    writer.append_observation(log, NEW_ROW)

    assert _in_position_order(log, count + 1) == [ACTIVE] + [
        _archive_tag(p) for p in range(1, count)
    ]


def test_a_gap_is_filled_before_any_archive_is_dropped(log: Path) -> None:
    count = retention.ARCHIVE_COUNT
    _seed(log, [p for p in range(1, count + 1) if p != 2])

    writer.append_observation(log, NEW_ROW)

    assert _archives(log, count) == {
        1: ACTIVE,
        2: _archive_tag(1),
        **{p: _archive_tag(p) for p in range(3, count + 1)},
    }


@pytest.mark.parametrize("count", [2, 3])
def test_the_policy_count_is_read_when_the_writer_rotates(
    log: Path, monkeypatch: pytest.MonkeyPatch, count: int
) -> None:
    monkeypatch.setattr(retention, "ARCHIVE_COUNT", count)
    log.parent.mkdir(parents=True)
    surplus = archive_path(log, count + 1)
    surplus.write_bytes(b"surplus\n")

    _rotate_generations(log, count + 2)

    assert _in_position_order(log, count) == [_generation(g) for g in range(count + 1, 1, -1)]
    assert surplus.read_bytes() == b"surplus\n", "a surplus archive was written by rotation"


# -- A shift that stops part-way --------------------------------------------------


def _clean_rotation(positions: list[int], count: int) -> list[bytes]:
    """What one clean rotation leaves, newest first, from archives at `positions`."""
    kept = [_archive_tag(p) for p in sorted(positions)]
    return ([ACTIVE + NEW_LINE] + kept)[:count]


def _shift_destinations(positions: list[int], count: int) -> list[int]:
    """Every position a rename lands on during the shift, in rename order."""
    free = next((p for p in range(1, count + 1) if p not in positions), count)
    return list(range(free, 0, -1))


_GAP_LAYOUT = [1, 2, 3]  # positions 4 and up are free
_FULL_LAYOUT = list(range(1, retention.ARCHIVE_COUNT + 1))


@pytest.mark.parametrize(
    ("positions", "refused"),
    [(_GAP_LAYOUT, d) for d in _shift_destinations(_GAP_LAYOUT, retention.ARCHIVE_COUNT)]
    + [(_FULL_LAYOUT, d) for d in _shift_destinations(_FULL_LAYOUT, retention.ARCHIVE_COUNT)],
    ids=lambda v: f"{len(v)}-archives" if isinstance(v, list) else f"refused-onto-{v}",
)
def test_a_refused_rename_keeps_the_row_and_every_archive_and_the_next_rotation_closes_the_gap(
    log: Path, monkeypatch: pytest.MonkeyPatch, positions: list[int], refused: int
) -> None:
    count = retention.ARCHIVE_COUNT
    _seed(log, positions)
    before = _in_position_order(log, count)
    with monkeypatch.context() as faulty:
        _refuse_renames_onto(faulty, archive_path(log, refused))
        writer.append_observation(log, NEW_ROW)

    assert log.read_bytes() == ACTIVE + NEW_LINE, "the row was lost or the active log moved"
    after_fault = _in_position_order(log, count)
    assert after_fault in (before, before[: count - 1]), "an archive was lost or reordered"

    writer.append_observation(log, LATER_ROW)

    assert _in_position_order(log, count) == _clean_rotation(positions, count)
    assert sorted(_archives(log, count)) == list(
        range(1, len(_clean_rotation(positions, count)) + 1)
    )
    assert log.read_bytes() == LATER_LINE


def test_a_position_that_cannot_be_examined_stops_the_rotation_and_keeps_the_row(
    log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(log, [1, 2])
    unexaminable = archive_path(log, 2)
    real_lstat = os.lstat

    def lstat(path, *args, **kwargs):
        if Path(path) == unexaminable:
            raise PermissionError("injected: position cannot be examined")
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    writer.append_observation(log, NEW_ROW)

    assert log.read_bytes() == ACTIVE + NEW_LINE
    assert _archives(log, retention.ARCHIVE_COUNT) == {1: _archive_tag(1), 2: _archive_tag(2)}


# -- The batched append ----------------------------------------------------------


def _rows_in_history(log: Path) -> list[str]:
    """Every line across the segments, oldest archive first, then the active log."""
    segments = [archive_path(log, p) for p in range(retention.ARCHIVE_COUNT, 0, -1)] + [log]
    return [
        line
        for segment in segments
        if segment.exists()
        for line in segment.read_text(encoding="utf-8").splitlines()
    ]


def _lines(count: int) -> list[str]:
    return [
        json.dumps({"seq": seq, "pad": "x" * 20}, separators=(",", ":")) for seq in range(count)
    ]


def test_append_lines_writes_every_row_once_and_in_order(tmp_path: Path) -> None:
    log = tmp_path / LOG_NAME
    lines = _lines(5)

    assert writer.append_lines(log, lines) == (5, None)
    assert _rows_in_history(log) == lines


def test_append_lines_rotates_between_rows_and_never_splits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    lines = _lines(9)
    row_bytes = len(lines[0]) + 1
    monkeypatch.setattr(writer, "OBSERVATIONS_MAX_BYTES", 3 * row_bytes)

    assert writer.append_lines(log, lines) == (9, None)

    assert _rows_in_history(log) == lines
    assert _archives(log, retention.ARCHIVE_COUNT).keys() == {1, 2}
    for position in (1, 2):
        assert archive_path(log, position).stat().st_size == 3 * row_bytes


def test_append_lines_holds_the_lock_for_at_most_one_batch_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    lines = _lines(10)
    row_bytes = len(lines[0]) + 1
    monkeypatch.setattr(writer, "APPEND_BATCH_BYTES", 3 * row_bytes)
    held: list[int] = []
    real_flock = writer.fcntl.flock

    def history_bytes() -> int:
        return sum(p.stat().st_size for p in log.parent.glob(f"{LOG_NAME}*"))

    def flock(fd, operation):
        if operation == writer.fcntl.LOCK_EX:
            held.append(-history_bytes())
        else:
            held[-1] += history_bytes()
        return real_flock(fd, operation)

    monkeypatch.setattr(writer.fcntl, "flock", flock)

    assert writer.append_lines(log, lines) == (10, None)
    assert held == [3 * row_bytes, 3 * row_bytes, 3 * row_bytes, row_bytes]


def test_a_row_longer_than_a_batch_is_written_whole_in_a_hold_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    monkeypatch.setattr(writer, "APPEND_BATCH_BYTES", 10)
    lines = ["short", json.dumps({"long": "y" * 40})]

    assert writer.append_lines(log, lines) == (2, None)
    assert _rows_in_history(log) == lines


def test_a_failed_write_reports_how_many_rows_landed_and_writes_none_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / LOG_NAME
    lines = _lines(6)
    failing_append = 4
    appends: list[str] = []

    def failing_open(file, mode="r", *args, **kwargs):
        if Path(file) == log and "a" in mode:
            appends.append(str(file))
            if len(appends) == failing_append:
                raise OSError("injected: disk full")
        return open(file, mode, *args, **kwargs)

    monkeypatch.setattr(writer, "open", failing_open, raising=False)

    written, error = writer.append_lines(log, lines)

    assert written == failing_append - 1
    assert error is not None
    assert "disk full" in error
    assert _rows_in_history(log) == lines[:written]


@pytest.mark.parametrize("broken", ["a\nb", "a\rb"])
def test_a_line_holding_a_line_break_is_refused_before_anything_is_written(
    tmp_path: Path, broken: str
) -> None:
    log = tmp_path / LOG_NAME

    written, error = writer.append_lines(log, ["fine", broken])

    assert written == 0
    assert error is not None
    assert not log.exists()


def test_no_lines_is_a_no_op(tmp_path: Path) -> None:
    log = tmp_path / LOG_NAME

    assert writer.append_lines(log, []) == (0, None)
    assert not log.exists()
