"""Plan the process text a hook delivers only to managed projects, as labelled parts.

Pure by construction: bodies, scope, event and agent kind come in as arguments
and the plan comes out as a tuple, with no file, environment or clock read.
Every slot process of the injector recomputes the same plan from the same
inputs and prints only its own entry, so no process needs to know about the
others and the order in which Claude Code runs them does not matter: each part
names its unit and its place (``part k of n``) in its first line.

Stdlib-only, like the hook modules that import it.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum

from _project_scope import Managed, ProjectScope

# Claude Code truncates a hook's additionalContext past this many characters.
MAX_PART_CHARS = 10_000

# The injector's header, specialised per part: "<prefix>: <unit>, part k of n".
LABEL_PREFIX = "## Praxion Rules (auto-injected)"

# A label never carries more digits than this in a position, so the room
# reserved for it is an upper bound for every real label.
_WIDEST_PLACE = 10**6


@dataclass(frozen=True)
class CoreUnit:
    """A managed-only unit no project blacklist can switch off."""

    unit_id: str
    path: str
    order: int


# Delivery order is the order field: the protocol first, then the rules that
# refer back to it. A test holds this table equal to the rules' frontmatter.
MANAGED_CORE_UNITS = (
    CoreUnit(
        "swe/swe-agent-coordination-protocol", "rules/swe/swe-agent-coordination-protocol.md", 1
    ),
    CoreUnit("swe/agent-intermediate-documents", "rules/swe/agent-intermediate-documents.md", 2),
    CoreUnit("swe/adr-conventions-resident", "rules/swe/adr-conventions-resident.md", 3),
)
_CORE_ORDER = {unit.unit_id: unit.order for unit in MANAGED_CORE_UNITS}


class Event(Enum):
    SESSION = "session"
    SUBAGENT = "subagent"


class AgentKind(Enum):
    INHERITING = "inheriting"  # loads the full instruction hierarchy
    LEAN = "lean"  # definition sets omitClaudeMd
    NO_INSTRUCTION_FILES = "no-instruction-files"  # Explore, Plan


_NO_INSTRUCTION_FILE_AGENTS = frozenset({"Explore", "Plan"})


@dataclass(frozen=True)
class DeliveryPart:
    """One printable slice of a unit: ``text`` opens with its own label line."""

    unit_id: str
    index: int  # 1-based position within the unit
    total: int
    text: str

    def __post_init__(self):
        if not 1 <= self.index <= self.total:
            raise ValueError(f"part {self.index} of {self.total} is outside its unit")
        if len(self.text) > MAX_PART_CHARS:
            raise ValueError(
                f"part of {len(self.text)} characters passes the {MAX_PART_CHARS} ceiling"
            )


@dataclass(frozen=True)
class Delivery:
    """What a session receives: an optional notice, then the planned parts of ``units``."""

    notice: str | None
    units: Mapping[str, str]
    parts: tuple[DeliveryPart, ...]

    def unit_ids(self) -> list[str]:
        return list(dict.fromkeys(part.unit_id for part in self.parts))

    def slot_texts(self) -> tuple[str, ...]:
        """One string per slot: the notice first, so a reader of the first line sees it."""
        return (*([self.notice] if self.notice else []), *(part.text for part in self.parts))

    def whole_text(self) -> str:
        """Every planned unit under one unlabelled header, as one string; empty for nothing."""
        bodies = [self.units[unit_id] for unit_id in self.unit_ids()]
        rules = f"{LABEL_PREFIX}\n\n" + "\n\n".join(bodies) if bodies else ""
        return "\n\n".join(text for text in (self.notice, rules) if text)


def parse_agent_kind(agent_type: str | None, omit_claude_md: bool | None) -> AgentKind:
    """The kind of a spawn, from its type and its definition's ``omitClaudeMd``.

    ``omit_claude_md`` is None when the definition could not be read; the safe
    direction is delivery, so that parses as `AgentKind.INHERITING`.
    """
    if agent_type in _NO_INSTRUCTION_FILE_AGENTS:
        return AgentKind.NO_INSTRUCTION_FILES
    if omit_claude_md is True:
        return AgentKind.LEAN
    return AgentKind.INHERITING


def plan_delivery(
    units: Mapping[str, str],
    managed_only: Collection[str],
    scope: ProjectScope,
    event: Event,
    agent: AgentKind,
    disable_set: Collection[str],
    natively_installed: Collection[str],
) -> tuple[DeliveryPart, ...]:
    """The parts to print, in delivery order, for one hook event.

    ``units`` maps a unit id to its file body (frontmatter already removed), in
    the order the manifest lists them; a unit that is empty is left out.
    ``managed_only`` names the units that reach only a managed scope. A unit
    still installed natively is skipped so nothing arrives twice. The disable
    set drops any unit but the core ones. ``agent`` matters only for a spawn.
    """
    parts: list[DeliveryPart] = []
    for unit_id in _wanted_ids(units, managed_only, scope, event, agent):
        if unit_id in natively_installed:
            continue
        if unit_id in disable_set and unit_id not in _CORE_ORDER:
            continue
        parts.extend(split_unit(unit_id, units[unit_id]))
    return tuple(parts)


def _wanted_ids(
    units: Mapping[str, str],
    managed_only: Collection[str],
    scope: ProjectScope,
    event: Event,
    agent: AgentKind,
) -> list[str]:
    """Every-scope units first, then the managed-only ones, the core units last in
    their own order; a stable sort keeps the manifest order within each group."""
    ordered = sorted(
        units, key=lambda unit_id: (unit_id in managed_only, _CORE_ORDER.get(unit_id, 0))
    )
    managed = isinstance(scope, Managed)
    if event is Event.SESSION:
        return [unit_id for unit_id in ordered if managed or unit_id not in managed_only]
    # A spawn inherits only the managed core units, never the session's other text.
    if managed and agent is AgentKind.INHERITING:
        return [
            unit_id for unit_id in ordered if unit_id in managed_only and unit_id in _CORE_ORDER
        ]
    return []


def split_unit(unit_id: str, body: str) -> tuple[DeliveryPart, ...]:
    """The labelled parts of one unit; their chunks, joined, are exactly ``body``."""
    if not body:
        return ()
    chunks = _chunks(body, chunk_budget(unit_id))
    return tuple(
        DeliveryPart(unit_id, number, len(chunks), _label(unit_id, number, len(chunks)) + chunk)
        for number, chunk in enumerate(chunks, start=1)
    )


def chunk_budget(unit_id: str) -> int:
    """How many body characters a part of this unit can carry beside its label."""
    return MAX_PART_CHARS - len(_label(unit_id, _WIDEST_PLACE, _WIDEST_PLACE))


def _label(unit_id: str, number: int, total: int) -> str:
    return f"{LABEL_PREFIX}: {unit_id}, part {number} of {total}\n\n"


# -- Splitting: coarsest boundary that fits, finer ones only for an oversize piece ------

_HEADING = re.compile(r"#{2,3} ")
_FENCE = re.compile(r" {0,3}(```|~~~)")


def _chunks(text: str, budget: int, boundaries=None) -> list[str]:
    """Pack consecutive pieces up to ``budget``; the chunks always rebuild ``text``.

    Headings (``##``/``###``) are the boundary that matters; an oversize
    section falls back to paragraphs, then lines, then a plain cut, so that a
    rule that outgrows the ceiling still arrives whole instead of failing.
    """
    boundaries = _BOUNDARIES if boundaries is None else boundaries
    if len(text) <= budget:
        return [text]
    if not boundaries:
        return [text[i : i + budget] for i in range(0, len(text), budget)]
    pieces = boundaries[0](text)
    if len(pieces) == 1:
        return _chunks(text, budget, boundaries[1:])
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(current) + len(piece) <= budget:
            current += piece
            continue
        if current:
            chunks.append(current)
        current = ""
        if len(piece) <= budget:
            current = piece
        else:
            chunks.extend(_chunks(piece, budget, boundaries[1:]))
    if current:
        chunks.append(current)
    return chunks


def _lines(text: str) -> list[str]:
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def _by_headings(text: str) -> list[str]:
    """Pieces that each start at a ``##``/``###`` line outside a code fence."""
    starts = [0]
    fence = None
    offset = 0
    for line in _lines(text):
        marker = _FENCE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
        elif fence is None and _HEADING.match(line) and offset > 0:
            starts.append(offset)
        offset += len(line)
    return _cut_at(text, starts)


def _by_paragraphs(text: str) -> list[str]:
    """Pieces that each start at the first non-blank line after a blank one."""
    starts = [0]
    offset = 0
    after_blank = False
    for line in _lines(text):
        if after_blank and line.strip():
            starts.append(offset)
        after_blank = not line.strip()
        offset += len(line)
    return _cut_at(text, starts)


def _cut_at(text: str, starts: list[int]) -> list[str]:
    return [text[a:b] for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]


_BOUNDARIES = (_by_headings, _by_paragraphs, _lines)
