"""Core behaviour of the diagram regeneration command, `scripts/regenerate_diagrams.py`.

The command reads a LikeC4 workspace through `likec4 export json`, gives every element
one category, and draws each view as D2 text in a fixed visual vocabulary. These tests
pin the pure core only: the token table, the category rule, the view projection, label
synthesis and D2 emission. The subprocess edge, the failure kinds, the modes and the
review checks have their own test files.

The module under test is imported as `regenerate_diagrams`, from this directory. It must
import with the standard library alone and have no side effect at import time. The
fixture `tests/fixtures/diagram_regen/export_small.json` has the real keys of the
`likec4 export json --skip-layout` reading, cut down to eleven elements, ten
relationships and six views (an element view of each kind, a dynamic view, two views
with a wrong number of C4 type tags, and a view of elements with no usable category).

Public surface these tests assume (a disagreement is raised with the planner, not
worked around here):

    UsageError                      Exception: a refused `style.json`, the exit-2 class

    Token (frozen dataclass)        one drawing per (category, form):
        category: str               exact vocabulary name
        frame: bool                 True when the element is drawn as an enclosing frame
        drawing_class: str          "category_" + snake_case(category), plus "_frame" for frames
        shape: str                  a D2 shape: rectangle, package, document, cylinder, queue
        fill: str | None            "#RRGGBB"; None when the frame has no fill
        stroke: str                 "#RRGGBB"
        stroke_width: float
        dash: int                   0 is solid, a positive value is the dash length
        radius: int                 0 is square
        extra: str                  "none", "3d" or "double-border"
        icon: str                   "none" or "person"
        text_colour: str            "#RRGGBB"
    DEFAULT_TOKENS: tuple[Token, ...]    every (category, form) the command draws by default
    UNCATEGORISED: Token                 category "Uncategorised", drawn when no category resolves
    VOCABULARIES: dict[str, tuple[str, ...]]
                                    "praxion" and "kit": the category names, in legend order
    load_style(text, base=DEFAULT_TOKENS) -> tuple[Token, ...]
                                    parse `style.json`; base tokens first, then the additions;
                                    raises UsageError naming the entry that fails

    resolve_category(element, specification) -> str | None
                                    `element["metadata"]["category"]` when it is a string, else
                                    the `notation` of its kind in `specification["elements"]`;
                                    None when neither gives a string

    project(model, tokens=DEFAULT_TOKENS) -> Projection
        Projection.views: tuple[View, ...]          View.id, title, c4_type, nodes, edges
        Projection.findings: tuple[Finding, ...]    Finding.check, view, status, evidence,
                                                    measured, threshold
        Node: id, name, category, technology, responsibility, is_frame
        Edge: source, target, label, line ("acts-on" | "read-only" | "step"), step_no
        All of these are frozen dataclasses.

    wrap_text(text, width) -> list[str]
    node_label_lines(node) -> list[str]
    legend_entries(view) -> list[LegendEntry]       LegendEntry.label, drawing_class
    emit_d2(view) -> str                            pure: no clock, no file, no network
"""

from __future__ import annotations

import base64
import dataclasses
import importlib
import json
import re
from pathlib import Path
from typing import NamedTuple

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "diagram_regen"

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

MEANING_ACTS_ON = "acts on (invokes, writes)"
MEANING_READ_ONLY = "read-only flow (consumed, not modified)"
MEANING_STEP = "numbered step, in order (dynamic views)"

DATA_URI = re.compile(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)")


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


# --- fixtures ----------------------------------------------------------------------------------


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


@pytest.fixture
def model() -> dict:
    return json.loads((FIXTURES / "export_small.json").read_text(encoding="utf-8"))


@pytest.fixture
def views(rd, model) -> dict:
    return {view.id: view for view in rd.project(model).views}


def _node(view, element_id):
    return next(node for node in view.nodes if node.id == element_id)


def _edge(view, source, target):
    return next(e for e in view.edges if (e.source, e.target) == (source, target))


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


# --- the category rule -------------------------------------------------------------------------

SPECIFICATION = {"elements": {"person": {"notation": "Person"}, "component": {"style": {}}}}


