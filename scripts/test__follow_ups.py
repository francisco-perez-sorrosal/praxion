"""Tests for `_follow_ups.py` -- the one grammar of the follow-up record.

The failure mode this closes: a follow-up the record cannot show in a final
state passing as done. Every shape the grammar cannot read must come back
`Unreadable`, and `Unreadable` must count as open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _follow_ups as fu  # noqa: E402

SHA = "a1b2c3d"
LONG_SHA = "0123456789abcdef0123456789abcdef01234567"


def only_item(line: str) -> fu.Item:
    (item,) = fu.parse_record(line)
    return item


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("- [open] wire the flag", fu.Open("wire the flag")),
        (f"- [fixed {SHA}] wire the flag", fu.Fixed(SHA, "wire the flag")),
        (f"- [fixed {LONG_SHA}] wire the flag", fu.Fixed(LONG_SHA, "wire the flag")),
        ("- [ledgered td-123] wire the flag", fu.Ledgered("td-123", "wire the flag")),
        ("- [ledgered td-1234] wire the flag", fu.Ledgered("td-1234", "wire the flag")),
        (
            "- [dropped superseded by the rewrite] wire the flag",
            fu.Dropped("superseded by the rewrite", "wire the flag"),
        ),
    ],
)
def test_each_state_parses_to_its_own_value(line, expected):
    assert only_item(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "- [later] wire the flag",
        "- [fixed] wire the flag",
        "- [ledgered] wire the flag",
        "- [dropped] wire the flag",
        "- [dropped ] wire the flag",
        "- [fixed soon] wire the flag",
        "- [fixed abc123] wire the flag",
        f"- [fixed {SHA}0123456789abcdef0123456789abcdef01234567] wire the flag",
        "- [fixed A1B2C3D] wire the flag",
        "- [ledgered row-seven] wire the flag",
        "- [ledgered td-12] wire the flag",
        "- [open now] wire the flag",
        "- [OPEN] wire the flag",
        "- [open]",
        "- [open]   ",
        "- open wire the flag",
        "- ",
        "- - ",
    ],
)
def test_a_line_the_grammar_cannot_read_is_unreadable_and_open(line):
    item = only_item(line)

    assert item == fu.Unreadable(line.strip())
    assert item.description == line.strip()
    assert fu.is_open(item)


def test_indentation_is_allowed_and_dropped_from_an_unreadable_line():
    assert only_item(f"    - [fixed {SHA}] wire the flag") == fu.Fixed(SHA, "wire the flag")
    assert only_item("\t- [later] x") == fu.Unreadable("- [later] x")


def test_lines_that_do_not_start_with_a_dash_and_blank_are_not_items():
    text = "\n".join(
        [
            "# Follow-ups",
            "",
            "Things still owed by this task.",
            "<!-- - [open] inside a comment is still prefixed by the comment opener -->",
            "-[open] no blank after the dash",
            "* [open] a different bullet",
            "- [open] the only item",
        ]
    )

    assert fu.parse_record(text) == (fu.Open("the only item"),)


def test_items_keep_document_order_and_each_description():
    text = f"- [open] one\n- [dropped moot] two\n- [fixed {SHA}] three\n"

    assert [item.description for item in fu.parse_record(text)] == ["one", "two", "three"]


def test_a_text_with_no_item_has_no_items():
    assert fu.parse_record("") == ()
    assert fu.open_items("# Follow-ups\n\nNothing owed.\n") == ()


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (fu.Open("a"), True),
        (fu.Unreadable("- [later] a"), True),
        (fu.Fixed(SHA, "a"), False),
        (fu.Ledgered("td-123", "a"), False),
        (fu.Dropped("moot", "a"), False),
    ],
)
def test_open_and_unreadable_are_open_and_the_other_three_are_final(item, expected):
    assert fu.is_open(item) is expected


def test_is_open_refuses_a_value_that_is_no_item():
    with pytest.raises(TypeError):
        fu.is_open("- [open] a string, not an item")  # type: ignore[arg-type]


def test_open_items_returns_only_what_is_still_owed_in_order():
    text = "\n".join(
        [
            "- [open] first",
            f"- [fixed {SHA}] done",
            "- [later] damaged",
            "- [ledgered td-123] filed",
            "- [dropped moot] gone",
            "- [open] last",
        ]
    )

    assert fu.open_items(text) == (
        fu.Open("first"),
        fu.Unreadable("- [later] damaged"),
        fu.Open("last"),
    )


def test_items_are_frozen():
    item = fu.Open("a")

    with pytest.raises(AttributeError):
        item.description = "b"  # type: ignore[misc]
