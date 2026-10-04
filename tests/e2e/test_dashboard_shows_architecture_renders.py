"""The dashboard keeps showing every committed architecture render, with nothing stripped.

Served against this repository, the dashboard's architecture page lists every
committed architecture render, and its existing diagram route serves each one with
every text, legend entry and category mark of the committed file intact; where the
page shows a render's markup inline, that markup keeps every text of the committed
file.
"""

from __future__ import annotations

import html
import tempfile
from pathlib import Path

import pytest

from tests.acceptance.drivers.architecture_model import RENDER_DIR, REPO_ROOT
from tests.acceptance.drivers.svg_render import normalise, read_render
from tests.e2e.drivers.dashboard import running_dashboard

RENDERS = sorted(RENDER_DIR.glob("*.svg"))


@pytest.fixture(scope="module")
def dashboard():
    with running_dashboard() as served:
        yield served


@pytest.fixture(scope="module")
def architecture_page(dashboard):
    page = dashboard.get("/architecture")
    assert page.status == 200, f"the architecture page answered {page.status}"
    return normalise(html.unescape(page.body))


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _served_render(body: str):
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as handle:
        handle.write(body)
    try:
        return read_render(Path(handle.name))
    finally:
        Path(handle.name).unlink()


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_the_architecture_page_lists_every_committed_render(architecture_page, render_path) -> None:
    committed_texts = [line.text for line in read_render(render_path).lines]

    listed_by_route = _relative(render_path) in architecture_page
    shown_inline = all(text in architecture_page for text in committed_texts)

    assert listed_by_route or shown_inline, (
        f"the architecture page neither lists nor shows {render_path.name}"
    )


@pytest.mark.parametrize("render_path", RENDERS, ids=lambda p: p.stem)
def test_the_diagram_route_serves_each_render_with_its_text_legend_and_marks_intact(
    dashboard, render_path
) -> None:
    committed = read_render(render_path)

    response = dashboard.diagram(_relative(render_path))
    served = _served_render(response.body)

    assert response.status == 200, (
        f"the diagram route answered {response.status} for {render_path.name}"
    )
    assert "svg" in response.content_type
    assert [line.text for line in served.lines] == [line.text for line in committed.lines]
    assert sorted(s.mark for s in served.shapes if s.visible) == sorted(
        s.mark for s in committed.shapes if s.visible
    )
