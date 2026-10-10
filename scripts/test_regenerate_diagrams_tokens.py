"""The visual vocabulary of the diagram regeneration command, `scripts/regenerate_diagrams.py`.

These tests pin the token table (one drawing per category and form, every default text and
outline with enough contrast on its fill and on the canvas, marks that differ once colour is
removed, the two vocabularies) and how a project's own `style.json` adds categories or is
refused by name. The command is imported as `regenerate_diagrams`, from this directory; it must import with the
standard library alone and have no side effect at import time. The surface of the pure core
these tests assume is stated in `_diagram_testkit.py`.
"""

from __future__ import annotations

import importlib
import json
from typing import NamedTuple

import pytest

CANVAS = "#FFFFFF"
TEXT_CONTRAST_FLOOR = 4.5
OUTLINE_CONTRAST_FLOOR = 3.0
LABEL_WIDTH = 28

PRAXION_NAMES = (
    "Person",
    "System in scope",
    "External system",
    "Knowledge asset",
    "Runtime agent",
    "Pipeline document",
    "Persistent store",
    "Tooling",
    "Layer",
)
KIT_NAMES = ("Person", "System in scope", "External system", "Container", "Component", "Data store")
KIT_NAMES = ("Person", "System in scope", "External system", "Container", "Component", "Data store")

INK = "#0F172A"


class _Drawing(NamedTuple):
    category: str
    frame: bool
    shape: str
    fill: str | None
    stroke: str
    stroke_width: float
    dashed: bool
    radius: int
    extra: str
    icon: str
    text_colour: str


# drawing class -> its drawing: the category-drawings table, value for value.
EXPECTED_TOKENS = {
    "category_person": _Drawing("Person", False, "rectangle", "#E6F0FA", "#1D4E89", 2, False, 0, "none", "person", INK),
    "category_system_in_scope": _Drawing("System in scope", False, "rectangle", "#4338CA", "#312E81", 3, False, 0, "none", "none", CANVAS),
    "category_system_in_scope_frame": _Drawing("System in scope", True, "rectangle", "#EEF2FF", "#4338CA", 2, False, 0, "none", "none", INK),
    "category_external_system": _Drawing("External system", False, "rectangle", "#ECEAE6", "#77726A", 2, True, 0, "none", "none", INK),
    "category_knowledge_asset": _Drawing("Knowledge asset", False, "package", "#E1F3EC", "#00684A", 2, False, 0, "none", "none", INK),
    "category_runtime_agent": _Drawing("Runtime agent", False, "rectangle", "#FDEFD9", "#A85A00", 2, False, 16, "none", "none", INK),
    "category_runtime_agent_frame": _Drawing("Runtime agent", True, "rectangle", None, "#A85A00", 2, True, 16, "none", "none", INK),
    "category_pipeline_document": _Drawing("Pipeline document", False, "document", "#E3F1FB", "#0B6FA4", 2, False, 0, "none", "none", INK),
    "category_persistent_store": _Drawing("Persistent store", False, "cylinder", "#F6E6F0", "#9B3A75", 2, False, 0, "none", "none", INK),
    "category_tooling": _Drawing("Tooling", False, "rectangle", "#F2F4F7", "#3F4B5C", 2, False, 0, "3d", "none", INK),
    "category_layer_frame": _Drawing("Layer", True, "rectangle", None, "#8C8780", 2, True, 0, "none", "none", INK),
    "category_layer": _Drawing("Layer", False, "rectangle", CANVAS, "#8C8780", 2, False, 0, "double-border", "none", INK),
    "category_container": _Drawing("Container", False, "rectangle", "#E3F1FB", "#0B6FA4", 2, False, 8, "none", "none", INK),
    "category_container_frame": _Drawing("Container", True, "rectangle", None, "#0B6FA4", 2, True, 8, "none", "none", INK),
    "category_component": _Drawing("Component", False, "rectangle", "#E1F3EC", "#00684A", 2, False, 0, "double-border", "none", INK),
    "category_data_store": _Drawing("Data store", False, "cylinder", "#F6E6F0", "#9B3A75", 2, False, 0, "none", "none", INK),
}  # fmt: skip


# --- helpers: an independent recomputation of the contrast and mark rules --------------------


def _channel(value: int) -> float:
    unit = value / 255
    return unit / 12.92 if unit <= 0.03928 else ((unit + 0.055) / 1.055) ** 2.4


def _luminance(colour: str) -> float:
    red, green, blue = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _mark(token) -> tuple:
    """What stays of a drawing once colour is removed."""
    return (
        token.shape,
        token.radius,
        token.extra,
        bool(token.dash),
        token.stroke_width,
        token.icon,
    )


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


# --- the token table ---------------------------------------------------------------------------


@pytest.mark.parametrize("drawing_class", sorted(EXPECTED_TOKENS))
def test_default_table_draws_each_category_form_as_designed(rd, drawing_class):
    expected = EXPECTED_TOKENS[drawing_class]

    token = next(t for t in rd.DEFAULT_TOKENS if t.drawing_class == drawing_class)

    assert (token.category, token.frame) == (expected.category, expected.frame)
    assert (token.shape, token.fill, token.stroke) == (
        expected.shape,
        expected.fill,
        expected.stroke,
    )
    assert (token.stroke_width, bool(token.dash), token.radius) == (
        expected.stroke_width,
        expected.dashed,
        expected.radius,
    )
    assert (token.extra, token.icon, token.text_colour) == (
        expected.extra,
        expected.icon,
        expected.text_colour,
    )


