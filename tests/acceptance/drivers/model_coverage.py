"""What the architecture model claims, compared before and after the restyle.

Identity of an element is its fully qualified id in the model. A relationship is
counted by its source and target ids (labels may be sharpened), so a model keeps a
relationship when it still records at least as many relationships between the same
two elements. "Drawn" means a committed render shows the element under its name.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from tests.acceptance.drivers.architecture_model import Model
from tests.acceptance.drivers.svg_render import normalise, read_render

COVERED_SUBJECTS = {
    "the system context": ("context",),
    "the system's internal building blocks": ("component", "container", "building block"),
    "the forward agent pipeline": ("pipeline",),
    "the continuous-improvement loop": ("continuous improvement", "continuous-improvement", "cis"),
    "the rework loop": ("rework",),
}


def uncovered_subjects(model: Model, render_dir: Path) -> list[str]:
    rendered = {path.stem for path in render_dir.glob("*.svg")}
    titles = [
        normalise(view.title or "").casefold()
        for view_id, view in model.views.items()
        if view_id in rendered
    ]
    return [
        subject
        for subject, words in COVERED_SUBJECTS.items()
        if not any(w in t for t in titles for w in words)
    ]


def lost_elements(before: Model, after: Model) -> list[str]:
    return sorted(set(before.elements) - set(after.elements))


def lost_relationships(before: Model, after: Model) -> list[str]:
    def counted(model: Model) -> Counter[tuple[str, str]]:
        return Counter((r.source, r.target) for r in model.relationships)

    missing = counted(before) - counted(after)
    return sorted(f"{source} -> {target} (x{n})" for (source, target), n in missing.items())


def undrawn_elements(model: Model, render_dir: Path) -> list[str]:
    renders = [read_render(path) for path in sorted(render_dir.glob("*.svg"))]
    return sorted(
        element.id
        for element in model.elements.values()
        if not any(render.element_block(element.title) is not None for render in renders)
    )


def views_without_render(model: Model, render_dir: Path) -> list[str]:
    rendered = {path.stem for path in render_dir.glob("*.svg")}
    return sorted(set(model.views) - rendered)
