"""Driver for the audience manifest (`rules/_audience.yaml`), not yet bound.

Scenarios describe entries in the specification's terms: a whole section or a
part of a mixed-audience section (the heading plus a leading-text prefix), one of
four scopes, the agents or declared groups a role entry names, the reason an
orchestrator-only or no-actor entry gives, and, for core and role, the verbatim or
condensed form with its pin. The manifest's file shape is designed later; every
hook below raises until a binding step writes it.

A writer must be able to write illegal shapes too: scenarios hand it entries the
checker has to refuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers.kernel_sandbox import UnboundDriverError


class _CurrentPin:
    def __repr__(self) -> str:
        return "the digest of the source section as it stands"


CURRENT_PIN = _CurrentPin()

ADR_AUTHORS = "the ADR-author group"
LEDGER_WRITERS = "the ledger-writer group"


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


def add_entry(root: Path, entry: AudienceEntry) -> None:
    raise UnboundDriverError(
        "writing an audience entry (section or part, scope, agents or groups, reason, "
        "form and pin) into the audience manifest is not designed yet"
    )


def remove_entries(root: Path, source: str, heading: str) -> None:
    raise UnboundDriverError(
        "removing a section's audience entries from the audience manifest is not designed yet"
    )


def declare_group(root: Path, name: str, members: tuple[str, ...]) -> None:
    raise UnboundDriverError("declaring a named agent group in the manifest is not designed yet")


def group_members(root: Path, group: str) -> tuple[str, ...]:
    raise UnboundDriverError(
        "reading the members of the ADR-author or ledger-writer group is not designed yet"
    )


def set_group_members(root: Path, group: str, members: tuple[str, ...]) -> None:
    raise UnboundDriverError(
        "changing the members of the ADR-author or ledger-writer group is not designed yet"
    )


def entries(root: Path) -> list[AudienceEntry]:
    raise UnboundDriverError("reading the audience manifest's entries is not designed yet")


def reclassify(root: Path, entry: AudienceEntry) -> None:
    """Give a section exactly one entry: `entry`."""
    remove_entries(root, entry.source, entry.heading)
    add_entry(root, entry)
