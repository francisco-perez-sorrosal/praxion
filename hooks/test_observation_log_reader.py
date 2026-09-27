"""`read_segment` streams one segment file and never raises.

A line is what text-mode file iteration yields: only a newline ends a JSONL
record, so a JSON-valid row whose string carries a raw Unicode line
separator is one row. A missing or unreadable file names its reason with no
rows; a line that is not a JSON object is reported by its 1-based physical
line number and never costs the rest of the segment.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hooks._observation_log.reader import read_segment


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
