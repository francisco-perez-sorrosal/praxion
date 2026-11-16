"""The one ownership rule of the step-loop driver: what a `Read-only:` entry means to the
gate, to the commit and to the prompt. Stdlib-only leaf; no file is opened.

An entry is a bare path (a file or a directory) or a node entry (`path::node`, cut at the
first `::` only, so `weird[1].txt` is a bare path). The three readers of one entry:

| Reader | Bare path                                   | Node entry                                |
|--------|---------------------------------------------|-------------------------------------------|
| gate   | owns every node under the path              | owns its node and the node's parameters   |
| commit | withholds the file, or every file under it  | withholds nothing                         |
| prompt | says nothing                                | tells the step whose `Files:` names the file that the node is its to turn green and the file its to edit |

A file under `tests/acceptance/` or `tests/e2e/` is withheld from every commit whatever the
plan says.

Normative ownership of a failed node -- a `Read-only:` entry owns every node it is a
prefix of, at a path, `::` or `[` boundary (`a.py::f` owns `a.py::f[x]` but not
`a.py::fg`). The longest owning entry decides. A node counts as pending only when every
entry tied for longest belongs to another step that is not done; any other failure is
a failure, so a tie with the step's own entry stays a failure. `Ownership.step`,
`done_steps` and the map keys share one id form; `step` must be a key of the map (a step
with no entries maps to `()`).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:  # the leaf stays free of the plan reader at run time
    from _plan_steps import PlanStep

OUTER_LOOP_PREFIXES = ("tests/acceptance/", "tests/e2e/")
_NODE_SEPARATOR = "::"
_NODE_BOUNDARIES = (_NODE_SEPARATOR, "[")
_PATH_BOUNDARY = "/"


# --- One entry, parsed once ---


@dataclass(frozen=True)
class BarePath:
    """A file or a directory."""

    path: str


@dataclass(frozen=True)
class NodeEntry:
    """One node of a file: `path::node...`."""

    path: str
    node: str


ReadOnlyEntry = Union[BarePath, NodeEntry]  # noqa: UP007 -- runtime value, 3.9 floor


def read_only_entry(text: str) -> ReadOnlyEntry:
    """The entry `text` spells, cut at the first `::`."""
    path, separator, node = text.partition(_NODE_SEPARATOR)
    return NodeEntry(path, node) if separator else BarePath(path)


# --- The gate's reading: who owns a failed node ---


def entry_owns(entry: str, node_id: str) -> bool:
    """Whether `entry` is a prefix of `node_id` at a path, `::` or `[` boundary (`/` only
    for a bare path entry: inside a node id a slash can only follow `[`)."""
    if not node_id.startswith(entry):
        return False
    rest = node_id[len(entry) :]
    boundaries = _NODE_BOUNDARIES if "::" in entry else (_PATH_BOUNDARY, *_NODE_BOUNDARIES)
    return rest == "" or entry.endswith(_PATH_BOUNDARY) or rest.startswith(boundaries)


@dataclass(frozen=True)
class Ownership:
    """Which step holds each outer-loop test: `step` is the one being gated,
    `read_only_by_step` maps every plan step to its `Read-only:` entries, and
    `done_steps` are the steps already complete."""

    step: str
    read_only_by_step: Mapping[str, tuple[str, ...]]
    done_steps: frozenset[str]

    def __post_init__(self) -> None:
        if self.step not in self.read_only_by_step:
            raise ValueError(f"step {self.step!r} is not a key of the Read-only map")

    def is_pending_error(self, node_id: str) -> bool:
        """An errored node is owned like a failed one."""
        return self.is_pending(node_id)

    def is_pending(self, node_id: str) -> bool:
        """True when only other steps that are not done own `node_id` (longest entry wins)."""
        claims = [
            (len(entry), owner)
            for owner, entries in self.read_only_by_step.items()
            for entry in entries
            if entry_owns(entry, node_id)
        ]
        if not claims:
            return False
        longest = max(length for length, _ in claims)
        owners = {owner for length, owner in claims if length == longest}
        return all(owner != self.step and owner not in self.done_steps for owner in owners)


# --- The commit's reading: which files no step's commit may take ---


def withheld(path: str, entries: Iterable[ReadOnlyEntry]) -> bool:
    """Whether a commit leaves `path` out. `path` and the entries' paths are normalised."""
    if (path + _PATH_BOUNDARY).startswith(OUTER_LOOP_PREFIXES):
        return True
    return any(
        isinstance(entry, BarePath)
        and (path == entry.path or path.startswith(entry.path + _PATH_BOUNDARY))
        for entry in entries
    )


# --- The prompt's reading: what a step may do with its own node entries ---


def own_node_permissions(step: PlanStep) -> tuple[str, ...]:
    """One sentence per node entry of `step` whose file its `Files:` names, outside the
    outer-loop directories; an outer-loop entry gets none."""
    files = tuple(posixpath.normpath(name) for name in step.files)
    sentences = []
    for text in step.read_only:
        entry = read_only_entry(text)
        path = posixpath.normpath(entry.path)
        if not isinstance(entry, NodeEntry) or not _names_file(files, path):
            continue
        if (path + _PATH_BOUNDARY).startswith(OUTER_LOOP_PREFIXES):
            continue
        sentences.append(
            f"Your Read-only entry `{text}` names a node that is yours to turn green, "
            f"and `{entry.path}` is yours to edit."
        )
    return tuple(sentences)


def _names_file(declared: tuple[str, ...], path: str) -> bool:
    return any(path == name or path.startswith(name + _PATH_BOUNDARY) for name in declared)
