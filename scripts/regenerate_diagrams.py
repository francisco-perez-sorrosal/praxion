#!/usr/bin/env python3
"""Regenerate the C4 renders of a LikeC4 workspace in one fixed visual vocabulary.

    ROOT      a diagram root holding `src/*.c4` and `rendered/`; default: every
              `<dir>/<name>/` under `docs/diagrams/` that has a `src/*.c4`
    --staged  pre-commit: only roots with a staged `src/*.c4`, then `git add <root>/rendered/`;
              failed checks print as non-blocking WARN lines
    --check   render into a temporary directory, byte-compare with the committed `rendered/`,
              run every review check; writes nothing in the checkout
    --json    findings as JSON Lines on stdout

Exit codes: 0 success (`--check`: no drift, no failed check); 1 a regeneration failure, or
under `--check` drift or a failed check; 2 a usage error (a refused `style.json` included);
3 (default, `--check`) `likec4` or `d2` absent from PATH or off its pinned version.

The model is read once, through `likec4 export json --skip-layout`, into a view projection;
each view is drawn as D2 text and rendered by `d2`. Every render guarantees:

- one category per element: its `metadata.category` when that is one string, else its
  kind's `notation`; without one it draws as "Uncategorised" and fails DRC-05, never the run;
- one drawing per (category, form): class `category_<snake_case>`, plus `_frame` for an
  element enclosing children in the view; in a vocabulary, marks differ without colour;
- plain, never markdown, element labels: name, `[Category]` or `[Category · technology]`,
  then the summary (else the description) wrapped at 28 characters, never truncated;
- one-way arrows labelled with the relationship title, or `<first title> +<k> more` over
  sorted titles; dynamic steps read `<n> · <title>`; kind `reads` is a dashed read-only line;
- a title block `<view title> — <C4 type> diagram` above the drawing, and below it a
  container labelled exactly `Legend` with one sample per drawing and line meaning used;
- no network address, clock or dark layer: an identical model and pinned toolchain give
  identical bytes; the only image is the Person glyph, embedded as a data URI.

`<diagram-root>/style.json` (`{"schema": 1, "categories": {"<Name>": {"box": {...},
"frame": {...}}}}`) adds categories; an entry missing a contrast floor or repeating a mark of
its form is a usage error naming it. Runs report a regeneration failure `{kind, target, what,
cause, fix}` (three stderr lines) and findings `{check, view, status, evidence, measured,
threshold}` (`<CHECK-ID> <VIEW> <STATUS> <EVIDENCE>`).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

LIKEC4_VERSION = "1.59.4"
D2_VERSION = "0.7.1"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_TOOLCHAIN = 3

CANVAS = "#FFFFFF"
INK = "#0F172A"
EDGE_INK = "#475569"
EDGE_LABEL_INK = "#334155"
STEP_INK = "#4338CA"
LEGEND_STROKE = "#8C8780"

TEXT_CONTRAST_FLOOR = 4.5
OUTLINE_CONTRAST_FLOOR = 3.0
LABEL_WIDTH = 28

ELEMENT_FONT_SIZE = 15
EDGE_FONT_SIZE = 14
TITLE_FONT_SIZE = 24
DASHED = 5
DOTTED = 2
CANVAS_PAD = 40
LEGEND_DOT = 8
LEGEND_COLUMNS = 4

LEGEND_KEY = "Legend"
TITLE_KEY = "Title"
FRAME_SUFFIX = " (boundary)"
UNCATEGORISED_NAME = "Uncategorised"

ACTS_ON = "acts-on"
READ_ONLY = "read-only"
STEP = "step"
READS_KIND = "reads"
PLACEHOLDER_LABEL = "[...]"
STEP_ID = re.compile(r"^step-(\d+)")

C4_TYPE_BY_TAG = {
    "c4_system_context": "System Context",
    "c4_system_landscape": "System Landscape",
    "c4_container": "Container",
    "c4_component": "Component",
    "c4_deployment": "Deployment",
}
DYNAMIC = "Dynamic"
C4_TAG_PREFIX = "c4_"

FAILURE_KINDS = frozenset(
    {"toolchain-error", "no-views", "view-without-render", "render-without-names"}
)
FINDING_STATUSES = frozenset({"PASS", "FAIL"})
CHECK_ID = re.compile(r"^DRC-\d{2}$")


class UsageError(Exception):
    """A request the command refuses before drawing anything (exit 2)."""


# --- the records -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """How one (category, form) is drawn; colours are `#RRGGBB`, `fill` None is no fill."""

    category: str
    frame: bool
    shape: str
    fill: str | None
    stroke: str
    stroke_width: float = 2
    dash: int = 0
    radius: int = 0
    extra: str = "none"
    icon: str = "none"
    text_colour: str = INK

    @property
    def drawing_class(self) -> str:
        return "category_" + snake_case(self.category) + ("_frame" if self.frame else "")

    @property
    def mark(self) -> tuple:
        """What stays of the drawing once colour is removed."""
        return (self.shape, self.radius, self.extra, bool(self.dash), self.stroke_width, self.icon)


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


@dataclass(frozen=True)
class LineDrawing:
    drawing_class: str
    meaning: str
    stroke: str
    stroke_width: float
    dash: int


# --- the token table ---------------------------------------------------------------------------

DEFAULT_TOKENS: tuple[Token, ...] = (
    Token("Person", False, "rectangle", "#E6F0FA", "#1D4E89", icon="person"),
    Token("System in scope", False, "rectangle", "#4338CA", "#312E81", 3, text_colour=CANVAS),
    Token("System in scope", True, "rectangle", "#EEF2FF", "#4338CA"),
    Token("External system", False, "rectangle", "#ECEAE6", "#77726A", dash=DASHED),
    Token("Knowledge asset", False, "package", "#E1F3EC", "#00684A"),
    Token("Runtime agent", False, "rectangle", "#FDEFD9", "#A85A00", radius=16),
    Token("Runtime agent", True, "rectangle", None, "#A85A00", 1.5, DASHED, 16),
    Token("Pipeline document", False, "document", "#E3F1FB", "#0B6FA4"),
    Token("Persistent store", False, "cylinder", "#F6E6F0", "#9B3A75"),
    Token("Tooling", False, "rectangle", "#F2F4F7", "#3F4B5C", extra="3d"),
    Token("Layer", True, "rectangle", None, "#8C8780", 1.5, DASHED),
    Token("Layer", False, "rectangle", CANVAS, "#8C8780", extra="double-border"),
    Token("Container", False, "rectangle", "#E3F1FB", "#0B6FA4", radius=8),
    Token("Container", True, "rectangle", None, "#0B6FA4", 1.5, DASHED, 8),
    Token("Component", False, "rectangle", "#E1F3EC", "#00684A", extra="double-border"),
    Token("Data store", False, "cylinder", "#F6E6F0", "#9B3A75"),
)

UNCATEGORISED = Token(UNCATEGORISED_NAME, False, "rectangle", CANVAS, INK, 1, DOTTED)

VOCABULARIES: dict[str, tuple[str, ...]] = {
    "praxion": (
        "Person",
        "System in scope",
        "External system",
        "Knowledge asset",
        "Runtime agent",
        "Pipeline document",
        "Persistent store",
        "Tooling",
        "Layer",
    ),
    "kit": ("Person", "System in scope", "External system", "Container", "Component", "Data store"),
}

LINE_DRAWINGS: dict[str, LineDrawing] = {
    ACTS_ON: LineDrawing("line_acts_on", "acts on (invokes, writes)", EDGE_INK, 2, 0),
    READ_ONLY: LineDrawing(
        "line_read_only", "read-only flow (consumed, not modified)", EDGE_INK, 2, DASHED
    ),
    STEP: LineDrawing("line_step", "numbered step, in order (dynamic views)", STEP_INK, 2.5, 0),
}
READ_ONLY_STEP = LineDrawing(
    "line_step_read_only", LINE_DRAWINGS[STEP].meaning, STEP_INK, 2.5, DASHED
)
LINE_ORDER = (ACTS_ON, READ_ONLY, STEP)

# Vendored here rather than fetched, so a render never reaches the network.
PERSON_GLYPH = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<circle cx="12" cy="7" r="4.5" fill="#1D4E89"/>'
    '<path d="M3 22c0-5 4-8.5 9-8.5s9 3.5 9 8.5z" fill="#1D4E89"/></svg>'
)
ICON_URIS = {
    "person": "data:image/svg+xml;base64," + base64.b64encode(PERSON_GLYPH.encode()).decode(),
}

_CATEGORY_RANK = {
    name: rank for rank, name in enumerate(dict.fromkeys(t.category for t in DEFAULT_TOKENS))
}


def snake_case(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


# --- contrast ----------------------------------------------------------------------------------


def contrast_ratio(first: str, second: str) -> float:
    """WCAG 2 contrast ratio of two `#RRGGBB` colours."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(colour: str) -> float:
    red, green, blue = (_linear(int(colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear(unit: float) -> float:
    return unit / 12.92 if unit <= 0.03928 else ((unit + 0.055) / 1.055) ** 2.4


# --- a project's own categories (style.json) ---------------------------------------------------

STYLE_SCHEMA = 1
STYLE_SHAPES = frozenset(
    {"rectangle", "square", "package", "document", "cylinder", "queue", "page", "hexagon", "oval"}
)
STYLE_REQUIRED = ("shape", "fill", "stroke", "text_colour")
STYLE_DEFAULTS = {"stroke_width": 2, "dash": 0, "radius": 0, "extra": "none", "icon": "none"}
STYLE_EXTRAS = frozenset({"none", "3d", "double-border"})
STYLE_FORMS = {"box": False, "frame": True}
HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_STROKE = 15  # the widest stroke D2 draws


def load_style(text: str, base: tuple[Token, ...] = DEFAULT_TOKENS) -> tuple[Token, ...]:
    """The base drawings followed by the categories a `style.json` adds, each validated."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise UsageError(f"style.json is not JSON: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != STYLE_SCHEMA:
        found = document.get("schema") if isinstance(document, dict) else None
        raise UsageError(f"style.json: schema must be {STYLE_SCHEMA}, found {found!r}")
    categories = document.get("categories")
    if not isinstance(categories, dict):
        raise UsageError("style.json: 'categories' must be an object")
    tokens = list(base)
    for name, forms in categories.items():
        tokens.extend(_style_entry(name, forms, tuple(tokens)))
    return tuple(tokens)


def _style_entry(name: str, forms: Any, drawn: tuple[Token, ...]) -> list[Token]:
    if not isinstance(forms, dict) or "box" not in forms or set(forms) - set(STYLE_FORMS):
        raise UsageError(f"style.json: category {name!r} needs a 'box' and at most a 'frame'")
    if any(token.category == name for token in drawn):
        raise UsageError(f"style.json: category {name!r} is already drawn")
    added = []
    for form, frame in STYLE_FORMS.items():
        if form in forms:
            token = _style_token(name, frame, forms[form])
            problem = _style_problem(token, (*drawn, *added))
            if problem:
                raise UsageError(f"style.json: category {name!r} {form}: {problem}")
            added.append(token)
    return added


def _style_token(name: str, frame: bool, given: Any) -> Token:
    if not isinstance(given, dict):
        raise UsageError(f"style.json: category {name!r} drawing must be an object")
    missing = [key for key in STYLE_REQUIRED if key not in given]
    unknown = sorted(set(given) - set(STYLE_REQUIRED) - set(STYLE_DEFAULTS))
    if missing or unknown:
        raise UsageError(f"style.json: category {name!r}: missing {missing}, unknown {unknown}")
    values = {**STYLE_DEFAULTS, **given}
    try:
        return Token(name, frame, **values)
    except TypeError as error:
        raise UsageError(f"style.json: category {name!r}: {error}") from error


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _style_problem(token: Token, drawn: Sequence[Token]) -> str | None:
    """Why a drawing cannot join the table, or None when it can."""
    colours = [c for c in (token.fill, token.stroke, token.text_colour) if c is not None]
    if not all(isinstance(c, str) and HEX_COLOUR.match(c) for c in colours):
        return "colours must be #RRGGBB"
    names = (token.shape, token.extra, token.icon)
    if not all(isinstance(n, str) for n in names) or token.shape not in STYLE_SHAPES:
        return f"shape must be one of {sorted(STYLE_SHAPES)}"
    if token.extra not in STYLE_EXTRAS or token.icon != "none":
        return f"extra must be one of {sorted(STYLE_EXTRAS)} and icon 'none'"
    sizes = (token.stroke_width, token.dash, token.radius)
    if not all(_is_number(n) and n >= 0 for n in sizes) or not 0 < token.stroke_width <= MAX_STROKE:
        return f"stroke_width must be in (0, {MAX_STROKE}], dash and radius non-negative numbers"
    if contrast_ratio(token.text_colour, token.fill or CANVAS) < TEXT_CONTRAST_FLOOR:
        return f"text contrast on its fill is below {TEXT_CONTRAST_FLOOR}:1"
    if contrast_ratio(token.stroke, CANVAS) < OUTLINE_CONTRAST_FLOOR:
        return f"outline contrast on the canvas is below {OUTLINE_CONTRAST_FLOOR}:1"
    twin = next((t for t in drawn if t.frame == token.frame and t.mark == token.mark), None)
    if twin is not None:
        return f"its mark repeats {twin.drawing_class}; change shape, radius, extra, dash or width"
    return None


# --- the category rule and the view projection -------------------------------------------------


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
    views: list[View] = []
    findings: list[Finding] = []
    for view_id, raw in sorted((model.get("views") or {}).items()):
        view, view_findings = _project_view(view_id, raw, model, drawings)
        views.append(view)
        findings.extend(view_findings)
    return Projection(tuple(views), tuple(findings))


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
        evidence = f"{len(unresolved)} element(s) draw as {UNCATEGORISED_NAME}: " + ", ".join(
            sorted(unresolved)
        )
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
    if own_label == PLACEHOLDER_LABEL:
        own_label = None
    if position is None:
        return Edge(
            raw["source"], raw["target"], relationship_label(titles) or own_label or "", reads=reads
        )
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


# --- labels ------------------------------------------------------------------------------------


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


# --- the legend --------------------------------------------------------------------------------


def legend_entries(view: View) -> list[LegendEntry]:
    """Boxes in vocabulary order, then frames, then the line meanings the view uses."""
    drawings, lines = _legend(view)
    entries = [LegendEntry(_legend_label(token), token.drawing_class) for token in drawings]
    return entries + [LegendEntry(line.meaning, None) for line in lines]


def _legend(view: View) -> tuple[list[Token], list[LineDrawing]]:
    unknown_rank = len(_CATEGORY_RANK)

    def order(token: Token) -> tuple:
        last = token.category == UNCATEGORISED_NAME
        return (token.frame, last, _CATEGORY_RANK.get(token.category, unknown_rank), token.category)

    drawings = sorted({node.drawing for node in view.nodes}, key=order)
    used = {edge.line for edge in view.edges}
    return drawings, [LINE_DRAWINGS[line] for line in LINE_ORDER if line in used]


def _legend_label(token: Token) -> str:
    return token.category + (FRAME_SUFFIX if token.frame else "")


# --- D2 emission -------------------------------------------------------------------------------


def emit_d2(view: View) -> str:
    """The view as D2 text; pure, and independent of the order nodes and edges are listed in."""
    drawings, lines = _legend(view)
    edge_drawings = sorted({_line_drawing(e) for e in view.edges} - set(lines), key=_class_of)
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
            **{line.drawing_class: _line_fields(line) for line in (*lines, *edge_drawings)},
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
        "stroke-width": _pixels(token.stroke_width),
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
        "stroke-width": _pixels(line.stroke_width),
        "font-color": _quote(EDGE_LABEL_INK),
        "font-size": EDGE_FONT_SIZE,
    }
    if line.dash:
        style["stroke-dash"] = line.dash
    return {"style": style}


def _class_of(line: LineDrawing) -> str:
    return line.drawing_class


def _line_drawing(edge: Edge) -> LineDrawing:
    if edge.line == STEP and edge.reads:
        return READ_ONLY_STEP
    return LINE_DRAWINGS[edge.line]


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
            _quote(node.id): {
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
        f"{{class: {_line_drawing(e).drawing_class}}}"
        for e in ordered
    ]


def _node_paths(view: View) -> dict[str, str]:
    """Each node's D2 key path: a model id's dots are quoted, D2's own dots mean nesting."""
    parents = {node.id: node.parent for node in view.nodes}

    def path(node_id: str) -> str:
        parent = parents.get(node_id)
        return _quote(node_id) if parent is None else f"{path(parent)}.{_quote(node_id)}"

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
        fields[token.drawing_class] = {
            "label": _quote(_legend_label(token)),
            "class": token.drawing_class,
        }
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


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _pixels(width: float) -> int:
    """D2 accepts whole-pixel stroke widths only; halves round up."""
    return int(width + 0.5)


# --- command line ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("roots", nargs="*", metavar="ROOT")
    for flag in ("--staged", "--check", "--json"):
        parser.add_argument(flag, action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(
        "[diagram-regen] the render edge is not wired in yet; nothing regenerated", file=sys.stderr
    )
    return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
