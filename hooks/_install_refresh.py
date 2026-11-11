"""The pure core of the install refresh after a plugin update.

Three questions are answered here from values alone, with no filesystem read: which
version directory of the plugin cache a link text points into, which of five
states the global instructions entry is in, and what to do to each script link in
the bin directory. The hook gathers a snapshot at its edge, calls these, and acts
on the answer; nothing in this module touches a file, the environment or the clock.

The cache rule mirrors the shell library's `_managed_rule_rel_path` glob
(`*/plugins/cache/*/praxion/*/...`), and `tests/fixtures/plugin_cache_targets.tsv`
holds the two equal. The rule asks for the whole structure, never a bare
`praxion` segment: a clone checkout is often named `praxion` and must read as
not-cache.

Stdlib only, and importable on Python 3.9, like the hook modules around it.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import NoReturn, Union

# .../plugins/cache/<marketplace>/praxion/<version>: the segments that name the cache
# before the marketplace, and the plugin directory that follows it.
_CACHE_ANCHOR = ("plugins", "cache")
_PLUGIN_DIRECTORY = "praxion"
# Segments up to and including the version: anchor, marketplace, plugin, version.
_ANCHOR_TO_VERSION_SPAN = len(_CACHE_ANCHOR) + 3


# -- The states of the global instructions entry ----------------------------------


class SnapshotKind(Enum):
    ABSENT = "absent"
    FILE = "file"
    LINK = "link"
    OTHER = "other"


@dataclass(frozen=True)
class InstructionsSnapshot:
    """What the edge saw at the instructions path.

    `text` and `resolves` describe a link and mean nothing for the other kinds.
    """

    kind: SnapshotKind
    text: str
    resolves: bool


@dataclass(frozen=True)
class NoInstructions:
    """Nothing is installed."""


@dataclass(frozen=True)
class UserOwned:
    """A regular file, or anything that is not a link: the user's, never replaced."""


@dataclass(frozen=True)
class ForeignLink:
    """A link outside every cache version directory, a clone's included, live or dangling."""


@dataclass(frozen=True)
class CachedRender:
    """A live link into the cache version directory `version_dir`."""

    version_dir: str


@dataclass(frozen=True)
class MissingCachedRender:
    """A dangling link into a cache version directory."""


# Built with Union, not `|`: the alias is evaluated at import, and `X | Y` on classes needs 3.10.
InstructionsState = Union[NoInstructions, UserOwned, ForeignLink, CachedRender, MissingCachedRender]  # noqa: UP007


def classify_instructions(snapshot: InstructionsSnapshot, link_dir: str) -> InstructionsState:
    """Map a snapshot to exactly one state; `link_dir` is the directory holding the entry."""
    if snapshot.kind is SnapshotKind.ABSENT:
        return NoInstructions()
    if snapshot.kind in (SnapshotKind.FILE, SnapshotKind.OTHER):
        return UserOwned()
    if snapshot.kind is SnapshotKind.LINK:
        return _classify_link(snapshot, link_dir)
    return unreachable(snapshot.kind)


def _classify_link(snapshot: InstructionsSnapshot, link_dir: str) -> InstructionsState:
    version_dir = cache_version_dir(snapshot.text, link_dir)
    if version_dir is None:
        return ForeignLink()
    return CachedRender(version_dir) if snapshot.resolves else MissingCachedRender()


# -- What to do to each script link ------------------------------------------------


class EntryKind(Enum):
    LINK = "link"
    FILE = "file"
    OTHER = "other"


@dataclass(frozen=True)
class BinEntry:
    """One entry of the bin directory as the edge saw it.

    `text` and `real` describe a link: its target as written, and the resolved path
    (None when it dangles). They mean nothing for the other kinds.
    """

    name: str
    kind: EntryKind
    text: str
    real: str | None


@dataclass(frozen=True)
class OfferedScript:
    """A script the installed version offers, and the path its link must point to."""

    name: str
    path: str


@dataclass(frozen=True)
class Keep:
    """The link already points to the offered script; its inode and text stay."""

    name: str


@dataclass(frozen=True)
class Repoint:
    name: str
    target: str


@dataclass(frozen=True)
class Remove:
    name: str


@dataclass(frozen=True)
class Link:
    name: str
    target: str


ScriptAction = Union[Keep, Repoint, Remove, Link]  # noqa: UP007


def plan_script_links(
    entries: Iterable[BinEntry], offered: Iterable[OfferedScript], link_dir: str
) -> tuple:
    """The actions that bring the bin directory in line with the offered scripts.

    The one choke point of the safety rule: only a link into the plugin cache is ever
    named by anything but `Keep`. A regular file, a directory, and a link that points
    anywhere else (a clone's included, live or dangling) get no action, whatever
    name they sit under. Placements follow `offered`, then removals follow `entries`.
    """
    entries = tuple(entries)
    offered = tuple(offered)
    by_name = {entry.name: entry for entry in entries}
    offered_names = {script.name for script in offered}
    placements = (_place(script, by_name.get(script.name), link_dir) for script in offered)
    removals = (
        Remove(entry.name)
        for entry in entries
        if entry.name not in offered_names and _is_cache_link(entry, link_dir)
    )
    return tuple(action for action in placements if action is not None) + tuple(removals)


def _place(script: OfferedScript, entry: BinEntry | None, link_dir: str):
    """The action for one offered script given what sits under its name, or None to leave it."""
    if entry is None:
        return Link(script.name, script.path)
    if entry.kind is not EntryKind.LINK:
        return None
    if script.path in (entry.text, entry.real):
        return Keep(script.name)
    return Repoint(script.name, script.path) if _is_cache_link(entry, link_dir) else None


def _is_cache_link(entry: BinEntry, link_dir: str) -> bool:
    """A link whose target lies in a cache version directory, live or dangling."""
    return entry.kind is EntryKind.LINK and cache_version_dir(entry.text, link_dir) is not None


# -- What counts as the plugin cache ----------------------------------------------


def cache_version_dir(target: str, link_dir: str) -> str | None:
    """The cache version directory the link text `target` lies in, or None.

    Lexical: a relative text is joined to `link_dir` and normalised, so a dangling
    link answers the same as a live one.
    """
    joined = target if posixpath.isabs(target) else posixpath.join(link_dir, target)
    segments = posixpath.normpath(joined).split("/")
    for start in range(len(segments) - _ANCHOR_TO_VERSION_SPAN + 1):
        if _is_cache_structure(segments[start : start + _ANCHOR_TO_VERSION_SPAN]):
            return "/".join(segments[: start + _ANCHOR_TO_VERSION_SPAN])
    return None


def _is_cache_structure(window: list) -> bool:
    """`window` is [plugins, cache, <marketplace>, praxion, <version>]; normalisation leaves no empty segment."""
    return tuple(window[:2]) == _CACHE_ANCHOR and window[3] == _PLUGIN_DIRECTORY


def unreachable(value: object) -> NoReturn:
    """Close an exhaustive dispatch; `typing.assert_never` exists only from 3.11."""
    raise AssertionError(f"unhandled case: {value!r}")
