"""A plugin update re-renders the global instructions with the user's own values, unasked.

On N+1's first session a marketplace install's `~/.claude/CLAUDE.md` reads as N+1's template
filled with the personal values N's render carried, even when a fresh install would derive other
values today; a default fills only a placeholder N never had a value for. A clone install's
instructions and a regular file the user owns are never touched, a dangling instructions link
recovers as a first install does, and the update path never asks a question.
"""

from __future__ import annotations

import os
import re

import pytest

from tests.acceptance.drivers import plugin_update as pu

ANSWER_WAIT_LIMIT = 20  # seconds: well under any prompt's own timeout, well over a refresh
QUESTION = re.compile(r"\?\s*$|\[y/n\]", re.IGNORECASE)


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


def _updated(sources, tmp_path_factory, instructions: str) -> pu.Update:
    n, n1, fresh = sources
    update = pu.prepare_update(
        tmp_path_factory.mktemp(instructions), n, n1, fresh, instructions=instructions
    )
    update.run()
    return update


@pytest.fixture(scope="module")
def updated(sources, tmp_path_factory) -> pu.Update:
    return _updated(sources, tmp_path_factory, "render")


def _n1_template(update: pu.Update) -> str:
    return (update.n1 / pu.TEMPLATE).read_text(encoding="utf-8")


def _script_link_refreshed(update: pu.Update) -> bool:
    """A script link N left behind now points into N+1's directory."""
    name = sorted(update.fresh.scripts)[len(pu.SCRIPT_ROLES)]
    return pu.inside(update.machine.bin / name, update.n1) == update.fresh.scripts[name]


def _rule_link_refreshed(update: pu.Update) -> bool:
    place = sorted(update.fresh.rules)[len(pu.RULE_ROLES)]
    return pu.inside(update.machine.rules / place, update.n1) == update.fresh.rules[place]


# -- N's render ------------------------------------------------------------------------------------


def test_the_instructions_read_as_the_new_template_filled_with_the_previous_values(updated):
    fresh_values = pu.values_in(updated.fresh.instructions, _n1_template(updated))
    assert fresh_values != updated.n_values, "the scenario needs today's derived values to differ"
    expected = pu.render(_n1_template(updated), updated.n_values)
    assert updated.machine.instructions.read_text(encoding="utf-8") == expected


@pytest.fixture(scope="module")
def updated_from_a_template_without_github(sources, tmp_path_factory) -> pu.Update:
    _, n1, fresh = sources
    root = tmp_path_factory.mktemp("no-github")
    n = pu.edited_template(pu.shipped_tree(root / "n"), pu.without_github_line)
    update = pu.prepare_update(root / "machine", n, n1, fresh)
    update.run()
    return update


def test_a_default_fills_only_the_placeholder_the_previous_render_had_no_value_for(
    updated_from_a_template_without_github,
):
    update = updated_from_a_template_without_github
    template = _n1_template(update)
    carried = update.n_values
    assert "GITHUB_URL" not in carried
    assert {"USERNAME", "EMAIL"} <= set(carried)
    default = pu.values_in(update.fresh.instructions, template)["GITHUB_URL"]
    expected = pu.render(template, {**carried, "GITHUB_URL": default})
    assert update.machine.instructions.read_text(encoding="utf-8") == expected


# -- Instructions the update never owns ------------------------------------------------------------


@pytest.fixture(scope="module")
def clone_install(sources, tmp_path_factory) -> pu.Update:
    return _updated(sources, tmp_path_factory, "clone")


@pytest.fixture(scope="module")
def user_owned(sources, tmp_path_factory) -> pu.Update:
    return _updated(sources, tmp_path_factory, "regular")


def test_a_clone_installs_instructions_link_keeps_pointing_into_the_clone(clone_install):
    key = str(clone_install.machine.instructions.relative_to(clone_install.machine.home))
    assert os.readlink(clone_install.machine.instructions) == clone_install.before[key][1]


def test_a_clone_installs_rendered_file_is_byte_identical_with_its_modification_time(
    clone_install,
):
    clone = clone_install.machine.root / "clone"
    assert pu.snapshot(clone) == clone_install.clone_before


def test_a_regular_file_instructions_is_left_byte_identical(user_owned):
    path = user_owned.machine.instructions
    assert not path.is_symlink()
    assert path.read_bytes() == b"# Instructions the user wrote and owns\n"


def test_a_regular_file_instructions_still_gets_its_script_and_rule_links_refreshed(user_owned):
    assert _script_link_refreshed(user_owned)
    assert _rule_link_refreshed(user_owned)


# -- A dangling instructions link ------------------------------------------------------------------


@pytest.fixture(scope="module")
def recovered(sources, tmp_path_factory) -> pu.Update:
    return _updated(sources, tmp_path_factory, "dangling")


def test_a_dangling_instructions_link_is_set_up_as_a_first_install_sets_it_up(recovered):
    assert (
        recovered.machine.instructions.read_text(encoding="utf-8") == recovered.fresh.instructions
    )


def test_a_dangling_instructions_link_still_gets_its_script_and_rule_links_refreshed(recovered):
    assert _script_link_refreshed(recovered)
    assert _rule_link_refreshed(recovered)


def test_a_dangling_instructions_link_leaves_a_clones_live_links_its_own(recovered):
    clone_script = recovered.machine.bin / recovered.roles["script:clone"]
    clone_rule = recovered.machine.rules / recovered.roles["rule:clone"]
    clone = recovered.machine.root / "clone"
    assert pu.inside(clone_script, clone)
    assert pu.inside(clone_rule, clone)


# -- Nothing is asked ------------------------------------------------------------------------------


@pytest.mark.parametrize("terminal", [True, False], ids=["terminal", "no-terminal"])
@pytest.mark.parametrize("instructions", ["render", "clone", "regular"])
def test_the_update_path_asks_nothing_and_waits_for_no_answer(
    sources, tmp_path_factory, instructions, terminal
):
    n, n1, fresh = sources
    update = pu.prepare_update(
        tmp_path_factory.mktemp(f"ask-{instructions}"), n, n1, fresh, instructions=instructions
    )
    session = update.run(terminal=terminal, timeout=ANSWER_WAIT_LIMIT)
    asked = [line for line in session.lines if QUESTION.search(line)]
    assert not session.timed_out, f"still waiting after {ANSWER_WAIT_LIMIT}s: {session.lines[-5:]}"
    assert not asked, f"the update path asked: {asked}"
