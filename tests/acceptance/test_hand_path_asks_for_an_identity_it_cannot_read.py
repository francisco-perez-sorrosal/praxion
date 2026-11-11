"""The hand path replaces instructions it cannot read back only with the person's answers.

When `~/.claude/CLAUDE.md` links a cache render that does not read back (hand-edited, cut short,
another template's; N's or the installed version's own), or is absent, or links into the cache
and dangles, the command asks for each personal value at a prompt in the person's terminal,
offering the derived value as the default, then shows the values it will write for the person to
confirm, and only then makes the instructions read as the
installed template filled with what the person gave or accepted. The render the link pointed to
is never modified. Declined at that confirmation, the instructions are named as skipped with
how to finish them. Declined, or with an input that ends before an answer, nothing about the
instructions changes and no personal value is written. The values the person gives are written
into the rendered instructions and nowhere else.
"""

from __future__ import annotations

import re
import time

import pytest

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import plugin_update as pu

TYPING = hc.Person(values=hc.TYPED)
HOW_TO_FINISH = re.compile(r"--complete-install|/praxion-complete-install")


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


def _unreadable_update(sources, scratch, how: str, where: str = "earlier") -> pu.Update:
    """An update whose instructions link a render that does not read back."""
    n, n1, fresh = sources
    update = pu.prepare_update(scratch, n, n1, fresh)
    target = (update.n if where == "earlier" else update.n1) / pu.RENDER
    target.write_text(hc.unreadable(update, how), encoding="utf-8")
    hc.point_instructions_at(update.machine, target)
    return update


@pytest.fixture(
    scope="module",
    params=[
        ("hand-edited", "earlier"),
        ("cut-short", "earlier"),
        ("another-template", "earlier"),
        ("hand-edited", "installed"),
    ],  # fmt: skip
    ids=lambda p: f"{p[0]}-{p[1]}",
)
def answered(request, sources, tmp_path_factory):
    how, where = request.param
    update = _unreadable_update(sources, tmp_path_factory.mktemp(f"{how}-{where}"), how, where)
    pointed_at = pu.snapshot(update.machine.instructions.resolve().parent)
    previous = update.machine.instructions.resolve()
    since = time.time()
    run = hc.run_command(update.n1, update.machine, TYPING)
    return update, run, previous, pointed_at, since


# -- Answered -------------------------------------------------------------------------------------


def test_the_instructions_read_as_the_installed_template_filled_with_the_given_values(answered):
    update, _, _, _, _ = answered
    expected = pu.render(hc.n1_template(update), hc.TYPED)

    assert update.machine.instructions.read_text(encoding="utf-8") == expected


def test_each_personal_value_is_asked_for(answered):
    _, run, _, _, _ = answered
    asked = {p.topic.partition(":")[2] for p in run.asked("value")}

    assert asked == set(hc.VALUE_NAMES), f"asked for {sorted(asked)}: {run.transcript[-1500:]}"


@pytest.mark.parametrize("name", hc.VALUE_NAMES)
def test_each_question_offers_the_derived_value_as_its_default(answered, name):
    update, run, _, _, _ = answered
    derived = hc.derived_values(update)[name]

    assert any(derived in p.text for p in run.value_questions), (
        f"no question about {name} offers {derived!r}: {[p.text for p in run.value_questions]}"
    )


def test_after_the_last_value_the_values_to_be_written_are_shown_for_confirmation(answered):
    _, run, _, _, _ = answered
    shown = "\n".join(p.text for p in run.confirmations)

    assert run.confirmations, f"no confirmation followed the values: {run.transcript[-1500:]}"
    assert hc.TYPED["EMAIL"] in shown, f"the confirmation does not show the values: {shown!r}"
    assert hc.TYPED["USERNAME"] in shown, f"the confirmation does not show the values: {shown!r}"


def test_the_render_the_link_pointed_to_is_never_modified(answered):
    _, _, previous, pointed_at, _ = answered

    assert pu.snapshot(previous.parent)[previous.name] == pointed_at[previous.name]


def test_the_given_values_are_written_into_the_rendered_instructions_and_nowhere_else(answered):
    update, _, _, _, _ = answered
    rendered = update.machine.instructions.resolve()
    holders = {
        name: [str(p) for p in hc.files_holding(update.machine.root, hc.TYPED[name])]
        for name in ("USERNAME", "EMAIL")
    }

    assert holders == {"USERNAME": [str(rendered)], "EMAIL": [str(rendered)]}


def test_no_log_written_during_the_run_holds_a_given_value(answered):
    update, _, _, _, since = answered
    leaked = [
        str(p)
        for p in pu.logs_written(update.machine.root, since)
        if any(v.encode() in p.read_bytes() for v in hc.TYPED.values())
    ]

    assert leaked == []


def test_the_run_is_reported_done_once_the_instructions_are_set_up(answered):
    update, run, _, _, _ = answered
    expected = pu.render(hc.n1_template(update), hc.TYPED)

    assert update.machine.instructions.read_text(encoding="utf-8") == expected
    assert run.says_done, run.report


