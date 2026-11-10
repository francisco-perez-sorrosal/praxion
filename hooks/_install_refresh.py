"""The pure core of the install refresh after a plugin update.

Two questions are answered here from values alone, with no filesystem read: which
version directory of the plugin cache a link text points into, and which of five
states the global instructions entry is in. The hook gathers a snapshot at its
edge, calls these, and acts on the answer; nothing in this module touches a file,
the environment or the clock.

The cache rule mirrors the shell library's `_managed_rule_rel_path` glob
(`*/plugins/cache/*/praxion/*/...`), and `tests/fixtures/plugin_cache_targets.tsv`
holds the two equal. The rule asks for the whole structure, never a bare
`praxion` segment: a clone checkout is often named `praxion` and must read as
not-cache.

Stdlib only, and importable on Python 3.9, like the hook modules around it.
"""

from __future__ import annotations

import posixpath
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
