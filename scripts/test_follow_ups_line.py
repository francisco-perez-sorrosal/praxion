"""Tests for the `Follow-ups:` return line and its copy into the record (`scripts/_follow_ups.py`).

`return_items` reads the line out of an agent's final text; `append_open` writes each item as an
open line, creating the record only when something is written and never repeating an open line.
Self-contained for the mutation sensor: only `_follow_ups`, `pytest` and the standard library.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _follow_ups as fu  # noqa: E402

# --- return_items -------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [None, "", "Step done.\n[COMPLETE]", "Follow-ups:\n[COMPLETE]"])
def test_a_text_with_no_line_or_no_item_yields_no_items(text):
    assert fu.return_items(text) == ()


def test_the_items_of_the_line_come_back_in_order_stripped():
    text = "Step done.\nFollow-ups:  rename the helper ;drop the fixture \n[COMPLETE]"

    assert fu.return_items(text) == ("rename the helper", "drop the fixture")


def test_empty_items_are_dropped():
    assert fu.return_items("Follow-ups: ; a;; ;b;\n[COMPLETE]") == ("a", "b")


def test_the_last_line_that_starts_with_the_prefix_is_the_one_read():
    text = "Follow-ups: early\nmore prose\nFollow-ups: late one; late two\n[COMPLETE]"

    assert fu.return_items(text) == ("late one", "late two")


def test_a_line_that_only_mentions_the_prefix_is_no_line():
    assert fu.return_items("I wrote no Follow-ups: here\n[COMPLETE]") == ()


def test_an_indented_line_still_starts_with_the_prefix():
    assert fu.return_items("   Follow-ups: a; b\n[COMPLETE]") == ("a", "b")


def test_the_prefix_is_matched_by_its_exact_spelling():
    assert fu.return_items("follow-ups: a\nFollow-up: b\nFOLLOW-UPS: c\n[COMPLETE]") == ()


def test_the_line_is_read_whatever_the_marker_says():
    assert fu.return_items("Follow-ups: a\n[BLOCKED]") == ("a",)


@pytest.mark.parametrize("none", ["none", "None.", "NONE", "none.", "None"])
def test_an_item_that_says_only_none_is_no_item(none):
    assert fu.return_items(f"Follow-ups: {none}\n[COMPLETE]") == ()


def test_none_among_other_items_is_dropped_and_the_others_kept():
    assert fu.return_items("Follow-ups: none; a real one\n[COMPLETE]") == ("a real one",)


def test_an_item_that_only_starts_with_none_is_kept():
    assert fu.return_items("Follow-ups: none of the fixtures use it\n[COMPLETE]") == (
        "none of the fixtures use it",
    )


@pytest.mark.parametrize(
    "line",
    [
        "**Follow-ups:** a; b",
        "- Follow-ups: a; b",
        "- **Follow-ups:** a; b",
        "* Follow-ups: a; b",
        "  - Follow-ups:   a; b",
    ],
)
def test_an_emphasised_or_bulleted_line_is_the_same_line(line):
    assert fu.return_items(f"Done.\n{line}\n[COMPLETE]") == ("a", "b")


def test_a_bulleted_line_is_not_confused_with_prose_that_mentions_the_prefix():
    assert fu.return_items("- I wrote no Follow-ups: here\n[COMPLETE]") == ()


# --- append_open --------------------------------------------------------------------------------


def test_the_record_is_created_with_its_heading_and_the_items_in_order(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"

    fu.append_open(record, ("first", "second"))

    assert record.read_text(encoding="utf-8") == "# Follow-ups\n\n- [open] first\n- [open] second\n"


def test_the_record_the_writer_creates_reads_back_as_its_items(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"

    fu.append_open(record, ("first", "second"))

    assert fu.parse_record(record.read_text(encoding="utf-8")) == (
        fu.Open("first"),
        fu.Open("second"),
    )


def test_no_items_leave_an_absent_record_absent(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"

    fu.append_open(record, ())

    assert not record.exists()


def test_no_items_never_read_the_record(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_bytes(b"\xff\xfe not utf-8")

    fu.append_open(record, ())

    assert record.read_bytes() == b"\xff\xfe not utf-8"


def test_no_items_leave_a_present_record_byte_for_byte(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_bytes(b"# Follow-ups\n\n- [open] held")

    fu.append_open(record, ())

    assert record.read_bytes() == b"# Follow-ups\n\n- [open] held"


def test_what_the_record_held_stays_as_it_was_and_the_items_follow(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    held = "# Follow-ups — task\n\n- [fixed 4f3c2a1] done\n- [open] pending\n"
    record.write_text(held, encoding="utf-8")

    fu.append_open(record, ("new one",))

    assert record.read_text(encoding="utf-8") == held + "- [open] new one\n"


def test_a_record_with_no_final_newline_gets_one_before_the_first_item(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_text("# Follow-ups\n\n- [open] held", encoding="utf-8")

    fu.append_open(record, ("next",))

    assert record.read_text(encoding="utf-8") == "# Follow-ups\n\n- [open] held\n- [open] next\n"


def test_an_empty_record_file_takes_the_items_without_a_second_heading(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_text("", encoding="utf-8")

    fu.append_open(record, ("only",))

    assert record.read_text(encoding="utf-8") == "- [open] only\n"


def test_an_item_whose_open_line_is_already_there_is_skipped(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_text("# Follow-ups\n\n- [open] held\n", encoding="utf-8")

    fu.append_open(record, ("held", "fresh"))

    assert record.read_text(encoding="utf-8") == "# Follow-ups\n\n- [open] held\n- [open] fresh\n"


def test_items_that_are_all_present_leave_the_record_byte_for_byte(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_bytes(b"# Follow-ups\n\n- [open] held\n")

    fu.append_open(record, ("held",))

    assert record.read_bytes() == b"# Follow-ups\n\n- [open] held\n"


def test_the_same_item_twice_in_one_call_is_written_once(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"

    fu.append_open(record, ("twice", "twice"))

    assert record.read_text(encoding="utf-8") == "# Follow-ups\n\n- [open] twice\n"


def test_an_item_held_in_a_final_state_is_still_appended_as_open(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    record.write_text("# Follow-ups\n\n- [fixed 4f3c2a1] same words\n", encoding="utf-8")

    fu.append_open(record, ("same words",))

    assert fu.open_items(record.read_text(encoding="utf-8")) == (fu.Open("same words"),)


def test_writing_the_same_items_twice_equals_writing_them_once(tmp_path):
    record = tmp_path / "FOLLOW_UPS.md"
    fu.append_open(record, ("a", "b"))
    once = record.read_bytes()

    fu.append_open(record, ("a", "b"))

    assert record.read_bytes() == once
