"""The review findings the command computes: one per check per view, from the model and the markup.

`run_checks` is the one gatherer the command calls. It reads each built render and the project's
markdown, hands both to pure verdict functions (each returns the problems it found, empty when
the check holds) and returns the findings in check order per view, then the root-wide DRC-12.
The thresholds and pass conditions are the table in
`skills/likec4-diagramming/references/review-checks.md`; this module only applies them, and its
SVG reading is `_diagram_svg.py`, independent of any other reader of a render.
"""

from __future__ import annotations

import html
import itertools
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from _diagram_core import C4_TYPES, DYNAMIC, Finding, Projection, RegenerationFailure, View
from _diagram_edge import RENDER_DIR
from _diagram_svg import Group, Svg, normalise, read_svg, spelled_at
from _diagram_tokens import LINE_DRAWINGS

TITLE_TYPES = (*C4_TYPES, DYNAMIC)
GENERIC_LABELS = frozenset(
    {"uses", "calls", "connects to", "interacts with", "talks to", "depends on"}
)
STEP_PREFIX = re.compile(r"^\d+\s*·\s*")
MAX_LISTED = 3

ROOT_WIDE = "-"
CATALOG_FILE = "README.md"
EMBED = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
BRACE_GROUP = re.compile(r"\{([^{}]*,[^{}]*)\}")
SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})
KEPT_HIDDEN_DIRS = frozenset({".ai-state"})

HELD = {
    "DRC-01": "a group names the view title and a C4 type",
    "DRC-02": "the legend names every category drawn and samples every line style used",
    "DRC-03": "every element states its name, its category or technology and its responsibility",
    "DRC-04": "every arrow points one way and states its intent",
    "DRC-05": "every element has one category and the categories differ without colour",
    "DRC-09": "no box draws an ancestor of another box",
    "DRC-11": "every embed of the view names its title and C4 type; the catalog lists it",
}
NO_DOCUMENTS = "no embeds or catalog in scope"


# --- the gatherer ----------------------------------------------------------------------------


def run_checks(projection: Projection, built: Path, root: Path) -> tuple[Finding, ...]:
    """Every finding for a built root: the model's own, merged per check and view with the rest."""
    readings = [_reading(view, built) for view in projection.views]
    documents = read_documents(root)
    foreign = inconsistent_drawings(readings)
    findings = []
    for reading in readings:
        view = reading.view
        problems = {check: verdict(reading) for check, verdict in READING_CHECKS}
        problems["DRC-05"] += foreign.get(view.id, [])
        problems["DRC-09"] = abstraction_problems(view)
        problems["DRC-11"] = embed_problems(view, documents)
        held_11 = HELD["DRC-11"] if documents.in_scope else NO_DOCUMENTS
        for check in sorted(problems):
            modelled = [
                f.evidence
                for f in projection.findings
                if (f.check, f.view, f.status) == (check, view.id, "FAIL")
            ]
            held = held_11 if check == "DRC-11" else HELD[check]
            findings.append(_finding(check, view.id, modelled + problems[check], held))
    held = f"regenerated {len(readings)} view(s) without a failure"
    return (*findings, _finding("DRC-12", ROOT_WIDE, [], held))


def regeneration_finding(failure: RegenerationFailure) -> Finding:
    """DRC-12 failing: the regeneration stopped, so no other check could run."""
    return _finding("DRC-12", ROOT_WIDE, [f"{failure.kind} {failure.target}: {failure.what}"], "")


def _finding(check: str, view: str, problems: list[str], held: str) -> Finding:
    if not problems:
        return Finding(check, view, "PASS", held)
    shown = "; ".join(problems[:MAX_LISTED])
    more = len(problems) - MAX_LISTED
    return Finding(check, view, "FAIL", f"{shown} (+{more} more)" if more > 0 else shown)


# --- one render read against its view --------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """A view with its render, and the group of the render that draws each of its elements."""

    view: View
    svg: Svg
    elements: Mapping[str, Group]


def _reading(view: View, built: Path) -> Reading:
    svg = read_svg((built / f"{view.id}.svg").read_text(encoding="utf-8"))
    return Reading(view, svg, _element_groups(view, svg))


def _element_groups(view: View, svg: Svg) -> dict[str, Group]:
    """For each node, the first group outside the legend that spells its name; none is shared."""
    candidates = [g for g in svg.drawn if g.lines and not g.arrows]
    found: dict[str, Group] = {}
    for node in sorted(view.nodes, key=lambda n: n.id):
        for group in candidates:
            if spelled_at([line.text for line in group.lines], node.name):
                found[node.id] = group
                candidates.remove(group)
                break
    return found


