"""The follow-up record: what a task still owes, and the state each debt is in.

`parse_record` reads the record's text into one frozen value per item line. The
readers are pure -- text in, values out, no file opened, no command run -- so
every consumer of the record shares one grammar for it. The module checks
nothing against git or the ledger: whether a sha names a real commit, or a
`td-NNN` row exists, is the verifier's judgment.

Normative grammar. An item line is any line whose first non-blank characters are
`- `. The well-formed shape is:

    - [<state>] <description>

  - `<state>` is one of:
      open               the only state an item leaves
      fixed <sha>        `<sha>` is 7 to 40 lowercase hex digits
      ledgered td-NNN    `td-` then 3 or more ASCII digits
      dropped <reason>   `<reason>` is non-empty and holds no `]`
  - `<description>` is the rest of the line after the `]` and at least one
    blank, trimmed, and is non-empty.
  - `open`, `fixed`, `ledgered` and `dropped` are matched exactly, in lowercase.
  - Every other line (the title, prose, blank lines, comments) is no item.
  - An item line that does not fit the shape above is `Unreadable`: an unknown
    state word, an empty description, a `fixed` with no sha or a non-sha, a
    `ledgered` with no `td-NNN` or something else, a `dropped` with no reason.

Open is the safe default: `Open` and `Unreadable` are open and the other three
are final, so a damaged item can never pass as done. `Unreadable` carries the
line (without its indentation and trailing blanks) as its description, so a
reader can show the owner what to repair.

The five item types are the closed state set and `parse_record` is their only
constructor; nothing outside the tests builds one by hand.

Stdlib-only and Python 3.9-safe (no runtime `X | Y` unions, no `match`): managed
projects run the consumers from `~/.local/bin` under a bare `python3`. Tests:
`scripts/test__follow_ups.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union

# --- the record's value types ---------------------------------------------------------------


@dataclass(frozen=True)
class Open:
    description: str


@dataclass(frozen=True)
class Fixed:
    sha: str
    description: str


@dataclass(frozen=True)
class Ledgered:
    row: str
    description: str


@dataclass(frozen=True)
class Dropped:
    reason: str
    description: str


@dataclass(frozen=True)
class Unreadable:
    raw: str

    @property
    def description(self) -> str:
        return self.raw


Item = Union[Open, Fixed, Ledgered, Dropped, Unreadable]  # noqa: UP007 -- runtime value, 3.9 floor

# --- the line grammar -----------------------------------------------------------------------

ITEM_PREFIX = "- "
_ITEM = re.compile(r"- \[(?P<state>[^\]]*)\]\s+(?P<description>\S.*)")
_SHA = re.compile(r"[0-9a-f]{7,40}")
_LEDGER_ROW = re.compile(r"td-[0-9]{3,}")


def parse_record(text: str) -> tuple[Item, ...]:
    """One item per item line of `text`, in document order."""
    lines = (line.lstrip() for line in text.splitlines())
    return tuple(_read_item(line.rstrip()) for line in lines if line.startswith(ITEM_PREFIX))


def open_items(text: str) -> tuple[Item, ...]:
    """The items of `text` that are still owed, in document order."""
    return tuple(item for item in parse_record(text) if is_open(item))


def is_open(item: Item) -> bool:
    if isinstance(item, (Open, Unreadable)):
        return True
    if isinstance(item, (Fixed, Ledgered, Dropped)):
        return False
    raise TypeError(f"not a follow-up item: {item!r}")


def _read_item(line: str) -> Item:
    shape = _ITEM.fullmatch(line)
    item = _read_state(shape["state"], shape["description"]) if shape else None
    return item if item is not None else Unreadable(line)


def _read_state(state: str, description: str) -> Optional[Item]:  # noqa: UP045 -- 3.9 floor
    if state == "open":
        return Open(description)
    word, _, argument = state.partition(" ")
    if word == "fixed" and _SHA.fullmatch(argument):
        return Fixed(argument, description)
    if word == "ledgered" and _LEDGER_ROW.fullmatch(argument):
        return Ledgered(argument, description)
    if word == "dropped" and argument.strip():
        return Dropped(argument.strip(), description)
    return None
