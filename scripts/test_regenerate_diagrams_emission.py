"""The legend and the D2 emission of the diagram regeneration command, `scripts/regenerate_diagrams.py`.

These tests pin the legend each view carries, the D2 text emitted for a view (title block,
node and arrow labels, the classes it defines, the embedded person glyph, determinism and
independence from the toolchain's listing order) and the layout intent a view declares
(direction, layer frames). The model is the small export reading
`_diagram_testkit.small_export` loads. The command is imported as `regenerate_diagrams`, from this directory; it must import with the
standard library alone and have no side effect at import time. The surface of the pure core
these tests assume is stated in `_diagram_testkit.py`.
"""

from __future__ import annotations

import base64
import dataclasses
import importlib
import re

import pytest
from _diagram_testkit import node_of, small_export

MEANING_ACTS_ON = "acts on (invokes, writes)"
MEANING_READ_ONLY = "read-only flow (consumed, not modified)"
MEANING_STEP = "numbered step, in order (dynamic views)"

DATA_URI = re.compile(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)")


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


@pytest.fixture
def model() -> dict:
    return small_export()


@pytest.fixture
def views(rd, model) -> dict:
    return {view.id: view for view in rd.project(model).views}


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
    agent = node_of(views["structure"], "praxion.orchestrator")
    quoting = dataclasses.replace(agent, responsibility="Reads ${PLUGIN_ROOT} at start")
    view = dataclasses.replace(views["structure"], nodes=(quoting,), edges=())

    text = rd.emit_d2(view)

    assert "\\${PLUGIN_ROOT}" in text
    assert not re.search(r"(?<!\\)\$\{", text)


@pytest.mark.parametrize("element_id", ["title", "LEGEND"])
def test_an_element_named_like_the_title_or_the_legend_stays_apart_from_both(rd, views, element_id):
    developer = dataclasses.replace(node_of(views["index"], "developer"), id=element_id)
    view = dataclasses.replace(views["index"], nodes=(developer,), edges=())

    text = rd.emit_d2(view)

    top_level_keys = [key.strip('"').lower() for key in re.findall(r"^(\S+?):", text, re.M)]
    assert len(set(top_level_keys)) == len(top_level_keys)
    assert "Praxion — System Context — System Context diagram" in text
    assert "Developer" in text


# --- layout intent: direction, groups and lone frames -------------------------------------------


def _structure_view(rd, edit):
    """The `structure` view of the small export, its raw form changed by `edit(raw_view)`."""
    model = small_export()
    edit(model["views"]["structure"])
    return {v.id: v for v in rd.project(model).views}["structure"]


@pytest.mark.parametrize(
    ("declared", "d2"),
    [("TB", "down"), ("BT", "up"), ("LR", "right"), ("RL", "left"), (None, "down")],
)
def test_a_views_auto_layout_direction_becomes_the_d2_direction(rd, declared, d2):
    view = _structure_view(rd, lambda raw: raw.update(autoLayout={"direction": declared}))

    assert view.direction == d2
    assert f"direction: {d2}\n" in rd.emit_d2(view).split("vars:")[0]


def test_a_view_group_is_drawn_as_a_titled_layer_frame_around_its_members(rd):
    def group(raw):
        for node in raw["nodes"]:
            if node["id"] in ("praxion.orchestrator", "praxion.doc_idea"):
                node["parent"] = "@gr1"
        raw["nodes"].append(
            {"id": "@gr1", "kind": "@group", "title": "Runtime", "parent": None, "children": [
                "praxion.orchestrator", "praxion.doc_idea"]}
        )  # fmt: skip

    view = _structure_view(rd, group)

    drawn = {node.id: node for node in view.nodes}
    assert (drawn["@gr1"].name, drawn["@gr1"].category, drawn["@gr1"].is_frame) == (
        "Runtime",
        "Layer",
        True,
    )
    assert drawn["praxion.doc_idea"].parent == "@gr1"
    assert "[Layer]" in rd.emit_d2(view)


def test_a_frame_stays_drawn_when_no_arrow_touches_it(rd):
    def untouched(raw):
        raw["edges"] = [
            e for e in raw["edges"] if "praxion.knowledge" not in (e["source"], e["target"])
        ]

    view = _structure_view(rd, untouched)

    assert "praxion.knowledge" in {node.id for node in view.nodes}


def test_every_legend_has_the_same_width(rd, views):
    widths = {re.search(r"^\s*width: (\d+)$", rd.emit_d2(v), re.M)[1] for v in views.values()}

    assert len(widths) == 1
