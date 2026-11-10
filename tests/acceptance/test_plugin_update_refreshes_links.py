"""A plugin update refreshes the user's script and rule links on the new version's first session.

A marketplace install of N is updated to N+1 with no relink. On N+1's first session every link
that pointed into another version's directory of the plugin cache points into N+1's, every script
N+1 offers and every rule N+1 links has a link, a cache link for anything N+1 no longer offers is
gone, and nothing outside the cache (a clone checkout's link, a dangling link elsewhere, a regular
file) is touched. What N+1 offers and links is what a fresh install of N+1 links.
"""

from __future__ import annotations

import os
import shutil

import pytest

from tests.acceptance.drivers import plugin_update as pu


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


@pytest.fixture(scope="module")
def updated(sources, tmp_path_factory) -> pu.Update:
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("machine"), n, n1, fresh)
    update.run()
    return update


def _target(update: pu.Update, directory, place: str) -> str | None:
    """Where a link resolves, relative to N+1's directory; None when it lies outside it."""
    return pu.inside(directory / place, update.n1)


def _untouched(update: pu.Update, path) -> bool:
    key = str(path.relative_to(update.machine.home))
    before = update.before.get(key)
    if before is None or not os.path.lexists(path):
        return False
    st = path.lstat()
    now = ("link", os.readlink(path)) if path.is_symlink() else ("file",)
    return before[: len(now)] == now and before[2] == st.st_ino


# -- Scripts ---------------------------------------------------------------------------------------


def test_the_first_session_ends_with_a_success_status(updated):
    assert updated.session.exit_code == 0, updated.session.stderr[-2000:]


def test_script_links_into_the_previous_version_now_point_into_the_new_one(updated):
    planted = set(pu.SCRIPT_ROLES) | {"retired", "stray", "own"}
    special = {updated.roles[f"script:{r}"] for r in planted}
    expected = {name: rel for name, rel in updated.fresh.scripts.items() if name not in special}
    actual = {name: _target(updated, updated.machine.bin, name) for name in expected}
    assert actual == expected, "script links still pointing outside N+1's directory"


def test_a_script_link_into_a_skipped_older_version_now_points_into_the_new_one(updated):
    name = updated.roles["script:skipped"]
    assert _target(updated, updated.machine.bin, name) == updated.fresh.scripts[name]


def test_a_script_link_already_into_the_new_version_is_left_exactly_as_it_was(updated):
    assert _untouched(updated, updated.machine.bin / updated.roles["script:current"])


def test_a_script_the_new_version_offers_under_a_free_name_is_linked(updated):
    name = updated.roles["script:free"]
    assert (updated.machine.bin / name).is_symlink(), f"{name} was not linked"
    assert _target(updated, updated.machine.bin, name) == updated.fresh.scripts[name]


@pytest.mark.parametrize(
    "role",
    ["retired", "stray"],
    ids=["into-the-previous-version", "into-the-new-version"],
)
def test_a_cache_link_under_a_name_the_new_version_does_not_offer_is_removed(updated, role):
    path = updated.machine.bin / updated.roles[f"script:{role}"]
    assert not os.path.lexists(path), f"{path.name} still links to {os.readlink(path)}"


@pytest.mark.parametrize(
    "role",
    ["clone", "gone_outside", "own"],
    ids=["into-a-clone-checkout", "dangling-outside-the-cache", "a-users-own-tool"],
)
def test_a_script_link_outside_the_plugin_cache_is_never_touched(updated, role):
    assert _untouched(updated, updated.machine.bin / updated.roles[f"script:{role}"])


def test_a_regular_file_under_an_offered_script_name_is_left_byte_identical(updated):
    path = updated.machine.bin / updated.roles["script:regular"]
    assert not path.is_symlink()
    assert path.read_bytes() == pu.USER_PROGRAM


# -- Rules ----------------------------------------------------------------------------------------


def test_rule_links_into_the_previous_version_now_point_into_the_new_one(updated):
    planted = set(pu.RULE_ROLES) | {"retired", "stray", "own"}
    special = {updated.roles[f"rule:{r}"] for r in planted}
    expected = {place: rel for place, rel in updated.fresh.rules.items() if place not in special}
    actual = {place: _target(updated, updated.machine.rules, place) for place in expected}
    assert actual == expected, "rule links still pointing outside N+1's directory"


def test_a_dangling_rule_link_into_a_skipped_older_version_now_points_into_the_new_one(updated):
    place = updated.roles["rule:skipped"]
    assert _target(updated, updated.machine.rules, place) == updated.fresh.rules[place]


def test_a_rule_link_already_into_the_new_version_is_left_exactly_as_it_was(updated):
    assert _untouched(updated, updated.machine.rules / updated.roles["rule:current"])


@pytest.mark.parametrize(
    "role", ["missing", "gone_outside"], ids=["empty-place", "dangling-link-outside-the-cache"]
)
def test_a_rule_the_new_version_links_gets_a_link_at_an_empty_or_dangling_place(updated, role):
    place = updated.roles[f"rule:{role}"]
    assert _target(updated, updated.machine.rules, place) == updated.fresh.rules[place]


def test_the_cache_links_among_the_rules_are_exactly_the_rules_the_new_version_links(updated):
    in_cache = {
        place: pu.inside(updated.machine.rules / place, updated.machine.cache)
        for place in pu.links(updated.machine.rules)
    }
    linked = {place for place, rel in in_cache.items() if rel is not None}
    assert linked == set(updated.fresh.rules) - {
        updated.roles["rule:clone"],
        updated.roles["rule:regular"],
    }


@pytest.mark.parametrize(
    "role", ["retired", "stray"], ids=["into-the-previous-version", "into-the-new-version"]
)
def test_a_cache_link_at_a_place_the_new_version_does_not_link_is_removed(updated, role):
    path = updated.machine.rules / updated.roles[f"rule:{role}"]
    assert not os.path.lexists(path), f"{path.name} still links to {os.readlink(path)}"


@pytest.mark.parametrize(
    "role", ["clone", "own"], ids=["a-clone-checkouts-rule", "a-personal-rule"]
)
def test_a_live_rule_link_outside_the_plugin_cache_is_never_touched(updated, role):
    assert _untouched(updated, updated.machine.rules / updated.roles[f"rule:{role}"])


def test_a_regular_file_at_a_rules_place_is_left_byte_identical(updated):
    path = updated.machine.rules / updated.roles["rule:regular"]
    assert not path.is_symlink()
    assert path.read_bytes() == pu.USER_RULE


# -- Removing the old version ---------------------------------------------------------------------


def test_removing_the_previous_versions_leaves_everything_refreshed_resolving(
    sources, tmp_path_factory
):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("removal"), n, n1, fresh)
    update.run()
    shutil.rmtree(update.n)
    shutil.rmtree(update.machine.version(pu.OLDER))
    cache_links = [
        directory / place
        for directory in (update.machine.bin, update.machine.rules)
        for place, text in pu.links(directory).items()
        if str(update.machine.cache) in text or pu.inside(directory / place, update.machine.cache)
    ]
    broken = [str(p) for p in [update.machine.instructions, *cache_links] if not p.exists()]
    assert not broken, f"left unresolved once the previous versions were removed: {broken}"
