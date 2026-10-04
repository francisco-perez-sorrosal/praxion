"""Documents keep showing the renders, and every embed describes what it shows.

Every documentation embed of an architecture render resolves to a committed render
in the vector format used today (`.svg`); every embed's alternative text names the
view's title and its C4 diagram type; the diagram catalog lists every committed
architecture render.
"""

from __future__ import annotations

import pytest

from tests.acceptance.drivers.architecture_model import RENDER_DIR, current_model
from tests.acceptance.drivers.doc_embeds import architecture_embeds, catalog_text
from tests.acceptance.drivers.render_review import C4_DIAGRAM_TYPES
from tests.acceptance.drivers.svg_render import normalise

EMBEDS = architecture_embeds()
RENDERS = sorted(RENDER_DIR.glob("*.svg"))


def _label(embed) -> str:
    return f"{embed.document.name}:{embed.target}"


def test_documents_embed_architecture_renders() -> None:
    assert EMBEDS, "no document embeds an architecture render"


@pytest.mark.parametrize("embed", EMBEDS, ids=_label)
def test_every_embed_resolves_to_a_committed_svg_render(embed) -> None:
    resolved = embed.resolved

    assert resolved.suffix == ".svg", f"{_label(embed)} does not embed the vector format"
    assert resolved.parent == RENDER_DIR.resolve(), (
        f"{_label(embed)} points outside the committed renders"
    )
    assert resolved.is_file(), f"{_label(embed)} resolves to no committed render"


@pytest.mark.parametrize("embed", EMBEDS, ids=_label)
def test_every_embed_alt_text_names_the_view_title_and_c4_diagram_type(embed) -> None:
    view = current_model().views.get(embed.resolved.stem)
    assert view is not None, f"{_label(embed)} embeds a render with no view in the model"
    alt = normalise(embed.alt).casefold()

    assert normalise(view.title or "").casefold() in alt, (
        f"alt text {embed.alt!r} does not name {view.title!r}"
    )
    assert any(kind in alt for kind in C4_DIAGRAM_TYPES), (
        f"alt text {embed.alt!r} names no C4 diagram type"
    )


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_the_diagram_catalog_lists_every_committed_render(render_path) -> None:
    assert f"rendered/{render_path.name}" in catalog_text()
