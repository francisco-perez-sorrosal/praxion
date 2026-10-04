"""A read-only reader of a rendered SVG: the one place the review checks look at markup.

`read_svg` turns d2's output into groups, each holding what it draws itself: text lines (with
resolved font size and colour), shapes and arrows. A group is one `<g>`; the `<g class="shape">`
wrapper d2 puts around a node's shape belongs to the node's group, and a marker's polygon,
masks and styles are not drawings. Colours come from the presentation attribute or the inline
`style` of an element, which is where the command's render keeps them (D2's theme classes are
pinned to the same values); stroke widths are the whole pixels the renderer draws. Pure: markup
text in, records out.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import cached_property

LEGEND_HEADING = "Legend"

Box = tuple[float, float, float, float]  # x0, y0, x1, y1

_SKIPPED = frozenset({"defs", "marker", "mask", "clipPath", "style", "title", "desc", "metadata"})
_SHAPES = frozenset({"rect", "path", "ellipse", "circle", "polygon", "polyline", "line", "image"})
_ARROWS = frozenset({"path", "line", "polyline"})
_WRAPPER_CLASS = "shape"
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")
_COMMAND = re.compile(r"[A-Za-z]")


# --- the records -----------------------------------------------------------------------------


@dataclass(frozen=True)
class TextLine:
    """One line of text; `x`, `y` are its anchor, `fill` is `#RRGGBB` or None."""

    text: str
    font_size: float | None
    fill: str | None
    x: float
    y: float
    anchor: str
    order: int


@dataclass(frozen=True)
class Shape:
    """A drawn shape with colour kept apart from the marks (geometry, dash, width, icon).

    `dash` is the dash length in pixels, 0 when solid; d2 stretches the gap to fit a path, so
    only the length says how a stroke is drawn. `stroke_width` is whole pixels.
    """

    geometry: str
    fill: str | None
    stroke: str | None
    dash: int
    stroke_width: int
    icon: str | None
    box: Box
    order: int

    @property
    def visible(self) -> bool:
        return self.fill is not None or self.icon is not None or self.stroke_width > 0

    @property
    def mark(self) -> tuple:
        """How the shape is drawn once colour is removed."""
        return (self.geometry, self.dash, self.stroke_width, self.icon)

    @property
    def drawing(self) -> tuple:
        return (*self.mark, self.fill, self.stroke)


@dataclass(frozen=True)
class Arrow:
    marker_start: bool
    marker_end: bool
    stroke: str | None
    dash: int
    stroke_width: int
    box: Box
    order: int


@dataclass(frozen=True)
class Group:
    """What one `<g>` draws itself, in document order."""

    classes: tuple[str, ...]
    lines: tuple[TextLine, ...]
    shapes: tuple[Shape, ...]
    arrows: tuple[Arrow, ...]

    @cached_property
    def box(self) -> Box | None:
        return _union([s.box for s in self.shapes if s.visible] + [a.box for a in self.arrows])

    @property
    def text(self) -> str:
        return normalise(" ".join(line.text for line in self.lines))

    @property
    def drawing(self) -> tuple:
        """The group's visible shapes, colour included, in a form that compares for equality."""
        return tuple(sorted((s.drawing for s in self.shapes if s.visible), key=repr))

    @property
    def mark(self) -> tuple:
        return tuple(sorted({s.mark for s in self.shapes if s.visible}, key=repr))


@dataclass(frozen=True)
class Svg:
    width: float
    height: float
    groups: tuple[Group, ...]

    @cached_property
    def legend(self) -> Group | None:
        """The group holding a line that reads exactly `Legend`."""
        return next(
            (g for g in self.groups if any(line.text == LEGEND_HEADING for line in g.lines)), None
        )

    @cached_property
    def legend_region(self) -> Box | None:
        return self.legend.box if self.legend else None

    def in_legend(self, group: Group) -> bool:
        """Whether the group stands inside the legend's region (the legend itself excluded)."""
        region, box = self.legend_region, group.box
        if region is None or box is None or group is self.legend:
            return False
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]

    @property
    def drawn(self) -> tuple[Group, ...]:
        """Groups of the view itself: the legend and what stands inside it are left out."""
        return tuple(g for g in self.groups if g is not self.legend and not self.in_legend(g))

    @property
    def samples(self) -> tuple[Group, ...]:
        return tuple(g for g in self.groups if self.in_legend(g))


