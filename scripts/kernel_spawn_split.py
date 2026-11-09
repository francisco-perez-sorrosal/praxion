"""The spawn split: the always-loaded rules a spawned agent receives, minus what only the main session acts on.

A rule file read for a split recipient keeps every byte except its *dropped spans*: the sections
and parts the audience manifest classifies `orchestrator-only`. One cutter serves the generator
(which stores the result in `claude/kernels/spawn_split.json`), the commit gate (which re-derives
it) and the shed count, so the three can never disagree about what a split recipient receives.

How a section is cut:

- a dropped section goes from its heading line to the line before the next heading of level two
  to four; a subsection is a section of its own and is classified on its own;
- a dropped part goes from the line its prefix begins to the next part (kept or dropped) or the
  section's end;
- the manifest cuts a heading into none of its parts, so while any part of a section stays,
  the heading and the lines up to its first part stay with it (a kept part is never read as
  part of the section before it); a section all of whose parts are dropped goes, heading and all;
- a `condensed` form is ignored: kept text is source bytes, never the authored text.

Stdlib plus the manifest model (PyYAML is read in `kernel_model`, never here). The body is the
hooks' own definition (`_rule_delivery.rule_body`), so a digest taken here is the one the hook
takes at spawn.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

import kernel_model as km
import kernel_sources as ks

# hooks/ sits beside scripts/; the hook's pure module is the one definition of the artifact's
# shape and of the body a digest is taken over.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _rule_delivery as rd  # noqa: E402  # pyright: ignore[reportMissingImports]

SPAWN_SPLIT_PATH = "claude/kernels/spawn_split.json"


class SplitCutError(ValueError):
    """The sections handed to the cutter are not the sections of the body."""


# -- Pure: cutting the text ----------------------------------------------------------


def split_text(
    body: str, sections: Sequence[ks.Section], entries: Iterable[km.AudienceEntry]
) -> str:
    """`body` with exactly the dropped spans of `entries` removed.

    `sections` are the body's own (`kernel_sources.split_sections`): they run from the first
    heading to the end, so what precedes that heading is kept as it stands.
    """
    scopes = {entry.target: entry.scope for entry in entries}
    cut_from = len(body) - sum(len(section.text) for section in sections)
    if cut_from < 0 or body[cut_from:] != "".join(section.text for section in sections):
        raise SplitCutError("the sections are not the tail of the body they were cut from")
    return body[:cut_from] + "".join(_kept(section, scopes) for section in sections)


def _kept(section: ks.Section, scopes: Mapping[km.Target, km.Scope]) -> str:
    if _is_dropped(scopes.get(km.SectionTarget(section.source, section.heading))):
        return ""
    prefixes = [
        target.prefix
        for target in scopes
        if isinstance(target, km.PartTarget)
        and (target.source, target.heading) == (section.source, section.heading)
    ]
    if not prefixes:
        return section.text
    parts = ks.split_parts(section, prefixes)
    kept = [part for part in parts if not _part_dropped(part, scopes)]
    if not kept:
        return ""
    opening = section.text[: len(section.text) - sum(len(part.text) for part in parts)]
    return opening + "".join(part.text for part in kept)


def _part_dropped(part: ks.Part, scopes: Mapping[km.Target, km.Scope]) -> bool:
    """Unprefixed text before the first part is never classified, so it is never dropped."""
    return part.prefix is not None and _is_dropped(
        scopes.get(km.PartTarget(part.source, part.heading, part.prefix))
    )


def _is_dropped(scope: km.Scope | None) -> bool:
    return isinstance(scope, km.OrchestratorOnly)


# -- Pure: the artifact --------------------------------------------------------------


def render_spawn_split(manifest_sha256: str, units: Mapping[str, rd.SplitEntry]) -> str:
    """The artifact's JSON: sorted keys, a trailing newline, the same bytes for the same input."""
    wire = {
        "schema": rd.SPLIT_SCHEMA,
        "manifest_sha256": manifest_sha256,
        "units": {unit_id: asdict(entry) for unit_id, entry in units.items()},
    }
    return json.dumps(wire, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def sha256_hex(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


# -- Edge: reading the repository ----------------------------------------------------


def expected_split(root: Path, manifest: km.Manifest, unit: rd.CoreUnit) -> rd.SplitEntry | None:
    """The split of `unit` as its source and `manifest` give it now.

    None when the unit has nothing to drop (or no source file): it then arrives whole.
    """
    if not (root / unit.path).is_file():
        return None
    body = rd.rule_body((root / unit.path).read_bytes().decode("utf-8"))
    text = split_text(body, ks.load_sections(root, unit.path), manifest.entries)
    if text == body:
        return None
    return rd.SplitEntry(unit.path, sha256_hex(body), text, sha256_hex(text))


def spawn_split_artifact(root: Path, manifest: km.Manifest) -> str:
    """The artifact for `root`: its units with something to drop, under the manifest's digest."""
    units = {
        unit.unit_id: entry
        for unit in rd.MANAGED_CORE_UNITS
        if (entry := expected_split(root, manifest, unit)) is not None
    }
    manifest_bytes = (root / km.MANIFEST_PATH).read_bytes()
    return render_spawn_split(sha256_hex(manifest_bytes), units)
