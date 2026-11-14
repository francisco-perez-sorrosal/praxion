"""Tests for classifying a delegation by its own words, ``hooks/_skill_delivery.py``.

A delegation is marked only by a marker in its own words: text inside fenced blocks, block quotes
and inline code spans is quoted material and never marks. The property tests interleave the three
quoting forms at random from a fixed seed.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR))
sys.path.append(str(HOOKS_DIR.parent / "scripts"))

import _skill_delivery as delivery  # noqa: E402
from _skill_delivery import Marked, NotServed, OwnWords, Unmarked, Unresolvable  # noqa: E402

IMPLEMENTER = "praxion:implementer"
TEST_ENGINEER = "praxion:test-engineer"
MARKER = "[Phase: Refactoring]"
PROPERTY_SEEDS = range(60)
PIECES_PER_DOCUMENT = 8


def never_read(path):
    raise AssertionError(f"the own-words route must not read a request, asked for {path}")


def classify(prompt, agent_type=IMPLEMENTER):
    return delivery.classify(agent_type, prompt, never_read)


# --- marked, unmarked ------------------------------------------------------------------------


@pytest.mark.parametrize("agent_type", [IMPLEMENTER, TEST_ENGINEER])
def test_marker_in_the_prompts_own_words_marks_a_served_role(agent_type):
    prompt = f"Lift the grammar into the module {MARKER}."

    assert classify(prompt, agent_type) == Marked(OwnWords())


def test_prompt_without_a_marker_is_unmarked():
    assert classify("Implement step 4 and run its tests.") == Unmarked()


def test_empty_prompt_is_unmarked():
    assert classify("") == Unmarked()


@pytest.mark.parametrize("marker", ["[phase: refactoring]", "[ PHASE :  Refactoring ]"])
def test_marker_matches_in_its_case_and_spacing_forms(marker):
    assert classify(f"do the work {marker}") == Marked(OwnWords())


# --- quoting: each form alone ----------------------------------------------------------------


@pytest.mark.parametrize(
    "quoted",
    [
        pytest.param(f"```\n{MARKER}\n```", id="backtick-fence"),
        pytest.param(f"~~~\n{MARKER}\n~~~", id="tilde-fence"),
        pytest.param(f"```markdown\n{MARKER}\n```", id="fence-with-info-string"),
        pytest.param(f"````\n```\n{MARKER}\n```\n````", id="outer-fence-encloses-inner"),
        pytest.param(f"~~~\n```\n{MARKER}\n```\n~~~", id="tilde-fence-encloses-backtick-fence"),
        pytest.param(f"```\n{MARKER}\n", id="unclosed-fence-runs-to-the-end"),
        pytest.param(f"> {MARKER}", id="block-quote"),
        pytest.param(f"  >{MARKER}", id="indented-block-quote"),
        pytest.param(f"> quoted\n> {MARKER}\n> more", id="multi-line-block-quote"),
        pytest.param(f"see `{MARKER}` for the grammar", id="inline-span"),
        pytest.param(f"see ``{MARKER}`` for the grammar", id="double-backtick-span"),
        pytest.param(f"see ``a ` b {MARKER}`` for it", id="span-holding-a-single-backtick"),
    ],
)
def test_marker_inside_quoted_material_never_marks(quoted):
    assert classify(f"Review the work.\n{quoted}\nThanks.") == Unmarked()


def test_text_after_a_closed_fence_is_the_prompts_own_words():
    assert classify(f"```\ncode\n```\n{MARKER}") == Marked(OwnWords())


def test_inner_fence_does_not_close_a_longer_outer_fence():
    prompt = f"````\n```\ninner\n```\n{MARKER}\n````"

    assert classify(prompt) == Unmarked()


def test_unmatched_backtick_runs_stay_literal_so_the_marker_marks():
    assert classify(f"a ` b\n{MARKER}\nc `` d") == Marked(OwnWords())


def test_removed_quoted_material_cannot_join_the_text_around_it_into_a_marker():
    assert classify("[Phase: `x`Refactoring]") == Unmarked()
    assert classify("[Phase:\n> quoted\nRefactoring]") == Unmarked()


# --- mixed -----------------------------------------------------------------------------------


def test_own_marker_beside_a_quoted_one_marks():
    prompt = f"> earlier brief said {MARKER}\nNow do it: {MARKER}"

    assert classify(prompt) == Marked(OwnWords())


def test_marker_in_prose_beside_code_that_quotes_it_marks():
    prompt = f"Use `{MARKER}` for refactoring steps. This one is {MARKER} too."

    assert classify(prompt) == Marked(OwnWords())


# --- another role ----------------------------------------------------------------------------


@pytest.mark.parametrize("agent_type", ["praxion:verifier", "Explore", "praxion:researcher", ""])
def test_a_marked_delegation_to_another_role_is_not_served(agent_type):
    assert classify(f"Verify the work {MARKER}", agent_type) == NotServed(agent_type)


# --- the grammar is unavailable --------------------------------------------------------------


@pytest.mark.parametrize("agent_type", [IMPLEMENTER, TEST_ENGINEER])
def test_missing_grammar_is_unresolvable_for_a_served_role_whatever_the_prompt(
    monkeypatch, agent_type
):
    monkeypatch.setattr(delivery, "MARKER_PATTERN", None)

    assert classify(MARKER, agent_type) == Unresolvable("grammar-unavailable")
    assert classify("no marker here", agent_type) == Unresolvable("grammar-unavailable")


def test_missing_grammar_leaves_another_role_not_served(monkeypatch):
    monkeypatch.setattr(delivery, "MARKER_PATTERN", None)

    assert classify(MARKER, "praxion:verifier") == NotServed("praxion:verifier")


# --- purity ----------------------------------------------------------------------------------


def test_classification_is_a_function_of_its_arguments_alone():
    prompt = f"x\n> y\n{MARKER}"

    assert classify(prompt) == classify(prompt)


def test_classify_does_not_call_the_request_reader_on_the_own_words_route():
    delivery.classify(IMPLEMENTER, f"{MARKER}", never_read)
    delivery.classify(IMPLEMENTER, "plain", never_read)


# --- property: random interleavings of the three quoting forms -------------------------------

QUOTED_PIECES = [
    f"```\n{MARKER}\n```",
    f"```python\ncode\n{MARKER}\n```",
    f"~~~\n{MARKER}\n~~~",
    f"````\n```\n{MARKER}\n```\n````",
    f"~~~~\n~~~\n{MARKER}\n~~~\n~~~~",
    f"~~~\n```\n{MARKER}\n```\n~~~",
    f"> {MARKER}",
    f"> a note\n> {MARKER}\n> more",
    f"   > {MARKER} indented",
    f"mention of `{MARKER}` inline",
    f"``{MARKER}`` double run",
    f"```{MARKER}``` triple run on one line",
    f"``a ` b {MARKER}`` run holding a lone backtick",
    "`[Phase:` and `Refactoring]` split across spans",
]
PLAIN_PIECES = [
    "Implement the step and run its tests.",
    "Phase: Refactoring without brackets",
    "[Phase: Refactor] is not the marker",
    "",
]
OWN_MARKER_PIECES = [
    f"Please do this {MARKER}",
    "[phase: refactoring]",
    "step [ PHASE : REFACTORING ] now",
]


def random_document(rng, extra=()):
    pieces = [rng.choice(QUOTED_PIECES + PLAIN_PIECES) for _ in range(PIECES_PER_DOCUMENT)]
    for piece in extra:
        pieces.insert(rng.randrange(len(pieces) + 1), piece)
    return "\n".join(pieces)


@pytest.mark.parametrize("seed", PROPERTY_SEEDS)
def test_no_interleaving_of_quoted_material_alone_ever_marks(seed):
    rng = random.Random(seed)
    document = random_document(rng)

    assert classify(document) == Unmarked(), document


@pytest.mark.parametrize("seed", PROPERTY_SEEDS)
def test_an_own_marker_marks_wherever_it_sits_among_quoted_material(seed):
    rng = random.Random(seed)
    document = random_document(rng, extra=[rng.choice(OWN_MARKER_PIECES)])

    assert classify(document) == Marked(OwnWords()), document