@pytest.fixture(scope="module")
def defaults_accepted(sources, tmp_path_factory):
    update = _unreadable_update(sources, tmp_path_factory.mktemp("defaults"), "hand-edited")
    run = hc.run_command(update.n1, update.machine, hc.Person())
    return update, run


def test_pressing_enter_at_each_question_renders_the_derived_values(defaults_accepted):
    update, run = defaults_accepted
    expected = pu.render(hc.n1_template(update), hc.derived_values(update))

    assert run.value_questions, "the command never asked about the personal values"
    assert update.machine.instructions.read_text(encoding="utf-8") == expected


# -- Declined -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def declined_at_the_values(sources, tmp_path_factory):
    update = _unreadable_update(sources, tmp_path_factory.mktemp("declined"), "hand-edited")
    before = hc.instructions_state(update.machine)
    run = hc.run_command(update.n1, update.machine, hc.Person(at_values="decline"))
    return update, run, before


def test_declining_at_the_values_prompt_leaves_the_link_and_every_render_byte_identical(
    declined_at_the_values,
):
    update, run, before = declined_at_the_values

    assert run.value_questions, "the command never asked about the personal values"
    assert hc.instructions_state(update.machine) == before


def test_declining_at_the_confirmation_names_the_instructions_skipped_and_how_to_finish(
    declined_at_the_values,
):
    _, run, _ = declined_at_the_values

    assert run.confirmations, "no confirmation followed the values"
    assert "skip" in run.instructions_report.lower(), run.report
    assert HOW_TO_FINISH.search(run.instructions_report), run.report


def test_declining_at_the_values_prompt_is_not_reported_done(declined_at_the_values):
    _, run, _ = declined_at_the_values

    assert run.value_questions, "the command never asked about the personal values"
    assert not run.says_done, run.report


# -- Missing instructions -------------------------------------------------------------------------


@pytest.fixture(scope="module", params=["absent", "dangling-into-the-cache"])
def missing(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp(request.param), n, n1, fresh)
    if request.param == "absent":
        update.machine.instructions.unlink()
    else:
        (update.n / pu.RENDER).unlink()
    run = hc.run_command(update.n1, update.machine, TYPING)
    return update, run


def test_missing_instructions_are_set_up_with_the_given_values(missing):
    update, run = missing
    expected = pu.render(hc.n1_template(update), hc.TYPED)

    assert run.asked("value"), "the command never asked for the personal values"
    assert update.machine.instructions.exists(), "the instructions are still missing"
    assert update.machine.instructions.read_text(encoding="utf-8") == expected


# -- No answer ------------------------------------------------------------------------------------


@pytest.fixture(
    scope="module",
    params=[
        ("hand-edited", "at-the-offer"),
        ("hand-edited", "at-the-values"),
        ("absent", "at-the-values"),
    ],  # fmt: skip
    ids=lambda p: f"{p[0]}-input-ends-{p[1]}",
)
def unanswered(request, sources, tmp_path_factory):
    state, when = request.param
    scratch = tmp_path_factory.mktemp(f"{state}-{when}")
    if state == "absent":
        n, n1, fresh = sources
        update = pu.prepare_update(scratch, n, n1, fresh)
        update.machine.instructions.unlink()
    else:
        update = _unreadable_update(sources, scratch, state)
    before = hc.instructions_state(update.machine)
    person = hc.Person(instructions="end") if when == "at-the-offer" else hc.Person(at_values="end")
    run = hc.run_command(update.n1, update.machine, person)
    return update, run, before, when


def test_an_input_that_ends_reaches_a_question_about_the_instructions(unanswered):
    _, run, _, when = unanswered
    reached = run.offers if when == "at-the-offer" else run.value_questions

    assert reached, f"no question {when} was reached: {[(p.topic, p.text) for p in run.prompts]}"
    assert reached[0].answer == hc.END_OF_INPUT.decode(), (
        f"the input never ended at a question {when}: {[(p.topic, p.text) for p in run.prompts]}"
    )


def test_an_input_that_ends_leaves_the_instructions_and_every_render_as_they_were(unanswered):
    update, _, before, _ = unanswered

    assert hc.instructions_state(update.machine) == before


def test_an_input_that_ends_writes_no_derived_value(unanswered):
    update, _, _, _ = unanswered
    derived = hc.derived_values(update)
    gitconfig = update.machine.home / ".gitconfig"
    written = [
        str(p)
        for name in ("USERNAME", "EMAIL")
        for p in hc.files_holding(update.machine.home, derived[name])
        if p != gitconfig
    ]

    assert written == []


def test_an_input_that_ends_never_reports_the_instructions_set_up(unanswered):
    _, run, _, _ = unanswered

    assert run.offers or run.value_questions, "the command never asked about the instructions"
    assert not run.says_done, run.report
