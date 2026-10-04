"""The restyle changes how the architecture is shown, not what it claims.

The views still cover the system context, the internal building blocks, the
forward agent pipeline, the continuous-improvement loop and the rework loop; every
element and relationship the model recorded before the change is still recorded,
each element under its same identity; and every element is drawn in at least one
committed render.
"""

from __future__ import annotations

from tests.acceptance.drivers.architecture_model import RENDER_DIR, base_model, current_model
from tests.acceptance.drivers.model_coverage import (
    lost_elements,
    lost_relationships,
    uncovered_subjects,
    undrawn_elements,
    views_without_render,
)


def test_the_rendered_views_still_cover_every_subject_documented_today() -> None:
    assert uncovered_subjects(current_model(), RENDER_DIR) == []


def test_every_view_of_the_model_has_a_committed_render() -> None:
    assert views_without_render(current_model(), RENDER_DIR) == []


def test_every_element_recorded_before_the_change_keeps_its_identity() -> None:
    assert lost_elements(base_model(), current_model()) == []


def test_every_relationship_recorded_before_the_change_is_still_recorded() -> None:
    assert lost_relationships(base_model(), current_model()) == []


def test_every_element_is_drawn_in_at_least_one_render() -> None:
    assert undrawn_elements(current_model(), RENDER_DIR) == []
