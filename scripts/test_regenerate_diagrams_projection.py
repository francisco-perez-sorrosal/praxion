"""The projection of the diagram regeneration command, `scripts/regenerate_diagrams.py`.

These tests pin how an element gets its one category, how each exported view projects to
nodes and edges with a finding for what cannot be drawn, how an arrow is labelled from the
relationships it stands for, and how a node's text wraps and reads. The model is the small
export reading `_diagram_testkit.small_export` loads. The command is imported as `regenerate_diagrams`, from this directory; it must import with the
standard library alone and have no side effect at import time. The surface of the pure core
these tests assume is stated in `_diagram_testkit.py`.
"""

from __future__ import annotations

import dataclasses
import importlib
import json

import pytest
from _diagram_testkit import edge_of, node_of, small_export

LABEL_WIDTH = 28


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


@pytest.fixture
def model() -> dict:
    return small_export()


@pytest.fixture
def views(rd, model) -> dict:
    return {view.id: view for view in rd.project(model).views}


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
    developer = node_of(views["index"], "developer")
    external = node_of(views["index"], "claude_code")
    agent = node_of(views["structure"], "praxion.orchestrator")

    assert (developer.name, developer.category) == ("Developer", "Person")
    assert developer.responsibility == "Writes the code and reviews the diagrams"
    assert (external.category, external.technology, external.responsibility) == (
        "External system",
        None,
        None,
    )
    assert (agent.category, agent.technology) == ("Runtime agent", "Claude Code")


def test_the_responsibility_is_the_summary_when_the_model_records_one(views):
    assert node_of(views["index"], "praxion").responsibility == "Agent harness for software work"


def test_a_component_takes_its_category_from_its_metadata(views):
    structure = views["structure"]

    assert node_of(structure, "praxion.knowledge.skills").category == "Knowledge asset"
    assert node_of(structure, "praxion.knowledge").category == "Layer"


def test_a_node_is_a_frame_when_the_view_draws_its_children(views):
    structure = views["structure"]

    assert node_of(structure, "praxion.knowledge").is_frame
    assert not node_of(structure, "praxion.knowledge.skills").is_frame
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
    assert edge_of(
        views["structure"], "praxion.knowledge.commands", "praxion.orchestrator"
    ).label == ("triggers")


def test_several_relationships_read_first_title_plus_the_rest(views):
    structure = views["structure"]

    assert edge_of(structure, "praxion.knowledge.skills", "praxion.orchestrator").label == (
        "constrains +1 more"
    )
    assert edge_of(structure, "praxion.orchestrator", "praxion.knowledge.commands").label == (
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

    assert edge_of(
        views["structure"], "praxion.orchestrator", "praxion.knowledge.commands"
    ).label == ("dispatches +2 more")


def test_no_label_is_the_toolchains_ellipsis_placeholder(views):
    labels = [edge.label for view in views.values() for edge in view.edges]

    assert labels
    assert not [label for label in labels if "[...]" in label or not label.strip()]


def test_a_relationship_of_kind_reads_is_a_read_only_arrow(views):
    structure = views["structure"]

    assert edge_of(structure, "praxion.doc_idea", "praxion.orchestrator").line == "read-only"
    assert edge_of(structure, "praxion.orchestrator", "praxion.doc_idea").line == "acts-on"
    assert edge_of(structure, "praxion.knowledge.skills", "praxion.orchestrator").line == "acts-on"


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
    agent = node_of(views["structure"], "praxion.orchestrator")

    assert rd.node_label_lines(agent) == [
        "Main Agent (Orchestrator)",
        "[Runtime agent · Claude Code]",
        "Tier selector, task-slug",
        "propagator, rework-worktree",
        "spawner, subagent dispatcher",
    ]


def test_a_node_without_technology_names_only_its_category(rd, views):
    skills = node_of(views["structure"], "praxion.knowledge.skills")

    assert rd.node_label_lines(skills) == [
        "Skills",
        "[Knowledge asset]",
        "Domain expertise modules",
    ]


def test_a_node_without_responsibility_has_no_third_group(rd, views):
    assert rd.node_label_lines(node_of(views["index"], "claude_code")) == [
        "Claude Code",
        "[External system]",
    ]
    assert rd.node_label_lines(node_of(views["structure"], "praxion.knowledge")) == [
        "Knowledge Layer",
        "[Layer]",
    ]


def test_a_long_name_wraps_before_the_category_line(rd, views):
    skills = node_of(views["structure"], "praxion.knowledge.skills")
    long_named = dataclasses.replace(skills, name="Agentic Transactions Architect Shadow Reviewer")

    lines = rd.node_label_lines(long_named)

    assert lines[:3] == ["Agentic Transactions", "Architect Shadow Reviewer", "[Knowledge asset]"]
