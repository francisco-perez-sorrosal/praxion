"""Tests for the step-loop route of the delivery classifier, ``hooks/_skill_delivery.py``.

The step-loop driver hands an agent a three-line pointer to a rendered request, not the step. The
classifier follows the pointer and decides on the heading line of the request's ``<step>`` element
alone. The driver's own golden request is the input, so a change to the driver's render format
fails here in the commit that makes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
# The mutation sensor runs this file from a `mutants/` copy one level down, so `scripts` is found
# next to the hooks directory or one level above it.
SCRIPTS_DIR = next(
    root / "scripts"
    for root in (HOOKS_DIR.parent, HOOKS_DIR.parent.parent)
    if (root / "scripts").is_dir()
)
GOLDEN_REQUEST = SCRIPTS_DIR / "fixtures" / "step_loop_prompt_golden.md"
sys.path.insert(0, str(HOOKS_DIR))
sys.path.append(str(SCRIPTS_DIR))

import _skill_delivery as delivery  # noqa: E402
from _skill_delivery import (  # noqa: E402
    Marked,
    NotServed,
    OwnWords,
    StepRequest,
    Unmarked,
    Unresolvable,
)

IMPLEMENTER = "praxion:implementer"
SLUG = "demo"
REQUEST_ID = "s7-a2-implement"
REQUEST_PATH = Path(f"/repo/.ai-work/{SLUG}/PROMPT_{REQUEST_ID}.md")
MARKER = "[Phase: Refactoring]"
UNTAGGED_HEADING = "### Add the widget [depends-on: 6]"
TAGGED_HEADING = UNTAGGED_HEADING.replace("### ", f"### {MARKER} ")


def pointer_prompt(path=REQUEST_PATH, slug=SLUG, request=REQUEST_ID):
    return (
        f"Task slug: {slug}\nSpawn request: {request}\n"
        f"Read {path} first and follow it; it holds your step and its constraints."
    )


class Reader:
    """A request reader that serves one text and remembers what it was asked for."""

    def __init__(self, text):
        self.text = text
        self.asked = []

    def __call__(self, path):
        self.asked.append(path)
        return self.text


def golden_request():
    return GOLDEN_REQUEST.read_text(encoding="utf-8")


def request_with(heading, body="**Assignee**: implementer\n"):
    return f'Task slug: {SLUG}\n\n<step id="7">\n{heading}\n\n{body}</step>\n'


def classify(prompt, text, agent_type=IMPLEMENTER, cwd=None):
    reader = Reader(text)
    return delivery.classify(agent_type, prompt, reader, cwd), reader


# --- the driver's golden request -------------------------------------------------------------


def test_the_drivers_golden_request_marks_the_step_it_heads():
    verdict, reader = classify(pointer_prompt(), golden_request())

    assert verdict == Marked(StepRequest(REQUEST_ID))
    assert reader.asked == [REQUEST_PATH]


def test_the_golden_request_without_its_tag_is_unmarked():
    untagged = golden_request().replace(f"{MARKER} ", "")

    assert classify(pointer_prompt(), untagged)[0] == Unmarked()


def test_a_golden_request_without_a_step_element_is_unresolvable():
    renamed = golden_request().replace("<step ", "<task ").replace("</step>", "</task>")

    assert classify(pointer_prompt(), renamed)[0] == Unresolvable("request-without-step")


# --- only the heading decides ----------------------------------------------------------------


def test_marker_in_plain_words_of_an_untagged_steps_text_never_marks():
    body = f"**Implementation**: Add {MARKER} to the delegation guidance.\n"

    assert classify(pointer_prompt(), request_with(UNTAGGED_HEADING, body))[0] == Unmarked()


def test_a_step_element_quoted_further_down_never_decides():
    body = f'**Implementation**: quote\n<step id="8">\n### {MARKER} Other\n</step>\n'

    assert classify(pointer_prompt(), request_with(UNTAGGED_HEADING, body))[0] == Unmarked()


def test_marker_before_the_step_element_never_marks():
    text = f"You are implementing a step {MARKER}.\n" + request_with(UNTAGGED_HEADING)

    assert classify(pointer_prompt(), text)[0] == Unmarked()


@pytest.mark.parametrize("tag", ["[phase: refactoring]", "[ Phase :  Refactoring ]"])
def test_the_plan_readers_spellings_of_the_tag_mark(tag):
    heading = f"### {tag} Add the widget"

    assert classify(pointer_prompt(), request_with(heading))[0] == Marked(StepRequest(REQUEST_ID))


def test_a_step_element_whose_first_line_is_not_a_heading_is_unresolvable():
    text = request_with(f"Add the widget {MARKER}")

    assert classify(pointer_prompt(), text)[0] == Unresolvable("request-without-step")


def test_blank_lines_before_the_heading_are_skipped():
    text = f'<step id="7">\n\n\n{TAGGED_HEADING}\n</step>\n'

    assert classify(pointer_prompt(), text)[0] == Marked(StepRequest(REQUEST_ID))


def test_an_empty_step_element_is_unresolvable():
    assert classify(pointer_prompt(), '<step id="7">\n')[0] == Unresolvable("request-without-step")


# --- the request cannot be used --------------------------------------------------------------


def test_an_unreadable_request_is_unresolvable():
    assert classify(pointer_prompt(), None)[0] == Unresolvable("request-unreadable")


def test_a_request_with_no_step_block_is_unresolvable():
    assert classify(pointer_prompt(), "Task slug: demo\nno step here")[0] == Unresolvable(
        "request-without-step"
    )


# --- the path a prompt names is never read unless it is the request's own --------------------


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/etc/passwd", id="arbitrary-file"),
        pytest.param(f"/repo/docs/PROMPT_{REQUEST_ID}.md", id="outside-ai-work"),
        pytest.param(f"/repo/.ai-work/other/PROMPT_{REQUEST_ID}.md", id="another-slug"),
        pytest.param("/repo/.ai-work/demo/PROMPT_s1-a1-implement.md", id="another-request"),
        pytest.param(f"/repo/.ai-work/{SLUG}/sub/PROMPT_{REQUEST_ID}.md", id="nested-directory"),
        pytest.param(f"/repo/.ai-work/{SLUG}/../x/PROMPT_{REQUEST_ID}.md", id="dot-dot-escape"),
        pytest.param(f"/repo/.ai-work/{SLUG}/../../PROMPT_{REQUEST_ID}.md", id="dot-dot-to-root"),
        pytest.param(f".ai-work/{SLUG}/PROMPT_{REQUEST_ID}.md", id="relative-without-a-cwd"),
    ],
)
def test_a_path_that_is_not_the_requests_own_is_refused_unread(path):
    verdict, reader = classify(pointer_prompt(path=path), golden_request())

    assert verdict == Unresolvable("request-path-refused")
    assert reader.asked == []


def test_a_path_with_a_harmless_dot_dot_that_lands_on_the_request_is_followed():
    path = f"/repo/.ai-work/{SLUG}/../{SLUG}/PROMPT_{REQUEST_ID}.md"

    verdict, reader = classify(pointer_prompt(path=path), golden_request())

    assert verdict == Marked(StepRequest(REQUEST_ID))
    assert reader.asked == [REQUEST_PATH]


def test_a_relative_path_is_resolved_against_the_spawns_working_directory():
    path = f".ai-work/{SLUG}/PROMPT_{REQUEST_ID}.md"

    verdict, reader = classify(pointer_prompt(path=path), golden_request(), cwd=Path("/repo"))

    assert verdict == Marked(StepRequest(REQUEST_ID))
    assert reader.asked == [REQUEST_PATH]


def test_a_relative_path_cannot_climb_out_of_ai_work_through_the_working_directory():
    path = f"../elsewhere/PROMPT_{REQUEST_ID}.md"

    verdict, reader = classify(pointer_prompt(path=path), golden_request(), cwd=Path("/repo"))

    assert verdict == Unresolvable("request-path-refused")
    assert reader.asked == []


# --- when the route is not considered --------------------------------------------------------


def test_a_prompt_with_own_words_marker_marks_without_reading_the_request():
    verdict, reader = classify(f"{pointer_prompt()}\nThis is {MARKER}.", golden_request())

    assert verdict == Marked(OwnWords())
    assert reader.asked == []


@pytest.mark.parametrize(
    "prompt",
    [
        pytest.param(f"Task slug: {SLUG}\nSpawn request: {REQUEST_ID}\nDo the work.", id="no-read"),
        pytest.param(f"Spawn request: {REQUEST_ID}\nRead {REQUEST_PATH} first.", id="no-slug"),
        pytest.param(f"Task slug: {SLUG}\nRead {REQUEST_PATH} first.", id="no-request"),
        pytest.param("Implement the widget.", id="plain-delegation"),
    ],
)
def test_a_prompt_that_is_not_the_drivers_pointer_is_unmarked_unread(prompt):
    verdict, reader = classify(prompt, golden_request())

    assert verdict == Unmarked()
    assert reader.asked == []


def test_a_pointer_quoted_in_a_fenced_block_is_not_followed():
    verdict, reader = classify(f"Notes:\n```\n{pointer_prompt()}\n```\n", golden_request())

    assert verdict == Unmarked()
    assert reader.asked == []


@pytest.mark.parametrize("agent_type", ["praxion:verifier", "Explore"])
def test_another_role_is_not_served_and_its_request_is_unread(agent_type):
    verdict, reader = classify(pointer_prompt(), golden_request(), agent_type)

    assert verdict == NotServed(agent_type)
    assert reader.asked == []


def test_missing_grammar_is_unresolvable_before_the_request_is_read(monkeypatch):
    monkeypatch.setattr(delivery, "MARKER_PATTERN", None)

    verdict, reader = classify(pointer_prompt(), golden_request())

    assert verdict == Unresolvable("grammar-unavailable")
    assert reader.asked == []
