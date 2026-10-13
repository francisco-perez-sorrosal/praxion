"""Driver for the audience manifest (`rules/_audience.yaml`).

Scenarios describe entries in the specification's terms: a whole section or a
part of a mixed-audience section (the heading plus a leading-text prefix), one of
four scopes, the agents or declared groups a role entry names, the reason an
orchestrator-only or no-actor entry gives, and, for core and role, the verbatim or
condensed form with its pin. The hooks read and write the manifest's wire shape
(the implementation plan's "Wire shapes": `version: 1`, `groups`, `modules`,
`authored`, `entries`) in a plugin checkout; a missing manifest reads as empty.

A writer must be able to write illegal shapes too: scenarios hand it entries the
checker has to refuse.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import AUDIENCE_MANIFEST


class _CurrentPin:
    def __repr__(self) -> str:
        return "the digest of the source section as it stands"


CURRENT_PIN = _CurrentPin()

ADR_AUTHORS = "the ADR-author group"
LEDGER_WRITERS = "the ledger-writer group"

# The declared names behind the two labels scenarios use.
_GROUP_NAMES = {ADR_AUTHORS: "adr-author", LEDGER_WRITERS: "ledger-writer"}
AUTHORED_DIR = "claude/kernels/src"


@dataclass(frozen=True)
class AudienceEntry:
    source: str  # repository-relative path of the source file
    heading: str  # the heading's text, without the leading hashes
    scope: str  # "core" | "role" | "orchestrator-only" | "no-actor"; "" is an empty audience
    part: str | None = None  # leading-text prefix of a part of a mixed-audience section
    agents: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()  # declared group names, or ADR_AUTHORS / LEDGER_WRITERS
    reason: str | None = None
    form: str | None = None  # "verbatim" | "condensed"
    condensed_text: str | None = None
    pin: object = None  # None, CURRENT_PIN, or a literal digest


_HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _group_name(group: str) -> str:
    return _GROUP_NAMES.get(group, group)


def _load(root: Path) -> dict:
    path = root / AUDIENCE_MANIFEST
    manifest = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    manifest = manifest or {}
    for key, empty in (("groups", {}), ("modules", {}), ("authored", []), ("entries", [])):
        manifest.setdefault(key, empty)
    manifest.setdefault("version", 1)
    return manifest


def _save(root: Path, manifest: dict) -> None:
    path = root / AUDIENCE_MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, width=100), encoding="utf-8")


def _section_bytes(root: Path, source: str, heading: str, part: str | None) -> bytes:
    """The source section's bytes: its heading line to the next heading (levels 2 to 4).

    A part runs from the paragraph starting with its prefix to the section's end.
    Trailing blank lines are not part of the extent: the bytes end at the last
    non-blank line, with one newline, so appending a section to the file leaves
    the previous section's pin intact.
    """
    lines = (root / source).read_text(encoding="utf-8").splitlines(keepends=True)
    found: list[str] | None = None
    fenced = False
    for line in lines:
        if _FENCE.match(line):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line.rstrip("\n"))
        if match:
            if found is not None:
                break
            if match.group(2) == heading:
                found = [line]
        elif found is not None:
            found.append(line)
    assert found is not None, f"{source} has no section headed {heading!r}"
    text = "".join(found)
    if part is not None:
        start = text.find(part)
        assert start >= 0, f"the section {heading!r} has no part starting {part!r}"
        text = text[start:]
    kept = text.split("\n")
    while kept and not kept[-1].strip():
        kept.pop()
    return ("\n".join(kept) + "\n").encode("utf-8")


def _pin_value(root: Path, entry: AudienceEntry) -> str | None:
    if entry.pin is CURRENT_PIN:
        digest = hashlib.sha1(_section_bytes(root, entry.source, entry.heading, entry.part))
        return digest.hexdigest()
    return entry.pin  # type: ignore[return-value]


def _text_id(entry: AudienceEntry) -> str:
    words = [entry.heading, *([entry.part] if entry.part else [])]
    return re.sub(r"[^a-z0-9]+", "-", " ".join(words).lower()).strip("-")


def _audience_module(manifest: dict, entry: AudienceEntry) -> str:
    """The module an authored condensed text belongs to: `core`, or the entry's audience."""
    names = [*(_group_name(g) for g in entry.groups), *entry.agents]
    if entry.scope != "role" or not names:
        return "core"
    manifest["modules"].setdefault(names[0], {"audience": [names[0]]})
    return names[0]


