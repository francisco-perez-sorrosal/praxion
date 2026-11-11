"""The hand path finishes a stopped refresh with the identity the earlier render carried.

N was installed and rendered under one identity; the git identity has changed since, and N+1 is
the installed version, but `~/.claude/CLAUDE.md` still links N's render. Run in the person's own
terminal, `install.sh code --complete-install` offers the instructions change at its own prompt.
Accepted, `~/.claude/CLAUDE.md` reads as N+1's template filled with N's values, nothing is asked
about them, a derived value fills only a placeholder N carried no value for, and N's render is
left as it was. Declined, nothing about the instructions changes, and the report says how to finish them. Run again once current, it
changes nothing, asks nothing and says the instructions are current.
"""

from __future__ import annotations

import os
import re
import shutil

import pytest

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import plugin_update as pu

HOW_TO_FINISH = re.compile(r"--complete-install|/praxion-complete-install")


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


def _finished(update: pu.Update, person: hc.Person) -> hc.CommandRun:
    return hc.run_command(update.n1, update.machine, person)


@pytest.fixture(scope="module")
def accepted(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("accepted"), n, n1, fresh)
    n_render_before = (update.n / pu.RENDER).read_bytes()
    run = _finished(update, hc.Person())
    return update, run, n_render_before


# -- Accepted -------------------------------------------------------------------------------------


def test_the_instructions_change_is_offered_at_its_own_prompt(accepted):
    _, run, _ = accepted

    assert len(run.offers) == 1, f"instructions offers: {[p.text for p in run.offers]}"
    assert run.asked("rules"), "the rules are no longer offered"
    assert run.asked("scripts"), "the scripts are no longer offered"


def test_the_instructions_read_as_the_new_template_filled_with_the_earlier_values(accepted):
    update, _, _ = accepted
    assert hc.derived_values(update) != update.n_values, "the scenario needs the values to differ"
    expected = pu.render(hc.n1_template(update), update.n_values)

    assert update.machine.instructions.read_text(encoding="utf-8") == expected


def test_no_question_is_asked_about_the_personal_values(accepted):
    _, run, _ = accepted

    assert run.value_questions == [], [p.text for p in run.value_questions]


def test_the_earlier_render_is_left_byte_identical(accepted):
    update, _, before = accepted

    assert (update.n / pu.RENDER).read_bytes() == before


def test_the_instructions_still_read_the_same_once_the_earlier_version_is_removed(
    sources, tmp_path_factory
):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("removed"), n, n1, fresh)
    _finished(update, hc.Person())
    shutil.rmtree(update.n)
    expected = pu.render(hc.n1_template(update), update.n_values)

    assert update.machine.instructions.exists(), "the instructions dangle once N is removed"
    assert update.machine.instructions.read_text(encoding="utf-8") == expected


def test_the_closing_report_says_the_instructions_were_set_up_and_done(accepted):
    _, run, _ = accepted

    assert run.instructions_report, f"the closing report says nothing of them: {run.report}"
    assert run.says_done, f"no '{hc.DONE}' in the closing report: {run.report}"


# -- A placeholder the earlier render carried no value for ----------------------------------------


def _github_left_as_placeholder(update: pu.Update) -> None:
    values = {**update.n_values, "GITHUB_URL": "{{GITHUB_URL}}"}
    (update.n / pu.RENDER).write_text(pu.render(update.n_template, values), encoding="utf-8")


@pytest.fixture(scope="module", params=["no-line-for-it", "left-as-the-placeholder"])
def partly_carried(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    root = tmp_path_factory.mktemp(request.param)
    if request.param == "no-line-for-it":
        n = pu.edited_template(pu.shipped_tree(root / "n"), pu.without_github_line)
    update = pu.prepare_update(root / "machine", n, n1, fresh)
    if request.param == "left-as-the-placeholder":
        _github_left_as_placeholder(update)
    run = _finished(update, hc.Person())
    return update, run


def test_a_derived_value_fills_only_the_placeholder_the_earlier_render_carried_none_for(
    partly_carried,
):
    update, _ = partly_carried
    carried = {k: v for k, v in update.n_values.items() if k != "GITHUB_URL"}
    expected = pu.render(
        hc.n1_template(update), {**carried, "GITHUB_URL": hc.derived_values(update)["GITHUB_URL"]}
    )

    assert {"USERNAME", "EMAIL"} <= set(carried)
    assert update.machine.instructions.read_text(encoding="utf-8") == expected


# -- Declined -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def declined(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("declined"), n, n1, fresh)
    before = hc.instructions_state(update.machine)
    run = _finished(update, hc.Person(instructions="decline"))
    return update, run, before


def test_a_declined_offer_was_made(declined):
    _, run, _ = declined

    assert len(run.offers) == 1, "the command never offered the instructions change"


def test_a_declined_offer_writes_nothing_to_the_instructions_or_any_render(declined):
    update, _, before = declined

    assert hc.instructions_state(update.machine) == before


def test_a_declined_offer_says_how_to_finish_the_instructions(declined):
    _, run, _ = declined

    assert HOW_TO_FINISH.search(run.instructions_report), run.report


def test_a_declined_offer_is_named_as_skipped_and_the_run_is_not_called_done(declined):
    _, run, _ = declined

    assert "skip" in run.instructions_report.lower(), run.report
    assert not run.says_done, f"'{hc.DONE}' over instructions left behind: {run.report}"


# -- Already current ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def current(sources, tmp_path_factory):
    """The first session of N+1 re-rendered the instructions; the hand path then runs."""
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("current"), n, n1, fresh)
    update.run()
    assert pu.inside(update.machine.instructions, update.n1) == pu.RENDER, "no N+1 render to start"
    before = hc.instructions_state(update.machine)
    run = _finished(update, hc.Person())
    return update, run, before


def test_current_instructions_are_left_byte_identical(current):
    update, _, before = current

    assert hc.instructions_state(update.machine) == before


def test_current_instructions_are_neither_offered_nor_asked_about(current):
    _, run, _ = current

    assert run.offers == [], [p.text for p in run.offers]
    assert run.value_questions == [], [p.text for p in run.value_questions]


def test_current_instructions_are_reported_as_current(current):
    _, run, _ = current

    assert "current" in run.instructions_report.lower(), run.report


def test_a_second_run_after_finishing_finds_the_instructions_current(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("twice"), n, n1, fresh)
    _finished(update, hc.Person())
    before = hc.instructions_state(update.machine)
    again = _finished(update, hc.Person())

    assert hc.instructions_state(update.machine) == before
    assert again.offers == []
    assert again.value_questions == []
    assert os.path.realpath(update.machine.instructions) != os.path.realpath(update.n / pu.RENDER)
