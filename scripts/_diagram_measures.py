"""The numeric review findings: contrast, legibility, proportions, and drift from the committed render.

Each function reads one render (a `Svg` from `_diagram_svg.py`), a view, or two files, and returns an
`Outcome`: the problems it found (none when the check holds), the reading nearest its limit with
that limit, and what it says when it holds. The thresholds are the table in
`skills/likec4-diagramming/references/review-checks.md`; the two contrast floors are the ones
`_diagram_tokens.py` already holds for validating a project's colours, and every other threshold
is a named constant below, stated once. Text is measured the way the acceptance driver measures
it: a line's box is estimated from its font size and character count, not from font metrics.
"""

from __future__ import annotations

import itertools
import os
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from _diagram_core import View
from _diagram_edge import RENDER_SUFFIXES
from _diagram_svg import Box, Shape, Svg, TextLine
from _diagram_tokens import OUTLINE_CONTRAST_FLOOR, TEXT_CONTRAST_FLOOR, contrast_ratio

REFERENCE_WIDTH = 960.0
MIN_TEXT_HEIGHT = 10.0
OVERLAP_TOLERANCE = 1.0
MIN_ASPECT, MAX_ASPECT = 0.5, 2.5
MAX_EDGES_PER_ELEMENT = 9

# A text line's box, estimated from its font size: the acceptance driver's reading.
GLYPH_WIDTH, ASCENT, DESCENT, DEFAULT_FONT_SIZE = 0.45, 0.7, 0.15, 12.0
# A shape spanning this much of the drawing in both axes is the canvas.
CANVAS_SPAN = 0.98
# What a transparent canvas is judged on: a white page and a dark one.
FALLBACK_CANVASES = ("#FFFFFF", "#121212")


@dataclass(frozen=True)
class Outcome:
    """What a check found: `measured` is the reading nearest `threshold`, None when not numeric."""

    problems: tuple[str, ...]
    measured: float | None
    threshold: float | None
    held: str

    @classmethod
    def plain(cls, problems: list[str], held: str) -> Outcome:
        return cls(tuple(problems), None, None, held)

    def with_problems(self, earlier: list[str]) -> Outcome:
        return replace(self, problems=(*earlier, *self.problems))


def combine(*outcomes: Outcome) -> Outcome:
    """One check made of several measures: all their problems, the first failing one's reading."""
    problems = tuple(p for outcome in outcomes for p in outcome.problems)
    lead = next((o for o in outcomes if o.problems), outcomes[0])
    return Outcome(problems, lead.measured, lead.threshold, "; ".join(o.held for o in outcomes))


# --- DRC-06: contrast ------------------------------------------------------------------------


def contrast_outcome(svg: Svg) -> Outcome:
    """Text against the surface painted behind it; outlines and arrows against the canvas."""
    canvas = _canvas(svg)
    bases = (canvas.fill,) if canvas and canvas.fill else FALLBACK_CANVASES
    return combine(_text_contrast(svg, canvas, bases), _outline_contrast(svg, canvas, bases))


def _text_contrast(svg: Svg, canvas: Shape | None, bases: tuple[str, ...]) -> Outcome:
    surfaces = [s for g in svg.groups for s in g.shapes if s.fill and s is not canvas]
    undeclared, judged = [], []
    for line in (line for group in svg.groups for line in group.lines):
        if line.fill is None:
            undeclared.append(f"the colour of {line.text!r} is not declared in the markup")
            continue
        for base in bases:
            behind = _surface_behind(line, surfaces, base)
            judged.append((contrast_ratio(line.fill, behind), repr(line.text), behind))
    return _judged("text", judged, TEXT_CONTRAST_FLOOR, undeclared)


def _surface_behind(line: TextLine, surfaces: list[Shape], base: str) -> str:
    """The colour at the centre of a line's box: the last fill painted before it (fills are
    opaque, so the topmost covers the rest), else the canvas."""
    x0, y0, x1, y1 = text_box(line)
    centre = ((x0 + x1) / 2, (y0 + y1) / 2)
    under = [s for s in surfaces if s.order < line.order and _holds(s.box, centre)]
    return max(under, key=lambda s: s.order).fill if under else base