def add_entry(root: Path, entry: AudienceEntry) -> None:
    """Write `entry` as given, legal or not; a condensed text is registered as authored."""
    manifest = _load(root)
    pin = _pin_value(root, entry) if entry.pin is not None else None
    text_id = None
    if entry.condensed_text is not None:
        text_id = _text_id(entry)
        path = f"{AUTHORED_DIR}/{text_id}.md"
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(entry.condensed_text.rstrip("\n") + "\n", encoding="utf-8")
        manifest["authored"] = [a for a in manifest["authored"] if a.get("id") != text_id]
        manifest["authored"].append(
            {
                "id": text_id,
                "path": path,
                "module": _audience_module(manifest, entry),
                "condenses": f"{entry.source}#{entry.heading}",
                "pinned_sha": pin,
            }
        )
    manifest["entries"].append(
        {
            "source": entry.source,
            "heading": entry.heading,
            "part": entry.part,
            "scope": entry.scope,
            "form": entry.form,
            "text": text_id,
            "pin": pin,
            "agents": list(entry.agents),
            "groups": [_group_name(g) for g in entry.groups],
            "reason": entry.reason,
        }
    )
    _save(root, manifest)


def remove_entries(root: Path, source: str, heading: str) -> None:
    manifest = _load(root)
    gone = [e for e in manifest["entries"] if e["source"] == source and e["heading"] == heading]
    manifest["entries"] = [e for e in manifest["entries"] if e not in gone]
    for text_id in {e["text"] for e in gone if e.get("text")}:
        still_used = any(e.get("text") == text_id for e in manifest["entries"])
        for row in [a for a in manifest["authored"] if a["id"] == text_id and a.get("condenses")]:
            if not still_used:
                manifest["authored"].remove(row)
                (root / row["path"]).unlink(missing_ok=True)
    _save(root, manifest)


def declare_group(root: Path, name: str, members: tuple[str, ...]) -> None:
    manifest = _load(root)
    manifest["groups"][_group_name(name)] = list(members)
    _save(root, manifest)


def group_members(root: Path, group: str) -> tuple[str, ...]:
    return tuple(_load(root)["groups"].get(_group_name(group), ()))


def set_group_members(root: Path, group: str, members: tuple[str, ...]) -> None:
    declare_group(root, group, members)


def entries(root: Path) -> list[AudienceEntry]:
    manifest = _load(root)
    authored = {a["id"]: a for a in manifest["authored"]}
    found = []
    for row in manifest["entries"]:
        text = None
        if row.get("text"):
            path = authored.get(row["text"], {}).get("path")
            readable = path and (root / path).is_file()
            text = (
                (root / path).read_text(encoding="utf-8").rstrip("\n") if readable else row["text"]
            )
        found.append(
            AudienceEntry(
                source=row["source"],
                heading=row["heading"],
                scope=row["scope"],
                part=row.get("part"),
                agents=tuple(row.get("agents") or ()),
                groups=tuple(row.get("groups") or ()),
                reason=row.get("reason"),
                form=row.get("form"),
                condensed_text=text,
                pin=row.get("pin"),
            )
        )
    return found


def reclassify(root: Path, entry: AudienceEntry) -> None:
    """Give a section exactly one entry: `entry`."""
    remove_entries(root, entry.source, entry.heading)
    add_entry(root, entry)
