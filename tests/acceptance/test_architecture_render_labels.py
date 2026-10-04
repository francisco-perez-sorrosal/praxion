"""Every render states, from itself alone, what it shows and what each box and line means.

Each element shows its name, a line stating its category or technology, and the
responsibility the model records for it; each arrow carries a specific intent label
and points one way; each render shows a title naming its subject and its C4 diagram
type.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.architecture_model import RENDER_DIR, category_of, current_model
from tests.acceptance.drivers.render_review import (
    arrow_violations,
    element_kind_line_violations,
    element_text_violations,
    title_violations,
)
from tests.acceptance.drivers.svg_render import read_render

RENDERS = sorted(RENDER_DIR.glob("*.svg"))


def _view(render_path):
    view = current_model().views.get(render_path.stem)
    assert view is not None, f"no view of the model has the id of render {render_path.name}"
    return view


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_every_drawn_element_shows_its_name_and_recorded_responsibility(render_path) -> None:
    assert element_text_violations(read_render(render_path), _view(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_every_drawn_element_shows_a_category_or_technology_line(render_path) -> None:
    violations = element_kind_line_violations(
        read_render(render_path), _view(render_path), category_of
    )

    assert violations == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_every_arrow_carries_a_specific_intent_label_and_one_arrowhead(render_path) -> None:
    assert arrow_violations(read_render(render_path), _view(render_path)) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_every_render_shows_a_title_naming_its_subject_and_c4_diagram_type(render_path) -> None:
    assert title_violations(read_render(render_path), _view(render_path)) == []
