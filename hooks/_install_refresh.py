"""The pure core of the install refresh after a plugin update.

Three questions are answered here from values alone, with no filesystem read: which
version directory of the plugin cache a link text points into, which of five
states the global instructions entry is in, and what to do to each script link in
the bin directory. The hook gathers a snapshot at its edge, calls these, and acts
on the answer; nothing in this module touches a file, the environment or the clock.

The hand path (the command a person runs in their own terminal) asks the same
states one more question, what to do about the instructions, and reports its result
as an exit status; both answers are decided here too, below the script-link planner.

The cache rule mirrors the shell library's `_managed_rule_rel_path` glob
(`*/plugins/cache/*/praxion/*/...`), and `tests/fixtures/plugin_cache_targets.tsv`
holds the two equal. The rule asks for the whole structure, never a bare
`praxion` segment: a clone checkout is often named `praxion` and must read as
not-cache.

Stdlib only, and importable on Python 3.9, like the hook modules around it.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
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
    """A live link into the cache version directory `version_dir`.

    `render` is the normalised path the link names, which is not always the version's
    primary render: a hand-path install may link a second file beside it. It lies
    inside `version_dir`; the check below is the invariant's enforcement point.
    """

    version_dir: str
    render: str

    def __post_init__(self) -> None:
        if not (self.render == self.version_dir or self.render.startswith(self.version_dir + "/")):
            raise ValueError(f"render {self.render!r} must lie inside {self.version_dir!r}")


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
    named = _normalised_link_text(snapshot.text, link_dir)
    version_dir = _version_dir_of(named)
    if version_dir is None:
        return ForeignLink()
    return CachedRender(version_dir, named) if snapshot.resolves else MissingCachedRender()


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


# -- What the hand path does about the instructions --------------------------------

# Where a version directory keeps its renders. A render is never written over the file
# the link resolves to, so a version directory has a second slot to alternate into.
PRIMARY = "claude/config/CLAUDE.md"
ALTERNATE = "claude/config/CLAUDE.alternate.md"

# The exit statuses of the hand path's instructions step; the installer maps them to words.
STATUS_DONE = 0
STATUS_FAILED = 1
STATUS_LEFT_BEHIND = 3


@dataclass(frozen=True)
class Carried:
    """The earlier render was read: the values it held, and the template's placeholders it did not fill."""

    values: Mapping[str, str]
    missing: frozenset[str]


@dataclass(frozen=True)
class Unreadable:
    """The earlier render, or the template to read it against, could not be read."""


Readback = Union[Carried, Unreadable]  # noqa: UP007


class LeaveAloneReason(Enum):
    OWN_FILE = "own-file"
    OUTSIDE_CACHE = "outside-cache"
    CHECKOUT = "checkout"


class AskReason(Enum):
    UNREADABLE = "unreadable"
    MISSING = "missing"


@dataclass(frozen=True)
class LeaveAlone:
    why: LeaveAloneReason


@dataclass(frozen=True)
class Current:
    """The link already reads from the installed version, with every placeholder filled."""


@dataclass(frozen=True)
class CarryForward:
    values: Mapping[str, str]
    missing: frozenset[str]


@dataclass(frozen=True)
class AskForValues:
    why: AskReason


HandPathPlan = Union[LeaveAlone, Current, CarryForward, AskForValues]  # noqa: UP007


def plan_hand_path_instructions(
    state: InstructionsState,
    readback: Readback,
    root_is_cache_version: bool,
    installed_version_dir: str,
) -> HandPathPlan:
    """What the hand path does about the instructions, by the first rule that applies.

    Order matters. The person's own file and a link outside the cache are named as
    such even from a checkout; only then does a checkout leave everything alone.
    `readback` is consulted only for a `CachedRender`; elsewhere pass `Unreadable()`.
    """
    if isinstance(state, UserOwned):
        return LeaveAlone(LeaveAloneReason.OWN_FILE)
    if isinstance(state, ForeignLink):
        return LeaveAlone(LeaveAloneReason.OUTSIDE_CACHE)
    if not root_is_cache_version:
        return LeaveAlone(LeaveAloneReason.CHECKOUT)
    if isinstance(state, CachedRender):
        return _plan_cached_render(state, readback, installed_version_dir)
    if isinstance(state, (NoInstructions, MissingCachedRender)):
        return AskForValues(AskReason.MISSING)
    return unreachable(state)


def _plan_cached_render(
    state: CachedRender, readback: Readback, installed_version_dir: str
) -> HandPathPlan:
    if isinstance(readback, Unreadable):
        return AskForValues(AskReason.UNREADABLE)
    if isinstance(readback, Carried):
        if state.version_dir == installed_version_dir and not readback.missing:
            return Current()
        return CarryForward(readback.values, readback.missing)
    return unreachable(readback)


def render_slot(live_render: str | None, root: str) -> str:
    """The slot, relative to `root`, a new render is written to.

    `live_render` is the file the link resolves to, or None when no live link names
    one; both paths are given with every link resolved, so two spellings of one file
    compare equal. `PRIMARY`, unless the link currently resolves to `root`'s own
    `PRIMARY`: that file is what the person reads now, and a failed write must leave
    it as it is.
    """
    return ALTERNATE if live_render == posixpath.join(root, PRIMARY) else PRIMARY


class SkipPoint(Enum):
    OFFER = "offer"
    CONFIRM = "confirm"


class FailureKind(Enum):
    READING = "reading"
    WRITING = "writing"
    PERMISSION = "permission"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class SetUp:
    """The instructions were rendered and linked."""


@dataclass(frozen=True)
class LeftAlone:
    why: LeaveAloneReason


@dataclass(frozen=True)
class Skipped:
    at: SkipPoint


@dataclass(frozen=True)
class NoAnswer:
    """The input ended before the person answered."""


@dataclass(frozen=True)
class Failed:
    kind: FailureKind


HandPathOutcome = Union[SetUp, Current, LeftAlone, Skipped, NoAnswer, Failed]  # noqa: UP007


def exit_status(outcome: HandPathOutcome) -> int:
    """The exit status for an outcome: 3 whenever the instructions are left behind unfinished."""
    if isinstance(outcome, (SetUp, Current)):
        return STATUS_DONE
    if isinstance(outcome, LeftAlone):
        return STATUS_LEFT_BEHIND if outcome.why is LeaveAloneReason.CHECKOUT else STATUS_DONE
    if isinstance(outcome, (Skipped, NoAnswer)):
        return STATUS_LEFT_BEHIND
    if isinstance(outcome, Failed):
        return STATUS_FAILED
    return unreachable(outcome)


# -- What counts as the plugin cache ----------------------------------------------


def cache_version_dir(target: str, link_dir: str) -> str | None:
    """The cache version directory the link text `target` lies in, or None.

    Lexical: a relative text is joined to `link_dir` and normalised, so a dangling
    link answers the same as a live one.
    """
    return _version_dir_of(_normalised_link_text(target, link_dir))


def _normalised_link_text(target: str, link_dir: str) -> str:
    """The path a link text names: joined to `link_dir` when relative, then normalised."""
    joined = target if posixpath.isabs(target) else posixpath.join(link_dir, target)
    return posixpath.normpath(joined)


def _version_dir_of(normalised: str) -> str | None:
    """The cache version directory a normalised path lies in, or None."""
    segments = normalised.split("/")
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