# --- text ------------------------------------------------------------------------------------


def normalise(text: str) -> str:
    return " ".join(text.split())


def spelled_at(lines: list[str], name: str) -> tuple[int, int] | None:
    """The run `[start, end)` of consecutive lines that spell `name`, whitespace-normalised."""
    wanted = normalise(name)
    for start in range(len(lines)):
        spelled = ""
        for end in range(start, len(lines)):
            spelled = normalise(f"{spelled} {lines[end]}")
            if spelled == wanted:
                return start, end + 1
            if not wanted.startswith(spelled):
                break
    return None


# --- reading ---------------------------------------------------------------------------------


def read_svg(markup: str) -> Svg:
    """Read an SVG document; raises `ET.ParseError` when it is not well-formed XML."""
    root = ET.fromstring(markup)
    width, height = _size(root)
    reader = _Reader()
    reader.walk(root, reader.open_group(()))
    return Svg(width, height, tuple(reader.finish()))


class _Reader:
    """Walks the markup once, handing every drawing to the group that owns it."""

    def __init__(self) -> None:
        self._groups: list[dict] = []
        self._order = 0

    def open_group(self, classes: tuple[str, ...]) -> dict:
        group = {"classes": classes, "lines": [], "shapes": [], "arrows": []}
        self._groups.append(group)
        return group

    def finish(self) -> list[Group]:
        return [
            Group(tuple(g["classes"]), tuple(g["lines"]), tuple(g["shapes"]), tuple(g["arrows"]))
            for g in self._groups
        ]

    def walk(self, element: ET.Element, group: dict) -> None:
        for child in element:
            tag = _local(child.tag)
            if tag in _SKIPPED:
                continue
            classes = tuple((child.get("class") or "").split())
            if tag == "g" and classes != (_WRAPPER_CLASS,):
                self.walk(child, self.open_group(classes))
            elif tag == "g" or tag == "svg":
                self.walk(child, group)
            elif tag == "text":
                self._text(child, group)
            elif tag in _SHAPES:
                self._shape(child, tag, group)

    def _next(self) -> int:
        self._order += 1
        return self._order

    def _shape(self, element: ET.Element, tag: str, group: dict) -> None:
        style = _style_of(element)
        box = _box(element, tag)
        if box is None:
            return
        stroke = _colour(style.get("stroke"))
        width = round(_number(style.get("stroke-width"), 1.0)) if stroke else 0
        dash = _dash(style.get("stroke-dasharray"))
        if tag in _ARROWS and (_marker(style, "marker-start") or _marker(style, "marker-end")):
            start, end = _marker(style, "marker-start"), _marker(style, "marker-end")
            arrow = Arrow(start, end, stroke, dash, width, box, self._next())
            group["arrows"].append(arrow)
            return
        default_fill = "none" if tag in ("line", "polyline", "image") else "black"
        fill = _colour(style.get("fill", default_fill))
        geometry, icon = _geometry(element, tag), _icon(element, tag)
        shape = Shape(geometry, fill, stroke, dash, width, icon, box, self._next())
        group["shapes"].append(shape)

    def _text(self, element: ET.Element, group: dict) -> None:
        style = _style_of(element)
        x, y = _number(element.get("x")), _number(element.get("y"))
        spans = [child for child in element if _local(child.tag) == "tspan"]
        if not spans:
            self._line("".join(element.itertext()), x, y, style, group)
        for span in spans:
            span_style = {**style, **_style_of(span)}
            x = _number(span.get("x"), x)
            y += _number(span.get("dy"))
            self._line("".join(span.itertext()), x, y, span_style, group)

    def _line(self, text: str, x: float, y: float, style: dict, group: dict) -> None:
        if not normalise(text):
            return
        size = style.get("font-size")
        anchor = style.get("text-anchor", "start")
        fill = _colour(style.get("fill"))
        line = TextLine(
            normalise(text), _number(size) if size else None, fill, x, y, anchor, self._next()
        )
        group["lines"].append(line)


