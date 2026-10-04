"""The pure core of the diagram renderer: an `export json` reading in, D2 text out.

Holds the result records, the category rule, the view projection, label synthesis, the
legend and D2 emission. Pure: no clock, file, network or subprocess.
"""

from __future__ import annotations

import re
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from _diagram_tokens import (
    ACTS_ON,
    CANVAS,
    CATEGORY_RANK,
    DEFAULT_TOKENS,
    EDGE_LABEL_INK,
    ICON_URIS,
    INK,
    LEGEND_STROKE,
    LINE_DRAWINGS,
    LINE_ORDER,
    READ_ONLY,
    STEP,
    UNCATEGORISED,
    UNCATEGORISED_NAME,
    LineDrawing,
    Token,
    snake_case,
)

LABEL_WIDTH = 28

ELEMENT_FONT_SIZE = 15
EDGE_FONT_SIZE = 14
TITLE_FONT_SIZE = 24
CANVAS_PAD = 40
LEGEND_DOT = 8
LEGEND_COLUMNS = 4

LEGEND_KEY = "Legend"
TITLE_KEY = "Title"
ELEMENT_KEY_PREFIX = "el_"
FRAME_SUFFIX = " (boundary)"

READS_KIND = "reads"
PLACEHOLDER_LABEL = "[...]"
STEP_ID = re.compile(r"^step-(\d+)")

C4_TAG_PREFIX = "c4_"
C4_TYPES = ("System Context", "System Landscape", "Container", "Component", "Deployment")
C4_TYPE_BY_TAG = {C4_TAG_PREFIX + snake_case(name): name for name in C4_TYPES}
DYNAMIC = "Dynamic"

FAILURE_KINDS = frozenset(
    {"toolchain-error", "no-views", "view-without-render", "render-without-names"}
)
FINDING_STATUSES = frozenset({"PASS", "FAIL"})
CHECK_ID = re.compile(r"^DRC-\d{2}$")

# --- the records -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    check: str
    view: str
    status: str
    evidence: str
    measured: float | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        if not CHECK_ID.match(self.check) or self.status not in FINDING_STATUSES:
            raise ValueError(f"not a finding: {self.check} {self.status}")


@dataclass(frozen=True)
class RegenerationFailure:
    kind: str
    target: str
    what: str
    cause: str
    fix: str

    def __post_init__(self) -> None:
        if self.kind not in FAILURE_KINDS:
            raise ValueError(f"not a regeneration failure kind: {self.kind}")


@dataclass(frozen=True)
class Node:
    """A drawn element; `parent` is the enclosing node drawn in the same view, if any."""

    id: str
    name: str
    drawing: Token
    technology: str | None
    responsibility: str | None
    is_frame: bool
    parent: str | None = None

    @property
    def category(self) -> str:
        return self.drawing.category


@dataclass(frozen=True)
class Edge:
    """A drawn arrow; `step_no` is set on dynamic steps, `reads` when every relationship reads."""

    source: str
    target: str
    label: str
    step_no: int | None = None
    reads: bool = False

    @property
    def line(self) -> str:
        if self.step_no is not None:
            return STEP
        return READ_ONLY if self.reads else ACTS_ON


@dataclass(frozen=True)
class View:
    id: str
    title: str
    c4_type: str | None
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


