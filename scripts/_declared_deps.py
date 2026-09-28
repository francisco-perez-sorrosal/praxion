"""The declared non-code test-dependency list, `tests/declared-deps.toml`.

Layout, imports and path literals cannot reveal every edge -- a test may read
a file through a computed path, or a subprocess may. This list holds only
those edges, as a two-variant sum type:

- `[[dep]]`   -- these `paths` feed these `tests` (a declared edge);
- `[[inert]]` -- nothing reads these `paths` (a reviewable non-source exemption).

`parse()` is the smart constructor: every structural invariant is checked at
this boundary and a violation raises `DeclaredDepsError` naming it. The
resolver turns that into a `declared-deps-invalid` widen -- an entry is never
dropped silently, because a dropped entry is a test the resolver stops
selecting without anyone noticing. The one invariant that needs the test
inventory (every `tests` glob matches a tracked test file) is checked by
`validate_against_inventory()` at resolve time and never cached.

Contract: `skills/testing-strategy/references/test-selection.md`.
Stdlib-only: it runs under a bare `python3` (gate-liveness GL05).
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _test_inventory import matches_glob  # noqa: E402

SCHEMA_VERSION = 1
TOP_LEVEL_KEYS = frozenset({"schema", "dep", "inert"})
DEP_KEYS = frozenset({"paths", "tests", "why"})
INERT_KEYS = frozenset({"paths", "why"})


class DeclaredDepsError(ValueError):
    """The declared list violates an invariant; the message names which."""


@dataclass(frozen=True)
class DepEntry:
    paths: tuple[str, ...]
    tests: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class InertEntry:
    paths: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class DeclaredDeps:
    deps: tuple[DepEntry, ...]
    inert: tuple[InertEntry, ...]


EMPTY = DeclaredDeps(deps=(), inert=())


def parse(path: Path) -> DeclaredDeps:
    """Parse and validate the list; an absent file is an empty list."""
    if not path.is_file():
        return EMPTY
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise DeclaredDepsError(f"cannot parse {path.name}: {exc}") from exc
    schema = data.get("schema")
    if schema != SCHEMA_VERSION:
        raise DeclaredDepsError(f"schema must be {SCHEMA_VERSION} (got {schema!r})")
    _reject_unknown(data, TOP_LEVEL_KEYS, "top level")
    return DeclaredDeps(
        deps=tuple(_dep(entry, f"dep[{i}]") for i, entry in enumerate(_tables(data, "dep"))),
        inert=tuple(_inert(entry, f"inert[{i}]") for i, entry in enumerate(_tables(data, "inert"))),
    )


def _tables(data: dict[str, object], key: str) -> list[dict[str, object]]:
    tables = data.get(key, [])
    if not isinstance(tables, list) or not all(isinstance(t, dict) for t in tables):
        raise DeclaredDepsError(f"{key} must be an array of tables ([[{key}]])")
    return tables


def _reject_unknown(table: dict[str, object], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise DeclaredDepsError(f"{where}: unknown key(s) {', '.join(unknown)}")


def _dep(table: dict[str, object], where: str) -> DepEntry:
    _reject_unknown(table, DEP_KEYS, where)
    return DepEntry(
        paths=_relative_paths(table, "paths", where),
        tests=_relative_paths(table, "tests", where),
        why=_why(table, where),
    )


def _inert(table: dict[str, object], where: str) -> InertEntry:
    _reject_unknown(table, INERT_KEYS, where)
    return InertEntry(paths=_relative_paths(table, "paths", where), why=_why(table, where))


def _relative_paths(table: dict[str, object], key: str, where: str) -> tuple[str, ...]:
    value = table.get(key)
    if not isinstance(value, list) or not value:
        raise DeclaredDepsError(f"{where}.{key} must be a non-empty list")
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise DeclaredDepsError(f"{where}.{key} entry {entry!r} must be a non-empty string")
        if entry.startswith("/"):
            raise DeclaredDepsError(f"{where}.{key} entry {entry!r} must be repo-relative")
        if ".." in entry.split("/"):
            raise DeclaredDepsError(f"{where}.{key} entry {entry!r} must not contain '..'")
    return tuple(value)


def _why(table: dict[str, object], where: str) -> str:
    why = table.get("why")
    if not isinstance(why, str) or not why.strip():
        raise DeclaredDepsError(f"{where}.why must be a non-empty string")
    return why


def validate_against_inventory(value: DeclaredDeps, tracked_test_files: Iterable[str]) -> None:
    """Every `tests` glob must match at least one tracked test file."""
    files = tuple(tracked_test_files)
    for index, entry in enumerate(value.deps):
        for pattern in entry.tests:
            if not any(matches_glob(path, pattern) for path in files):
                raise DeclaredDepsError(
                    f"dep[{index}].tests glob {pattern!r} matches no tracked test file"
                )


def classify_path(value: DeclaredDeps, path: str) -> Literal["dep", "inert"] | None:
    """Which variant claims `path`. `dep` wins a tie -- the over-select direction."""
    if dep_entries_for(value, path):
        return "dep"
    if any(_claims(entry.paths, path) for entry in value.inert):
        return "inert"
    return None


def dep_entries_for(value: DeclaredDeps, path: str) -> tuple[DepEntry, ...]:
    return tuple(entry for entry in value.deps if _claims(entry.paths, path))


def _claims(patterns: Iterable[str], path: str) -> bool:
    return any(matches_glob(path, pattern) for pattern in patterns)