@pytest.mark.parametrize(
    ("element", "expected"),
    [
        pytest.param({"kind": "person"}, "Person", id="kind-notation"),
        pytest.param(
            {"kind": "person", "metadata": {"category": "Tooling"}}, "Tooling", id="metadata-wins"
        ),
        pytest.param(
            {"kind": "component", "metadata": {"category": "Layer"}}, "Layer", id="spanning-kind"
        ),
        pytest.param({"kind": "component"}, None, id="kind-without-notation"),
        pytest.param({"kind": "gadget"}, None, id="kind-not-in-the-specification"),
        pytest.param(
            {"kind": "component", "metadata": {"category": ["Tooling", "Layer"]}},
            None,
            id="merged-into-a-list",
        ),
        pytest.param(
            {"kind": "person", "metadata": {"owner": "docs"}}, "Person", id="other-metadata-ignored"
        ),
    ],
)
def test_an_element_has_the_category_its_metadata_or_its_kind_names(rd, element, expected):
    assert rd.resolve_category(element, SPECIFICATION) == expected


# --- the view projection -----------------------------------------------------------------------


def test_the_projection_has_one_view_per_exported_view(rd, model):
    projection = rd.project(model)

    assert {view.id for view in projection.views} == set(model["views"])


def test_a_view_keeps_the_models_title_and_names_its_c4_type_from_its_tag(views):
    assert (views["index"].title, views["index"].c4_type) == (
        "Praxion — System Context",
        "System Context",
    )
    assert views["structure"].c4_type == "Component"


def test_a_dynamic_view_is_of_type_dynamic(views):
    assert views["flow"].c4_type == "Dynamic"


@pytest.mark.parametrize("view_id", ["untagged", "double_tagged"])
def test_a_view_without_exactly_one_type_tag_is_a_failed_finding_not_a_crash(rd, model, view_id):
    findings = rd.project(model).findings

    assert any(f.check == "DRC-01" and f.view == view_id and f.status == "FAIL" for f in findings)


def test_a_node_carries_what_it_draws(views):
    developer = _node(views["index"], "developer")
    external = _node(views["index"], "claude_code")
    agent = _node(views["structure"], "praxion.orchestrator")

    assert (developer.name, developer.category) == ("Developer", "Person")
    assert developer.responsibility == "Writes the code and reviews the diagrams"
    assert (external.category, external.technology, external.responsibility) == (
        "External system",
        None,
        None,
    )
    assert (agent.category, agent.technology) == ("Runtime agent", "Claude Code")


def test_the_responsibility_is_the_summary_when_the_model_records_one(views):
    assert _node(views["index"], "praxion").responsibility == "Agent harness for software work"


def test_a_component_takes_its_category_from_its_metadata(views):
    structure = views["structure"]

    assert _node(structure, "praxion.knowledge.skills").category == "Knowledge asset"
    assert _node(structure, "praxion.knowledge").category == "Layer"


def test_a_node_is_a_frame_when_the_view_draws_its_children(views):
    structure = views["structure"]

    assert _node(structure, "praxion.knowledge").is_frame
    assert not _node(structure, "praxion.knowledge.skills").is_frame
    assert not any(node.is_frame for node in views["index"].nodes)


def test_an_element_without_a_usable_category_is_drawn_uncategorised(views):
    unresolved = views["unresolved"]

    assert {n.category for n in unresolved.nodes} == {"Uncategorised"}


def test_an_element_without_a_usable_category_is_a_failed_finding_naming_it(rd, model):
    findings = [f for f in rd.project(model).findings if f.check == "DRC-05"]

    assert {f.view for f in findings} == {"unresolved"}
    assert all(f.status == "FAIL" for f in findings)
    evidence = " ".join(f.evidence for f in findings)
    for element in ("praxion.stray", "praxion.odd", "praxion.twice"):
        assert element in evidence


def test_a_resolved_view_has_no_finding(rd, model):
    findings = rd.project(model).findings

    assert not {f.view for f in findings} & {"index", "structure", "flow"}


# --- labels ------------------------------------------------------------------------------------


def test_one_relationship_labels_its_arrow_with_its_title(views):
    assert _edge(
        views["structure"], "praxion.knowledge.commands", "praxion.orchestrator"
    ).label == ("triggers")


