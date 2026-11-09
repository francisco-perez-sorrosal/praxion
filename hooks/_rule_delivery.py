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

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from _project_scope import Managed, ProjectScope

# Claude Code truncates a hook's additionalContext past this many characters.
MAX_PART_CHARS = 10_000

# The injector's header, specialised per part: "<prefix>: <unit>, part k of n".
LABEL_PREFIX = "## Praxion Rules (auto-injected)"

# `<namespace>:<role>` names an agent of this plugin, defined in its `agents/<role>.md`.
PLUGIN_NAMESPACE = "praxion"

# The leading YAML block of a rule or agent definition; `rule_body` removes it.
FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# The spawn-split artifact's only schema; a hook reads any other as absent.
SPLIT_SCHEMA = 1
# Where the generator writes the spawn split and which file's bytes it digests, both relative
# to the plugin root; the hook reads the same two. `scripts/kernel_model.py` names the audience
# manifest on its own (`MANIFEST_PATH`, it imports no hook module): if you move it, move both;
# `scripts/test_kernel_spawn_split.py` holds them equal.
SPAWN_SPLIT_PATH = "claude/kernels/spawn_split.json"
AUDIENCE_MANIFEST_PATH = "rules/_audience.yaml"
_DIGEST = re.compile(r"[0-9a-f]{64}")

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
    # Both recipient kinds load the full instruction hierarchy and receive the core units.
    SPLIT_RECIPIENT = "split-recipient"  # a plugin role read from its definition: may get the split
    WHOLE_RECIPIENT = "whole-recipient"  # every other loader of the hierarchy: always whole
    LEAN = "lean"  # definition sets omitClaudeMd
    NO_INSTRUCTION_FILES = "no-instruction-files"  # Explore, Plan


_NO_INSTRUCTION_FILE_AGENTS = frozenset({"Explore", "Plan"})
_CORE_RECIPIENTS = frozenset({AgentKind.SPLIT_RECIPIENT, AgentKind.WHOLE_RECIPIENT})


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


def rule_body(raw: str) -> str:
    """A rule file's text without its leading frontmatter: the body the hook delivers and
    the generator digests, one definition so their digests agree."""
    return FRONTMATTER_RE.sub("", raw, count=1).lstrip("\n")


def parse_agent_kind(
    agent_type: str | None, omit_claude_md: bool | None, plugin_definition_read: bool
) -> AgentKind:
    """The kind of a spawn, from its type, its definition's ``omitClaudeMd`` and whether that
    definition was read from this plugin.

    The one place a spawn becomes a split recipient: a ``praxion:<role>`` type whose plugin
    definition was read and keeps the instruction files. Anything unread, absent or
    doubtful is a whole recipient, the safe direction.
    """
    if agent_type in _NO_INSTRUCTION_FILE_AGENTS:
        return AgentKind.NO_INSTRUCTION_FILES
    if omit_claude_md is True:
        return AgentKind.LEAN
    if plugin_definition_read and omit_claude_md is False and _is_plugin_role(agent_type):
        return AgentKind.SPLIT_RECIPIENT
    return AgentKind.WHOLE_RECIPIENT


def _is_plugin_role(agent_type: str | None) -> bool:
    prefix = f"{PLUGIN_NAMESPACE}:"
    return (
        agent_type is not None and agent_type.startswith(prefix) and len(agent_type) > len(prefix)
    )


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
    if managed and agent in _CORE_RECIPIENTS:
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


# -- The spawn split: a stored shorter text per unit, trusted one unit at a time ---------


@dataclass(frozen=True)
class SplitEntry:
    """One unit's stored split: ``text`` is ``source``'s body (digest ``whole_sha256``) with
    the spans a split recipient does not need removed."""

    source: str
    whole_sha256: str
    text: str
    text_sha256: str


@dataclass(frozen=True)
class SpawnSplit:
    """The parsed artifact: its entries, cut under the audience manifest of ``manifest_sha256``.
    Its one writer is the generator; the schema number is checked at parsing, not stored."""

    manifest_sha256: str
    units: Mapping[str, SplitEntry]


def parse_spawn_split(text: str) -> SpawnSplit | None:
    """The artifact's JSON as a `SpawnSplit`; None for anything that is not exactly the
    schema, so the interior never sees a partial table. A text that cannot be encoded as
    UTF-8 (a lone surrogate escape) is not the schema: no digest can be taken over it. Extra
    keys are ignored: a later writer may add them."""
    try:
        wire = json.loads(text)
    except ValueError:
        return None
    if not isinstance(wire, dict) or type(wire.get("schema")) is not int:
        return None
    if wire["schema"] != SPLIT_SCHEMA or not _is_digest(wire.get("manifest_sha256")):
        return None
    wire_units = wire.get("units")
    if not isinstance(wire_units, dict):
        return None
    entries: dict[str, SplitEntry] = {}
    for unit_id, wire_entry in wire_units.items():
        entry = _parse_entry(wire_entry)
        if entry is None:
            return None
        entries[unit_id] = entry
    return SpawnSplit(wire["manifest_sha256"], MappingProxyType(entries))


def _parse_entry(wire: object) -> SplitEntry | None:
    if not isinstance(wire, dict):
        return None
    source, text = wire.get("source"), wire.get("text")
    whole, stored = wire.get("whole_sha256"), wire.get("text_sha256")
    if not (isinstance(source, str) and isinstance(text, str) and _encodes_as_utf8(text)):
        return None
    if not (isinstance(whole, str) and isinstance(stored, str)):
        return None
    if not (_is_digest(whole) and _is_digest(stored)):
        return None
    return SplitEntry(source, whole, text, stored)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _encodes_as_utf8(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def spawn_units(
    units: Mapping[str, str], split: SpawnSplit | None, manifest_sha: str | None
) -> Mapping[str, str]:
    """The text each unit reaches a split recipient as, in the order of ``units``.

    A unit gets its stored split text only when its entry exists and three digests agree:
    its current body against ``whole_sha256``, ``manifest_sha`` against the manifest the
    split was cut under, and the stored text against ``text_sha256``. Each unit is judged
    alone; any doubt, or no artifact, gives that unit its whole body.
    """
    if split is None or split.manifest_sha256 != manifest_sha:
        return dict(units)
    return {
        unit_id: _trusted_text(split.units.get(unit_id), body) for unit_id, body in units.items()
    }


def distrusted_units(
    units: Mapping[str, str], split: SpawnSplit, manifest_sha: str
) -> tuple[str, ...]:
    """The units, in the order of ``units``, whose stored split exists but disagrees with
    their current sources (a stale or hand-edited entry, or a split cut under another audience
    manifest), so `spawn_units` gives each its whole body."""
    current = split.manifest_sha256 == manifest_sha
    return tuple(
        unit_id
        for unit_id, body in units.items()
        if (entry := split.units.get(unit_id)) is not None
        and not (current and _trusts(entry, body))
    )


def _trusted_text(entry: SplitEntry | None, body: str) -> str:
    return entry.text if entry is not None and _trusts(entry, body) else body


def _trusts(entry: SplitEntry, body: str) -> bool:
    return entry.whole_sha256 == _sha256(body) and entry.text_sha256 == _sha256(entry.text)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
