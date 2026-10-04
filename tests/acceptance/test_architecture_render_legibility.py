"""Renders stay legible at the width they are embedded, balanced, and above contrast floors.

Scaled to the 960-pixel reference embed width, no text renders below 10 pixels and
no two labels overlap; every render's width-to-height ratio lies between 0.5 and
2.5; no element is met by more than 9 arrows; text meets 4.5:1 against the surface
behind it and outlines and arrows meet 3:1 against the canvas (a transparent canvas
is judged against both a white and a near-black page).
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.architecture_model import RENDER_DIR, current_model
from tests.acceptance.drivers.render_review import (
    fan_in_violations,
    graphic_contrast_violations,
    overlap_violations,
    proportion_violations,
    text_contrast_violations,
    text_height_violations,
)
from tests.acceptance.drivers.svg_render import read_render

RENDERS = sorted(RENDER_DIR.glob("*.svg"))


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_no_text_renders_below_ten_pixels_at_the_reference_embed_width(render_path) -> None:
    assert text_height_violations(read_render(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_no_two_text_labels_overlap(render_path) -> None:
    assert overlap_violations(read_render(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_render_proportions_stay_between_a_strip_and_a_ribbon(render_path) -> None:
    assert proportion_violations(read_render(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_no_element_is_met_by_more_than_nine_arrows(render_path) -> None:
    view = current_model().views.get(render_path.stem)
    assert view is not None, f"no view of the model has the id of render {render_path.name}"

    assert fan_in_violations(view) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_text_meets_four_and_a_half_to_one_contrast_against_its_surface(render_path) -> None:
    assert text_contrast_violations(read_render(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_outlines_and_arrows_meet_three_to_one_contrast_against_the_canvas(render_path) -> None:
    assert graphic_contrast_violations(read_render(render_path)) == []