def test_default_table_has_no_drawing_beyond_the_designed_ones(rd):
    classes = [t.drawing_class for t in rd.DEFAULT_TOKENS]

    assert sorted(classes) == sorted(EXPECTED_TOKENS)


def test_every_default_text_has_enough_contrast_on_its_fill(rd):
    for token in (*rd.DEFAULT_TOKENS, rd.UNCATEGORISED):
        surface = token.fill or CANVAS

        assert _contrast(token.text_colour, surface) >= TEXT_CONTRAST_FLOOR, token.drawing_class


def test_every_default_outline_has_enough_contrast_on_the_canvas(rd):
    for token in (*rd.DEFAULT_TOKENS, rd.UNCATEGORISED):
        assert _contrast(token.stroke, CANVAS) >= OUTLINE_CONTRAST_FLOOR, token.drawing_class


@pytest.mark.parametrize(
    ("vocabulary", "names", "box_marks", "frame_marks"),
    [("praxion", PRAXION_NAMES, 9, 3), ("kit", KIT_NAMES, 6, 2)],
)
def test_marks_within_a_vocabulary_differ_once_colour_is_removed(
    rd, vocabulary, names, box_marks, frame_marks
):
    assert rd.VOCABULARIES[vocabulary] == names
    tokens = [t for t in rd.DEFAULT_TOKENS if t.category in names]
    boxes = [_mark(t) for t in tokens if not t.frame]
    frames = [_mark(t) for t in tokens if t.frame]

    assert len(boxes) == len(set(boxes)) == box_marks
    assert len(frames) == len(set(frames)) == frame_marks


def test_vocabularies_are_the_only_two_the_command_knows(rd):
    assert set(rd.VOCABULARIES) == {"praxion", "kit"}


def test_uncategorised_token_is_a_dotted_white_box(rd):
    token = rd.UNCATEGORISED

    assert (token.category, token.frame) == ("Uncategorised", False)
    assert token.drawing_class == "category_uncategorised"
    assert token.fill == CANVAS
    assert token.dash > 0
    assert token.stroke_width == 1


# --- a project's own categories (style.json) ---------------------------------------------------

QUEUE_BOX = {"shape": "queue", "fill": "#FFF4D6", "stroke": "#8A5A00", "text_colour": INK}


def _style(categories: dict) -> str:
    return json.dumps({"schema": 1, "categories": categories})


def test_style_file_adds_a_category_after_the_defaults(rd):
    tokens = rd.load_style(_style({"Queue": {"box": QUEUE_BOX}}))

    assert tokens[: len(rd.DEFAULT_TOKENS)] == rd.DEFAULT_TOKENS
    (added,) = tokens[len(rd.DEFAULT_TOKENS) :]
    assert (added.category, added.frame, added.drawing_class) == ("Queue", False, "category_queue")
    assert (added.shape, added.fill, added.stroke) == ("queue", "#FFF4D6", "#8A5A00")
    assert (added.stroke_width, added.dash, added.radius) == (2, 0, 0)
    assert (added.extra, added.icon) == ("none", "none")


def test_style_file_names_a_category_with_spaces_in_snake_case(rd):
    box = {
        "shape": "rectangle",
        "fill": CANVAS,
        "stroke": "#334155",
        "text_colour": INK,
        "radius": 4,
    }

    tokens = rd.load_style(_style({"Web app": {"box": box}}))

    assert tokens[-1].drawing_class == "category_web_app"


def test_style_file_adds_a_frame_when_it_gives_one(rd):
    frame = {
        "shape": "rectangle",
        "fill": None,
        "stroke": "#8A5A00",
        "stroke_width": 2,
        "dash": 5,
        "radius": 4,
        "text_colour": INK,
    }

    tokens = rd.load_style(_style({"Queue": {"box": QUEUE_BOX, "frame": frame}}))

    added = tokens[len(rd.DEFAULT_TOKENS) :]
    assert [(t.drawing_class, t.frame, t.fill) for t in added] == [
        ("category_queue", False, "#FFF4D6"),
        ("category_queue_frame", True, None),
    ]


@pytest.mark.parametrize(
    "box",
    [
        pytest.param({**QUEUE_BOX, "text_colour": "#9CA3AF"}, id="text-too-faint-on-fill"),
        pytest.param({**QUEUE_BOX, "stroke": "#D1D5DB"}, id="outline-too-faint-on-canvas"),
        pytest.param(
            {"shape": "cylinder", "fill": "#FFF4D6", "stroke": "#8A5A00", "text_colour": INK},
            id="same-mark-as-persistent-store",
        ),
        pytest.param({"shape": "queue", "fill": "#FFF4D6", "text_colour": INK}, id="no-outline"),
        pytest.param({**QUEUE_BOX, "stroke_width": 1.5}, id="fractional-width"),
        pytest.param({**QUEUE_BOX, "shape": "cylinder", "extra": "3d"}, id="3d-on-a-cylinder"),
        pytest.param(
            {**QUEUE_BOX, "shape": "package", "extra": "double-border"},
            id="double-border-on-a-package",
        ),
    ],
)
def test_style_file_entry_that_breaks_a_rule_is_refused_by_name(rd, box):
    with pytest.raises(rd.UsageError, match="Queue"):
        rd.load_style(_style({"Queue": {"box": box}}))


def test_style_file_with_another_schema_is_refused(rd):
    text = json.dumps({"schema": 2, "categories": {}})

    with pytest.raises(rd.UsageError, match="schema"):
        rd.load_style(text)


def test_style_file_that_is_not_json_is_refused(rd):
    with pytest.raises(rd.UsageError):
        rd.load_style("{not json")