def test_several_relationships_read_first_title_plus_the_rest(views):
    structure = views["structure"]

    assert _edge(structure, "praxion.knowledge.skills", "praxion.orchestrator").label == (
        "constrains +1 more"
    )
    assert _edge(structure, "praxion.orchestrator", "praxion.knowledge.commands").label == (
        "dispatches +2 more"
    )


def test_the_first_title_is_the_first_in_sorted_order_not_in_model_order(rd, model):
    spawns_first = ["r8", "r9", "r10"]  # titles: spawns, dispatches (gated), dispatches
    reordered = json.loads(json.dumps(model))
    edge = next(
        e for e in reordered["views"]["structure"]["edges"] if e["relations"] == spawns_first
    )
    edge["relations"] = list(reversed(spawns_first))

    views = {view.id: view for view in rd.project(reordered).views}

    assert _edge(
        views["structure"], "praxion.orchestrator", "praxion.knowledge.commands"
    ).label == ("dispatches +2 more")


def test_no_label_is_the_toolchains_ellipsis_placeholder(views):
    labels = [edge.label for view in views.values() for edge in view.edges]

    assert labels
    assert not [label for label in labels if "[...]" in label or not label.strip()]


def test_a_relationship_of_kind_reads_is_a_read_only_arrow(views):
    structure = views["structure"]

    assert _edge(structure, "praxion.doc_idea", "praxion.orchestrator").line == "read-only"
    assert _edge(structure, "praxion.orchestrator", "praxion.doc_idea").line == "acts-on"
    assert _edge(structure, "praxion.knowledge.skills", "praxion.orchestrator").line == "acts-on"


def test_dynamic_steps_are_numbered_by_their_step_id(views):
    steps = {e.step_no: e for e in views["flow"].edges}

    assert sorted(steps) == [1, 2, 10]
    assert steps[1].label == "1 · drafts the proposal"
    assert steps[2].label == "2 · informs the plan"
    assert steps[10].label == "10 · files the proposal"


def test_every_dynamic_step_is_a_step_line_whatever_its_relationship_kind(views):
    assert {edge.line for edge in views["flow"].edges} == {"step"}


def test_arrows_of_element_views_carry_no_step_number(views):
    assert {e.step_no for e in views["structure"].edges} == {None}


# --- node text ---------------------------------------------------------------------------------


def test_text_wraps_at_word_boundaries_and_keeps_a_line_of_exactly_the_width(rd):
    text = "Tier selector, task-slug propagator, rework-worktree spawner, subagent dispatcher"

    lines = rd.wrap_text(text, LABEL_WIDTH)

    assert lines == [
        "Tier selector, task-slug",
        "propagator, rework-worktree",
        "spawner, subagent dispatcher",
    ]
    assert max(len(line) for line in lines) == LABEL_WIDTH


def test_a_word_longer_than_the_width_stays_whole_on_its_own_line(rd):
    word = "x" * (LABEL_WIDTH + 5)

    assert rd.wrap_text(f"see {word} now", LABEL_WIDTH) == ["see", word, "now"]


def test_wrapped_lines_rejoin_to_the_original_words(rd):
    text = "Out-of-band quality measurement over completed artifacts, read-only"

    lines = rd.wrap_text(text, LABEL_WIDTH)

    assert " ".join(lines) == text
    assert all(line == line.strip() for line in lines)


def test_a_node_states_its_name_its_category_with_technology_and_its_responsibility(rd, views):
    agent = _node(views["structure"], "praxion.orchestrator")

    assert rd.node_label_lines(agent) == [
        "Main Agent (Orchestrator)",
        "[Runtime agent · Claude Code]",
        "Tier selector, task-slug",
        "propagator, rework-worktree",
        "spawner, subagent dispatcher",
    ]


def test_a_node_without_technology_names_only_its_category(rd, views):
    skills = _node(views["structure"], "praxion.knowledge.skills")

    assert rd.node_label_lines(skills) == [
        "Skills",
        "[Knowledge asset]",
        "Domain expertise modules",
    ]


def test_a_node_without_responsibility_has_no_third_group(rd, views):
    assert rd.node_label_lines(_node(views["index"], "claude_code")) == [
        "Claude Code",
        "[External system]",
    ]
    assert rd.node_label_lines(_node(views["structure"], "praxion.knowledge")) == [
        "Knowledge Layer",
        "[Layer]",
    ]


