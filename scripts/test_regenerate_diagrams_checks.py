"""The structural review findings of the diagram command: what each check reads and when it fails.

`run_checks(projection, built, root)` reads the renders in `built`, the markdown around `root`
and the projected views, and returns one finding per check per view plus the root-wide DRC-12.
Each check has a passing reading and a failing one. The good renders are real `d2` output
committed under `tests/fixtures/diagram_regen/renders/` (three views of `export_small.json`:
a system context, a component view with frames and a read-only arrow, and a dynamic view); a
failing reading is a good render with one thing changed, written next to the test that needs
it, or a view with one thing changed. One test regenerates the renders with the pinned `d2`
and compares the bytes, so a change to the drawing vocabulary fails there first.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from _diagram_testkit import D2_PIN, Toolchain

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "diagram_regen"
RENDERS = FIXTURES / "renders"
RENDERED_VIEWS = ("flow", "index", "structure")
STRUCTURAL_CHECKS = ("DRC-01", "DRC-02", "DRC-03", "DRC-04", "DRC-05", "DRC-09", "DRC-11")
CHECKS_PER_VIEW = 11  # the structural seven and the numeric DRC-06, DRC-07, DRC-08, DRC-10
INDEX_TYPE = "System Context"
INDEX_TITLE = "Praxion — System Context"


@pytest.fixture
def rd():
    return importlib.import_module("regenerate_diagrams")


@pytest.fixture
def checks():
    return importlib.import_module("_diagram_checks")


@pytest.fixture
def svg():
    return importlib.import_module("_diagram_svg")


@pytest.fixture
def d2_path() -> str:
    """The pinned `d2` on PATH; the test is skipped without it."""
    found = shutil.which("d2")
    version = (
        subprocess.run([found, "--version"], capture_output=True, text=True).stdout if found else ""
    )
    if D2_PIN not in version:
        pytest.skip("the pinned d2 is not on PATH")
    return found


@pytest.fixture
def views(rd) -> dict:
    model = json.loads((FIXTURES / "export_small.json").read_text(encoding="utf-8"))
    return {view.id: view for view in rd.project(model).views}


@pytest.fixture
def built(tmp_path) -> Path:
    """A copy of the good renders that a test may change one of."""
    copy = tmp_path / "built"
    shutil.copytree(RENDERS, copy)
    return copy


@pytest.fixture
def project(tmp_path) -> Path:
    """A project directory with a `.git` marker and a diagram root with nothing around it."""
    top = tmp_path / "project"
    (top / ".git").mkdir(parents=True)
    (top / "docs/diagrams/architecture/rendered").mkdir(parents=True)
    return top


@pytest.fixture
def run(rd, checks, views, built, project):
    """Run the checks on the (possibly changed) renders; `edit` changes a view first."""

    def go(*, findings=(), edit=None, ids=RENDERED_VIEWS) -> dict:
        chosen = [edit(views[i]) if edit and edit.view == i else views[i] for i in ids]
        projection = rd.Projection(tuple(chosen), tuple(findings))
        root = project / "docs/diagrams/architecture"
        return {(f.check, f.view): f for f in checks.run_checks(projection, built, root)}

    return go


def change(built: Path, view: str, old: str, new: str, *, count: int = 1) -> None:
    """Replace `old` in a built render, failing the test when the render has no such text."""
    path = built / f"{view}.svg"
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{view}.svg has no {old!r}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def change_matching(built: Path, view: str, pattern: str, replacement: str) -> None:
    path = built / f"{view}.svg"
    text, found = re.subn(pattern, replacement, path.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert found, f"{view}.svg has nothing matching {pattern!r}"
    path.write_text(text, encoding="utf-8")


class EditView:
    """A change to one projected view, applied by `run(edit=...)`."""

    def __init__(self, view: str, apply) -> None:
        self.view, self.apply = view, apply

    def __call__(self, view):
        return self.apply(view)


def failing(found: dict, check: str, view: str) -> str:
    finding = found[(check, view)]
    assert finding.status == "FAIL", f"{check} {view} passed: {finding.evidence}"
    return finding.evidence


# --- the good renders pass every check ---------------------------------------------------------


@pytest.mark.parametrize("view", RENDERED_VIEWS)
def test_a_real_render_passes_each_structural_check(run, view):
    found = run()

    statuses = {
        check: f.status
        for (check, name), f in found.items()
        if name == view and check in STRUCTURAL_CHECKS
    }

    assert statuses == dict.fromkeys(STRUCTURAL_CHECKS, "PASS")


def test_there_is_one_finding_per_check_per_view_and_one_root_wide_regeneration_finding(run):
    found = run()

    assert len(found) == CHECKS_PER_VIEW * len(RENDERED_VIEWS) + 1
    regenerated = found[("DRC-12", "-")]
    assert (regenerated.status, regenerated.evidence) == (
        "PASS",
        "regenerated 3 view(s) without a failure",
    )


@pytest.mark.parametrize("name", RENDERED_VIEWS)
def test_a_good_render_is_what_the_pinned_d2_draws_from_the_current_emission(
    rd, views, tmp_path, d2_path, name
):
    edge = importlib.import_module("_diagram_edge")
    source, drawn = tmp_path / f"{name}.d2", tmp_path / f"{name}.svg"
    source.write_text(rd.emit_d2(views[name]), encoding="utf-8")

    subprocess.run([d2_path, str(source), str(drawn)], check=True, capture_output=True)

    scrubbed = edge.D2_STAMP.sub(edge.SCRUBBED_D2_STAMP, drawn.read_bytes())
    assert scrubbed == (RENDERS / f"{name}.svg").read_bytes(), f"{name}.svg is out of date"


# --- DRC-01: the title names the subject and the C4 type -----------------------------------------


def test_a_title_without_a_c4_type_fails(run, built):
    change(built, "structure", " — Component diagram", " diagram")

    assert "names none of" in failing(run(), "DRC-01", "structure")


def test_a_title_that_is_not_shown_fails(run, built):
    change(built, "index", f"{INDEX_TITLE} — {INDEX_TYPE} diagram", "A diagram")

    assert "no group shows the view title" in failing(run(), "DRC-01", "index")


def test_the_models_own_type_tag_finding_is_part_of_the_views_title_finding(rd, run):
    modelled = rd.Finding(
        "DRC-01", "index", "FAIL", "view carries 0 C4 type tags, expected 1: none"
    )

    assert failing(run(findings=[modelled]), "DRC-01", "index") == modelled.evidence


# --- DRC-02: the legend is complete --------------------------------------------------------------


def test_a_render_without_a_legend_heading_fails(run, built):
    change(built, "index", ">Legend<", ">Key<")

    assert "'Legend'" in failing(run(), "DRC-02", "index")


def test_a_legend_that_misses_a_category_name_fails(run, built):
    change(built, "structure", ">Knowledge asset</text>", ">Assets</text>")

    assert "'Knowledge asset'" in failing(run(), "DRC-02", "structure")


def test_a_legend_sample_drawn_unlike_its_category_fails(run, built):
    change_matching(
        built, "structure", r'(fill=")#FDEFD9(".{0,400}?>Runtime agent</text>)', r"\1#FFFFFF\2"
    )

    assert "'Runtime agent' (box)" in failing(run(), "DRC-02", "structure")


def test_a_legend_without_a_sample_of_a_dash_style_the_view_uses_fails(run, built):
    change_matching(
        built,
        "structure",
        r'stroke-dasharray:[^;"]*;(?=" marker-end[^>]*/><rect[^>]*/><text[^>]*>read-only flow)',
        "",
    )

    assert "no dashed arrow sample" in failing(run(), "DRC-02", "structure")


# --- DRC-03: an element states its name, category or technology and responsibility ---------------


def test_an_element_whose_name_is_not_spelled_fails(run, built):
    change(built, "structure", ">Skills</tspan>", ">Abilities</tspan>")

    assert "'Skills'" in failing(run(), "DRC-03", "structure")


def test_an_element_that_states_neither_category_nor_technology_fails(run, built):
    change_matching(
        built, "structure", r"(>Skills</tspan><tspan[^>]*>)\[Knowledge asset\]", r"\1[Asset]"
    )

    assert "'Skills' states neither" in failing(run(), "DRC-03", "structure")


def test_an_element_that_drops_its_responsibility_fails(run, built):
    change(built, "structure", "Domain expertise modules", "Domain modules")

    assert "'Skills' does not show its responsibility" in failing(run(), "DRC-03", "structure")


def test_a_technology_line_satisfies_the_kind_line(run, built):
    found = run()

    assert found[("DRC-03", "flow")].status == "PASS"  # `[Runtime agent · Claude Code]`


# --- DRC-04: arrows state intent and point one way -----------------------------------------------


def test_an_arrow_with_two_arrowheads_fails(run, built):
    path = built / "index.svg"
    text = path.read_text(encoding="utf-8")
    heads = list(re.finditer(r'marker-end="(url\(#[^)]*\))"', text))
    element_arrow = heads[1]  # the first is the legend's sample
    both = f'marker-start="{element_arrow.group(1)}" ' + element_arrow.group(0)
    path.write_text(
        text[: element_arrow.start()] + both + text[element_arrow.end() :], encoding="utf-8"
    )

    assert "has two arrowheads" in failing(run(), "DRC-04", "index")


def test_an_arrow_labelled_with_a_generic_verb_fails(run, built):
    change(built, "index", ">develops<", ">uses<")

    assert "the arrow labelled 'uses' states no intent" in failing(run(), "DRC-04", "index")


def test_an_arrow_with_no_label_fails(run, built):
    change(built, "index", ">develops<", "><")

    assert "states no intent" in failing(run(), "DRC-04", "index")


def test_a_step_label_that_is_only_a_generic_verb_after_its_number_fails(run, built):
    change(built, "flow", ">1 · drafts the proposal<", ">1 · calls<")

    assert "'1 · calls' states no intent" in failing(run(), "DRC-04", "flow")


def test_fewer_arrows_drawn_than_the_view_has_edges_fails(rd, run, views):
    index = views["index"]
    extra = dataclasses.replace(index.edges[0], target="claude_code", label="reaches")

    found = run(edit=EditView("index", lambda v: dataclasses.replace(v, edges=(*v.edges, extra))))

    assert "2 arrows drawn, the view has 3" in failing(found, "DRC-04", "index")


# --- DRC-05: categories are told apart without colour --------------------------------------------


def test_two_categories_drawn_with_one_mark_fail(run, built):
    pipeline_document = "M 144 249 L 144 152 L 326 152 L 326 249 C 296 228 265 228 235 249 C 205 270 174 270 144 249 Z"
    change(built, "structure", pipeline_document, "M 1 1 L 2 2 L 3 3 L 4 4 L 5 5 L 6 6 Z")

    evidence = failing(run(), "DRC-05", "structure")

    assert "Knowledge asset, Pipeline document are drawn alike without colour" in evidence


def test_a_category_drawn_differently_in_two_renders_fails_in_the_later_one(run, built):
    change(built, "structure", 'fill="#FDEFD9"', 'fill="#FFFFFF"')

    found = run()

    assert "'Runtime agent' (box) is drawn differently from view flow" in failing(
        found, "DRC-05", "structure"
    )
    assert found[("DRC-05", "flow")].status == "PASS"


def test_an_element_without_a_category_fails_through_the_models_own_finding(rd, run):
    modelled = rd.Finding("DRC-05", "index", "FAIL", "1 element(s) draw as Uncategorised: x")

    assert failing(run(findings=[modelled]), "DRC-05", "index") == modelled.evidence


# --- DRC-09: one level of abstraction ------------------------------------------------------------


def test_a_box_beside_its_own_ancestor_box_fails(run):
    def flatten(view):
        return dataclasses.replace(
            view,
            nodes=tuple(
                dataclasses.replace(n, is_frame=False) if n.id == "praxion.knowledge" else n
                for n in view.nodes
            ),
        )

    evidence = failing(run(edit=EditView("structure", flatten)), "DRC-09", "structure")

    assert (
        "praxion.knowledge.skills is drawn as a box beside its ancestor praxion.knowledge"
        in evidence
    )


def test_an_ancestor_that_is_not_the_parent_still_counts(rd, checks, views):
    def box(element_id):
        return rd.Node(element_id, element_id, rd.UNCATEGORISED, None, None, False)

    view = dataclasses.replace(views["index"], nodes=(box("a"), box("a.b.c")))

    assert checks.abstraction_problems(view) == [
        "a.b.c is drawn as a box beside its ancestor a, also a box"
    ]


def test_a_view_that_draws_an_ancestor_only_as_a_frame_passes(checks, views):
    assert checks.abstraction_problems(views["structure"]) == []


# --- DRC-11: embeds describe what they show ------------------------------------------------------


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def embed(alt: str, target: str = "diagrams/architecture/rendered/index.svg") -> str:
    return f"![{alt}]({target})\n"


CATALOG = "| `architecture/` | `rendered/{flow,index,structure}.{d2,svg}` |\n"


def test_a_project_with_neither_embeds_nor_catalog_passes_saying_so(run):
    evidence = run()[("DRC-11", "index")].evidence

    assert evidence == "no embeds or catalog in scope"


def test_an_embed_whose_alt_names_the_title_and_type_and_a_catalog_listing_it_pass(run, project):
    write(project / "docs/arch.md", embed(f"{INDEX_TITLE}, C4 {INDEX_TYPE} diagram"))
    write(project / "docs/diagrams/README.md", CATALOG)

    found = run()

    assert found[("DRC-11", "index")].status == "PASS"
    assert found[("DRC-11", "index")].evidence != "no embeds or catalog in scope"


def test_an_embed_in_the_project_root_readme_is_found_through_the_git_marker(run, project):
    write(
        project / "README.md", embed("a diagram", "docs/diagrams/architecture/rendered/index.svg")
    )

    evidence = failing(run(), "DRC-11", "index")

    assert "README.md: alt text 'a diagram' lacks the view title" in evidence


def test_an_alt_text_without_the_c4_type_name_fails(run, project):
    write(
        project / "docs/arch.md",
        embed(
            "Praxion — Knowledge and Orchestration", "diagrams/architecture/rendered/structure.svg"
        ),
    )

    assert "lacks the C4 type name" in failing(run(), "DRC-11", "structure")


def test_a_catalog_that_does_not_list_a_render_fails(run, project):
    write(project / "docs/diagrams/README.md", "| `architecture/` | `rendered/index.svg` |\n")

    found = run()

    assert found[("DRC-11", "index")].status == "PASS"
    assert "README.md does not list structure.svg" in failing(found, "DRC-11", "structure")


def test_an_embed_of_another_roots_render_is_not_this_roots_embed(run, project):
    write(project / "docs/arch.md", embed("nothing", "diagrams/other/rendered/index.svg"))

    assert run()[("DRC-11", "index")].evidence == "no embeds or catalog in scope"


def test_markdown_under_hidden_and_vendored_folders_is_not_read(run, project):
    for folder in (".claude/worktrees/x", "node_modules/p"):
        write(
            project / folder / "doc.md",
            embed("hidden", "../../docs/diagrams/architecture/rendered/index.svg"),
        )

    assert run()[("DRC-11", "index")].evidence == "no embeds or catalog in scope"


# --- DRC-12 and the findings' shape --------------------------------------------------------------


def test_a_regeneration_failure_is_a_failed_root_wide_finding(rd, checks):
    failure = rd.RegenerationFailure(
        "no-views", "docs/diagrams/x", "the source yields no view", "c", "f"
    )

    finding = checks.regeneration_finding(failure)

    assert (finding.check, finding.view, finding.status) == ("DRC-12", "-", "FAIL")
    assert finding.evidence == "no-views docs/diagrams/x: the source yields no view"


def test_many_problems_are_listed_three_at_a_time_with_a_count_of_the_rest(rd, run):
    modelled = [rd.Finding("DRC-05", "index", "FAIL", f"problem {n}") for n in range(5)]

    evidence = failing(run(findings=modelled), "DRC-05", "index")

    assert evidence == "problem 0; problem 1; problem 2 (+2 more)"


# --- the reader ----------------------------------------------------------------------------------

TINY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
<g class="a"><g class="shape"><rect x="1" y="2" width="30" height="10" rx="4"
 style="stroke-width:2;stroke-dasharray:10.000000,9.865639;" stroke="#abc" fill="#FF0000"/></g>
<text x="5" y="6" fill="#00ff00" style="text-anchor:middle;font-size:15px">
<tspan x="5" dy="0">one</tspan><tspan x="5" dy="16">two</tspan></text>
<path d="M 0 0 L 4 4" stroke="#000000" style="stroke-width:3;" marker-end="url(#m)"/>
<marker id="m"><polygon points="0,0 1,1 0,1" fill="#111111"/></marker></g></svg>"""


