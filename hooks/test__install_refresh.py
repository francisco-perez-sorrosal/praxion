"""The update path's pure core: which links count as the plugin cache, and which
state a global instructions entry is in.

Both are lexical, so the tests need no filesystem and no mock: snapshots are
built by hand. The cache table is the same file the bash rule is tested against,
which keeps the two implementations of "what counts as the cache" equal.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

# Flat import, as the sibling hook tests do: the mutation sensor runs this
# directory's files side by side, so a package-qualified import would escape it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _install_refresh import (  # noqa: E402
    CachedRender,
    ForeignLink,
    InstructionsSnapshot,
    MissingCachedRender,
    NoInstructions,
    SnapshotKind,
    UserOwned,
    cache_version_dir,
    classify_instructions,
    unreachable,
)

CACHE_TARGETS_TABLE = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "plugin_cache_targets.tsv"
)
LINK_DIR = "/home/example/.claude"
VERSION_DIR = "/home/example/.claude/plugins/cache/example-market/praxion/0.60.0"


def _cache_rows() -> list:
    lines = CACHE_TARGETS_TABLE.read_text().splitlines()[1:]
    rows = [line.split("\t") for line in lines if line]
    return [
        pytest.param(link_dir, target, is_cache == "true", id=label)
        for label, link_dir, target, is_cache in rows
    ]


def _link(target: str, *, resolves: bool = True) -> InstructionsSnapshot:
    return InstructionsSnapshot(SnapshotKind.LINK, target, resolves)


@pytest.mark.parametrize(("link_dir", "target", "is_cache"), _cache_rows())
def test_table_row_is_classified_as_the_cache_or_not(link_dir, target, is_cache):
    assert (cache_version_dir(target, link_dir) is not None) is is_cache


def test_table_has_the_clone_shaped_rows():
    assert len(_cache_rows()) >= 12


def test_plugin_root_returns_its_own_version_directory():
    assert cache_version_dir(VERSION_DIR, LINK_DIR) == VERSION_DIR


def test_file_inside_the_cache_returns_the_enclosing_version_directory():
    assert cache_version_dir(f"{VERSION_DIR}/rules/swe/x.md", LINK_DIR) == VERSION_DIR


def test_relative_text_is_joined_to_the_link_directory():
    relative = "plugins/cache/example-market/praxion/0.60.0/CLAUDE.md"
    assert cache_version_dir(relative, LINK_DIR) == VERSION_DIR


def test_dot_dot_segments_are_normalised_before_the_cache_is_judged():
    inside = f"{VERSION_DIR}/rules/../scripts/x.py"
    assert cache_version_dir(inside, LINK_DIR) == VERSION_DIR


def test_dot_dot_segments_leaving_the_version_directory_are_not_the_cache():
    outside = f"{VERSION_DIR}/../../../../../elsewhere/x.py"
    assert cache_version_dir(outside, LINK_DIR) is None


def test_no_entry_is_no_instructions():
    snapshot = InstructionsSnapshot(SnapshotKind.ABSENT, "", False)
    assert classify_instructions(snapshot, LINK_DIR) == NoInstructions()


@pytest.mark.parametrize("kind", [SnapshotKind.FILE, SnapshotKind.OTHER])
def test_regular_file_or_other_entry_is_user_owned(kind):
    assert classify_instructions(InstructionsSnapshot(kind, "", False), LINK_DIR) == UserOwned()


@pytest.mark.parametrize("resolves", [True, False])
def test_link_outside_every_cache_version_directory_is_foreign_whether_live_or_dangling(resolves):
    snapshot = _link("/home/example/dev/praxion/claude/config/CLAUDE.md", resolves=resolves)
    assert classify_instructions(snapshot, LINK_DIR) == ForeignLink()


def test_live_link_into_a_cache_version_directory_is_a_cached_render():
    snapshot = _link(f"{VERSION_DIR}/claude/config/CLAUDE.md")
    assert classify_instructions(snapshot, LINK_DIR) == CachedRender(VERSION_DIR)


def test_dangling_link_into_a_cache_version_directory_is_a_missing_cached_render():
    snapshot = _link(f"{VERSION_DIR}/claude/config/CLAUDE.md", resolves=False)
    assert classify_instructions(snapshot, LINK_DIR) == MissingCachedRender()


def test_relative_link_text_into_the_cache_is_a_cached_render():
    snapshot = _link("plugins/cache/example-market/praxion/0.60.0/CLAUDE.md")
    assert classify_instructions(snapshot, LINK_DIR) == CachedRender(VERSION_DIR)


@pytest.mark.parametrize("kind", list(SnapshotKind))
def test_every_snapshot_kind_maps_to_exactly_one_state(kind):
    snapshot = InstructionsSnapshot(kind, f"{VERSION_DIR}/CLAUDE.md", True)
    states = (NoInstructions, UserOwned, ForeignLink, CachedRender, MissingCachedRender)
    state = classify_instructions(snapshot, LINK_DIR)
    assert sum(isinstance(state, candidate) for candidate in states) == 1


def test_states_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        CachedRender(VERSION_DIR).version_dir = "elsewhere"  # type: ignore[misc]


def test_unreachable_names_the_value_it_was_given():
    with pytest.raises(AssertionError, match="unhandled"):
        unreachable("unhandled")
