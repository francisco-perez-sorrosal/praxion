"""`read_segment` streams one segment file and never raises; discovery, raw reads,
row identity and row time are the reader's other contracts.

A line is what text-mode file iteration yields: only a newline ends a JSONL
record, so a JSON-valid row whose string carries a raw Unicode line
separator is one row. A missing or unreadable file names its reason with no
rows; a line that is not a JSON object is reported by its 1-based physical
line number and never costs the rest of the segment.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hooks._observation_log import retention
from hooks._observation_log.reader import (
    LOG_FILENAME,
    UNTIMED,
    SegmentListing,
    read_raw_segment,
    read_segment,
    row_identity,
    row_time,
    segment_listing,
    segments,
)


def _segment(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "seg.jsonl"
    path.write_bytes(content)
    return path


def test_a_missing_segment_names_the_reason_with_no_rows(tmp_path: Path) -> None:
    read = read_segment(tmp_path / "absent.jsonl")

    assert (read.rows, read.malformed_lines, read.error) == ((), (), "missing")


def test_malformed_lines_are_reported_by_physical_line_number(tmp_path: Path) -> None:
    path = _segment(tmp_path, b'{"a": 1}\nnot-json\n\n[1, 2]\n{"b": 2}\n')

    read = read_segment(path)

    assert read.rows == ({"a": 1}, {"b": 2})
    assert read.malformed_lines == (2, 4)
    assert read.error is None


def test_a_torn_utf8_sequence_costs_one_line(tmp_path: Path) -> None:
    path = _segment(tmp_path, b'{"a":1}\n{"b":"\xff\n{"c":3}\n')

    read = read_segment(path)

    assert read.rows == ({"a": 1}, {"c": 3})
    assert read.malformed_lines == (2,)


def test_an_unreadable_segment_names_the_reason_with_no_rows(tmp_path: Path) -> None:
    read = read_segment(tmp_path)

    assert read.error.startswith("unreadable:")
    assert (read.rows, read.malformed_lines) == ((), ())


@pytest.mark.parametrize("separator", ["\u0085", " ", " "])
def test_a_json_valid_row_with_a_raw_line_separator_is_one_row(
    tmp_path: Path, separator: str
) -> None:
    row = {"event_type": "recovery", "summary": f"a{separator}b"}
    line = json.dumps(row, ensure_ascii=False)
    path = _segment(tmp_path, f"{line}\nnot-json\n".encode())

    read = read_segment(path)

    assert read.rows == (row,)
    assert read.malformed_lines == (2,)


# -- discovery: the segments a history reader walks ---------------------------------


def _touch(directory: Path, *names: str) -> None:
    for name in names:
        (directory / name).write_text('{"a": 1}\n')


def test_the_active_log_alone_is_listed_when_archives_are_not_asked_for(tmp_path: Path) -> None:
    _touch(tmp_path, LOG_FILENAME, f"{LOG_FILENAME}.1")

    listing = segment_listing(tmp_path, archives=False)

    assert listing == SegmentListing(segments=(tmp_path / LOG_FILENAME,), missing=())


def test_no_directory_is_listed_when_archives_are_not_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path, LOG_FILENAME)

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a directory was listed")

    for scan in ("scandir", "listdir"):
        monkeypatch.setattr(os, scan, refuse)
    monkeypatch.setattr(Path, "iterdir", refuse)
    monkeypatch.setattr(Path, "glob", refuse)

    assert segment_listing(tmp_path, archives=False).segments == (tmp_path / LOG_FILENAME,)


def test_archives_come_oldest_first_by_descending_position_then_the_active_log(
    tmp_path: Path,
) -> None:
    _touch(tmp_path, LOG_FILENAME, *(f"{LOG_FILENAME}.{p}" for p in (2, 3, 1)))

    listing = segment_listing(tmp_path, archives=True)

    assert [p.name for p in listing.segments] == [
        f"{LOG_FILENAME}.3",
        f"{LOG_FILENAME}.2",
        f"{LOG_FILENAME}.1",
        LOG_FILENAME,
    ]
    assert listing.missing == ()


def test_order_follows_position_never_modification_time(tmp_path: Path) -> None:
    _touch(tmp_path, f"{LOG_FILENAME}.1", f"{LOG_FILENAME}.2")
    os.utime(tmp_path / f"{LOG_FILENAME}.2", (4_000_000_000, 4_000_000_000))

    names = [p.name for p in segment_listing(tmp_path, archives=True).segments]

    assert names == [f"{LOG_FILENAME}.2", f"{LOG_FILENAME}.1"]


def test_a_position_between_one_and_the_highest_present_is_named_missing(
    tmp_path: Path,
) -> None:
    _touch(tmp_path, LOG_FILENAME, f"{LOG_FILENAME}.1", f"{LOG_FILENAME}.4")

    listing = segment_listing(tmp_path, archives=True)

    assert [p.name for p in listing.missing] == [f"{LOG_FILENAME}.3", f"{LOG_FILENAME}.2"]
    assert not set(listing.segments) & set(listing.missing)


def test_a_missing_newest_archive_is_a_gap_even_when_older_ones_exist(tmp_path: Path) -> None:
    _touch(tmp_path, LOG_FILENAME, f"{LOG_FILENAME}.2")

    listing = segment_listing(tmp_path, archives=True)

    assert [p.name for p in listing.missing] == [f"{LOG_FILENAME}.1"]


def test_a_position_above_the_policy_count_is_still_read(tmp_path: Path) -> None:
    surplus = retention.ARCHIVE_COUNT + 2
    _touch(tmp_path, LOG_FILENAME, f"{LOG_FILENAME}.1", f"{LOG_FILENAME}.{surplus}")

    names = [p.name for p in segment_listing(tmp_path, archives=True).segments]

    assert names[0] == f"{LOG_FILENAME}.{surplus}"


def test_files_that_only_resemble_archives_are_not_listed(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        LOG_FILENAME,
        f"{LOG_FILENAME}.0",
        f"{LOG_FILENAME}.01",
        f"{LOG_FILENAME}.1.bak",
        "observations.lock",
        "other.jsonl.1",
    )

    listing = segment_listing(tmp_path, archives=True)

    assert listing == SegmentListing(segments=(tmp_path / LOG_FILENAME,), missing=())


def test_a_state_directory_that_cannot_be_listed_has_no_archives(tmp_path: Path) -> None:
    listing = segment_listing(tmp_path / "absent", archives=True)

    assert listing == SegmentListing(segments=(), missing=())


def test_segments_is_the_listing_without_the_gaps(tmp_path: Path) -> None:
    _touch(tmp_path, LOG_FILENAME, f"{LOG_FILENAME}.1", f"{LOG_FILENAME}.3")

    assert segments(tmp_path, archives=True) == segment_listing(tmp_path, archives=True).segments
    assert segments(tmp_path, archives=False) == (tmp_path / LOG_FILENAME,)


def test_the_archive_written_before_the_policy_is_listed_as_position_one(
    tmp_path: Path,
) -> None:
    _touch(tmp_path, f"{LOG_FILENAME}.1", LOG_FILENAME)

    listing = segment_listing(tmp_path, archives=True)

    assert [p.name for p in listing.segments] == [f"{LOG_FILENAME}.1", LOG_FILENAME]


# -- raw reads: what a segment stores ----------------------------------------------


def test_a_raw_read_keeps_the_stored_text_and_the_row_unchanged(tmp_path: Path) -> None:
    legacy = (
        '{"timestamp":"2026-09-01T00:00:00+00:00","event_type":"agent_stop",'
        '"start_correlation":"unobserved-agent","session_id":"s","extra":1}'
    )
    path = _segment(tmp_path, f"{legacy}\n".encode())

    raw = read_raw_segment(path)
    shaped = read_segment(path)

    assert raw.entries == ((legacy, json.loads(legacy)),)
    assert shaped.rows != (json.loads(legacy),)  # the shared view upcasts; the raw one does not


def test_a_raw_read_strips_the_newline_and_keeps_a_last_line_without_one(
    tmp_path: Path,
) -> None:
    path = _segment(tmp_path, b'{"a": 1}\n\n{"b": 2}')

    raw = read_raw_segment(path)

    assert [text for text, _ in raw.entries] == ['{"a": 1}', '{"b": 2}']


def test_a_raw_read_reports_malformed_lines_as_the_shared_read_does(tmp_path: Path) -> None:
    path = _segment(tmp_path, b'{"a": 1}\nnot-json\n\n[1, 2]\n{"b": 2}\n')

    raw = read_raw_segment(path)

    assert raw.malformed_lines == read_segment(path).malformed_lines == (2, 4)
    assert [row for _, row in raw.entries] == [{"a": 1}, {"b": 2}]
    assert raw.error is None


def test_a_raw_read_of_a_missing_segment_names_the_reason(tmp_path: Path) -> None:
    raw = read_raw_segment(tmp_path / "absent.jsonl")

    assert (raw.entries, raw.malformed_lines, raw.error) == ((), (), "missing")


def test_a_raw_read_of_an_unreadable_segment_names_the_reason(tmp_path: Path) -> None:
    raw = read_raw_segment(tmp_path)

    assert raw.error.startswith("unreadable:")
    assert (raw.entries, raw.malformed_lines) == ((), ())


# -- row identity ------------------------------------------------------------------


def test_identity_ignores_key_order() -> None:
    assert row_identity({"a": 1, "b": [1, 2]}) == row_identity({"b": [1, 2], "a": 1})


@pytest.mark.parametrize(
    "other",
    [{"a": 2, "b": 1}, {"a": 1}, {"a": 1, "b": 1, "c": 1}, {"a": "1", "b": 1}, {"a": 1, "b": True}],
)
def test_identity_changes_with_any_field(other: dict) -> None:
    assert row_identity({"a": 1, "b": 1}) != row_identity(other)


def test_identity_is_a_128_bit_hex_digest() -> None:
    identity = row_identity({"a": 1})

    assert len(identity) == 32
    assert int(identity, 16) >= 0


def test_identity_is_stable_for_non_ascii_text() -> None:
    row = {"summary": "café ☃"}

    assert row_identity(row) == row_identity(json.loads(json.dumps(row)))


# -- row time ----------------------------------------------------------------------

_NOON = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-20T12:00:00Z",
        "2026-09-20T12:00:00+00:00",
        "2026-09-20T14:00:00+02:00",
        "2026-09-20T12:00:00",
    ],
)
def test_row_time_reads_zulu_offset_and_naive_stamps_as_one_instant(stamp: str) -> None:
    assert row_time({"timestamp": stamp}) == _NOON


def test_row_time_is_aware() -> None:
    assert row_time({"timestamp": "2026-09-20T12:00:00"}).utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"timestamp": None},
        {"timestamp": 1_790_000_000},
        {"timestamp": ""},
        {"timestamp": "soon"},
    ],
)
def test_a_row_with_no_readable_time_is_untimed(row: dict) -> None:
    assert row_time(row) == UNTIMED


def test_untimed_rows_sort_after_dated_rows_in_their_original_order() -> None:
    rows = [
        {"id": "u1"},
        {"id": "late", "timestamp": "2026-09-21T00:00:00Z"},
        {"id": "u2", "timestamp": "garbage"},
        {"id": "early", "timestamp": "2026-09-19T00:00:00+00:00"},
        {"id": "tie-a", "timestamp": "2026-09-20T00:00:00"},
        {"id": "tie-b", "timestamp": "2026-09-20T00:00:00Z"},
    ]

    ordered = [row["id"] for row in sorted(rows, key=row_time)]

    assert ordered == ["early", "tie-a", "tie-b", "late", "u1", "u2"]