def test_the_reader_resolves_groups_text_shapes_and_arrows_from_markup(svg):
    group = next(g for g in svg.read_svg(TINY).groups if g.classes == ("a",))

    (shape,) = group.shapes
    assert (shape.geometry, shape.fill, shape.stroke) == ("rect(rx=4)", "#FF0000", "#AABBCC")
    assert (shape.dash, shape.stroke_width, shape.box) == (10, 2, (1, 2, 31, 12))
    assert [(line.text, line.font_size, line.fill, line.y) for line in group.lines] == [
        ("one", 15.0, "#00FF00", 6.0),
        ("two", 15.0, "#00FF00", 22.0),
    ]
    (arrow,) = group.arrows
    assert (arrow.marker_start, arrow.marker_end, arrow.stroke_width) == (False, True, 3)


def test_a_path_box_follows_the_one_number_vertical_and_horizontal_commands(svg):
    cylinder = (
        '<svg viewBox="0 0 9 9"><g class="a"><path d="M 1 2 C 3 4 5 6 7 8 V 20 H 30 Z"'
        ' fill="#FFFFFF" stroke="#000000"/></g></svg>'
    )

    (group,) = (g for g in svg.read_svg(cylinder).groups if g.classes == ("a",))

    assert group.box == (1, 2, 30, 20)


