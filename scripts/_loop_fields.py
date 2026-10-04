"""The loop fields a plan step declares, and the check one of them carries.

A plan step may declare a completion check: the command that proves it, and
the counts the step's own recorded `Result:` line must show. This module owns
the grammar of that line and the judging of a check against a recorded result.
It reads text only and never runs a declared command.

Normative grammar of the `Check:` line -- one logical line in the step block,
at column 0 or as a list item, the label optionally bold (`**Check**:` or
`**Check:**`). A line inside a code fence is never a `Check:` line.

    Check: `<command>` expects <key><op><count> [<key><op><count> ...]

with `<key>` one of `pass fail skip pending`, `<op>` one of `=` (exactly) or
`>=` (at least), and `<count>` a decimal integer. For example:

    **Check**: `uv run pytest tests/test_widget.py -q` expects pass>=4 fail=0 pending=2

`parse_check_field` enforces every invariant: `pass` and `fail` are both
present (a run of zero tests cannot meet a check); each key appears at most
once; the command is non-empty and holds no backtick; no unknown key and no
token trails the expectations. This is stricter than the `Result:` line on
purpose: a typo in a plan must read as unreadable, never as met. A step block
holding two `Check:` lines is unreadable ("declared twice").

Only the keys a check declares are judged. `pending` is read from the raw text
of the `Result:` line, because the shared result parser does not know that key;
absent means 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from _step_schema import Counts, split_step_blocks

# The one-line grammar the prose sites quote; the docstring above is normative.
CHECK_GRAMMAR_LINE = "Check: `<command>` expects <key><op><count> [<key><op><count> ...]"

CHECK_KEYS = ("pass", "fail", "skip", "pending")
_REQUIRED_KEYS = ("pass", "fail")

_CHECK_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+)?\*{0,2}Check\*{0,2}\s*:\s*\*{0,2}\s*(?P<value>.*)$")
_EXPECTS_RE = re.compile(r"^\s+expects(?:\s+(?P<rest>.*))?$")
_EXPECTATION_RE = re.compile(r"^(?P<key>[a-z]+)(?P<op>>=|=)(?P<count>[0-9]+)$")
_PENDING_TOKEN_RE = re.compile(r"(?:^|\s)pending=(?P<value>\S*)")
_CODE_FENCE_RE = re.compile(r"^[ \t]{0,3}(```|~~~)")


@dataclass(frozen=True)
class Expectation:
    """One `<key><op><count>` token; `op` is `=` or `>=`."""

    key: str
    op: str
    count: int


@dataclass(frozen=True)
class Check:
    """A readable check: the command and each expectation as distinct parts."""

    command: str
    expectations: tuple[Expectation, ...]


@dataclass(frozen=True)
class UnreadableCheck:
    """A `Check:` line that breaks the grammar, naming why and quoting the line."""

    reason: str
    line: str


CheckLine = Union[Check, UnreadableCheck]  # noqa: UP007 -- runtime value, 3.9 floor


class _UnreadableError(Exception):
    """A `Check:` line broke the grammar; the message is the reason."""


def parse_check_field(line: str) -> CheckLine | None:
    """One line -> a `Check`, an `UnreadableCheck`, or None when it is no `Check:` line."""
    match = _CHECK_LINE_RE.match(line)
    if match is None:
        return None
    try:
        command, rest = _split_command(match["value"].strip())
        return Check(command, _parse_expectations(rest))
    except _UnreadableError as unreadable:
        return UnreadableCheck(str(unreadable), line.strip())


def _split_command(value: str) -> tuple[str, str]:
    close = value.find("`", 1)
    if not value.startswith("`") or close == -1:
        raise _UnreadableError("the command must be wrapped in backticks")
    command = value[1:close].strip()
    if not command:
        raise _UnreadableError("the command is empty")
    after = value[close + 1 :]
    expects = _EXPECTS_RE.match(after)
    if expects is None:
        raise _UnreadableError(
            "the command contains a backtick" if "`" in after else "`expects` must follow it"
        )
    return command, expects["rest"] or ""


def _parse_expectations(rest: str) -> tuple[Expectation, ...]:
    seen: dict[str, Expectation] = {}
    for token in rest.split():
        match = _EXPECTATION_RE.match(token)
        if match is None:
            raise _UnreadableError(f"unreadable expectation: {token!r}")
        key = match["key"]
        if key not in CHECK_KEYS:
            raise _UnreadableError(f"unknown key: {key}")
        if key in seen:
            raise _UnreadableError(f"key declared twice: {key}")
        seen[key] = Expectation(key, match["op"], int(match["count"]))
    missing = [key for key in _REQUIRED_KEYS if key not in seen]
    if missing:
        raise _UnreadableError(f"missing required key(s): {', '.join(missing)}")
    return tuple(seen.values())


def parse_step_checks(plan_text: str) -> dict[str, CheckLine]:
    """Map each `"Step <id>"` that declares a check to it; a step with no line has no entry.

    Reads each step block of the plan outside code fences. A step holding two
    `Check:` lines reads as `UnreadableCheck("declared twice")`.
    """
    declared: dict[str, list[str]] = {}
    for block in split_step_blocks(plan_text):
        found = [line for line in _unfenced_lines(block.text) if _CHECK_LINE_RE.match(line)]
        if found and block.step is not None:
            declared.setdefault(block.step, []).extend(found)
    return {step: _read_declared(lines) for step, lines in declared.items()}


def _read_declared(lines: list[str]) -> CheckLine:
    if len(lines) > 1:
        return UnreadableCheck("declared twice", lines[0].strip())
    reading = parse_check_field(lines[0])
    assert reading is not None  # the line matched the label pattern
    return reading


def _unfenced_lines(text: str) -> list[str]:
    """The lines of `text` outside a ``` or ~~~ code fence (the fence lines excluded)."""
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = _CODE_FENCE_RE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
        elif fence is None:
            kept.append(line)
    return kept


@dataclass(frozen=True)
class UnmetExpectation:
    key: str
    op: str
    expected: int
    observed: int

    def render(self) -> str:
        return f"{self.key}=: expected {self.op}{self.expected}, observed {self.observed}"


@dataclass(frozen=True)
class Met:
    """Every declared expectation holds."""


@dataclass(frozen=True)
class Unmet:
    """At least one declared expectation fails; `unmet` lists each in declared order."""

    unmet: tuple[UnmetExpectation, ...]


@dataclass(frozen=True)
class NoResult:
    """No countable result speaks for the step; `reason` says why."""

    reason: str


CheckOutcome = Union[Met, Unmet, NoResult]  # noqa: UP007 -- runtime value, 3.9 floor


def evaluate_check(check: Check, step: str, test_results_text: str) -> CheckOutcome:
    """Judge `check` against the latest `Counts` line in `step`'s own results block.

    Only the step's own block counts: a result recorded for another step, a
    file-wide fallback, `Result: none`, a malformed line or no line at all is
    never `Met`.
    """
    label = step if step.startswith("Step") else f"Step {step}"
    latest = _latest_counts_line(label, test_results_text)
    if latest is None:
        return NoResult(f"no Result: recorded for {label}")
    counts, raw_line = latest
    observed = {
        "pass": counts.passed,
        "fail": counts.failed,
        "skip": counts.skipped,
        "pending": _observed_pending(raw_line),
    }
    unmet = []
    for item in check.expectations:
        value = observed[item.key]
        if value is None:
            return NoResult(f"pending= on the Result: line recorded for {label} is not a count")
        if not (value >= item.count if item.op == ">=" else value == item.count):
            unmet.append(UnmetExpectation(item.key, item.op, item.count, value))
    return Unmet(tuple(unmet)) if unmet else Met()


def _latest_counts_line(label: str, test_results_text: str) -> tuple[Counts, str] | None:
    """The step's own latest `Counts` line with its raw text, across all its blocks."""
    latest: tuple[int, Counts, str] | None = None
    for block in split_step_blocks(test_results_text):
        if block.step != label:
            continue
        lines = block.text.splitlines()
        for number, parsed in block.results:
            if isinstance(parsed, Counts) and (latest is None or number > latest[0]):
                latest = (number, parsed, lines[number - block.first_line])
    return None if latest is None else (latest[1], latest[2])


def _observed_pending(raw_line: str) -> int | None:
    """The `pending=` count on a raw `Result:` line: 0 when absent, None when unreadable."""
    values = [match["value"] for match in _PENDING_TOKEN_RE.finditer(raw_line)]
    if not values:
        return 0
    if len(values) > 1 or not (values[0].isascii() and values[0].isdigit()):
        return None
    return int(values[0])