def _outline_contrast(svg: Svg, canvas: Shape | None, bases: tuple[str, ...]) -> Outcome:
    drawn: list[tuple[str, str | None]] = []
    for group in svg.groups:
        drawn += [
            (f"the outline of a {_kind(s)}", s.stroke)
            for s in group.shapes
            if s.stroke_width > 0 and s is not canvas
        ]
        drawn += [(f"the arrow labelled {group.text!r}", a.stroke) for a in group.arrows]
    undeclared = [f"the colour of {who} is not declared in the markup" for who, c in drawn if not c]
    judged = [(contrast_ratio(c, base), who, base) for who, c in drawn if c for base in bases]
    return _judged("outline", judged, OUTLINE_CONTRAST_FLOOR, undeclared)


def _judged(
    what: str, judged: list[tuple[float, str, str]], floor: float, undeclared: list[str]
) -> Outcome:
    """Every (ratio, who, against) below the floor is a problem; the lowest ratio is the reading."""
    below = [
        f"{who} has contrast {ratio:.2f}:1 against {against}"
        for ratio, who, against in judged
        if ratio < floor
    ]
    lowest = min((ratio for ratio, _, _ in judged), default=None)
    held = (
        f"lowest {what} contrast {lowest:.2f}:1 (floor {floor:g}:1)"
        if lowest is not None
        else f"no {what}"
    )
    return Outcome(tuple(dict.fromkeys(undeclared + below)), lowest, floor, held)


# --- DRC-07: legibility at the reference width ------------------------------------------------


def legibility_outcome(svg: Svg) -> Outcome:
    lines = [line for group in svg.groups for line in group.lines]
    return combine(_text_height(svg, lines), _overlaps(lines))


def _text_height(svg: Svg, lines: list[TextLine]) -> Outcome:
    scale = min(1.0, REFERENCE_WIDTH / svg.width) if svg.width > 0 else 0.0
    heights = [(line.font_size * scale, line) for line in lines if line.font_size]
    problems = []
    if len(heights) < len(lines):
        problems.append(f"{len(lines) - len(heights)} text line(s) declare no font size")
    if not heights:
        return Outcome(tuple(problems), None, MIN_TEXT_HEIGHT, "no text")
    height, smallest = min(heights, key=lambda pair: pair[0])
    reading = (
        f"min rendered text {height:.1f}px at {REFERENCE_WIDTH:g}px "
        f"(font-size {smallest.font_size:g}, width {svg.width:g})"
    )
    if height >= MIN_TEXT_HEIGHT:
        held = f"{reading} >= {MIN_TEXT_HEIGHT:g}px"
        return Outcome(tuple(problems), height, MIN_TEXT_HEIGHT, held)
    below = sum(h < MIN_TEXT_HEIGHT for h, _ in heights)
    problems.append(f"{reading} < {MIN_TEXT_HEIGHT:g}px ({below} line(s) below)")
    return Outcome(tuple(problems), height, MIN_TEXT_HEIGHT, "")


def _overlaps(lines: list[TextLine]) -> Outcome:
    boxed = [(line, text_box(line)) for line in lines]
    found = [
        (_overlap_depth(a_box, b_box), a, b)
        for (a, a_box), (b, b_box) in itertools.combinations(boxed, 2)
    ]
    over = [(depth, a, b) for depth, a, b in found if depth > OVERLAP_TOLERANCE]
    problems = [f"{a.text!r} overlaps {b.text!r} by {depth:.1f}px" for depth, a, b in over]
    deepest = max((depth for depth, _, _ in over), default=0.0)
    held = f"no two text lines overlap by more than {OVERLAP_TOLERANCE:g}px"
    return Outcome(tuple(problems), deepest, OVERLAP_TOLERANCE, held)


def text_box(line: TextLine) -> Box:
    size = line.font_size or DEFAULT_FONT_SIZE
    width = GLYPH_WIDTH * size * len(line.text)
    left = line.x - {"middle": width / 2, "end": width}.get(line.anchor, 0.0)
    return (left, line.y - ASCENT * size, left + width, line.y + DESCENT * size)


def _overlap_depth(a: Box, b: Box) -> float:
    """How far two boxes overlap along the axis they overlap least on; not above 0 when apart."""
    return min(min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1]))


