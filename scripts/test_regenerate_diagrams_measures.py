"""The numeric review findings of the diagram command: what each measures and where it fails.

DRC-06 contrast, DRC-07 legibility at 960 px, DRC-08 proportions and fan-in, and DRC-10 drift
from the committed render. The good case is a real `d2` render committed under
`tests/fixtures/diagram_regen/renders/` (`index`); a bad case is that render with one thing
changed, a small hand-written drawing where the boundary itself is the point, or a real render
bad as drawn (`structure` is too wide to read at 960 px, `flow` has overlapping step labels).
The last section runs `--check` through `main`, for the summary line and the exit.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import regenerate_diagrams as rd
from _diagram_checks import run_checks
from _diagram_measures import (
    contrast_outcome,
    drift_outcome,
    first_difference,
    legibility_outcome,
    proportions_outcome,
)
from _diagram_svg import read_svg
from _diagram_testkit import D2_PIN, Toolchain, reading
from _diagram_tokens import LINE_DRAWINGS

CHECKS_PER_VIEW = 11  # DRC-01 to DRC-11, the root-wide DRC-12 apart
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "diagram_regen"
RENDERS = FIXTURES / "renders"
TITLE_INK = 'fill="#0F172A" class="text-bold" style="text-anchor:middle;font-size:24px"'
CANVAS = 'fill="#FFFFFF" class=" fill-N7"'
SVG_OPEN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
CANVAS_RECT = '<rect x="0" y="0" width="{w}" height="{h}" fill="#FFFFFF" stroke-width="0"/>'
LABEL = '<text x="{x}" y="{y}" fill="#000000" style="text-anchor:start;font-size:{size}px">{text}</text>'


@pytest.fixture(scope="module")
def views() -> dict:
    model = json.loads((FIXTURES / "export_small.json").read_text(encoding="utf-8"))
    return {view.id: view for view in rd.project(model).views}


def render(name: str, *edits: tuple[str, str], count: int = 1):
    """A fixture render read with each `(old, new)` applied (the first `count` times)."""
    text = (RENDERS / f"{name}.svg").read_text(encoding="utf-8")
    for old, new in edits:
        assert old in text, f"{name}.svg has no {old!r}"
        text = text.replace(old, new, count)
    return read_svg(text)


def drawing(width: float, height: float, *labels: tuple) -> object:
    """A canvas of `width` x `height` with text lines `(x, y, font size, text)`."""
    body = "".join(LABEL.format(x=x, y=y, size=size, text=text) for x, y, size, text in labels)
    return read_svg(
        SVG_OPEN.format(w=width, h=height) + CANVAS_RECT.format(w=width, h=height) + body + "</svg>"
    )


# --- DRC-06: contrast ----------------------------------------------------------------------------


def test_a_real_render_has_text_and_outlines_above_the_contrast_floors():
    found = contrast_outcome(render("index"))

    assert found.problems == ()
    assert found.measured > 4.5
    assert "lowest text contrast 7.90:1 (floor 4.5:1); lowest outline contrast 3.56:1" in found.held


def ink(colour: str) -> tuple[str, str]:
    return (TITLE_INK, TITLE_INK.replace("#0F172A", colour))


def test_text_at_exactly_the_floor_colour_4_54_to_1_passes():
    assert contrast_outcome(render("index", ink("#767676"))).problems == ()


@pytest.mark.parametrize("colour", ["#777777", "#7A7A7A"])
def test_text_below_4_5_to_1_on_the_canvas_fails(colour):
    found = contrast_outcome(render("index", ink(colour)))

    assert re.search(r"'Praxion .*' has contrast 4\.\d\d:1 against #FFFFFF", found.problems[0])
    assert (found.measured, found.threshold) == (pytest.approx(4.4, abs=0.2), 4.5)


def test_text_on_a_strip_at_3_4_to_1_fails_though_the_canvas_would_pass_it():
    strip = '<rect x="-313" y="-70" width="1131" height="70" fill="#6C6C6C" stroke-width="0"/>'
    drawn = render(
        "index", (f'{CANVAS} stroke-width="0" />', f'{CANVAS} stroke-width="0" />{strip}')
    )

    found = contrast_outcome(drawn)

    assert len(found.problems) == 1
    assert re.fullmatch(r"'Praxion .*' has contrast 3\.4\d:1 against #6C6C6C", found.problems[0])


def arrow_stroke(colour: str) -> tuple[str, str]:
    return ('stroke="#475569" fill="none"', f'stroke="{colour}" fill="none"')


def test_an_arrow_at_3_03_to_1_against_the_canvas_passes():
    assert contrast_outcome(render("index", arrow_stroke("#949494"))).problems == ()


@pytest.mark.parametrize("colour", ["#959595", "#A0A0A0"])
def test_an_arrow_below_3_to_1_against_the_canvas_fails(colour):
    found = contrast_outcome(render("index", arrow_stroke(colour)))

    assert found.problems[0].startswith("the arrow labelled ")
    assert (found.measured, found.threshold) == (pytest.approx(2.8, abs=0.3), 3.0)


def test_a_box_outline_below_3_to_1_fails():
    found = contrast_outcome(render("index", ('stroke="#1D4E89"', 'stroke="#D0D0D0"')))

    assert found.problems[0].startswith("the outline of a rect has contrast 1.")


def test_a_transparent_canvas_is_judged_on_white_and_on_near_black():
    found = contrast_outcome(render("index", (CANVAS, 'fill="transparent"')))

    assert any("against #121212" in problem for problem in found.problems)
    assert not any("against #FFFFFF" in problem for problem in found.problems)


def test_a_text_whose_colour_the_markup_does_not_declare_fails():
    found = contrast_outcome(render("index", (TITLE_INK, TITLE_INK.replace('fill="#0F172A" ', ""))))

    assert found.problems[0].endswith("is not declared in the markup")


# --- DRC-07: legible at the reference width ------------------------------------------------------


def test_a_real_render_reads_at_ten_pixels_or_more_with_no_overlapping_lines():
    found = legibility_outcome(render("index"))

    assert found.problems == ()
    assert (found.measured, found.threshold) == (pytest.approx(10.09, abs=0.01), 10.0)


def test_text_of_font_size_8_fails_naming_the_smallest_reading():
    found = legibility_outcome(render("index", ("font-size:15px", "font-size:8px"), count=99))

    assert found.problems[0].startswith(
        "min rendered text 5.8px at 960px (font-size 8, width 1332) < 10px ("
    )


def test_a_real_render_too_wide_for_its_text_to_reach_ten_pixels_fails():
    markup = (RENDERS / "structure.svg").read_text(encoding="utf-8")
    widened = markup.replace('viewBox="0 0 1332 1391"', 'viewBox="0 0 2000 1391"', 1)

    found = legibility_outcome(read_svg(widened))

    assert len(found.problems) == 1
    assert found.problems[0].startswith(
        "min rendered text 6.7px at 960px (font-size 14, width 2000) < 10px ("
    )


@pytest.mark.parametrize(("width", "size"), [(960, 10), (1920, 20), (400, 10)])
def test_rendered_text_of_ten_pixels_exactly_passes(width, size):
    assert legibility_outcome(drawing(width, 500, (20, 200, size, "label"))).problems == ()


@pytest.mark.parametrize(("width", "size"), [(960, 9), (1920, 19)])
def test_rendered_text_below_ten_pixels_fails(width, size):
    assert legibility_outcome(drawing(width, 500, (20, 200, size, "label"))).problems


def test_a_text_with_no_declared_font_size_fails():
    bare = SVG_OPEN.format(w=960, h=500) + '<text x="5" y="50" fill="#000000">label</text></svg>'

    assert legibility_outcome(read_svg(bare)).problems == ("1 text line(s) declare no font size",)


def test_a_real_render_with_overlapping_step_labels_fails_naming_both():
    found = legibility_outcome(read_svg((RENDERS / "flow.svg").read_text(encoding="utf-8")))

    assert "'1 · drafts the proposal' overlaps '10 · files the proposal' by 4.9px" in found.problems
    assert (found.measured, found.threshold) == (pytest.approx(4.9), 1.0)


def stacked(apart: int):
    return drawing(960, 500, (20, 100, 20, "first"), (20, 100 + apart, 20, "second"))


@pytest.mark.parametrize("apart", [16, 30])
def test_lines_overlapping_by_one_pixel_or_not_at_all_pass(apart):
    assert legibility_outcome(stacked(apart)).problems == ()


def test_lines_overlapping_by_two_pixels_in_both_axes_fail():
    assert legibility_outcome(stacked(15)).problems == ("'first' overlaps 'second' by 2.0px",)


def test_lines_side_by_side_do_not_overlap_however_close_in_height():
    found = legibility_outcome(drawing(960, 500, (20, 100, 20, "first"), (400, 100, 20, "second")))

    assert found.problems == ()


# --- DRC-08: proportions and fan-in --------------------------------------------------------------


def test_a_real_render_is_within_the_proportions_and_the_fan_in(views):
    found = proportions_outcome(render("index"), views["index"])

    assert found.problems == ()
    assert found.held == (
        "width/height 1.48 (1332x898) within 0.5-2.5; most arrows meeting one element: 2 (at most 9)"
    )


@pytest.mark.parametrize(("width", "height"), [(1000, 400), (400, 800)])
def test_width_to_height_at_the_bounds_passes(views, width, height):
    assert proportions_outcome(drawing(width, height), views["index"]).problems == ()


@pytest.mark.parametrize(
    ("width", "height", "said"),
    [
        (1000, 399, "width/height 2.51 (1000x399)"),
        (400, 801, "width/height 0.50 (400x801)"),
        (3000, 917, "width/height 3.27 (3000x917)"),
    ],
)
def test_width_to_height_outside_half_to_two_and_a_half_fails(views, width, height, said):
    found = proportions_outcome(drawing(width, height), views["index"])

    assert found.problems == (f"{said} is outside 0.5-2.5",)


def edges_on_one_element(view, count: int):
    """The view with `count` arrows, each meeting `hub`, no other element more than once."""
    spokes = tuple(rd.Edge("hub", f"spoke{n}", "feeds") for n in range(count))
    return dataclasses.replace(view, edges=spokes)


def test_an_element_meeting_nine_arrows_passes(views):
    found = proportions_outcome(render("index"), edges_on_one_element(views["index"], 9))

    assert found.problems == ()


def test_an_element_meeting_more_than_nine_arrows_fails(views):
    found = proportions_outcome(render("index"), edges_on_one_element(views["index"], 10))

    assert found.problems == ("hub is met by 10 arrows (most allowed: 9)",)
    assert (found.measured, found.threshold) == (10.0, 9.0)


def test_an_arrow_from_an_element_to_itself_meets_it_once(views):
    loops = tuple(rd.Edge("hub", "hub", "retries") for _ in range(5))
    view = edges_on_one_element(views["index"], 4)

    found = proportions_outcome(
        render("index"), dataclasses.replace(view, edges=view.edges + loops)
    )

    assert found.problems == ()


def test_the_failing_reading_is_the_one_that_failed_not_the_first(views):
    found = proportions_outcome(drawing(1000, 400), edges_on_one_element(views["index"], 10))

    assert (found.measured, found.threshold) == (10.0, 9.0)


# --- DRC-10: the committed render is a fresh regeneration ----------------------------------------


@pytest.fixture
def fresh(tmp_path) -> Path:
    built = tmp_path / "built"
    shutil.copytree(RENDERS, built)
    return built


@pytest.fixture
def committed(tmp_path, fresh) -> Path:
    """`rendered/` of a diagram root inside a project, holding the committed copy of `fresh`."""
    root = tmp_path / "project/docs/diagrams/architecture"
    (tmp_path / "project/.git").mkdir(parents=True)
    shutil.copytree(fresh, root / "rendered")
    return root / "rendered"


def test_a_committed_render_identical_to_the_fresh_one_passes(fresh, committed):
    assert drift_outcome("index", fresh, committed).problems == ()


def test_a_changed_byte_is_reported_at_its_offset(fresh, committed):
    original = (fresh / "index.svg").read_bytes()
    (committed / "index.svg").write_bytes(original[:100] + b"X" + original[101:])

    found = drift_outcome("index", fresh, committed)

    assert found.problems == (
        "rendered/index.svg differs from a fresh regeneration (first difference at byte 100)",
    )


@pytest.mark.parametrize(
    ("old", "new", "at"), [(b"abc", b"abcd", 3), (b"abcd", b"abc", 3), (b"", b"a", 0)]
)
def test_a_render_that_is_a_prefix_of_the_other_differs_where_the_shorter_one_ends(old, new, at):
    assert first_difference(old, new) == at


def test_a_view_with_no_committed_render_is_missing_one(fresh, committed):
    (committed / "index.svg").unlink()

    assert drift_outcome("index", fresh, committed).problems == ("rendered/index.svg is missing",)


def test_the_d2_source_written_beside_a_render_is_compared_too(fresh, committed):
    (fresh / "index.d2").write_text("a -> b\n", encoding="utf-8")
    (committed / "index.d2").write_text("a -> c\n", encoding="utf-8")

    found = drift_outcome("index", fresh, committed)

    assert found.problems == (
        "rendered/index.d2 differs from a fresh regeneration (first difference at byte 5)",
    )


@pytest.fixture
def gather(views, fresh, committed):
    """`run_checks` over the good renders against the committed ones: finding by (check, view)."""

    def go() -> dict:
        projection = rd.Projection(tuple(views[n] for n in ("flow", "index", "structure")), ())
        return {(f.check, f.view): f for f in run_checks(projection, fresh, committed.parent)}

    return go


def test_a_render_committed_for_no_view_is_a_root_wide_drift(gather, committed):
    (committed / "gone.svg").write_text("<svg/>", encoding="utf-8")

    stale = gather()[("DRC-10", "-")]

    assert (stale.status, stale.evidence) == (
        "FAIL",
        "rendered/gone.svg belongs to no view (regeneration deletes it)",
    )


def test_each_view_has_one_drift_finding_and_a_root_wide_one_only_when_a_render_is_stale(gather):
    found = gather()

    assert [found[("DRC-10", name)].status for name in ("flow", "index", "structure")] == [
        "PASS"
    ] * 3
    assert ("DRC-10", "-") not in found


def test_the_numeric_findings_carry_their_reading_and_limit_in_check_order(gather):
    found = gather()

    legible = found[("DRC-07", "structure")]
    assert (legible.status, legible.measured, legible.threshold) == (
        "PASS",
        pytest.approx(10.09, abs=0.05),
        10.0,
    )
    assert found[("DRC-06", "index")].measured == pytest.approx(7.9, abs=0.05)
    order = [check for (check, name) in found if name == "index"]
    assert order == sorted(order)
    assert len(order) == CHECKS_PER_VIEW


# --- the stroke widths a fresh render carries ----------------------------------------------------


@pytest.mark.parametrize("name", ["flow", "index", "structure"])
def test_every_stroke_width_read_from_a_fresh_render_is_its_tokens_whole_pixel_width(
    views, tmp_path, name
):
    d2 = _pinned_d2()
    source, drawn = tmp_path / f"{name}.d2", tmp_path / f"{name}.svg"
    source.write_text(rd.emit_d2(views[name]), encoding="utf-8")
    subprocess.run([d2, str(source), str(drawn)], check=True, capture_output=True)
    svg = read_svg(drawn.read_text(encoding="utf-8"))
    view = views[name]

    expected = {node.drawing.stroke_width for node in view.nodes}
    boxes = {s.stroke_width for g in svg.drawn for s in g.shapes if s.stroke_width and not s.icon}
    lines = {a.stroke_width for g in svg.drawn for a in g.arrows}

    assert boxes <= expected, f"boxes drawn at {boxes}, tokens say {expected}"
    assert lines == {LINE_DRAWINGS[edge.line].width for edge in view.edges}
    assert all(isinstance(width, int) for width in boxes | lines)


def _pinned_d2() -> str:
    found = shutil.which("d2")
    said = (
        subprocess.run([found, "--version"], capture_output=True, text=True).stdout if found else ""
    )
    if D2_PIN not in said:
        pytest.skip("the pinned d2 is not on PATH")
    return found


# --- `--check`: the summary line and the exit ----------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A project and a toolchain: the stub `likec4` (reading `model`, else a small one) and the
    real pinned `d2`. Called as `top, tools = workspace()`."""

    def build(model: dict | None = None) -> tuple[Path, Toolchain]:
        top = tmp_path / "work"
        (top / "docs/diagrams/architecture/src").mkdir(parents=True)
        (top / "docs/diagrams/architecture/src/model.c4").write_text("m {}\n", encoding="utf-8")
        monkeypatch.chdir(top)
        tools = Toolchain(tmp_path / "bin")
        if model:
            tools.use_model(model)
        (tools.directory / "d2").unlink()
        (tools.directory / "d2").symlink_to(_pinned_d2())
        return top, tools

    return build


