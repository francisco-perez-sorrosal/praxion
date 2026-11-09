"""Editing a plugin checkout so its spawn delivery disagrees with its sources, and the drift check.

A *plant* is one kind of disagreement a split recipient's delivery can carry, applied to a sandbox
checkout. The drift check is the commit-time kernel gate, read against what a split recipient
actually receives. The regeneration a maintainer runs after editing a rule or the audience manifest
is bound provisionally to the kernel generator.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.audience_split_delivery import BASE_COMMIT, REPO_ROOT, spawn
from tests.acceptance.drivers.audience_split_oracle import (
    CORE_UNITS,
    DROPPED,
    HEADING,
    INTERMEDIATE,
    PROTOCOL,
    SPLIT_UNITS,
    Unit,
    section_spans,
    source_text,
    split_text,
)
from tests.acceptance.drivers.kernel_sandbox import (
    AUDIENCE_MANIFEST,
    GateVerdict,
    Sandbox,
    commit_gate,
    regenerate,
)

# -- Editing a plugin checkout ----------------------------------------------------------------

PLANTED = "A sentence planted after the spawn delivery was last brought up to date."


def insert_under_heading(sandbox: Sandbox, unit: Unit, heading: str, text: str = PLANTED) -> None:
    """Put a new paragraph right under a section's heading line."""
    lines = sandbox.read(unit.source).splitlines(keepends=True)
    matches = [
        i
        for i, ln in enumerate(lines)
        if (m := HEADING.match(ln.rstrip("\n"))) and m.group(2) == heading
    ]
    assert len(matches) == 1, f"{unit.source} has no single section headed {heading!r}"
    lines.insert(matches[0] + 1, f"\n{text}\n")
    sandbox.write(unit.source, "".join(lines))


def _entry_block(lines: list[str], source: str, heading: str) -> tuple[int, int]:
    """(first, end) line indices of the manifest entry for a whole section."""
    for i, line in enumerate(lines[:-1]):
        if line.strip() == f"- source: {source}" and lines[i + 1].strip() in (
            f'heading: "{heading}"',
            f"heading: {heading}",
        ):
            end = i + 2
            while (
                end < len(lines)
                and lines[end].startswith("    ")
                and not lines[end].lstrip().startswith("- ")
            ):
                end += 1
            block = lines[i:end]
            assert not any(ln.strip().startswith("part:") for ln in block), (
                f"the entry for {heading!r} is a part; give a whole-section heading"
            )
            return i, end
    raise AssertionError(f"{AUDIENCE_MANIFEST} has no whole-section entry for {source} {heading!r}")


def reclassify(
    sandbox: Sandbox,
    unit: Unit,
    heading: str,
    scope: str,
    *,
    reason: str | None = None,
    form: str | None = None,
) -> None:
    """Give a whole section a new scope (and the reason or form that scope asks for)."""
    lines = sandbox.read(AUDIENCE_MANIFEST).splitlines(keepends=True)
    first, end = _entry_block(lines, unit.source, heading)
    block = [f"  - source: {unit.source}\n", f'    heading: "{heading}"\n', f"    scope: {scope}\n"]
    if form:
        block.append(f"    form: {form}\n")
    if reason:
        block.append(f'    reason: "{reason}"\n')
    sandbox.write(AUDIENCE_MANIFEST, "".join(lines[:first] + block + lines[end:]))


def add_dropped_section(sandbox: Sandbox, unit: Unit, heading: str) -> None:
    """Append a new orchestrator-only section to the unit and classify it."""
    sandbox.append(unit.source, f"### {heading}\n\n{PLANTED}\n")
    sandbox.append(
        AUDIENCE_MANIFEST,
        f"  - source: {unit.source}\n"
        f'    heading: "{heading}"\n'
        f"    scope: {DROPPED}\n"
        '    reason: "A section planted for the drift canary."\n',
    )


def remove_section(sandbox: Sandbox, unit: Unit, heading: str) -> None:
    """Delete a whole section from the unit and its manifest entry."""
    lines = sandbox.read(unit.source).splitlines(keepends=True)
    body_offset = len(lines) - len(source_text(sandbox.root, unit).splitlines(keepends=True))
    spans = [s for s in section_spans(lines[body_offset:]) if s.heading == heading]
    assert len(spans) == 1, f"{unit.source} has no single section headed {heading!r}"
    start, end = spans[0].start + body_offset, spans[0].end + body_offset
    sandbox.write(unit.source, "".join(lines[:start] + lines[end:]))
    manifest = sandbox.read(AUDIENCE_MANIFEST).splitlines(keepends=True)
    first, stop = _entry_block(manifest, unit.source, heading)
    sandbox.write(AUDIENCE_MANIFEST, "".join(manifest[:first] + manifest[stop:]))


def bring_up_to_date(root: Path) -> None:
    """The regeneration a maintainer runs after editing a rule or the audience manifest.

    Provisionally the kernel generator, the one regeneration step that exists today: the
    spawn delivery is assumed to come back into agreement through the same command.
    """
    regenerate(root)


def snapshot(sandbox: Sandbox) -> dict[str, bytes]:
    """Every file of the checkout a plant may touch or regenerate, by path."""
    return {
        str(p.relative_to(sandbox.root)): p.read_bytes()
        for top in ("rules", "claude", "agents", "hooks")
        for p in sorted((sandbox.root / top).rglob("*"))
        if p.is_file()
    }