@dataclass(frozen=True)
class Projection:
    views: tuple[View, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class LegendEntry:
    label: str
    drawing_class: str | None


# --- the category rule and the view projection -----------------------------------------------


def resolve_category(element: Mapping[str, Any], specification: Mapping[str, Any]) -> str | None:
    """`metadata.category` when declared (a string), else the `notation` of the element's kind."""
    metadata = element.get("metadata") or {}
    if "category" in metadata:
        declared = metadata["category"]
        return declared if isinstance(declared, str) else None
    kind = (specification.get("elements") or {}).get(element.get("kind")) or {}
    notation = kind.get("notation")
    return notation if isinstance(notation, str) else None


def project(model: Mapping[str, Any], tokens: tuple[Token, ...] = DEFAULT_TOKENS) -> Projection:
    """Parse an `export json` reading into drawable views; model faults become findings."""
    drawings = {(token.category, token.frame): token for token in tokens}
    raw_views = sorted((model.get("views") or {}).items())
    projected = [_project_view(view_id, raw, model, drawings) for view_id, raw in raw_views]
    findings = tuple(finding for _, found in projected for finding in found)
    return Projection(tuple(view for view, _ in projected), findings)


def _project_view(
    view_id: str, raw: Mapping[str, Any], model: Mapping[str, Any], drawings: Mapping
) -> tuple[View, list[Finding]]:
    findings = []
    c4_type, type_problem = _c4_type(raw)
    if type_problem:
        findings.append(Finding("DRC-01", view_id, "FAIL", type_problem))
    raw_nodes = raw.get("nodes") or []
    in_view = {node["id"] for node in raw_nodes}
    nodes, unresolved = [], []
    for raw_node in raw_nodes:
        node, problem = _project_node(raw_node, model, drawings, in_view)
        nodes.append(node)
        if problem:
            unresolved.append(f"{node.id} ({problem})")
    if unresolved:
        listed = ", ".join(sorted(unresolved))
        evidence = f"{len(unresolved)} element(s) draw as {UNCATEGORISED_NAME}: {listed}"
        findings.append(Finding("DRC-05", view_id, "FAIL", evidence))
    dynamic = raw.get("_type") == "dynamic"
    relations = model.get("relations") or {}
    edges = [
        _project_edge(e, relations, position if dynamic else None)
        for position, e in enumerate(raw.get("edges") or [], 1)
    ]
    view = View(view_id, raw.get("title") or view_id, c4_type, tuple(nodes), tuple(edges))
    return view, findings


def _c4_type(raw: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The view's C4 type, and why there is none when the tags do not name exactly one."""
    if raw.get("_type") == "dynamic":
        return DYNAMIC, None
    tags = sorted(tag for tag in raw.get("tags") or [] if tag.startswith(C4_TAG_PREFIX))
    if len(tags) != 1:
        listed = ", ".join(tags) or "none"
        return None, f"view carries {len(tags)} C4 type tags, expected 1: {listed}"
    if tags[0] not in C4_TYPE_BY_TAG:
        return None, f"tag {tags[0]} names no C4 type; use one of {', '.join(C4_TYPE_BY_TAG)}"
    return C4_TYPE_BY_TAG[tags[0]], None


def _project_node(
    raw: Mapping[str, Any], model: Mapping[str, Any], drawings: Mapping, in_view: set
) -> tuple[Node, str | None]:
    """The node as drawn, and why it draws as Uncategorised when it does."""
    element = (model.get("elements") or {}).get(raw.get("modelRef") or raw["id"]) or raw
    is_frame = any(child in in_view for child in raw.get("children") or [])
    category = resolve_category(element, model.get("specification") or {})
    drawing = drawings.get((category, is_frame))
    problem = None
    if category is None:
        problem = "no category: declare one string metadata.category or a kind notation"
    elif drawing is None:
        problem = f"'{category}' names no {'frame' if is_frame else 'box'} drawing"
    parent = raw.get("parent")
    node = Node(
        id=raw["id"],
        name=raw.get("title") or element.get("title") or raw["id"],
        drawing=drawing or UNCATEGORISED,
        technology=_string(element.get("technology")),
        responsibility=_text(element.get("summary")) or _text(element.get("description")),
        is_frame=is_frame,
        parent=parent if parent in in_view else None,
    )
    return node, problem


def _project_edge(
    raw: Mapping[str, Any], relations: Mapping[str, Any], position: int | None
) -> Edge:
    """`position` is the step's place in a dynamic view; None for an element view's arrow."""
    linked = [relations[r] for r in raw.get("relations") or [] if r in relations]
    titles = [title for title in (_string(r.get("title")) for r in linked) if title]
    kinds = [r.get("kind") for r in linked] or [raw.get("kind")]
    reads = all(kind == READS_KIND for kind in kinds)
    own_label = _string(raw.get("label"))
    own_label = None if own_label == PLACEHOLDER_LABEL else own_label
    if position is None:
        label = relationship_label(titles) or own_label or ""
        return Edge(raw["source"], raw["target"], label, reads=reads)
    step_no = _step_number(raw.get("id"), position)
    title = own_label or relationship_label(titles)
    label = f"{step_no} · {title}" if title else str(step_no)
    return Edge(raw["source"], raw["target"], label, step_no, reads)


def _step_number(edge_id: str | None, position: int) -> int:
    match = STEP_ID.match(edge_id or "")
    return int(match.group(1)) if match else position


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _text(value: Any) -> str | None:
    """LikeC4 records prose as `{"txt": ...}` or `{"md": ...}`."""
    if isinstance(value, Mapping):
        return _string(value.get("txt")) or _string(value.get("md"))
    return _string(value)


# --- labels ----------------------------------------------------------------------------------


def relationship_label(titles: Sequence[str]) -> str:
    """One title as is; several as the first in sorted order plus how many more."""
    if not titles:
        return ""
    ordered = sorted(titles)
    return ordered[0] if len(ordered) == 1 else f"{ordered[0]} +{len(ordered) - 1} more"


def wrap_text(text: str, width: int) -> list[str]:
    """Word-boundary lines of at most `width` characters; a longer word stays whole."""
    return textwrap.wrap(
        " ".join(text.split()), width, break_long_words=False, break_on_hyphens=False
    )


def node_label_lines(node: Node) -> list[str]:
    classifier = " · ".join(part for part in (node.category, node.technology) if part)
    lines = [*wrap_text(node.name, LABEL_WIDTH), f"[{classifier}]"]
    if node.responsibility:
        lines.extend(wrap_text(node.responsibility, LABEL_WIDTH))
    return lines


# --- the legend ------------------------------------------------------------------------------


def legend_entries(view: View) -> list[LegendEntry]:
    """Boxes in vocabulary order, then frames, then the line meanings the view uses."""
    drawings, lines = _legend(view)
    entries = [LegendEntry(_legend_label(token), token.drawing_class) for token in drawings]
    return entries + [LegendEntry(line.meaning, None) for line in lines]


def _legend(view: View) -> tuple[list[Token], list[LineDrawing]]:
    unknown_rank = len(CATEGORY_RANK)

    def order(token: Token) -> tuple:
        last = token.category == UNCATEGORISED_NAME
        return (token.frame, last, CATEGORY_RANK.get(token.category, unknown_rank), token.category)

    drawings = sorted({node.drawing for node in view.nodes}, key=order)
    used = {edge.line for edge in view.edges}
    return drawings, [LINE_DRAWINGS[line] for line in LINE_ORDER if line in used]


def _legend_label(token: Token) -> str:
    return token.category + (FRAME_SUFFIX if token.frame else "")


# --- D2 emission -----------------------------------------------------------------------------


def emit_d2(view: View) -> str:
    """The view as D2 text; pure, and independent of the order nodes and edges are listed in."""
    drawings, lines = _legend(view)
    document = {
        "vars": {
            "d2-config": {
                "layout-engine": "elk",
                "pad": CANVAS_PAD,
                "theme-overrides": {
                    "N1": _quote(INK),
                    "N2": _quote(EDGE_LABEL_INK),
                    "N7": _quote(CANVAS),
                },
            }
        },
        "classes": {
            **{token.drawing_class: _token_fields(token) for token in drawings},
            **{line.drawing_class: _line_fields(line) for line in lines},
        },
        TITLE_KEY: _title_fields(view),
        **_node_entries(view),
        LEGEND_KEY: _legend_fields(drawings, lines),
    }
    return "\n".join([*_render(document), *_edge_lines(view)]) + "\n"


def _token_fields(token: Token) -> dict:
    style = {
        "fill": _quote(token.fill) if token.fill else "transparent",
        "stroke": _quote(token.stroke),
        "stroke-width": token.stroke_width,
        "font-color": _quote(token.text_colour),
        "font-size": ELEMENT_FONT_SIZE,
    }
    if token.dash:
        style["stroke-dash"] = token.dash
    if token.radius:
        style["border-radius"] = token.radius
    if token.extra != "none":
        style[token.extra] = "true"
    fields: dict = {"shape": token.shape}
    if token.icon != "none":
        fields["icon"] = _quote(ICON_URIS[token.icon])
    return {**fields, "style": style}


def _line_fields(line: LineDrawing) -> dict:
    style = {
        "fill": _quote(CANVAS),
        "stroke": _quote(line.stroke),
        "stroke-width": line.width,
        "font-color": _quote(EDGE_LABEL_INK),
        "font-size": EDGE_FONT_SIZE,
    }
    if line.dash:
        style["stroke-dash"] = line.dash
    return {"style": style}


def _title_fields(view: View) -> dict:
    title = view.title if view.c4_type is None else f"{view.title} — {view.c4_type} diagram"
    return {
        "label": _quote(title),
        "shape": "text",
        "near": "top-center",
        "style": {"font-size": TITLE_FONT_SIZE, "bold": "true", "font-color": _quote(INK)},
    }


def _node_entries(view: View) -> dict:
    """Top-level nodes keyed by quoted id, each frame holding the nodes it encloses."""
    children: dict[str | None, list[Node]] = {}
    for node in sorted(view.nodes, key=lambda n: n.id):
        children.setdefault(node.parent, []).append(node)

    def entries(parent: str | None) -> dict:
        return {
            _node_key(node.id): {
                "label": _quote("\n".join(node_label_lines(node))),
                "class": node.drawing.drawing_class,
                **entries(node.id),
            }
            for node in children.get(parent, [])
        }

    return entries(None)


def _edge_lines(view: View) -> list[str]:
    paths = _node_paths(view)
    ordered = sorted(view.edges, key=lambda e: (e.step_no or 0, e.source, e.target, e.label))
    return [
        f"{paths[e.source]} -> {paths[e.target]}: {_quote(e.label)} "
        f"{{class: {LINE_DRAWINGS[e.line].drawing_class}}}"
        for e in ordered
    ]


def _node_paths(view: View) -> dict[str, str]:
    """Each node's D2 key path: a model id's dots are quoted, D2's own dots mean nesting."""
    parents = {node.id: node.parent for node in view.nodes}

    def path(node_id: str) -> str:
        parent = parents.get(node_id)
        key = _node_key(node_id)
        return key if parent is None else f"{path(parent)}.{key}"

    return {node_id: path(node_id) for node_id in parents}


def _legend_fields(drawings: Sequence[Token], lines: Sequence[LineDrawing]) -> dict:
    """A grid of one sample per drawing, then one per line meaning."""
    fields: dict = {
        "label": _quote(LEGEND_KEY),
        "near": "bottom-center",
        "grid-columns": LEGEND_COLUMNS,
        "style": {
            "fill": _quote(CANVAS),
            "stroke": _quote(LEGEND_STROKE),
            "stroke-width": 1,
            "font-color": _quote(INK),
        },
    }
    for token in drawings:
        drawing_class = token.drawing_class
        fields[drawing_class] = {"label": _quote(_legend_label(token)), "class": drawing_class}
    for line in lines:
        fields[f"{line.drawing_class}_sample"] = _line_sample(line)
    return fields


def _line_sample(line: LineDrawing) -> dict:
    """An arrow between two dots, laid out left to right in its own unframed cell."""
    dot = {
        "label": '""',
        "shape": "circle",
        "width": LEGEND_DOT,
        "height": LEGEND_DOT,
        "style": {"fill": _quote(line.stroke), "stroke": _quote(line.stroke)},
    }
    return {
        "label": '""',
        "direction": "right",
        "style": {"fill": "transparent", "stroke-width": 0},
        "tail": dot,
        "head": dot,
        "tail -> head": {"label": _quote(line.meaning), "class": line.drawing_class},
    }


def _render(fields: Mapping[str, Any], indent: str = "") -> list[str]:
    """D2 text of a nested mapping; keys and values are already D2 tokens."""
    rendered = []
    for key, value in fields.items():
        if isinstance(value, Mapping):
            rendered += [f"{indent}{key}: {{", *_render(value, indent + "  "), f"{indent}}}"]
        else:
            rendered.append(f"{indent}{key}: {value}")
    return rendered


def _node_key(element_id: str) -> str:
    """D2 keys ignore case and quoting, so a bare id `title` would merge into the title block."""
    return _quote(ELEMENT_KEY_PREFIX + element_id)


def _quote(text: str) -> str:
    """A D2 double-quoted string; `$` is escaped because D2 substitutes `${...}` inside one."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + escaped.replace("$", "\\$") + '"'