def title_problems(reading: Reading) -> list[str]:
    title = normalise(reading.view.title)
    titled = [g.text for g in reading.svg.groups if title in g.text]
    if not titled:
        return [f"no group shows the view title {title!r}"]
    if not any(kind in text for text in titled for kind in TITLE_TYPES):
        return [f"the group showing the title names none of {', '.join(TITLE_TYPES)}"]
    return []


def legend_problems(reading: Reading) -> list[str]:
    svg = reading.svg
    if svg.legend is None:
        return ["no group holds a line reading exactly 'Legend'"]
    if svg.legend_region is None:
        return ["the legend draws no region that encloses its entries"]
    lines = [line.text for group in (svg.legend, *svg.samples) for line in group.lines]
    sampled = {group.drawing for group in svg.samples}
    problems = []
    for category, frame in sorted({(n.category, n.is_frame) for n in reading.view.nodes}):
        if not any(line.startswith(category) for line in lines):
            problems.append(f"no legend line begins with the category name {category!r}")
        drawings = {
            reading.elements[n.id].drawing
            for n in reading.view.nodes
            if (n.category, n.is_frame) == (category, frame) and n.id in reading.elements
        }
        if drawings - sampled:
            problems.append(f"no legend sample is drawn the way {_form(category, frame)} is")
    return problems + _line_style_problems(reading)


def _line_style_problems(reading: Reading) -> list[str]:
    used = {_dash_name(LINE_DRAWINGS[edge.line].dash) for edge in reading.view.edges}
    sampled = {_dash_name(a.dash) for g in reading.svg.samples for a in g.arrows}
    return [f"the legend has no {style} arrow sample" for style in sorted(used - sampled)]


def content_problems(reading: Reading) -> list[str]:
    problems = []
    for node in reading.view.nodes:
        group = reading.elements.get(node.id)
        if group is None:
            problems.append(f"no group spells the name {node.name!r} on consecutive lines")
            continue
        texts = [line.text for line in group.lines]
        start, end = spelled_at(texts, node.name) or (0, 0)
        rest = texts[:start] + texts[end:]
        stated = [text for text in (node.category, node.technology) if text]
        if not any(text in line for text in stated for line in rest):
            problems.append(f"{node.name!r} states neither its category nor its technology")
        if node.responsibility and normalise(node.responsibility) not in normalise(" ".join(rest)):
            problems.append(f"{node.name!r} does not show its responsibility")
    return problems


def arrow_problems(reading: Reading) -> list[str]:
    arrows = [(g, a) for g in reading.svg.drawn for a in g.arrows]
    problems = []
    if len(arrows) != len(reading.view.edges):
        problems.append(f"{len(arrows)} arrows drawn, the view has {len(reading.view.edges)}")
    for group, arrow in arrows:
        if arrow.marker_start == arrow.marker_end:
            count = "two arrowheads" if arrow.marker_start else "no arrowhead"
            problems.append(f"the arrow labelled {group.text!r} has {count}")
        if _states_no_intent(group.text):
            problems.append(f"the arrow labelled {group.text!r} states no intent")
    return problems


def mark_problems(reading: Reading) -> list[str]:
    """Two categories of one form never share a mark (geometry, dash, width, icon)."""
    problems = []
    for frame in (False, True):
        by_mark: dict[tuple, set[str]] = {}
        for node in reading.view.nodes:
            if node.is_frame == frame and node.id in reading.elements:
                by_mark.setdefault(reading.elements[node.id].mark, set()).add(node.category)
        problems += [
            f"{', '.join(sorted(shared))} are drawn alike without colour"
            for shared in by_mark.values()
            if len(shared) > 1
        ]
    return problems


READING_CHECKS: tuple[tuple[str, Callable[[Reading], list[str]]], ...] = (
    ("DRC-01", title_problems),
    ("DRC-02", legend_problems),
    ("DRC-03", content_problems),
    ("DRC-04", arrow_problems),
    ("DRC-05", mark_problems),
)


# --- across renders, and the model alone -----------------------------------------------------


def inconsistent_drawings(readings: list[Reading]) -> dict[str, list[str]]:
    """Per view, each (category, form) drawn unlike its first drawing in an earlier render."""
    first: dict[tuple[str, bool], tuple[str, tuple]] = {}
    problems: dict[str, list[str]] = {}
    for reading in readings:
        for node in reading.view.nodes:
            group = reading.elements.get(node.id)
            if group is None:
                continue
            seen_in, drawing = first.setdefault(
                (node.category, node.is_frame), (reading.view.id, group.drawing)
            )
            if drawing != group.drawing:
                form = _form(node.category, node.is_frame)
                problems.setdefault(reading.view.id, []).append(
                    f"{form} is drawn differently from view {seen_in}"
                )
    return {view: list(dict.fromkeys(found)) for view, found in problems.items()}


