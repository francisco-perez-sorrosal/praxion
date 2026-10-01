"""Praxion's footprint registry stays parseable, live, and in step with the selector sources.

`.ai-state/FOOTPRINTS.md` names the paths each measurable cost lives in. Three
lists of the test-selection sources exist (`SELECTOR_FILES`, the measurer's
`RESOLVER_MODULES`, this registry), so the row is pinned to `SELECTOR_FILES`
here: a source added to the resolver without the registry row would let a change
move the selection size with no criterion required.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_footprint_criteria as cfc  # noqa: E402
from _footprint_grammar import Footprint, Registry, parse_registry  # noqa: E402
from resolve_test_scope import SELECTOR_FILES  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
REGISTRY_FILE = REPO / ".ai-state" / "FOOTPRINTS.md"
DECLARED_DEPS = "tests/declared-deps.toml"
SELECTION_ROW = "test-selection-size"
TOKEN_ROWS = ("always-loaded-tokens", "listing-tokens")
EXPECTED_ROWS = (
    SELECTION_ROW,
    *TOKEN_ROWS,
    "prompt-size",
    "hook-latency",
    "observation-log-volume",
    "spawn-count",
)


def selection_sources_missing(row: Footprint) -> frozenset[str]:
    """The selector sources and the declared list that the row's include globs do not cover."""
    wanted = SELECTOR_FILES | {DECLARED_DEPS}
    return frozenset(path for path in wanted if not cfc.footprint_paths(row, (path,)))


def tracked_files() -> tuple[str, ...]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True, text=True
    )
    return tuple(p for p in out.stdout.split("\0") if p)


@pytest.fixture(scope="module")
def registry() -> Registry:
    parsed = parse_registry(REGISTRY_FILE.read_text(encoding="utf-8"))
    assert not parsed.findings, [f.message for f in parsed.findings]
    assert isinstance(parsed.registry, Registry)
    return parsed.registry


def row_named(registry: Registry, name: str) -> Footprint:
    return next(fp for fp in registry.footprints if fp.name == name)


def test_registry_holds_the_seven_footprints(registry: Registry) -> None:
    assert tuple(fp.name for fp in registry.footprints) == EXPECTED_ROWS


def test_every_include_glob_matches_a_tracked_file(registry: Registry) -> None:
    assert cfc.dead_globs(registry, tracked_files()) == ()


def test_selection_row_covers_every_selector_source_and_the_declared_list(
    registry: Registry,
) -> None:
    assert selection_sources_missing(row_named(registry, SELECTION_ROW)) == frozenset()


def test_the_selection_assertion_fails_when_a_member_is_dropped(registry: Registry) -> None:
    """Canary: the assertion above can fail."""
    row = row_named(registry, SELECTION_ROW)
    dropped = sorted(SELECTOR_FILES)[0]
    narrowed = dataclasses.replace(
        row, include_globs=tuple(g for g in row.include_globs if g != dropped)
    )
    assert selection_sources_missing(narrowed) == {dropped}


@pytest.mark.parametrize("name", TOKEN_ROWS)
def test_token_rows_forbid_the_ratcheting_flag(registry: Registry, name: str) -> None:
    row = row_named(registry, name)
    assert row.command is not None
    assert "--json" in row.command
    assert "--ratchet" not in row.command
    assert "never" in row.reading
    assert "--ratchet" in row.reading


def test_suite_elapsed_time_stays_unregistered(registry: Registry) -> None:
    assert not any("suite" in fp.name or "elapsed" in fp.name for fp in registry.footprints)
