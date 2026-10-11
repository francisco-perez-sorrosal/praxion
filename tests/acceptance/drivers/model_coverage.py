"""What the architecture model claims, compared before and after the restyle.

Identity of an element is its fully qualified id in the model. A relationship is
counted by its source and target ids (labels may be sharpened), so a model keeps a
relationship when it still records at least as many relationships between the same
two elements. "Drawn" means a committed render shows the element under its name.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import yaml

from tests.acceptance.drivers.architecture_model import Model
from tests.acceptance.drivers.svg_render import normalise, read_render

DECISIONS_DIR = Path(__file__).resolve().parents[3] / ".ai-state" / "decisions"
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def retired_elements(decisions_dir: Path = DECISIONS_DIR) -> frozenset[str]:
    """Elements an accepted decision records as retired from the model.

    An element may be absent from the model only when an accepted decision names it in
    `retires_elements`; any other missing element or relationship still fails the guard.
    """
    retired: set[str] = set()
    for path in sorted(decisions_dir.glob("[0-9]*.md")):
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if match is None:
            continue
        meta = yaml.safe_load(match.group(1)) or {}
        if meta.get("status") == "accepted":
            retired.update(meta.get("retires_elements") or [])
    return frozenset(retired)


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


def lost_elements(before: Model, after: Model, retired: frozenset[str] | None = None) -> list[str]:
    retired = retired_elements() if retired is None else retired
    return sorted(set(before.elements) - set(after.elements) - retired)


def lost_relationships(
    before: Model, after: Model, retired: frozenset[str] | None = None
) -> list[str]:
    retired = retired_elements() if retired is None else retired

    def counted(model: Model) -> Counter[tuple[str, str]]:
        return Counter(
            (r.source, r.target)
            for r in model.relationships
            if r.source not in retired and r.target not in retired
        )

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
