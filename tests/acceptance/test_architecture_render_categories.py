"""A reader tells element categories apart at a glance, and each view explains its notation.

Every element of Praxion's architecture model belongs to one category of the
vocabulary (people, the system in scope, external systems, knowledge assets,
runtime agents, pipeline documents, persistent stores, tooling). In every committed
render, categories in one view differ by a mark other than colour, a category is
drawn the same way in every view, and the view's own legend names each category
and line style it uses with a sample of how it is drawn.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.architecture_model import RENDER_DIR, category_of, current_model
from tests.acceptance.drivers.render_review import (
    PRAXION_VOCABULARY,
    category_consistency_violations,
    category_distinctness_violations,
    legend_category_violations,
    legend_line_style_violations,
    vocabulary_violations,
)
from tests.acceptance.drivers.svg_render import read_render

RENDERS = sorted(RENDER_DIR.glob("*.svg"))


def _view(render_path):
    view = current_model().views.get(render_path.stem)
    assert view is not None, f"no view of the model has the id of render {render_path.name}"
    return view


def test_every_model_element_belongs_to_one_vocabulary_category_and_none_are_merged() -> None:
    categories = [category_of(element) for element in current_model().elements.values()]

    assert vocabulary_violations(categories, PRAXION_VOCABULARY) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_categories_in_a_view_differ_by_a_mark_other_than_colour(render_path) -> None:
    violations = category_distinctness_violations(
        read_render(render_path), _view(render_path), category_of
    )

    assert violations == []


def test_a_category_is_drawn_the_same_way_in_every_view() -> None:
    pairs = [(read_render(path), _view(path)) for path in RENDERS]

    assert category_consistency_violations(pairs, category_of) == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_each_view_legend_names_and_samples_every_category_it_draws(render_path) -> None:
    violations = legend_category_violations(
        read_render(render_path), _view(render_path), category_of
    )

    assert violations == []


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_each_view_legend_samples_every_line_style_it_uses(render_path) -> None:
    assert legend_line_style_violations(read_render(render_path)) == []