def restore(sandbox: Sandbox, before: dict[str, bytes]) -> None:
    """Put the checkout back to `before`: files written back, files a plant added removed."""
    for rel in set(snapshot(sandbox)) - set(before):
        sandbox.path(rel).unlink()
    for rel, data in before.items():
        sandbox.path(rel).parent.mkdir(parents=True, exist_ok=True)
        sandbox.path(rel).write_bytes(data)


def changed_data_files(root: Path = REPO_ROOT) -> list[str]:
    """Plugin data files (no code, no registration, no source rule) added or changed since the base."""
    changed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            BASE_COMMIT,
            "--",
            "claude",
            "rules",
            "hooks",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    untracked = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "claude",
            "rules",
            "hooks",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    sources = {u.source for u in CORE_UNITS}
    return sorted(
        rel
        for rel in set(changed) | set(untracked)
        if (root / rel).is_file()
        and not rel.endswith(".py")
        and rel != "hooks/hooks.json"
        and rel not in sources
        and not re.search(r"(?:^|/)test_[^/]*$", rel)
    )


def damage(sandbox: Sandbox, rel: str, how: str) -> None:
    """Make a data file of the plugin missing, unreadable to a parser, or cut short."""
    path = sandbox.path(rel)
    if how == "missing":
        path.unlink()
    elif how == "garbage":
        path.write_bytes(b"\x00\xff not what was written here {[\n")
    elif how == "truncated":
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])
    else:
        raise ValueError(how)


# -- The drift check ---------------------------------------------------------------------------


def kernel_gate(root: Path) -> GateVerdict:
    """The commit-time kernel checks, as `.pre-commit-config.yaml` registers them."""
    return commit_gate(root)


def names_unit(output: str, unit: Unit) -> bool:
    return unit.id in output or unit.source in output


@dataclass(frozen=True)
class DriftReading:
    disagreeing: tuple[str, ...]  # units a split recipient receives other than as split text
    refused: bool  # the commit-time kernel checks refused the tree
    named: tuple[str, ...]  # units the checks' output names
    output: str


def drift_reading(
    sandbox: Sandbox, project: Path, recipient: str = "praxion:verifier"
) -> DriftReading:
    """What a split recipient receives in `sandbox`, set against the kernel gate's verdict."""
    delivery = spawn(sandbox.root, project, recipient)
    disagreeing = tuple(
        u.id
        for u in SPLIT_UNITS
        if delivery.text_of(u) is None or delivery.text_of(u) != split_text(sandbox.root, u)
    )
    verdict = kernel_gate(sandbox.root)
    named = tuple(u.id for u in SPLIT_UNITS if names_unit(verdict.output, u))
    return DriftReading(
        disagreeing, verdict.refused, named if verdict.refused else (), verdict.output
    )


# Each kind of disagreement a split recipient's delivery can carry, planted in a checkout. A
# plant that changes kernel text regenerates the kernels, so no other kernel check has cause to
# refuse the tree; one that changes only text no kernel carries leaves the tree as edited.
PLANTS = (
    "dropped-span-edited-in-the-protocol",
    "dropped-span-edited-in-the-intermediate-documents-rule",
    "kept-span-edited-in-the-protocol",
    "kept-span-edited-in-the-intermediate-documents-rule",
    "dropped-section-reclassified-as-kept",
    "kept-section-reclassified-as-dropped",
    "dropped-section-added",
    "dropped-section-removed",
)


def plant(sandbox: Sandbox, name: str) -> Unit:
    """Apply one plant; returns the unit it touches."""
    if name == "dropped-span-edited-in-the-protocol":
        insert_under_heading(sandbox, PROTOCOL, "Available Agents")
        return PROTOCOL
    if name == "dropped-span-edited-in-the-intermediate-documents-rule":
        insert_under_heading(sandbox, INTERMEDIATE, "Document Lifecycle")
        return INTERMEDIATE
    if name == "kept-span-edited-in-the-protocol":
        insert_under_heading(sandbox, PROTOCOL, "Delegation Checklists")
        regenerate(sandbox.root)
        return PROTOCOL
    if name == "kept-span-edited-in-the-intermediate-documents-rule":
        insert_under_heading(sandbox, INTERMEDIATE, "`.ai-work/` — Ephemeral Pipeline Documents")
        regenerate(sandbox.root)
        return INTERMEDIATE
    if name == "dropped-section-reclassified-as-kept":
        reclassify(
            sandbox,
            PROTOCOL,
            "Available Agents",
            "no-actor",
            reason="The roster, kept for every reader.",
        )
        return PROTOCOL
    if name == "kept-section-reclassified-as-dropped":
        reclassify(
            sandbox,
            PROTOCOL,
            "Delegation Checklists",
            DROPPED,
            reason="Delegation is the main session's.",
        )
        regenerate(sandbox.root)
        return PROTOCOL
    if name == "dropped-section-added":
        add_dropped_section(sandbox, PROTOCOL, "Planted Orchestration Notes")
        return PROTOCOL
    if name == "dropped-section-removed":
        remove_section(sandbox, PROTOCOL, "Background Agents")
        return PROTOCOL
    raise ValueError(name)


# Plants that change only the touched unit's source, never the manifest: the other unit's
# split stands on its own and must still be delivered as split text.
SOURCE_ONLY_PLANTS = PLANTS[:4]


def other_unit(unit: Unit) -> Unit:
    return INTERMEDIATE if unit == PROTOCOL else PROTOCOL