def command(capsys, tools, *argv):
    code = rd.main(list(argv), tool_path=str(tools.directory))
    out, err = capsys.readouterr()
    return code, out, err.splitlines()


SUMMARY = "[diagram-regen] {n} renders · {f} failed checks · {d} drifted"


def test_a_check_on_a_freshly_regenerated_root_exits_0_and_says_nothing_drifted(workspace, capsys):
    top, tools = workspace()

    written = command(capsys, tools)
    checked = command(capsys, tools, "--check")

    assert written[:2] == (0, "")
    assert not any("failed checks" in line for line in written[2])  # the summary is `--check`'s
    assert checked[0] == 0
    assert checked[2][-1] == SUMMARY.format(n=2, f=0, d=0)
    assert [line for line in checked[1].splitlines() if line.startswith("DRC-10")] == [
        "DRC-10 index PASS the committed render is byte-identical to a fresh regeneration",
        "DRC-10 structure PASS the committed render is byte-identical to a fresh regeneration",
    ]


def test_a_check_on_a_root_with_no_committed_renders_reports_each_view_drifted(workspace, capsys):
    code, out, err = command(capsys, workspace()[1], "--check")

    assert code == 1
    assert "DRC-10 index FAIL rendered/index.svg is missing; rendered/index.d2 is missing" in out
    assert err[-1] == SUMMARY.format(n=2, f=2, d=2)


def test_a_check_after_a_committed_render_changed_names_the_byte_and_exits_1(workspace, capsys):
    top, tools = workspace()
    command(capsys, tools)
    committed = top / "docs/diagrams/architecture/rendered/index.svg"
    original = committed.read_bytes()
    committed.write_bytes(original[:50] + b"#" + original[51:])

    code, out, err = command(capsys, tools, "--check")

    assert code == 1
    assert (
        "DRC-10 index FAIL rendered/index.svg differs from a fresh regeneration (first difference at byte 50)"
        in out
    )
    assert err[-1] == SUMMARY.format(n=2, f=1, d=1)
    assert (
        committed.read_bytes() == original[:50] + b"#" + original[51:]
    )  # `--check` writes nothing


def test_the_summary_counts_a_failed_check_that_is_not_drift_apart(workspace, capsys):
    _, tools = workspace(reading("index", "unresolved"))
    command(capsys, tools)

    code, out, err = command(capsys, tools, "--check")

    assert code == 1
    assert "DRC-05 unresolved FAIL" in out
    assert re.fullmatch(
        r"\[diagram-regen\] 2 renders · [1-9]\d* failed checks · 0 drifted", err[-1]
    )
