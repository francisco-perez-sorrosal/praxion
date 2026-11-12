"""The hand path never takes over instructions it does not own, and says why it left them.

A regular-file `~/.claude/CLAUDE.md`, or a link outside the plugin cache (a clone checkout's
render, live or dangling), is left byte-identical with its modification time, as is whatever it
points to; nothing is offered or asked, and the closing report says the instructions were left
alone because they are the person's own file or a link outside the plugin cache. Run from a clone
checkout instead of a version directory, the command changes no instructions, asks for no
personal value, and names that checkout's `install.sh code` as the way to set them up.
"""

from __future__ import annotations

import re

import pytest

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import plugin_update as pu

LEFT_ALONE = re.compile(r"\bleft\b|\balone\b|untouched|not touch", re.IGNORECASE)
WHY = {
    "regular": re.compile(r"\byour own\b|\bown file\b|regular file", re.IGNORECASE),
    "clone": re.compile(r"outside", re.IGNORECASE),
    "outside-and-dangling": re.compile(r"outside", re.IGNORECASE),
}
CLONE_INSTALLER = re.compile(r"install\.sh\"?\s+code(?!\s+--complete)")


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


@pytest.fixture(scope="module", params=list(WHY))
def not_owned(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    kind = "clone" if request.param == "outside-and-dangling" else request.param
    update = pu.prepare_update(tmp_path_factory.mktemp(request.param), n, n1, fresh,
                               instructions=kind)  # fmt: skip
    clone = update.machine.root / "clone"
    if request.param == "outside-and-dangling":
        (clone / pu.RENDER).unlink()
    before = (pu.snapshot(update.machine.home / ".claude"), pu.snapshot(clone))
    run = hc.run_command(update.n1, update.machine, hc.Person(values=hc.TYPED))
    return update, run, before, request.param


def test_instructions_not_owned_are_left_byte_identical_with_what_they_point_to(not_owned):
    update, _, (home_before, clone_before), _ = not_owned
    key = "CLAUDE.md"

    assert pu.snapshot(update.machine.home / ".claude")[key] == home_before[key]
    assert pu.snapshot(update.machine.root / "clone") == clone_before


def test_instructions_not_owned_are_neither_offered_nor_asked_about(not_owned):
    _, run, _, _ = not_owned

    assert run.offers == [], [p.text for p in run.offers]
    assert run.value_questions == [], [p.text for p in run.value_questions]


def test_the_closing_report_says_why_the_instructions_were_left_alone(not_owned):
    _, run, _, kind = not_owned
    said = run.instructions_report

    assert LEFT_ALONE.search(said), f"the report never says they were left alone: {run.report}"
    assert WHY[kind].search(said), f"the report never says why ({kind}): {run.report}"


# -- Run from a clone checkout --------------------------------------------------------------------


@pytest.fixture(scope="module")
def from_a_checkout(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("from-a-checkout"), n, n1, fresh)
    checkout = pu.as_git_repository(pu.shipped_tree(update.machine.root / "own-checkout"))
    before = hc.instructions_state(update.machine)
    run = hc.run_command(checkout, update.machine, hc.Person(values=hc.TYPED))
    return update, run, before


def test_a_checkouts_command_changes_no_instructions(from_a_checkout):
    update, _, before = from_a_checkout

    assert hc.instructions_state(update.machine) == before


def test_a_checkouts_command_asks_for_no_personal_value(from_a_checkout):
    _, run, _ = from_a_checkout

    assert run.value_questions == [], [p.text for p in run.value_questions]


def test_a_checkouts_command_names_its_own_installer_for_the_instructions(from_a_checkout):
    _, run, _ = from_a_checkout

    assert CLONE_INSTALLER.search(run.instructions_report), run.report