def test_a_long_name_wraps_before_the_category_line(rd, views):
    skills = _node(views["structure"], "praxion.knowledge.skills")
    long_named = dataclasses.replace(skills, name="Agentic Transactions Architect Shadow Reviewer")

    lines = rd.node_label_lines(long_named)

    assert lines[:3] == ["Agentic Transactions", "Architect Shadow Reviewer", "[Knowledge asset]"]


# --- the legend --------------------------------------------------------------------------------


def test_the_legend_lists_each_category_and_line_meaning_the_view_uses_in_order(rd, views):
    labels = [entry.label for entry in rd.legend_entries(views["structure"])]

    assert labels == [
        "Knowledge asset",
        "Runtime agent",
        "Pipeline document",
        "Layer (boundary)",
        MEANING_ACTS_ON,
        MEANING_READ_ONLY,
    ]


def test_a_legend_sample_is_drawn_with_the_class_of_the_elements_it_stands_for(rd, views):
    entries = rd.legend_entries(views["structure"])

    classes = {entry.label: entry.drawing_class for entry in entries}
    assert classes["Knowledge asset"] == "category_knowledge_asset"
    assert classes["Layer (boundary)"] == "category_layer_frame"
    assert classes[MEANING_ACTS_ON] is None


def test_a_context_view_legend_has_boxes_only_and_the_acts_on_line(rd, views):
    labels = [entry.label for entry in rd.legend_entries(views["index"])]

    assert labels == ["Person", "System in scope", "External system", MEANING_ACTS_ON]


def test_a_dynamic_view_legend_explains_its_numbered_steps_and_nothing_else_about_lines(rd, views):
    labels = [entry.label for entry in rd.legend_entries(views["flow"])]

    assert labels == ["Runtime agent", "Pipeline document", MEANING_STEP]


def test_the_legend_names_the_uncategorised_drawing_when_a_view_has_one(rd, views):
    entries = rd.legend_entries(views["unresolved"])

    assert [(e.label, e.drawing_class) for e in entries] == [
        ("Uncategorised", "category_uncategorised")
    ]


# --- D2 emission -------------------------------------------------------------------------------

ALL_VIEWS = ["index", "structure", "flow", "unresolved"]


def test_the_title_block_names_the_subject_and_the_diagram_type(rd, views):
    text = rd.emit_d2(views["index"])

    assert "Praxion — System Context — System Context diagram" in text
    assert "near: top-center" in text
    assert "Proposal flow — Dynamic diagram" in rd.emit_d2(views["flow"])


@pytest.mark.parametrize("view_id", ALL_VIEWS)
def test_every_label_line_of_every_node_is_in_the_text(rd, views, view_id):
    text = rd.emit_d2(views[view_id])

    for node in views[view_id].nodes:
        for line in rd.node_label_lines(node):
            assert line in text


@pytest.mark.parametrize("view_id", ALL_VIEWS)
def test_labels_are_plain_never_markdown_and_never_the_placeholder(rd, views, view_id):
    text = rd.emit_d2(views[view_id])

    assert "|md" not in text
    assert "|`" not in text
    assert "[...]" not in text


def test_each_arrow_is_drawn_once_pointing_one_way_with_its_label(rd, views):
    text = rd.emit_d2(views["structure"])

    for edge in views["structure"].edges:
        assert edge.label in text
    assert "<->" not in text
    assert "<-" not in text


def test_dynamic_step_labels_carry_their_numbers(rd, views):
    text = rd.emit_d2(views["flow"])

    for label in ("1 · drafts the proposal", "2 · informs the plan", "10 · files the proposal"):
        assert label in text


def test_steps_and_plain_arrows_use_their_own_line_colours(rd, views):
    assert "#4338CA" in rd.emit_d2(views["flow"])
    assert "#4338CA" not in rd.emit_d2(views["structure"])
    assert "#475569" in rd.emit_d2(views["structure"])


def test_only_the_classes_a_view_uses_are_defined(rd, views):
    context = rd.emit_d2(views["index"])
    flow = rd.emit_d2(views["flow"])

    for used in ("category_person", "category_system_in_scope", "category_external_system"):
        assert used in context
    for unused in (
        "category_knowledge_asset",
        "category_runtime_agent",
        "category_tooling",
        "category_layer",
    ):
        assert unused not in context
    assert "category_runtime_agent" in flow
    assert "category_pipeline_document" in flow
    assert "category_person" not in flow


