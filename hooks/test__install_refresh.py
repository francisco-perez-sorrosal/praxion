"""The update path's pure core: which links count as the plugin cache, which
state a global instructions entry is in, and what to do to each script link.

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
    BinEntry,
    CachedRender,
    EntryKind,
    ForeignLink,
    InstructionsSnapshot,
    Keep,
    Link,
    MissingCachedRender,
    NoInstructions,
    OfferedScript,
    Remove,
    Repoint,
    SnapshotKind,
    UserOwned,
    cache_version_dir,
    classify_instructions,
    plan_script_links,
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


# -- The script-link planner ------------------------------------------------------

BIN_DIR = "/home/example/.local/bin"
OLD_VERSION_DIR = "/home/example/.claude/plugins/cache/example-market/praxion/0.59.0"
OFFERED = OfferedScript("tool", f"{VERSION_DIR}/scripts/tool")
OLD_TOOL = f"{OLD_VERSION_DIR}/scripts/tool"
CLONE_TOOL = "/home/example/dev/praxion/scripts/tool"
# The offered script reached through a relative text, so only its real path equals the offer.
RELATIVE_TO_OFFERED = "../../.claude/plugins/cache/example-market/praxion/0.60.0/scripts/tool"


def _bin_link(name: str, text: str, real: str | None) -> BinEntry:
    return BinEntry(name, EntryKind.LINK, text, real)


def _plan(entries: list, offered: list) -> tuple:
    return plan_script_links(entries, offered, BIN_DIR)


def test_link_into_another_cached_version_under_an_offered_name_is_repointed():
    plan = _plan([_bin_link("tool", OLD_TOOL, OLD_TOOL)], [OFFERED])
    assert plan == (Repoint("tool", OFFERED.path),)


def test_dangling_link_into_a_removed_cached_version_under_an_offered_name_is_repointed():
    plan = _plan([_bin_link("tool", OLD_TOOL, None)], [OFFERED])
    assert plan == (Repoint("tool", OFFERED.path),)


def test_link_whose_text_is_the_offered_path_is_kept():
    plan = _plan([_bin_link("tool", OFFERED.path, OFFERED.path)], [OFFERED])
    assert plan == (Keep("tool"),)


def test_link_whose_real_path_is_the_offered_path_is_kept_whatever_its_text():
    plan = _plan([_bin_link("tool", RELATIVE_TO_OFFERED, OFFERED.path)], [OFFERED])
    assert plan == (Keep("tool"),)


def test_offered_name_with_no_entry_is_linked():
    assert _plan([], [OFFERED]) == (Link("tool", OFFERED.path),)


def test_cache_link_under_a_dropped_name_is_removed():
    plan = _plan([_bin_link("gone", f"{OLD_VERSION_DIR}/scripts/gone", None)], [OFFERED])
    assert Remove("gone") in plan


def test_new_versions_own_link_under_a_dropped_name_is_removed():
    own = _bin_link("gone", f"{VERSION_DIR}/scripts/gone", f"{VERSION_DIR}/scripts/gone")
    assert _plan([own], []) == (Remove("gone"),)


def test_regular_file_under_an_offered_name_is_not_acted_on():
    entry = BinEntry("tool", EntryKind.FILE, "", None)
    assert _plan([entry], [OFFERED]) == ()


def test_directory_under_an_offered_name_is_not_acted_on():
    entry = BinEntry("tool", EntryKind.OTHER, "", None)
    assert _plan([entry], [OFFERED]) == ()


def test_live_clone_link_under_an_offered_name_is_never_touched():
    assert _plan([_bin_link("tool", CLONE_TOOL, CLONE_TOOL)], [OFFERED]) == ()


def test_dangling_link_outside_the_cache_under_an_offered_name_is_never_touched():
    assert _plan([_bin_link("tool", "/gone/tool", None)], [OFFERED]) == ()


def test_clone_link_under_a_dropped_name_is_never_removed():
    assert _plan([_bin_link("old", CLONE_TOOL, CLONE_TOOL)], []) == ()


def test_one_run_plans_every_kind_of_action_in_a_stable_order():
    offered = [OFFERED, OfferedScript("fresh", f"{VERSION_DIR}/scripts/fresh")]
    entries = [_bin_link("tool", OLD_TOOL, OLD_TOOL), _bin_link("gone", OLD_TOOL, None)]
    assert _plan(entries, offered) == (
        Repoint("tool", OFFERED.path),
        Link("fresh", f"{VERSION_DIR}/scripts/fresh"),
        Remove("gone"),
    )


def test_the_same_input_plans_the_same_actions():
    entries = [_bin_link("tool", OLD_TOOL, OLD_TOOL), _bin_link("gone", OLD_TOOL, None)]
    assert _plan(entries, [OFFERED]) == _plan(list(entries), [OFFERED])


def test_actions_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Repoint("tool", "/x").name = "other"  # type: ignore[misc]


# Every target class a link can have, as (text, real); `real` is None when it dangles.
TARGET_CLASSES = {
    "other-version-live": (OLD_TOOL, OLD_TOOL),
    "other-version-dangling": (OLD_TOOL, None),
    "own-version-by-text": (OFFERED.path, OFFERED.path),
    "own-version-by-real-path": (RELATIVE_TO_OFFERED, OFFERED.path),
    "clone-live": (CLONE_TOOL, CLONE_TOOL),
    "outside-dangling": ("/gone/tool", None),
}


def _entry_of(kind: EntryKind, target_class: str) -> BinEntry:
    text, real = TARGET_CLASSES[target_class] if kind is EntryKind.LINK else ("", None)
    return BinEntry("tool", kind, text, real)


def _offered_list(offered: bool) -> list:
    return [OFFERED] if offered else []


def _forbidden_actions(plan: tuple, entry: BinEntry) -> list:
    """Actions that break the invariant: only a cache link may be named by anything but Keep.

    Link is forbidden too, since it names a free name and these tables always hold an entry.
    """
    is_cache_link = entry.kind is EntryKind.LINK and cache_version_dir(entry.text, BIN_DIR)
    return [
        action
        for action in plan
        if not isinstance(action, Keep) and (isinstance(action, Link) or not is_cache_link)
    ]


@pytest.mark.parametrize("offered", [True, False], ids=["offered", "dropped"])
@pytest.mark.parametrize("target_class", list(TARGET_CLASSES))
@pytest.mark.parametrize("kind", list(EntryKind))
def test_no_action_but_keep_names_an_entry_that_is_not_a_cache_link(kind, target_class, offered):
    entry = _entry_of(kind, target_class)
    assert _forbidden_actions(_plan([entry], _offered_list(offered)), entry) == []


@pytest.mark.parametrize(
    ("target_class", "offered", "expected"),
    [
        ("other-version-live", True, Repoint("tool", OFFERED.path)),
        ("other-version-dangling", True, Repoint("tool", OFFERED.path)),
        ("own-version-by-text", True, Keep("tool")),
        ("own-version-by-real-path", True, Keep("tool")),
        ("clone-live", True, None),
        ("outside-dangling", True, None),
        ("other-version-live", False, Remove("tool")),
        ("other-version-dangling", False, Remove("tool")),
        ("own-version-by-text", False, Remove("tool")),
        ("own-version-by-real-path", False, Remove("tool")),
        ("clone-live", False, None),
        ("outside-dangling", False, None),
    ],
)
def test_each_link_class_gets_exactly_its_action(target_class, offered, expected):
    plan = _plan([_entry_of(EntryKind.LINK, target_class)], _offered_list(offered))
    assert plan == (() if expected is None else (expected,))


@pytest.mark.parametrize("offered", [True, False], ids=["offered", "dropped"])
@pytest.mark.parametrize("kind", [EntryKind.FILE, EntryKind.OTHER])
def test_a_file_or_other_entry_gets_no_action_at_all(kind, offered):
    assert _plan([_entry_of(kind, "clone-live")], _offered_list(offered)) == ()
