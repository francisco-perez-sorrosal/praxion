"""Tests for `_markdown_tables.py` -- the reading layer under the footprint grammars.

The failure mode this closes: a table quoted as an example being read as the real
one, or a real table being skipped because the reader mistook it for code. Each
case names the exact lines it expects, so a reader that errs in either direction
is caught.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _markdown_tables as md  # noqa: E402

TABLE = "| a | b |\n|---|---|\n| 1 | 2 |"

# (label, lines, which lines are code)
CODE_CASES = [
    ("backtick fence", ["x", "```", "| a |", "```", "y"], [0, 1, 1, 1, 0]),
    ("tilde fence", ["~~~py", "z", "~~~", "y"], [1, 1, 1, 0]),
    ("fence indented three columns", ["   ```", "z", "   ```"], [1, 1, 1]),
    ("unclosed fence runs to the end", ["```", "a", "b"], [1, 1, 1]),
    (
        "outer fence encloses an inner one",
        ["````", "```", "| a |", "```", "````", "y"],
        [1, 1, 1, 1, 1, 0],
    ),
    ("a shorter fence does not close", ["````", "```", "a", "````", "y"], [1, 1, 1, 1, 0]),
    ("another character does not close", ["```", "~~~", "a", "```", "y"], [1, 1, 1, 1, 0]),
    ("a closing fence carries no info string", ["```", "```py", "a", "```", "y"], [1, 1, 1, 1, 0]),
    ("triple backticks on one line are inline code", ["```x```", "| a |"], [0, 0]),
    (
        "indented after a blank line",
        ["intro", "", "    | a |", "    | b |", "", "out"],
        [0, 0, 1, 1, 0, 0],
    ),
    ("tab-indented after a blank line", ["", "\t| a |"], [0, 1]),
    ("indented line continuing a paragraph", ["intro", "    | a |"], [0, 0]),
    ("indented block inside a list item", ["- item", "", "    | a |", "", "out"], [0, 0, 0, 0, 0]),
    (
        "indented block after the list ended",
        ["- item", "", "plain", "", "    | a |"],
        [0, 0, 0, 0, 1],
    ),
    ("three columns is not code", ["", "   | a |"], [0, 0]),
]


@pytest.mark.parametrize(("label", "lines", "code"), CODE_CASES, ids=[c[0] for c in CODE_CASES])
def test_code_mask_marks_fenced_and_indented_code(label, lines, code):
    assert md.code_mask(lines) == [bool(flag) for flag in code], label


def test_tables_inside_code_are_never_read_or_counted_as_strays():
    quoted = "```\n" + TABLE + "\n```\n\n    " + TABLE.replace("\n", "\n    ") + "\n"
    table, strays = md.table_and_strays(md.split_lines(quoted + "\n" + TABLE + "\n"))
    assert table == md.Table(("a", "b"), (("1", "2"),))
    assert strays == []


def test_first_table_is_read_and_every_other_pipe_run_is_a_stray():
    lines = md.split_lines(TABLE + "\n\n| x | y |\n\n" + TABLE + "\n")
    table, strays = md.table_and_strays(lines)
    assert table == md.Table(("a", "b"), (("1", "2"),))
    assert [block.lines[0] for block in strays] == ["| x | y |", "| a | b |"]
    assert [block.start for block in strays] == [4, 6]


def test_a_run_without_a_separator_row_is_not_a_table():
    assert md.as_table(md.Block(0, ("| a | b |", "| 1 | 2 |"))) is None
    assert md.as_table(md.Block(0, ("| a | b |",))) is None


def test_section_runs_to_the_next_heading_of_its_level_or_higher():
    lines = ["# T", "## A", "x", "### S", "y", "#### deep", "z", "### Next", "n", "## B", "b"]
    assert md.find_section(lines, 2, "A") == (2, 9)
    assert md.find_section(lines, 3, "s") == (4, 7)
    assert md.subsection(lines, md.find_section(lines, 2, "A"), "Next") == (8, 9)
    assert md.subsection(lines, None, "Next") is None
    assert md.find_section(lines, 2, "Missing") is None


def test_heading_inside_code_does_not_open_a_section():
    lines = ["## A", "```", "### S", "```", "    ### S", "", "### S", "body"]
    assert md.find_section(lines, 3, "S") == (7, 8)


def test_split_lines_blanks_comments_without_shifting_line_numbers():
    text = "﻿# T\n<!-- one -->\n<!--\n| a |\n-->\nlast\n"
    lines = md.split_lines(text)
    assert lines == ["# T", "", "", "", "", "last"]
    assert md.has_content(lines)
    assert not md.has_content(md.split_lines("# T\n\n<!-- x -->\n"))


def test_cells_trim_split_and_unescape_a_pipe():
    assert md.cells("| a | b\\|c | d |") == ("a", "b|c", "d")
    assert md.cells("| a | b \\|") == ("a", "b |")
    assert md.cells("|a|") == ("a",)
