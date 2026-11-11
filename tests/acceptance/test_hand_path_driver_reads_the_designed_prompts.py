"""The command driver reads each prompt of the hand path's designed conversation as what it is.

The conversation is the offer (`[1] Bring ~/.claude/CLAUDE.md to this version` / `[2] Skip
instructions` / `Choice [1]:`), one free-text line per personal value (`Username [<derived>]:`,
`Email [<derived>]:`, `GitHub URL [<derived>]:`), the confirmation (the values, then `Write these
to ~/.claude/CLAUDE.md? [Y/n]:`), the rules and scripts offers with their present text, and an end
of input that is Ctrl-D on an empty line and on every later prompt. Fixed prompt transcripts are
fed to the driver's conversation; no command runs.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers import hand_path_command as hc

OFFER = (
    "\n  Your ~/.claude/CLAUDE.md is an earlier version's render that cannot be read back.\n"
    "\n  [1] Bring ~/.claude/CLAUDE.md to this version\n"
    "  [2] Skip instructions\n"
    "\n  Choice [1]: "
)
RULES_OFFER = (
    "\n  [1] Symlink rules to ~/.claude/rules/?\n"
    "      Auto-loaded by Claude Code. Shapes agent behavior globally\n"
    "      across every project — coding style, coordination protocols,\n"
    "      id-citation-discipline, ADR conventions, etc.\n"
    "  [2] Skip rules\n"
    "\n  Choice [1]: "
)
SCRIPTS_OFFER = (
    "\n  [1] Symlink CLI scripts to ~/.local/bin/?\n"
    "      check_id_citation_discipline.py, praxion-parallel (multi-session launcher),\n"
    "      chronograph-ctl, phoenix-ctl, onboard-project — runnable from any\n"
    "      shell. Filters internal helpers (merge drivers, git hooks).\n"
    "  [2] Skip scripts\n"
    "\n  Choice [1]: "
)
DERIVED = {
    "USERNAME": "madeup-user",
    "EMAIL": "madeup@example.invalid",
    "GITHUB_URL": "https://example.invalid/madeup",
}
LABELS = {"USERNAME": "Username", "EMAIL": "Email", "GITHUB_URL": "GitHub URL"}


def value_line(name: str, default: str | None = None) -> str:
    return f"\n  {LABELS[name]} [{default or DERIVED[name]}]: "


def confirmation(*, extra: str = "") -> str:
    return (
        "\n  These will be written:\n"
        f"    Username:   {hc.TYPED['USERNAME']}\n"
        f"    Email:      {hc.TYPED['EMAIL']}\n"
        f"    GitHub URL: {hc.TYPED['GITHUB_URL']}\n"
        f"{extra}"
        "\n  Write these to ~/.claude/CLAUDE.md? [Y/n]: "
    )


def conversation(person: hc.Person) -> hc._Conversation:
    return hc._Conversation(person)


# -- The offer ------------------------------------------------------------------------------------


def test_accepting_the_instructions_offer_picks_bring_it_to_this_version():
    talk = conversation(hc.Person())

    assert talk.answer(OFFER) == b"1\n"
    assert [p.topic for p in talk.prompts] == ["instructions"]


def test_declining_the_instructions_offer_picks_skip():
    talk = conversation(hc.Person(instructions="decline"))

    assert talk.answer(OFFER) == b"2\n"
    assert [p.topic for p in talk.prompts] == ["instructions"]


# -- The value lines ------------------------------------------------------------------------------

# A derived default may hold any word the driver once searched a line for.
TRAPPED_DEFAULTS = [
    (
        "USERNAME",
        "github-handle",
    ),  # the golden bad case: a Username line whose default holds github
    ("USERNAME", "email-person"),
    ("EMAIL", "github-user@example.invalid"),
    ("GITHUB_URL", "https://example.invalid/email-user"),
]


@pytest.mark.parametrize("name", hc.VALUE_NAMES)
def test_each_value_line_is_read_as_the_value_its_label_names(name):
    talk = conversation(hc.Person(values=hc.TYPED))
    talk.answer(OFFER)

    reply = talk.answer(value_line(name))

    assert talk.prompts[-1].topic == f"value:{name}"
    assert reply == f"{hc.TYPED[name]}\n".encode()


@pytest.mark.parametrize(("name", "default"), TRAPPED_DEFAULTS)
def test_a_value_line_is_read_by_its_label_and_never_by_the_default_it_shows(name, default):
    talk = conversation(hc.Person(values=hc.TYPED))
    talk.answer(OFFER)

    reply = talk.answer(value_line(name, default))

    assert talk.prompts[-1].topic == f"value:{name}", (
        f"{value_line(name, default).strip()!r} was read as {talk.prompts[-1].topic}"
    )
    assert reply == f"{hc.TYPED[name]}\n".encode()


@pytest.mark.parametrize("name", hc.VALUE_NAMES)
def test_an_empty_answer_takes_the_derived_value_when_the_person_types_nothing(name):
    talk = conversation(hc.Person())
    talk.answer(OFFER)

    assert talk.answer(value_line(name)) == b"\n"


# -- The confirmation -----------------------------------------------------------------------------


def after_the_value_lines(person: hc.Person) -> hc._Conversation:
    talk = conversation(person)
    talk.answer(OFFER)
    for name in hc.VALUE_NAMES:
        talk.answer(value_line(name))
    return talk


def test_the_confirmation_after_the_last_value_is_confirmed_with_y():
    talk = after_the_value_lines(hc.Person(values=hc.TYPED))

    assert talk.answer(confirmation()) == b"y\n"
    assert talk.prompts[-1].topic == "values"


def test_the_confirmation_is_declined_with_n_when_the_person_declines_the_values():
    talk = after_the_value_lines(hc.Person(values=hc.TYPED, at_values="decline"))

    assert talk.answer(confirmation()) == b"n\n"


def test_a_confirmation_whose_lines_hold_the_word_default_is_still_a_confirmation():
    talk = after_the_value_lines(hc.Person(values=hc.TYPED))
    noted = "\n  Press Enter to take the default.\n"

    reply = talk.answer(confirmation(extra=noted))

    assert reply == b"y\n", f"a confirmation was read as another question: {talk.prompts[-1]}"


def test_the_confirmation_is_the_values_question_asked_after_the_last_value_line():
    talk = after_the_value_lines(hc.Person(values=hc.TYPED))
    talk.answer(confirmation())
    run = hc.CommandRun(0, "", talk.prompts, [], timed_out=False)

    assert [p.text for p in run.confirmations] == [talk.prompts[-1].text]
    assert hc.TYPED["EMAIL"] in run.confirmations[0].text
    assert [p.topic for p in run.asked("value")] == [f"value:{n}" for n in hc.VALUE_NAMES]


# -- The rules and scripts offers -----------------------------------------------------------------


def test_the_rules_and_scripts_offers_are_read_as_theirs_and_accepted():
    talk = conversation(hc.Person(instructions="decline"))

    replies = [talk.answer(RULES_OFFER), talk.answer(SCRIPTS_OFFER)]

    assert [p.topic for p in talk.prompts] == ["rules", "scripts"]
    assert replies == [b"1\n", b"1\n"]


def test_the_rules_and_scripts_offers_never_stand_for_the_instructions_offer():
    talk = conversation(hc.Person(instructions="decline"))
    talk.answer(RULES_OFFER)
    talk.answer(SCRIPTS_OFFER)

    assert talk.answer(OFFER) == b"2\n"
    assert talk.prompts[-1].topic == "instructions"


# -- End of input ---------------------------------------------------------------------------------


LATER_PROMPTS = (value_line("EMAIL"), confirmation(), RULES_OFFER, SCRIPTS_OFFER)


def test_end_of_input_at_the_offer_is_ctrl_d_and_every_later_prompt_gets_one_too():
    talk = conversation(hc.Person(instructions="end"))

    replies = [talk.answer(OFFER), *(talk.answer(s) for s in LATER_PROMPTS)]

    assert replies == [hc.END_OF_INPUT] * 5


def test_end_of_input_at_the_first_value_line_is_ctrl_d_and_every_later_prompt_gets_one_too():
    talk = conversation(hc.Person(at_values="end"))
    accepted = talk.answer(OFFER)

    replies = [talk.answer(value_line("USERNAME")), *(talk.answer(s) for s in LATER_PROMPTS)]

    assert accepted == b"1\n"
    assert replies == [hc.END_OF_INPUT] * 5
