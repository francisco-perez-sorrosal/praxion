"""The specification's split text, computed from a rule and the audience manifest alone.

`split_text` removes exactly the `orchestrator-only` sections and parts the manifest names:
each section (heading levels two to four, outside fences) runs from its heading line to the line
before the next such heading; a part runs from the one line its prefix begins to the next part or
the section's end; a section all of whose parts are removed goes heading and all, and every other
byte stays. When the manifest cannot classify the unit exactly (absent, unparseable, a section or
part without exactly one entry, an entry naming nothing, an unknown scope) there is no split text
and only the whole unit is acceptable.

Also here: the units under test and the agent roles that do and do not receive the split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import AUDIENCE_MANIFEST

DROPPED = "orchestrator-only"
SCOPES = frozenset({"core", "role", DROPPED, "no-actor"})


@dataclass(frozen=True)
class Unit:
    id: str
    source: str


PROTOCOL = Unit(
    "swe/swe-agent-coordination-protocol", "rules/swe/swe-agent-coordination-protocol.md"
)
INTERMEDIATE = Unit("swe/agent-intermediate-documents", "rules/swe/agent-intermediate-documents.md")
ADR_RESIDENT = Unit("swe/adr-conventions-resident", "rules/swe/adr-conventions-resident.md")
SPLIT_UNITS = (PROTOCOL, INTERMEDIATE)
CORE_UNITS = (PROTOCOL, INTERMEDIATE, ADR_RESIDENT)

SPLIT_ROLES = (
    "agentic-transactions-architect",
    "architect-validator",
    "cicd-engineer",
    "context-engineer",
    "discipline-consultant",
    "doc-engineer",
    "implementation-planner",
    "interface-designer",
    "promethean",
    "roadmap-cartographer",
    "sentinel",
    "skill-genesis",
    "verifier",
)
LEAN_ROLES = ("researcher", "implementer", "test-engineer", "systems-architect")


# -- The specification's split text ------------------------------------------------------------

HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _body(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            text = text[end + len("\n---\n") :]
    return text.lstrip("\n")


def source_text(root: Path, unit: Unit) -> str:
    """The unit as rule delivery reads it: its file without the frontmatter block."""
    return _body((root / unit.source).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Span:
    heading: str
    start: int  # the heading line
    end: int  # one past the section's last line


def section_spans(lines: list[str]) -> list[Span]:
    heads: list[tuple[int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else HEADING.match(line.rstrip("\n"))
        if match:
            heads.append((i, match.group(2)))
    return [
        Span(heading, start, heads[k + 1][0] if k + 1 < len(heads) else len(lines))
        for k, (start, heading) in enumerate(heads)
    ]


def audience_entries(root: Path, unit: Unit) -> list[dict] | None:
    """The audience manifest's entries for `unit`; None when the manifest cannot be read."""
    try:
        manifest = yaml.safe_load((root / AUDIENCE_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return None
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        return None
    return [e for e in entries if e.get("source") == unit.source]


def split_text(root: Path, unit: Unit) -> str | None:
    """The unit's text with exactly its orchestrator-only spans removed; None if undefined."""
    entries = audience_entries(root, unit)
    if entries is None:
        return None
    lines = source_text(root, unit).splitlines(keepends=True)
    sections = section_spans(lines)
    headings = [s.heading for s in sections]
    by_heading: dict[str | None, list[dict]] = {}
    for entry in entries:
        by_heading.setdefault(entry.get("heading"), []).append(entry)
    if len(set(headings)) != len(headings) or set(by_heading) != set(headings):
        return None
    dropped = [False] * len(lines)

    def drop(start: int, end: int) -> None:
        for i in range(start, end):
            dropped[i] = True

    for section in sections:
        found = by_heading[section.heading]
        if any(e.get("scope") not in SCOPES for e in found):
            return None
        whole = [e for e in found if not e.get("part")]
        parts = [e for e in found if e.get("part")]
        if (whole and parts) or len(whole) > 1:
            return None
        if whole:
            if whole[0]["scope"] == DROPPED:
                drop(section.start, section.end)
            continue
        starts = []
        for entry in parts:
            prefix = str(entry["part"])
            hits = [i for i in range(section.start + 1, section.end) if lines[i].startswith(prefix)]
            if len(hits) != 1:
                return None
            starts.append((hits[0], entry["scope"]))
        starts.sort()
        if len({i for i, _ in starts}) != len(starts):
            return None
        if all(scope == DROPPED for _, scope in starts):
            drop(section.start, section.end)
            continue
        for k, (start, scope) in enumerate(starts):
            if scope == DROPPED:
                drop(start, starts[k + 1][0] if k + 1 < len(starts) else section.end)
    return "".join(line for line, gone in zip(lines, dropped, strict=True) if not gone).lstrip("\n")


def dropped_headings(root: Path, unit: Unit) -> list[str]:
    """Headings of the sections the manifest classifies orchestrator-only as a whole."""
    entries = audience_entries(root, unit) or []
    return [e["heading"] for e in entries if not e.get("part") and e.get("scope") == DROPPED]
