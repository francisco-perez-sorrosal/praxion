"""The guidance names review checks an agent applies from text alone, and speaks with one voice.

Within one link of the diagram conventions entry point, the guidance names review
checks covering the title, legend, element content, arrows, colour-free category
marks, contrast, legibility at the reference width, proportions and fan-in, one
level of abstraction per view, and agreement with a fresh regeneration. Each check
states the evidence that decides it (model source, render markup, or a command's
output) and its pass condition, uses the specification's thresholds, and never asks
for the image to be looked at. Every place that states a toolchain version states
the same one, and the architect's instructions point at the checks.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.diagram_rules import (
    ARCHITECT_INSTRUCTIONS,
    markdown_links,
    stated_versions,
)
from tests.acceptance.drivers.review_guidance import CONVENTIONS_ENTRY_POINT, review_checks

REQUIRED_TOPICS = {
    "a title with subject and C4 diagram type": ("title",),
    "legend completeness": ("legend",),
    "element name, category or technology, and responsibility": ("responsibilit",),
    "arrow intent labels and direction": ("arrow", "relationship label", "edge label"),
    "categories told apart without colour": ("colour", "color", "greyscale", "grayscale"),
    "contrast": ("contrast",),
    "legibility at the reference embed width": ("960",),
    "proportions": ("ratio", "proportion"),
    "arrow fan-in": ("fan-in", "fan in", "arrows meeting", "arrows meet"),
    "one level of abstraction per view": ("abstraction",),
    "agreement with a fresh regeneration": ("regenerat",),
}
THRESHOLDS = {
    "legibility at the reference embed width": ("960", "10"),
    "proportions": ("0.5", "2.5"),
    "arrow fan-in": ("9",),
    "contrast": ("4.5:1", "3:1"),
}
ALLOWED_EVIDENCE = ("model", "source", "markup", "svg", "text", "command", "output")
IMAGE_INSPECTION = (
    "look at the image",
    "looking at the image",
    "visual inspection",
    "visually inspect",
    "eyeball",
    "view the image",
)


def _checks_on(topic: str) -> list:
    words = REQUIRED_TOPICS[topic]
    return [check for check in review_checks() if any(w in check.text.casefold() for w in words)]


def test_the_review_checks_are_within_one_link_of_the_diagram_conventions_entry_point() -> None:
    reachable = {CONVENTIONS_ENTRY_POINT.resolve(), *markdown_links(CONVENTIONS_ENTRY_POINT)}

    sources = {check.source.resolve() for check in review_checks()}

    assert sources, "the guidance names no review checks"
    assert sources <= reachable, (
        f"checks stated beyond one link of the entry point: {sorted(sources - reachable)}"
    )


@pytest.mark.parametrize("topic", sorted(REQUIRED_TOPICS))
def test_a_review_check_covers_each_required_topic(topic) -> None:
    assert _checks_on(topic), f"no review check covers {topic}"


def test_every_review_check_states_its_evidence_and_pass_condition_without_looking_at_the_image() -> (
    None
):
    incomplete = [
        check.name
        for check in review_checks()
        if not check.pass_condition.strip()
        or not any(word in check.evidence.casefold() for word in ALLOWED_EVIDENCE)
        or any(phrase in check.text.casefold() for phrase in IMAGE_INSPECTION)
    ]

    assert incomplete == []


@pytest.mark.parametrize("topic", sorted(THRESHOLDS))
def test_review_check_thresholds_equal_the_specified_ones(topic) -> None:
    stated = " ".join(check.text for check in _checks_on(topic))

    assert all(value in stated for value in THRESHOLDS[topic]), (
        f"{topic}: expected {THRESHOLDS[topic]} in {stated!r}"
    )


@pytest.mark.parametrize("tool", ["likec4", "d2"])
def test_every_place_that_states_a_toolchain_version_states_the_same_one(tool) -> None:
    versions = stated_versions(tool)

    assert len(versions) <= 1, f"{tool} is stated at different versions: {versions}"


def test_the_architect_instructions_direct_it_to_the_review_checks() -> None:
    instructions = ARCHITECT_INSTRUCTIONS.read_text(encoding="utf-8")
    guidance_files = {check.source.resolve() for check in review_checks()}

    cited = [path for path in guidance_files if path.name in instructions]

    assert cited, (
        f"the architect's instructions cite none of {sorted(p.name for p in guidance_files)}"
    )