def abstraction_problems(view: View) -> list[str]:
    """No box draws a model ancestor of its own that is also drawn as a box."""
    boxes = {node.id for node in view.nodes if not node.is_frame}
    return [
        f"{node} is drawn as a box beside its ancestor {ancestor}, also a box"
        for node in sorted(boxes)
        for ancestor in _ancestors(node)
        if ancestor in boxes
    ]


def _ancestors(element_id: str) -> list[str]:
    parts = element_id.split(".")
    return [".".join(parts[:end]) for end in range(len(parts) - 1, 0, -1)]


# --- documents (DRC-11) ----------------------------------------------------------------------


@dataclass(frozen=True)
class Embed:
    document: str
    view: str
    alt: str


@dataclass(frozen=True)
class Documents:
    """The markdown embeds of this root's renders, and the catalog text (braces expanded)."""

    embeds: tuple[Embed, ...]
    catalog: str | None

    @property
    def in_scope(self) -> bool:
        return bool(self.embeds) or self.catalog is not None


def embed_problems(view: View, documents: Documents) -> list[str]:
    problems = []
    title = normalise(view.title).casefold()
    kind = (view.c4_type or "").casefold()
    for embed in (e for e in documents.embeds if e.view == view.id):
        alt = embed.alt.casefold()
        if title not in alt:
            problems.append(f"{embed.document}: alt text {embed.alt!r} lacks the view title")
        if not kind or kind not in alt:
            problems.append(f"{embed.document}: alt text {embed.alt!r} lacks the C4 type name")
    listed = re.search(rf"(?<![\w.-]){re.escape(view.id)}\.svg", documents.catalog or "")
    if documents.catalog is not None and not listed:
        problems.append(f"{CATALOG_FILE} does not list {view.id}.svg")
    return problems


def read_documents(root: Path) -> Documents:
    """Gather the embeds of `root`'s renders from the project's markdown, and the catalog."""
    renders = (root / RENDER_DIR).resolve()
    top = _project_root(root)
    embeds = []
    for document in _markdown_files(top):
        text = document.read_text(encoding="utf-8", errors="replace")
        if RENDER_DIR + "/" not in text:
            continue
        for alt, target in EMBED.findall(text):
            resolved = (document.parent / target.split("#")[0].split("?")[0]).resolve()
            if resolved.parent == renders and resolved.suffix == ".svg":
                embeds.append(
                    Embed(str(document.relative_to(top)), resolved.stem, html.unescape(alt))
                )
    catalog = root.parent / CATALOG_FILE
    expanded = _expand_braces(catalog.read_text(encoding="utf-8")) if catalog.is_file() else None
    return Documents(tuple(embeds), expanded)


def _project_root(root: Path) -> Path:
    """The checkout holding `root`; without one, the folder two levels above it."""
    resolved = root.resolve()
    return next(
        (p for p in (resolved, *resolved.parents) if (p / ".git").exists()), resolved.parent.parent
    )


def _markdown_files(top: Path) -> list[Path]:
    found = []
    for folder, names, files in os.walk(top):
        names[:] = [n for n in names if _walked(n)]
        found += [Path(folder, name) for name in files if name.endswith(".md")]
    return sorted(found)


def _walked(directory: str) -> bool:
    hidden = directory.startswith(".") and directory not in KEPT_HIDDEN_DIRS
    return not hidden and directory not in SKIPPED_DIRS


def _expand_braces(text: str) -> str:
    """Shell brace forms (`{a,b}`) written in a catalog read as the paths they stand for."""
    return " ".join(itertools.chain.from_iterable(_expand(t) for t in re.split(r"[\s`|()]+", text)))


def _expand(token: str) -> list[str]:
    match = BRACE_GROUP.search(token)
    if match is None:
        return [token]
    head, tail = token[: match.start()], token[match.end() :]
    return [t for option in match.group(1).split(",") for t in _expand(head + option + tail)]


# --- small shared judgments ------------------------------------------------------------------


def _form(category: str, frame: bool) -> str:
    return f"{category!r} ({'frame' if frame else 'box'})"


def _dash_name(dash: int) -> str:
    return "dashed" if dash else "solid"


def _states_no_intent(label: str) -> bool:
    """An arrow label that is empty, only punctuation, or only a generic verb."""
    words = normalise(re.sub(r"[\W\d_]+", " ", STEP_PREFIX.sub("", label))).casefold()
    return not words or words in GENERIC_LABELS
