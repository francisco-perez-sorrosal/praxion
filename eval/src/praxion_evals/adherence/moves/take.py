"""Prove from a session's own record that its arm took, so the session may be scored.

What each arm owes the record at session start, judged over the lines of the moved rule's body:

- ``full``: every line of the rule (today's delivery);
- ``lean``: every line of the rule's resident kernel and not the whole rule; the lines the
  kernel does not keep are owed at the point of use, and a session they never reached is still
  scored, as a trigger failure (the move's risk, not a fault of the arm);
- ``floor``: no line of the rule.

Anything else is refused with the reason, and so is a record that cannot be read or a rule that
cannot be found: a take that cannot be proven is never scored. No session is asked to echo
anything; the proof reads the record alone (via ``session_record``, its only reader).

``prove`` takes no checkout in the declaration's terms, so the rule's text is read from the
checkout this package is installed from unless the caller names another.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from praxion_evals.adherence.moves import session_record
from praxion_evals.adherence.moves.model import KernelDerive, MoveArm, MoveDeclaration, Take
from praxion_evals.adherence.moves.session_record import Arrival, Parsed

CHECKOUT_ROOT = Path(__file__).resolve().parents[5]  # the checkout whose rule a session was given
CODE_FENCE = "```"
HEADING = "#"
_FRONTMATTER_FENCE = "---"
QUOTED_LINES = 1  # how many missing or carried lines a refusal quotes


class _RefusalError(Exception):
    """A take that cannot be proven; the message is the reason scoring is refused."""


@dataclass(frozen=True)
class _Rule:
    """The moved rule's prose lines, and the ones its lean kernel keeps resident."""

    lines: tuple[str, ...]
    kernel: tuple[str, ...]

    @property
    def beyond_kernel(self) -> tuple[str, ...]:
        return tuple(line for line in self.lines if line not in self.kernel)


def prove(
    declaration: MoveDeclaration,
    arm: MoveArm,
    record_path: Path,
    checkout: Path = CHECKOUT_ROOT,
) -> Take:
    """Whether the session recorded at ``record_path`` was given what ``arm`` owes it."""
    try:
        rule = _read_rule(declaration, checkout)
        start, later = _arrived_lines(_read_record(record_path))
        match arm:
            case "full":
                _require_whole(rule, start)
            case "lean":
                _require_kernel_only(rule, start)
                return Take.taken(trigger_failure=bool(_absent(rule.beyond_kernel, later)))
            case "floor":
                _require_none(rule, start)
            case _:
                assert_never(arm)
    except _RefusalError as refusal:
        return Take.refused(str(refusal))
    return Take.taken()


# -- What an arm owes the start of the session ------------------------------------------------


def _require_whole(rule: _Rule, start: Collection[str]) -> None:
    missing = _absent(rule.lines, start)
    if missing:
        raise _RefusalError(
            f"a full session lacks the moved rule at session start ({len(missing)} of"
            f" {len(rule.lines)} lines missing, e.g. {_quote(missing)})"
        )


def _require_kernel_only(rule: _Rule, start: Collection[str]) -> None:
    missing = _absent(rule.kernel, start)
    if missing:
        raise _RefusalError(
            f"a lean session lacks the resident kernel at session start ({len(missing)} of"
            f" {len(rule.kernel)} lines missing, e.g. {_quote(missing)})"
        )
    if not _absent(rule.lines, start):
        raise _RefusalError("a lean session carries the whole moved rule at session start")


def _require_none(rule: _Rule, start: Collection[str]) -> None:
    carried = tuple(line for line in rule.lines if line in start)
    if carried:
        raise _RefusalError(
            f"a floor session carries {len(carried)} of {len(rule.lines)} lines of the moved rule"
            f" at session start, e.g. {_quote(carried)}"
        )


def _absent(owed: tuple[str, ...], arrived: Collection[str]) -> tuple[str, ...]:
    return tuple(line for line in owed if line not in arrived)


def _quote(lines: tuple[str, ...]) -> str:
    return ", ".join(repr(line) for line in lines[:QUOTED_LINES])


# -- Reading the rule and the record ----------------------------------------------------------


def _read_rule(declaration: MoveDeclaration, checkout: Path) -> _Rule:
    path = checkout / declaration.moved_rule.value
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise _RefusalError(f"the moved rule at {path} cannot be read: {error}") from error
    body = [line.rstrip() for line in _without_frontmatter(text).splitlines()]
    prefixes = tuple(
        prefix
        for change in declaration.arms.for_arm("lean")
        if isinstance(change, KernelDerive)
        for prefix in change.prefixes
    )
    prose = tuple(line.strip() for line in body if _is_prose(line))
    kernel = tuple(line.strip() for line in body if _is_prose(line) and line.startswith(prefixes))
    return _Rule(prose, kernel)


def _without_frontmatter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return text
    for end, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONTMATTER_FENCE:
            return "".join(lines[end + 1 :])
    return text


def _is_prose(line: str) -> bool:
    """A line that says something: not blank, a heading, a code fence or a table rule."""
    stripped = line.strip()
    return (
        any(char.isalnum() for char in stripped)
        and not stripped.startswith(HEADING)
        and not stripped.startswith(CODE_FENCE)
    )


def _read_record(record_path: Path) -> Parsed:
    events = session_record.parse(record_path)
    if isinstance(events, session_record.Unreadable):
        raise _RefusalError(events.reason)
    return events


def _arrived_lines(events: Parsed) -> tuple[frozenset[str], frozenset[str]]:
    """The lines that arrived at session start, and the lines that arrived later."""
    arrivals = events.arrivals
    return (
        _lines_of(a for a in arrivals if a.at_session_start),
        _lines_of(a for a in arrivals if not a.at_session_start),
    )


def _lines_of(arrivals: Iterable[Arrival]) -> frozenset[str]:
    return frozenset(
        line.strip() for arrival in arrivals for line in arrival.text.splitlines() if line.strip()
    )