def test_a_marker_polygon_is_not_a_drawing_and_the_size_is_the_view_box(svg):
    reading = svg.read_svg(TINY)

    assert (reading.width, reading.height) == (200, 100)
    assert all(
        "polygon" not in shape.geometry for group in reading.groups for shape in group.shapes
    )


def test_markup_that_is_not_xml_is_refused_by_the_parser(svg):
    with pytest.raises(ET.ParseError):
        svg.read_svg("<svg><g></svg>")


def test_the_legend_region_is_the_legends_own_frame_and_samples_stand_inside_it(svg):
    reading = svg.read_svg((RENDERS / "index.svg").read_text(encoding="utf-8"))

    assert reading.legend.lines[0].text == "Legend"
    assert reading.legend_region == (-272.0, 556.0, 777.0, 796.0)
    assert {line.text for g in reading.samples for line in g.lines} >= {"Person", "System in scope"}
    assert reading.legend not in reading.drawn
    assert all(not reading.in_legend(g) for g in reading.drawn)


@pytest.mark.parametrize(
    ("lines", "name", "run_found"),
    [
        (["Main Agent", "(Orchestrator)", "[Agent]"], "Main Agent (Orchestrator)", (0, 2)),
        (["[Agent]", "Skills", "text"], "Skills", (1, 2)),
        (["Skills x", "y"], "Skills", None),
    ],
)
def test_a_name_is_spelled_by_consecutive_lines_only(svg, lines, name, run_found):
    assert svg.spelled_at(lines, name) == run_found


