"""The adherence run index as the commit gate reads it: plain JSON and digests, no eval code.

`.ai-state/eval_ledger/adherence/index.json` has one writer, the adherence eval (every run as it
finalizes, and its `--reindex`). It names each results file with the sha256 of its bytes, the root
of the lineage the run belongs to, and per role the complete pairs and the flip label the whole
lineage reached; every part of a continued run carries its lineage's values, and an index whose
parts disagree or whose root is not listed is refused. The gate trusts the index only as far as it
can check it, so `read_adherence` returns the index together with the
digest of every JSON file beside it, and `Adherence.lineage_of` resolves a run only while its
file is still there. A run resolves through the lineage the index names, never through a results
file's own `earlier` listing, which on a continued run's tip holds its own predecessor parts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, get_args

import kernel_model as km

RESULTS_DIR = ".ai-state/eval_ledger/adherence"
INDEX_NAME = "index.json"
INDEX_PATH = f"{RESULTS_DIR}/{INDEX_NAME}"
INDEX_SCHEMA = 1
Flip = Literal["clear", "not clear", "underpowered"]  # a closed lineage already reads "not clear"
FLIP_LABELS: tuple[Flip, ...] = get_args(Flip)
CLEAR: Flip = "clear"
RESULTS_GLOB = "*.json"


@dataclass(frozen=True)
class Standing:
    """What a lineage reached for one role it measured."""

    complete_pairs: int
    flip: Flip


@dataclass(frozen=True)
class Lineage:
    """A run as one declared run: its first part, every part in order, what it reached per role."""

    root: str
    parts: tuple[str, ...]
    roles: Mapping[str, Standing]


@dataclass(frozen=True)
class Entry:
    """One results file as the index lists it."""

    file: str
    sha256: str
    lineage_root: str
    roles: Mapping[str, Standing]


@dataclass(frozen=True)
class Adherence:
    """The run index and the directory it describes.

    `entries` maps run id to its entry (empty when there is no index), `skipped` the JSON files
    the index names as no run, `files` every JSON file beside the index to the sha256 of its bytes.
    """

    entries: Mapping[str, Entry]
    skipped: frozenset[str]
    files: Mapping[str, str]

    def lineage_of(self, run_id: str) -> Lineage | None:
        """The whole lineage `run_id` is part of; None when the index lists no file still here."""
        entry = self.entries.get(run_id)
        if entry is None or entry.file not in self.files:
            return None
        root = entry.lineage_root
        parts = tuple(sorted(rid for rid, e in self.entries.items() if e.lineage_root == root))
        return Lineage(root, parts, entry.roles)  # ids open with their start, so sorted is in order


def read_adherence(root: Path) -> Adherence:
    """The index under `root` and the digests of the files beside it; an unreadable index raises."""
    directory = root / RESULTS_DIR
    paths = sorted(directory.glob(RESULTS_GLOB)) if directory.is_dir() else []
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.name != INDEX_NAME
    }
    index = directory / INDEX_NAME
    if not index.is_file():
        return Adherence(MappingProxyType({}), frozenset(), MappingProxyType(files))
    entries, skipped = parse_index(index.read_bytes())
    return Adherence(entries, skipped, MappingProxyType(files))


def parse_index(data: bytes) -> tuple[Mapping[str, Entry], frozenset[str]]:
    """The index's entries by run id and its skipped names; raises on any other shape."""
    try:
        raw = json.loads(data.decode("utf-8"))
        if raw["schema"] != INDEX_SCHEMA:
            raise ValueError(f"schema {raw['schema']!r}, not {INDEX_SCHEMA}")
        entries = {_text(run_id): _entry(row) for run_id, row in _mapping(raw["runs"]).items()}
        _refuse_split_lineages(entries)
        skipped = frozenset(_text(name) for name in _list(raw["skipped"]))
    except (ValueError, KeyError, TypeError) as exc:  # JSON and UTF-8 decode errors are ValueErrors
        raise km.KernelModelError(
            f"{INDEX_PATH}: not a run index this gate can read: {exc}"
        ) from exc
    return MappingProxyType(entries), skipped


def _refuse_split_lineages(entries: Mapping[str, Entry]) -> None:
    """Every part names a listed root and carries its roles, so any part judges like the whole."""
    for run_id, entry in entries.items():
        root = entries.get(entry.lineage_root)
        if root is None:
            raise ValueError(f"run {run_id}'s lineage root {entry.lineage_root} is not listed")
        if entry.roles != root.roles:
            raise ValueError(f"run {run_id} and its lineage root {entry.lineage_root} differ")


def _entry(row: Any) -> Entry:
    row = _mapping(row)
    roles = {_text(role): _standing(value) for role, value in _mapping(row["roles"]).items()}
    return Entry(
        _text(row["file"]),
        _text(row["sha256"]),
        _text(row["lineage_root"]),
        MappingProxyType(roles),
    )


def _standing(value: Any) -> Standing:
    value = _mapping(value)
    pairs, flip = value["complete_pairs"], value["flip"]
    if type(pairs) is not int or pairs < 0:
        raise ValueError(f"complete_pairs {pairs!r} is not a count")
    if flip not in FLIP_LABELS:
        raise ValueError(f"flip {flip!r} is none of {', '.join(FLIP_LABELS)}")
    return Standing(pairs, flip)


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{value!r} is not a mapping")
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{value!r} is not a list")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{value!r} is not text")
    return value
