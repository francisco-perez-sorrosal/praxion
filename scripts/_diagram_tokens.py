"""The visual vocabulary of the diagram renderer: one drawing per (category, form).

Holds the default token table, the line drawings, the two vocabularies, the vendored Person
glyph, WCAG contrast, and the validation of a project's `style.json` additions. Pure: no I/O.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

CANVAS = "#FFFFFF"
INK = "#0F172A"
EDGE_INK = "#475569"
EDGE_LABEL_INK = "#334155"
STEP_INK = "#4338CA"
LEGEND_STROKE = "#8C8780"

TEXT_CONTRAST_FLOOR = 4.5
OUTLINE_CONTRAST_FLOOR = 3.0
DASHED = 5
DOTTED = 2

UNCATEGORISED_NAME = "Uncategorised"
ACTS_ON = "acts-on"
READ_ONLY = "read-only"
STEP = "step"


class UsageError(Exception):
    """A request the command refuses before drawing anything (exit 2)."""


# --- drawings --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Token:
    """How one (category, form) is drawn; colours are `#RRGGBB`, `fill` None is no fill."""

    category: str
    frame: bool
    shape: str
    fill: str | None
    stroke: str
    stroke_width: int = 2
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
class LineDrawing:
    drawing_class: str
    meaning: str
    stroke: str
    width: int
    dash: int


DEFAULT_TOKENS: tuple[Token, ...] = (
    Token("Person", False, "rectangle", "#E6F0FA", "#1D4E89", icon="person"),
    Token("System in scope", False, "rectangle", "#4338CA", "#312E81", 3, text_colour=CANVAS),
    Token("System in scope", True, "rectangle", "#EEF2FF", "#4338CA"),
    Token("External system", False, "rectangle", "#ECEAE6", "#77726A", dash=DASHED),
    Token("Knowledge asset", False, "package", "#E1F3EC", "#00684A"),
    Token("Runtime agent", False, "rectangle", "#FDEFD9", "#A85A00", radius=16),
    Token("Runtime agent", True, "rectangle", None, "#A85A00", 2, DASHED, 16),
    Token("Pipeline document", False, "document", "#E3F1FB", "#0B6FA4"),
    Token("Persistent store", False, "cylinder", "#F6E6F0", "#9B3A75"),
    Token("Tooling", False, "rectangle", "#F2F4F7", "#3F4B5C", extra="3d"),
    Token("Layer", True, "rectangle", None, "#8C8780", 2, DASHED),
    Token("Layer", False, "rectangle", CANVAS, "#8C8780", extra="double-border"),
    Token("Container", False, "rectangle", "#E3F1FB", "#0B6FA4", radius=8),
    Token("Container", True, "rectangle", None, "#0B6FA4", 2, DASHED, 8),
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
    STEP: LineDrawing("line_step", "numbered step, in order (dynamic views)", STEP_INK, 3, 0),
}
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

CATEGORY_RANK = {
    name: rank for rank, name in enumerate(dict.fromkeys(t.category for t in DEFAULT_TOKENS))
}


def snake_case(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", name.lower()).strip("_")


# --- contrast --------------------------------------------------------------------------------


def contrast_ratio(first: str, second: str) -> float:
    """WCAG 2 contrast ratio of two `#RRGGBB` colours."""
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(colour: str) -> float:
    red, green, blue = (_linear(int(colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _linear(unit: float) -> float:
    return unit / 12.92 if unit <= 0.03928 else ((unit + 0.055) / 1.055) ** 2.4


# --- a project's own categories (style.json) -------------------------------------------------

STYLE_SCHEMA = 1
STYLE_SHAPES = frozenset(
    {"rectangle", "square", "package", "document", "cylinder", "queue", "page", "hexagon", "oval"}
)
STYLE_REQUIRED = ("shape", "fill", "stroke", "text_colour")
STYLE_DEFAULTS = {"stroke_width": 2, "dash": 0, "radius": 0, "extra": "none", "icon": "none"}
# The shapes D2 accepts each extra mark on; it refuses the rest at compile time.
STYLE_EXTRAS = {
    "none": STYLE_SHAPES,
    "3d": frozenset({"rectangle", "square", "hexagon"}),
    "double-border": frozenset({"rectangle", "square", "oval"}),
}
STYLE_FORMS = {"box": False, "frame": True}
HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_STROKE = 15  # D2 draws whole-pixel strokes, 0 to 15


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


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _style_problem(token: Token, drawn: Sequence[Token]) -> str | None:
    """Why a drawing cannot join the table, or None when it can."""
    colours = [c for c in (token.fill, token.stroke, token.text_colour) if c is not None]
    if not all(isinstance(c, str) and HEX_COLOUR.match(c) for c in colours):
        return "colours must be #RRGGBB"
    names = (token.shape, token.extra, token.icon)
    if not all(isinstance(n, str) for n in names) or token.shape not in STYLE_SHAPES:
        return f"shape must be one of {sorted(STYLE_SHAPES)}"
    if token.shape not in STYLE_EXTRAS.get(token.extra, ()) or token.icon != "none":
        return f"extra {token.extra!r} cannot mark a {token.shape}, and icon must be 'none'"
    sizes = (token.stroke_width, token.dash, token.radius)
    if (
        not all(_is_integer(n) and n >= 0 for n in sizes)
        or not 1 <= token.stroke_width <= MAX_STROKE
    ):
        return (
            f"stroke_width must be a whole number 1 to {MAX_STROKE}, dash and radius whole numbers"
        )
    if contrast_ratio(token.text_colour, token.fill or CANVAS) < TEXT_CONTRAST_FLOOR:
        return f"text contrast on its fill is below {TEXT_CONTRAST_FLOOR}:1"
    if contrast_ratio(token.stroke, CANVAS) < OUTLINE_CONTRAST_FLOOR:
        return f"outline contrast on the canvas is below {OUTLINE_CONTRAST_FLOOR}:1"
    twin = next((t for t in drawn if t.frame == token.frame and t.mark == token.mark), None)
    if twin is not None:
        return f"its mark repeats {twin.drawing_class}; change shape, radius, extra, dash or width"
    return None