# --- the command's wiring ------------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A project whose model is the stub toolchain's, run through `main`."""
    top = tmp_path / "work"
    (top / "docs/diagrams/architecture/src").mkdir(parents=True)
    (top / "docs/diagrams/architecture/src/model.c4").write_text("model {}\n", encoding="utf-8")
    monkeypatch.chdir(top)
    return top


def command(rd, tools, capsys, *argv):
    code = rd.main(list(argv), tool_path=str(tools.directory))
    out, err = capsys.readouterr()
    return code, out, err


def test_check_reports_a_failed_structural_check_for_a_render_that_shows_nothing_of_the_view(
    rd, tmp_path, workspace, capsys
):
    tools = Toolchain(tmp_path / "bin")  # its `d2` writes a render with no legend and no arrows

    code, out, _ = command(rd, tools, capsys, "--check")

    lines = out.splitlines()
    assert code == 1
    assert "DRC-02 index FAIL no group holds a line reading exactly 'Legend'" in lines
    assert "DRC-12 - PASS regenerated 2 view(s) without a failure" in lines


def test_a_regeneration_failure_prints_the_failed_root_wide_finding_before_it_stops(
    rd, tmp_path, workspace, capsys
):
    tools = Toolchain(tmp_path / "bin")
    tools.set(render_status=3)

    code, out, err = command(rd, tools, capsys, "--check")

    assert code == 1
    assert out.startswith("DRC-12 - FAIL toolchain-error ")
    assert "[diagram-regen] FAIL toolchain-error" in err


def test_a_real_render_of_a_small_model_passes_every_check_the_command_runs(
    rd, tmp_path, workspace, capsys, d2_path
):
    tools = Toolchain(tmp_path / "bin")
    (tools.directory / "d2").unlink()
    (tools.directory / "d2").symlink_to(d2_path)
    assert command(rd, tools, capsys)[0] == 0  # the committed renders a check compares with

    code, out, _ = command(rd, tools, capsys, "--check")

    statuses = [line.split(" ")[2] for line in out.splitlines()]
    assert (code, set(statuses)) == (0, {"PASS"})
    assert len(statuses) == CHECKS_PER_VIEW * 2 + 1