# --- DRC-08: proportions and fan-in -----------------------------------------------------------


def proportions_outcome(svg: Svg, view: View) -> Outcome:
    return combine(_aspect(svg), _fan_in(view))


def _aspect(svg: Svg) -> Outcome:
    if svg.width <= 0 or svg.height <= 0:
        return Outcome(("the render declares no size",), None, MIN_ASPECT, "")
    ratio = svg.width / svg.height
    bound = MAX_ASPECT if ratio >= 1 else MIN_ASPECT
    reading = f"width/height {ratio:.2f} ({svg.width:g}x{svg.height:g})"
    if MIN_ASPECT <= ratio <= MAX_ASPECT:
        return Outcome((), ratio, bound, f"{reading} within {MIN_ASPECT:g}-{MAX_ASPECT:g}")
    problem = f"{reading} is outside {MIN_ASPECT:g}-{MAX_ASPECT:g}"
    return Outcome((problem,), ratio, bound, "")


def _fan_in(view: View) -> Outcome:
    """Edges meeting each element; an edge from an element to itself meets it once."""
    met = Counter(end for edge in view.edges for end in {edge.source, edge.target})
    names = {node.id: node.name for node in view.nodes}
    problems = [
        f"{names.get(element, element)} is met by {count} arrows (most allowed: {MAX_EDGES_PER_ELEMENT})"
        for element, count in sorted(met.items())
        if count > MAX_EDGES_PER_ELEMENT
    ]
    most = max(met.values(), default=0)
    held = f"most arrows meeting one element: {most} (at most {MAX_EDGES_PER_ELEMENT})"
    return Outcome(tuple(problems), float(most), float(MAX_EDGES_PER_ELEMENT), held)


# --- DRC-10: the committed render is a fresh regeneration -------------------------------------


def drift_outcome(view: str, built: Path, rendered: Path) -> Outcome:
    """Each file the regeneration wrote for `view`, byte-compared with the committed one."""
    problems = []
    for name in (f"{view}{suffix}" for suffix in RENDER_SUFFIXES):
        if not (built / name).is_file():
            continue
        fresh = (built / name).read_bytes()
        committed = rendered / name
        if not committed.is_file():
            problems.append(f"rendered/{name} is missing")
        elif (old := committed.read_bytes()) != fresh:
            at = first_difference(old, fresh)
            problems.append(
                f"rendered/{name} differs from a fresh regeneration (first difference at byte {at})"
            )
    return Outcome.plain(problems, "the committed render is byte-identical to a fresh regeneration")


def stale_outcome(views: list[str], rendered: Path) -> Outcome:
    """Render files committed for no view: the regeneration deletes them."""
    wanted = {f"{view}{suffix}" for view in views for suffix in RENDER_SUFFIXES}
    found = sorted(rendered.iterdir()) if rendered.is_dir() else []
    problems = [
        f"rendered/{p.name} belongs to no view (regeneration deletes it)"
        for p in found
        if p.is_file() and p.suffix in RENDER_SUFFIXES and p.name not in wanted
    ]
    return Outcome.plain(problems, "no committed render belongs to a view that is gone")


def first_difference(old: bytes, new: bytes) -> int:
    """The offset of the first byte two files differ at; the shorter length when one is a prefix."""
    return len(os.path.commonprefix([old, new]))


# --- small shared judgments -------------------------------------------------------------------


def _canvas(svg: Svg) -> Shape | None:
    """The first painted shape that fills the whole drawing; everything else stands on it."""
    if svg.width <= 0 or svg.height <= 0:
        return None
    painted = sorted((s for g in svg.groups for s in g.shapes if s.fill), key=lambda s: s.order)
    return next((s for s in painted if _spans(s.box, svg)), None)


def _spans(box: Box, svg: Svg) -> bool:
    return (
        box[2] - box[0] >= CANVAS_SPAN * svg.width and box[3] - box[1] >= CANVAS_SPAN * svg.height
    )


def _holds(box: Box, point: tuple[float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _kind(shape: Shape) -> str:
    """A shape's geometry as a word: `rect(rx=16)` is a rect, `path:MLLZ` a path."""
    return shape.geometry.split("(")[0].split(":")[0]
