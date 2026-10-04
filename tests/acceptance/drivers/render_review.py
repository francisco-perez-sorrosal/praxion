"""The review checks of the specification, applied to a render and its view.

Each function returns the violations it finds, as sentences naming what is wrong
and where, so a scenario asserts an empty list and a failure reads as a report.
Every threshold is the one the specification sets. Nothing here looks at pixels:
the evidence is the render's markup (through `svg_render`) and the model's reading
of the view (through `architecture_model`).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

from tests.acceptance.drivers.architecture_model import Element, Model, View
from tests.acceptance.drivers.svg_render import (
    Block,
    Render,
    blend,
    boxes_overlap,
    contrast,
    normalise,
    read_render,
)

MIN_TEXT_HEIGHT = 10.0
MIN_RATIO, MAX_RATIO = 0.5, 2.5
MAX_ARROWS_PER_ELEMENT = 9
TEXT_CONTRAST = 4.5
GRAPHIC_CONTRAST = 3.0
C4_DIAGRAM_TYPES = (
    "system context",
    "system landscape",
    "container",
    "component",
    "dynamic",
    "deployment",
)
GENERIC_LABELS = ("uses", "calls", "connects to", "interacts with", "talks to", "depends on")

CategoryOf = Callable[[Element], str]


def render_views(render_dir: Path, model: Model) -> list[tuple[str, Path, View | None]]:
    """Every committed render with the model view it shows (same id as the file stem)."""
    return [
        (path.stem, path, model.views.get(path.stem)) for path in sorted(render_dir.glob("*.svg"))
    ]


def drawn_blocks(render: Render, view: View) -> list[tuple[Element, Block]]:
    pairs = []
    for node in view.nodes:
        block = render.element_block(node.title)
        if block is not None:
            pairs.append((node, block))
    return pairs


# ── one view, read on its own ─────────────────────────────────────────────────


def title_violations(render: Render, view: View) -> list[str]:
    if not view.title:
        return [f"{render.path.name}: the view has no title in the model"]
    wanted = normalise(view.title).casefold()
    blocks = [text for text in _group_texts(render) if wanted in text]
    if not blocks:
        return [f"{render.path.name}: the title {view.title!r} is not shown in the render"]
    if not any(kind in text for text in blocks for kind in C4_DIAGRAM_TYPES):
        return [
            f"{render.path.name}: the title {view.title!r} does not name a C4 diagram type {C4_DIAGRAM_TYPES}"
        ]
    return []


def legend_line_style_violations(render: Render) -> list[str]:
    if render.legend_region is None:
        return [f"{render.path.name}: no legend (a region headed 'Legend') in the render"]
    used = {arrow.dashed for arrow in render.relationship_arrows}
    sampled = {arrow.dashed for arrow in render.legend_arrows}
    sampled |= {
        s.dashed
        for s in render.legend_shapes
        if s.fill is None and s.tag in ("line", "path", "polyline")
    }
    missing = sorted(used - sampled)
    return [
        f"{render.path.name}: the legend shows no sample of the {style} line style the view uses"
        for style in missing
    ]


def legend_category_violations(render: Render, view: View, category_of: CategoryOf) -> list[str]:
    if render.legend_region is None:
        return [f"{render.path.name}: no legend (a region headed 'Legend') in the render"]
    entries = [normalise(line.text).casefold() for line in render.legend_lines]
    samples = _legend_sample_drawings(render)
    violations = []
    for category, blocks in _blocks_by_category(render, view, category_of).items():
        if not any(entry.startswith(category.casefold()) for entry in entries):
            violations.append(
                f"{render.path.name}: no legend entry begins with the category name {category!r}"
            )
        if not any(block.drawing in samples for block in blocks):
            violations.append(
                f"{render.path.name}: the legend has no sample drawn the way {category!r} is drawn"
            )
    return violations


def element_text_violations(render: Render, view: View) -> list[str]:
    violations = []
    for node in view.nodes:
        block = render.element_block(node.title)
        if block is None:
            violations.append(
                f"{render.path.name}: {node.id} is not shown under its name {node.title!r}"
            )
            continue
        shown = block.text.casefold()
        if node.responsibilities and not any(
            normalise(t).casefold() in shown for t in node.responsibilities
        ):
            violations.append(
                f"{render.path.name}: {node.id} does not show its responsibility {node.responsibilities[0]!r}"
            )
    return violations


def element_kind_line_violations(render: Render, view: View, category_of: CategoryOf) -> list[str]:
    violations = []
    for node, block in drawn_blocks(render, view):
        accepted = [t.casefold() for t in (node.technology, category_of(node)) if t]
        name = normalise(node.title).casefold()
        lines = [normalise(line.text).casefold().strip("[]() ") for line in block.lines]
        if not any(word in line and line not in name for line in lines for word in accepted):
            violations.append(
                f"{render.path.name}: {node.id} shows no line stating its category or technology {accepted}"
            )
    return violations


def arrow_violations(render: Render, view: View) -> list[str]:
    arrows = render.relationship_arrows
    violations = []
    if len(arrows) != len(view.edges):
        violations.append(
            f"{render.path.name}: {len(arrows)} arrows with an arrowhead drawn, the view has {len(view.edges)}"
        )
    for arrow in arrows:
        if arrow.heads != 1:
            violations.append(
                f"{render.path.name}: an arrow labelled {arrow.label!r} has {arrow.heads} arrowheads"
            )
        if _is_generic(arrow.label):
            violations.append(
                f"{render.path.name}: an arrow carries no specific intent label ({arrow.label!r})"
            )
    return violations


def text_height_violations(render: Render) -> list[str]:
    return [
        f"{render.path.name}: {line.text!r} is {render.rendered_text_height(line):.1f}px high at the 960px reference width"
        for line in render.lines
        if line.font_size is None or render.rendered_text_height(line) < MIN_TEXT_HEIGHT
    ]


def overlap_violations(render: Render) -> list[str]:
    lines = render.lines
    return [
        f"{render.path.name}: {a.text!r} overlaps {b.text!r}"
        for i, a in enumerate(lines)
        for b in lines[i + 1 :]
        if a.unit != b.unit and boxes_overlap(a.box, b.box)
    ]


def proportion_violations(render: Render) -> list[str]:
    ratio = render.aspect_ratio
    if MIN_RATIO <= ratio <= MAX_RATIO:
        return []
    return [
        f"{render.path.name}: width-to-height ratio {ratio:.2f} ({render.width:.0f}x{render.height:.0f}) is outside 0.5-2.5"
    ]


def fan_in_violations(view: View) -> list[str]:
    counts: Counter[str] = Counter()
    for edge in view.edges:
        counts.update({edge.source, edge.target})
    return [
        f"view {view.id}: {node} is met by {n} arrows"
        for node, n in counts.items()
        if n > MAX_ARROWS_PER_ELEMENT
    ]


def text_contrast_violations(render: Render) -> list[str]:
    violations = []
    for line in render.lines:
        if line.colour is None:
            violations.append(
                f"{render.path.name}: the colour of {line.text!r} is not declared in the markup"
            )
            continue
        for backdrop in render.backdrops(line):
            ratio = contrast(blend(line.colour, line.opacity, backdrop), backdrop)
            if ratio < TEXT_CONTRAST:
                violations.append(
                    f"{render.path.name}: {line.text!r} has contrast {ratio:.2f}:1 against {backdrop}"
                )
    return violations


def graphic_contrast_violations(render: Render) -> list[str]:
    strokes = [
        (f"outline of a {s.tag}", s.stroke)
        for s in render.shapes
        if s.stroke is not None and s.stroke_width > 0 and s.order != render.canvas_order
    ]
    strokes += [(f"arrow {a.label!r}", a.stroke) for a in render.arrows]
    violations = []
    for what, colour in strokes:
        if colour is None:
            violations.append(
                f"{render.path.name}: the colour of the {what} is not declared in the markup"
            )
            continue
        for canvas in render.canvases():
            ratio = contrast(colour, canvas)
            if ratio < GRAPHIC_CONTRAST:
                violations.append(
                    f"{render.path.name}: the {what} has contrast {ratio:.2f}:1 against the canvas {canvas}"
                )
    return sorted(set(violations))


# ── categories across views ────────────────────────────────────────────────────


def category_distinctness_violations(
    render: Render, view: View, category_of: CategoryOf
) -> list[str]:
    """Two categories in one view never share a drawing once colour is removed."""
    violations = []
    for frame in (False, True):
        marks: dict[tuple, set[str]] = {}
        for node, block in drawn_blocks(render, view):
            if node.boundary == frame:
                marks.setdefault(block.mark, set()).add(category_of(node))
        violations += [
            f"{render.path.name}: categories {sorted(cats)} are drawn alike without colour ({mark})"
            for mark, cats in marks.items()
            if len(cats) > 1
        ]
    return violations


def category_consistency_violations(
    pairs: Iterable[tuple[Render, View]], category_of: CategoryOf
) -> list[str]:
    """A category is drawn the same way in every view (boxes with boxes, frames with frames)."""
    seen: dict[tuple[str, bool], dict[tuple, list[str]]] = {}
    for render, view in pairs:
        for node, block in drawn_blocks(render, view):
            key = (category_of(node), node.boundary)
            seen.setdefault(key, {}).setdefault(block.drawing, []).append(
                f"{render.path.stem}:{node.id}"
            )
    return [
        f"category {category!r} ({'frame' if frame else 'box'}) is drawn {len(drawings)} different ways: "
        + "; ".join(sorted(where[0] for where in drawings.values()))
        for (category, frame), drawings in seen.items()
        if len(drawings) > 1
    ]


def vocabulary_violations(categories: Iterable[str], vocabulary: tuple[str, ...]) -> list[str]:
    """Every vocabulary category is a category of the model under its exact name (case aside)."""
    names = {normalise(name).casefold() for name in categories}
    violations = ["an element has no category name" for name in names if not name]
    violations += [
        f"no category of the model is named {term!r}"
        for term in vocabulary
        if term.casefold() not in names
    ]
    return violations


PRAXION_VOCABULARY = (
    "Person",
    "System in scope",
    "External system",
    "Knowledge asset",
    "Runtime agent",
    "Pipeline document",
    "Persistent store",
    "Tooling",
)

ONBOARDED_VOCABULARY = (
    "Person",
    "System in scope",
    "External system",
    "Container",
    "Component",
    "Data store",
)


def all_render_check_violations(
    render_dir: Path, model: Model, category_of: CategoryOf
) -> list[str]:
    """Every per-render review check, for a project's renders (used on onboarded projects)."""
    violations = []
    pairs = []
    for _, path, view in render_views(render_dir, model):
        if view is None:
            violations.append(f"{path.name}: no view of the model has this render's id")
            continue
        render = read_render(path)
        pairs.append((render, view))
        violations += title_violations(render, view)
        violations += legend_line_style_violations(render)
        violations += legend_category_violations(render, view, category_of)
        violations += element_text_violations(render, view)
        violations += element_kind_line_violations(render, view, category_of)
        violations += arrow_violations(render, view)
        violations += (
            text_height_violations(render)
            + overlap_violations(render)
            + proportion_violations(render)
        )
        violations += fan_in_violations(view)
        violations += text_contrast_violations(render) + graphic_contrast_violations(render)
        violations += category_distinctness_violations(render, view, category_of)
    return violations + category_consistency_violations(pairs, category_of)


# ── helpers ────────────────────────────────────────────────────────────────────


def _group_texts(render: Render) -> list[str]:
    groups: dict[tuple, list[str]] = {}
    for line in render.lines:
        groups.setdefault(line.group, []).append(line.text)
    return [normalise(" ".join(texts)).casefold() for texts in groups.values()]


def _is_generic(label: str) -> bool:
    words = re.sub(r"[^a-z ]", " ", normalise(label).casefold())
    words = normalise(words)
    return not words or words in GENERIC_LABELS


def _blocks_by_category(
    render: Render, view: View, category_of: CategoryOf
) -> dict[str, list[Block]]:
    result: dict[str, list[Block]] = {}
    for node, block in drawn_blocks(render, view):
        result.setdefault(category_of(node), []).append(block)
    return result


def _legend_sample_drawings(render: Render) -> set[tuple]:
    """Drawings of every group (at any nesting depth) holding legend sample shapes."""
    by_group: dict[tuple, list] = {}
    for shape in render.legend_shapes:
        for depth in range(1, len(shape.group) + 1):
            by_group.setdefault(shape.group[:depth], []).append(shape)
    return {tuple(sorted((s.drawing for s in shapes), key=repr)) for shapes in by_group.values()}
