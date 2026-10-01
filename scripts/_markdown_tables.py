"""Markdown reading layer: sections, code and tables, with no idea what a table means.

Private sibling of `_footprint_grammar.py`; stdlib-only and Python 3.9-safe, like
every module the footprint check loads. It answers three questions about a
document and nothing else: which lines are code, where a heading's section
begins and ends, and which runs of pipe rows are tables.

Code is never read. A line is code when it sits in a fenced block (delimiters
included) or in an indented block. A closing fence is the same character as its
opener and at least as long, so an outer fence encloses an inner one; an
unclosed fence runs to the end of the document. A line indented four columns is
indented code only after a blank line or other code (it cannot interrupt a
paragraph) and outside a list item, which is recognised by its marker.

Line numbers count the document as written: an HTML comment is blanked, and keeps
its line breaks.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_HEADING = re.compile(r"(#{1,6})\s+(.+?)\s*$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_LIST_ITEM = re.compile(r"\s*([-*+]|[0-9]+[.)])\s")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")
_BYTE_ORDER_MARK = "﻿"
_TAB_WIDTH = 4
_INDENTED_CODE_WIDTH = 4


class Table(NamedTuple):
    header: tuple[str, ...]  # lowercase, trimmed
    rows: tuple[tuple[str, ...], ...]  # trimmed cells, `\|` unescaped


class Block(NamedTuple):
    """A run of consecutive pipe-row lines outside any code."""

    start: int  # index of the first line in the document
    lines: tuple[str, ...]


class _Fence(NamedTuple):
    char: str
    length: int


def split_lines(text: str) -> list[str]:
    """The document's lines, without a byte-order mark and with comments blanked."""
    return _HTML_COMMENT.sub(_blank_keeping_breaks, text.lstrip(_BYTE_ORDER_MARK)).splitlines()


def _blank_keeping_breaks(comment: re.Match[str]) -> str:
    return "\n" * comment.group().count("\n")


def has_content(lines: list[str]) -> bool:
    """True when some line is neither blank nor a heading."""
    return any(line.strip() and not _HEADING.fullmatch(line.strip()) for line in lines)


def code_mask(lines: list[str]) -> list[bool]:
    """True for every line that is code: fenced (delimiters included) or indented."""
    flags: list[bool] = []
    fence: _Fence | None = None
    previous = "blank"  # blank | code | text
    in_list = False
    for line in lines:
        if fence is not None:
            flags.append(True)
            fence = None if _closes(line, fence) else fence
            previous = "blank"
            continue
        opened = _opens(line)
        if opened is not None:
            flags.append(True)
            fence, previous = opened, "blank"
            continue
        blank = not line.strip()
        indented = _indent(line) >= _INDENTED_CODE_WIDTH
        is_code = indented and not blank and not in_list and previous != "text"
        if not blank and not is_code:
            continues = in_list and (previous != "blank" or indented)
            in_list = _LIST_ITEM.match(line) is not None or continues
        flags.append(is_code)
        previous = "blank" if blank else "code" if is_code else "text"
    return flags


def _opens(line: str) -> _Fence | None:
    match = _FENCE.match(line)
    if match is None:
        return None
    marks, info = match.groups()
    if marks[0] == "`" and "`" in info:  # ```x``` on one line is inline code
        return None
    return _Fence(marks[0], len(marks))


def _closes(line: str, fence: _Fence) -> bool:
    match = _FENCE.match(line)
    if match is None:
        return False
    marks, rest = match.groups()
    return marks[0] == fence.char and len(marks) >= fence.length and not rest.strip()


def _indent(line: str) -> int:
    expanded = line.expandtabs(_TAB_WIDTH)
    return len(expanded) - len(expanded.lstrip(" "))


def find_section(
    lines: list[str], level: int, title: str, lo: int = 0, hi: int | None = None
) -> tuple[int, int] | None:
    """The body span of the heading `title` at `level`: up to the next heading of that level or higher."""
    end = len(lines) if hi is None else hi
    code = code_mask(lines)
    wanted = title.strip().lower()
    start = None
    for index in range(lo, end):
        heading = None if code[index] else _HEADING.fullmatch(lines[index].strip())
        if heading is None:
            continue
        depth = len(heading.group(1))
        if start is not None and depth <= level:
            return start, index
        if start is None and depth == level and heading.group(2).strip().lower() == wanted:
            start = index + 1
    return None if start is None else (start, end)


def subsection(
    lines: list[str], parent: tuple[int, int] | None, title: str
) -> tuple[int, int] | None:
    """The `###` section `title` inside the span `parent`, if both exist."""
    return None if parent is None else find_section(lines, 3, title, *parent)


def slice_lines(lines: list[str], span: tuple[int, int] | None) -> list[str] | None:
    return None if span is None else lines[span[0] : span[1]]


def blocks(lines: list[str]) -> list[Block]:
    """Every run of consecutive pipe-row lines outside code."""
    found: list[Block] = []
    run: list[str] = []
    start = 0
    code = code_mask(lines)
    for index, line in enumerate(lines):
        if not code[index] and line.lstrip().startswith("|"):
            start = start if run else index
            run.append(line)
        elif run:
            found.append(Block(start, tuple(run)))
            run = []
    if run:
        found.append(Block(start, tuple(run)))
    return found


def as_table(block: Block) -> Table | None:
    """A block is a table when its second line is a separator row."""
    if len(block.lines) < 2 or not _is_separator(block.lines[1]):
        return None
    header = tuple(cell.lower() for cell in cells(block.lines[0]))
    return Table(header, tuple(cells(row) for row in block.lines[2:]))


def table_and_strays(lines: list[str]) -> tuple[Table | None, list[Block]]:
    """The first table outside code, and every other run of pipe rows (never silently dropped)."""
    table: Table | None = None
    strays: list[Block] = []
    for block in blocks(lines):
        candidate = None if table is not None else as_table(block)
        if candidate is not None:
            table = candidate
        else:
            strays.append(block)
    return table, strays


def stray_messages(strays: list[Block]) -> list[str]:
    return [
        f"{len(block.lines)} pipe-row line(s) outside the one table read, "
        f"starting {block.lines[0].strip()[:60]!r}"
        for block in strays
    ]


def _is_separator(line: str) -> bool:
    return line.lstrip().startswith("|") and all(_SEPARATOR_CELL.fullmatch(c) for c in cells(line))


def cells(line: str) -> tuple[str, ...]:
    """The trimmed cells of a pipe row, a `\\|` read as a literal pipe."""
    body = line.strip()[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return tuple(cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT.split(body))