# --- markup helpers --------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _size(root: ET.Element) -> tuple[float, float]:
    view_box = [float(n) for n in _NUMBER.findall(root.get("viewBox") or "")]
    if len(view_box) == 4:
        return view_box[2], view_box[3]
    return _number(root.get("width")), _number(root.get("height"))


def _style_of(element: ET.Element) -> dict[str, str]:
    """Inline `style` declarations over the presentation attributes this reader uses."""
    resolved = {k: v for k in _PROPERTIES if (v := element.get(k)) is not None}
    for declaration in (element.get("style") or "").split(";"):
        key, _, value = declaration.partition(":")
        if value:
            resolved[key.strip().lower()] = value.strip()
    return resolved


_PROPERTIES = (
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "font-size",
    "text-anchor",
    "marker-start",
    "marker-end",
)


def _number(value: str | None, default: float = 0.0) -> float:
    found = _NUMBER.search(value or "")
    return float(found.group()) if found else default


def _colour(value: str | None) -> str | None:
    """`#RRGGBB` upper-cased, or None for no paint (`none`, `transparent`, anything else)."""
    text = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.upper()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", text):
        return "#" + "".join(c * 2 for c in text[1:]).upper()
    return None


def _dash(value: str | None) -> int:
    """The dash length of a stroke-dasharray, 0 for a solid stroke."""
    if not value or value.strip() in ("none", "0"):
        return 0
    return round(_number(value))


def _marker(style: dict, name: str) -> bool:
    return style.get(name, "none").strip() not in ("", "none")


def _icon(element: ET.Element, tag: str) -> str | None:
    if tag != "image":
        return None
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href") or ""
    return hashlib.sha1(href.encode("utf-8")).hexdigest()[:8]


def _geometry(element: ET.Element, tag: str) -> str:
    """The shape's outline kind without its size: a path is its command letters."""
    if tag == "rect":
        return f"rect(rx={round(_number(element.get('rx')))})"
    if tag == "path":
        return "path:" + "".join(_COMMAND.findall(element.get("d") or "")).upper()
    if tag in ("polygon", "polyline"):
        return f"{tag}{len(_NUMBER.findall(element.get('points') or '')) // 2}"
    return "ellipse" if tag == "circle" else tag


def _box(element: ET.Element, tag: str) -> Box | None:
    a = element.get
    if tag in ("rect", "image"):
        x, y = _number(a("x")), _number(a("y"))
        return (x, y, x + _number(a("width")), y + _number(a("height")))
    if tag in ("ellipse", "circle"):
        rx = _number(a("rx"), _number(a("r")))
        ry = _number(a("ry"), _number(a("r")))
        cx, cy = _number(a("cx")), _number(a("cy"))
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    if tag == "line":
        xs, ys = [_number(a("x1")), _number(a("x2"))], [_number(a("y1")), _number(a("y2"))]
        return (min(xs), min(ys), max(xs), max(ys))
    points = _path_points(a("d")) if tag == "path" else _pairs(a("points") or "")
    return _union([(x, y, x, y) for x, y in points])


def _pairs(text: str) -> list[tuple[float, float]]:
    numbers = [float(n) for n in _NUMBER.findall(text)]
    return [(numbers[i], numbers[i + 1]) for i in range(0, len(numbers) - 1, 2)]


def _path_points(d: str | None) -> list[tuple[float, float]]:
    """Every coordinate a path names (control points too), for the absolute commands d2 writes.

    `H` and `V` carry one number, so a path cannot be read as a flat list of pairs.
    """
    points: list[tuple[float, float]] = []
    x = y = 0.0
    for command, args in re.findall(r"([A-Za-z])([^A-Za-z]*)", d or ""):
        numbers = [float(n) for n in _NUMBER.findall(args)]
        if command.upper() == "H":
            found = [(n, y) for n in numbers]
        elif command.upper() == "V":
            found = [(x, n) for n in numbers]
        elif command.upper() == "A":
            found = [(numbers[i + 5], numbers[i + 6]) for i in range(0, len(numbers) - 6, 7)]
        else:
            found = _pairs(args)
        if found:
            x, y = found[-1]
            points += found
    return points


def _union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