def test_an_uncategorised_element_is_drawn_with_the_uncategorised_class(rd, views):
    assert "category_uncategorised" in rd.emit_d2(views["unresolved"])


def test_the_legend_is_a_container_near_the_bottom_holding_every_entry(rd, views):
    text = rd.emit_d2(views["structure"])

    assert re.search(r"^\s*\"?Legend\"?\s*:", text, re.MULTILINE)
    assert "near: bottom-center" in text
    for entry in rd.legend_entries(views["structure"]):
        assert entry.label in text


def test_a_legend_line_sample_is_an_unlabelled_arrow_ending_at_its_caption(rd, views):
    text = rd.emit_d2(views["structure"])

    assert re.search(r"tail -> caption: \{\s+class: line_acts_on\s+\}", text)
    assert re.search(rf'caption: \{{\s+label: "{re.escape(MEANING_ACTS_ON)}"', text)


def test_the_text_pins_the_layout_engine(rd, views):
    assert "layout-engine: elk" in rd.emit_d2(views["structure"])


def test_the_person_glyph_is_embedded_as_a_data_uri(rd, views):
    text = rd.emit_d2(views["index"])

    payloads = DATA_URI.findall(text)
    assert payloads
    for payload in payloads:
        glyph = base64.b64decode(payload).decode("utf-8")
        assert glyph.lstrip().startswith("<svg")
        assert "</svg>" in glyph
    assert len(set(payloads)) == 1


@pytest.mark.parametrize("view_id", ["structure", "flow", "unresolved"])
def test_a_view_without_a_person_embeds_no_icon(rd, views, view_id):
    text = rd.emit_d2(views[view_id])

    assert "data:" not in text
    assert "icon:" not in text


@pytest.mark.parametrize("view_id", ALL_VIEWS)
def test_the_text_reaches_for_no_network_address(rd, views, view_id):
    assert "http" not in rd.emit_d2(views[view_id])


@pytest.mark.parametrize("view_id", ALL_VIEWS)
def test_emission_is_deterministic(rd, views, view_id):
    assert rd.emit_d2(views[view_id]) == rd.emit_d2(views[view_id])


@pytest.mark.parametrize("view_id", ["structure", "flow"])
def test_emission_does_not_depend_on_the_order_the_toolchain_listed_things(rd, views, view_id):
    view = views[view_id]
    reversed_view = dataclasses.replace(
        view, nodes=tuple(reversed(view.nodes)), edges=tuple(reversed(view.edges))
    )

    assert rd.emit_d2(reversed_view) == rd.emit_d2(view)


def test_a_step_over_a_read_only_relationship_draws_like_every_other_step(rd, views):
    flow = views["flow"]  # step-02 stands for a relationship of kind reads

    assert "stroke-dash" not in rd.emit_d2(flow)
    assert [e.label for e in rd.legend_entries(flow) if e.drawing_class is None] == [MEANING_STEP]


def test_a_dollar_sign_in_model_text_reaches_d2_escaped(rd, views):
    agent = _node(views["structure"], "praxion.orchestrator")
    quoting = dataclasses.replace(agent, responsibility="Reads ${PLUGIN_ROOT} at start")
    view = dataclasses.replace(views["structure"], nodes=(quoting,), edges=())

    text = rd.emit_d2(view)

    assert "\\${PLUGIN_ROOT}" in text
    assert not re.search(r"(?<!\\)\$\{", text)


@pytest.mark.parametrize("element_id", ["title", "LEGEND"])
def test_an_element_named_like_the_title_or_the_legend_stays_apart_from_both(rd, views, element_id):
    developer = dataclasses.replace(_node(views["index"], "developer"), id=element_id)
    view = dataclasses.replace(views["index"], nodes=(developer,), edges=())

    text = rd.emit_d2(view)

    top_level_keys = [key.strip('"').lower() for key in re.findall(r"^(\S+?):", text, re.M)]
    assert len(set(top_level_keys)) == len(top_level_keys)
    assert "Praxion — System Context — System Context diagram" in text
    assert "Developer" in text
