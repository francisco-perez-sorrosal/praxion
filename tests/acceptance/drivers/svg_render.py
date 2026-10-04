"""Driver that reads a committed SVG render the way a text-only reviewer would.

Nothing here looks at pixels. A render is read from its markup alone:

* its intrinsic size (root `width`/`height`, else the root `viewBox`);
* its canvas: the colour of a filled shape covering the whole drawing, or `None`
  when the canvas is left transparent;
* every text line (`<text>`, each `<tspan>` line, each block inside a
  `<foreignObject>`) with its content, position, resolved font size and colour;
* every drawn shape with its resolved fill, stroke, dash pattern and box;
* every arrow: a stroked path or line carrying `marker-start`/`marker-end`, with the
  text lines of its group as its label.

Styles resolve the way SVG does for the simple cases renderers emit: inline
`style` over matching class rules from the render's own `<style>` blocks over
presentation attributes, then inheritance for inherited properties. Coordinates
follow `translate` transforms and nested `<svg>` viewBox offsets.

Grouping (bound to the render shape at the base commit): an element drawn in a
view is the innermost `<g>` whose own text lines spell the element's name; its
text block and shapes are what that group holds. A legend is the region of the
group headed by a line reading "Legend" (or "Key"/"Notation").
"""

from __future__ import annotations

import functools
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REFERENCE_EMBED_WIDTH = 960.0
LEGEND_HEADINGS = ("legend", "key", "notation")
WHITE = (255, 255, 255)
NEAR_BLACK = (18, 18, 18)

_SKIP_TAGS = {
    "defs",
    "mask",
    "marker",
    "clipPath",
    "pattern",
    "style",
    "symbol",
    "title",
    "desc",
    "metadata",
    "script",
}
_SHAPE_TAGS = {"rect", "circle", "ellipse", "polygon", "polyline", "path", "line", "image", "use"}
_INHERITED = {
    "fill",
    "stroke",
    "color",
    "font-size",
    "stroke-dasharray",
    "stroke-width",
    "fill-opacity",
    "visibility",
    "text-anchor",
}
_BLOCK_HTML = {
    "p",
    "div",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "td",
    "th",
    "pre",
    "table",
    "ul",
    "ol",
    "tr",
    "tbody",
    "thead",
    "blockquote",
}
_PRESENTATION = (
    "fill",
    "stroke",
    "color",
    "font-size",
    "stroke-dasharray",
    "stroke-width",
    "opacity",
    "fill-opacity",
    "visibility",
    "marker-start",
    "marker-end",
    "display",
    "text-anchor",
)
_NAMED_COLOURS = {
    "white": WHITE,
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "purple": (128, 0, 128),
    "navy": (0, 0, 128),
    "teal": (0, 128, 128),
    "silver": (192, 192, 192),
}

Colour = tuple[int, int, int]
Box = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(frozen=True)
class TextLine:
    text: str
    x: float
    y: float
    font_size: float | None
    colour: Colour | None
    opacity: float
    group: tuple[int, ...]
    order: int
    box: Box
    unit: int  # lines of one foreignObject share a unit; overlap is judged between units


@dataclass(frozen=True)
class Shape:
    tag: str
    geometry: str
    fill: Colour | None
    fill_alpha: float
    stroke: Colour | None
    stroke_width: float
    dashed: str
    icon: str | None
    box: Box
    group: tuple[int, ...]
    order: int

    @property
    def visible(self) -> bool:
        return (
            self.fill is not None
            or (self.stroke is not None and self.stroke_width > 0)
            or self.icon is not None
        )

    @property
    def mark(self) -> tuple:
        """How the shape is drawn once colour is removed."""
        return (self.geometry, self.dashed, round(self.stroke_width, 1), self.icon)

    @property
    def drawing(self) -> tuple:
        """How the shape is drawn, colour included."""
        return (*self.mark, self.fill, round(self.fill_alpha, 2), self.stroke)


@dataclass(frozen=True)
class Arrow:
    group: tuple[int, ...]
    heads: int
    stroke: Colour | None
    stroke_width: float
    dashed: str
    box: Box
    label: str


@dataclass(frozen=True)
class Block:
    """What one drawn element shows: its text lines and its shapes."""

    group: tuple[int, ...]
    lines: tuple[TextLine, ...]
    shapes: tuple[Shape, ...]

    @property
    def text(self) -> str:
        return normalise(" ".join(line.text for line in self.lines))

    @property
    def mark(self) -> tuple:
        return tuple(sorted(shape.mark for shape in self.shapes if shape.visible))

    @property
    def drawing(self) -> tuple:
        return tuple(sorted((shape.drawing for shape in self.shapes if shape.visible), key=repr))


@dataclass
class Render:
    path: Path
    width: float
    height: float
    scale: float  # intrinsic pixels per user unit
    canvas: Colour | None
    canvas_order: int
    lines: list[TextLine] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    def rendered_text_height(self, line: TextLine) -> float:
        """Font size in intrinsic pixels, scaled down to the reference embed width."""
        return (line.font_size or 0.0) * self.scale * min(1.0, REFERENCE_EMBED_WIDTH / self.width)

    @property
    def text(self) -> str:
        return normalise(" ".join(line.text for line in self.lines))

    @functools.cached_property
    def legend_region(self) -> Box | None:
        for line in self.lines:
            if normalise(line.text).casefold().rstrip(":") in LEGEND_HEADINGS:
                boxes = [s.box for s in self.shapes if _within(s.group, line.group) and s.visible]
                boxes += [other.box for other in self.lines if _within(other.group, line.group)]
                return _union(boxes)
        return None

    def in_legend(self, box: Box) -> bool:
        region = self.legend_region
        if region is None:
            return False
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]

    @property
    def legend_lines(self) -> list[TextLine]:
        return [line for line in self.lines if self.in_legend(line.box)]

    @property
    def legend_shapes(self) -> list[Shape]:
        return [
            s
            for s in self.shapes
            if s.visible and self.in_legend(s.box) and s.box != self.legend_region
        ]

    @property
    def legend_arrows(self) -> list[Arrow]:
        return [a for a in self.arrows if self.in_legend(a.box)]

    @property
    def relationship_arrows(self) -> list[Arrow]:
        """Arrows of the view itself, legend samples excluded."""
        return [a for a in self.arrows if not self.in_legend(a.box)]

    def element_block(self, name: str) -> Block | None:
        """The innermost group outside the legend whose own lines spell `name`."""
        wanted = normalise(name).casefold()
        arrow_groups = {a.group for a in self.arrows}
        candidates: list[Block] = []
        for group in sorted({line.group for line in self.lines}, key=len, reverse=True):
            if group in arrow_groups:
                continue
            own = [
                line for line in self.lines if line.group == group and not self.in_legend(line.box)
            ]
            if _spells(own, wanted):
                shapes = tuple(
                    s
                    for s in self.shapes
                    if _within(s.group, group) and s.order != self.canvas_order
                )
                candidates.append(Block(group, tuple(own), shapes))
        return candidates[0] if candidates else None

    def backdrops(self, line: TextLine) -> list[Colour]:
        """The surface colour(s) directly behind a text line, composited in paint order."""
        cx, cy = (line.box[0] + line.box[2]) / 2, (line.box[1] + line.box[3]) / 2
        bases = [self.canvas] if self.canvas is not None else [WHITE, NEAR_BLACK]
        covering = [
            s
            for s in self.shapes
            if s.fill is not None
            and s.order < line.order
            and s.order != self.canvas_order
            and s.box[0] <= cx <= s.box[2]
            and s.box[1] <= cy <= s.box[3]
        ]
        result = []
        for base in bases:
            colour = base
            for shape in sorted(covering, key=lambda s: s.order):
                colour = blend(shape.fill, shape.fill_alpha, colour)
            result.append(colour)
        return result

    def canvases(self) -> list[Colour]:
        return [self.canvas] if self.canvas is not None else [WHITE, NEAR_BLACK]


def read_render(path: Path) -> Render:
    return _read(str(path), path.stat().st_mtime_ns)


@functools.cache
def _read(path: str, _mtime: int) -> Render:
    root = ET.parse(path).getroot()
    rules = _css_rules(root)
    width, height, vb = _root_size(root)
    render = Render(Path(path), width, height, width / vb[2] if vb[2] else 1.0, None, -1)
    _Walker(render, rules).walk(root, {}, (0.0, 0.0), (), 1.0)
    _find_canvas(render, vb)
    return render


# ── text and colour helpers ────────────────────────────────────────────────────


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def luminance(colour: Colour) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Colour, b: Colour) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def blend(top: Colour, alpha: float, bottom: Colour) -> Colour:
    return tuple(round(t * alpha + b * (1 - alpha)) for t, b in zip(top, bottom, strict=True))  # type: ignore[return-value]


def boxes_overlap(a: Box, b: Box, tolerance: float = 1.0) -> bool:
    return (
        min(a[2], b[2]) - max(a[0], b[0]) > tolerance
        and min(a[3], b[3]) - max(a[1], b[1]) > tolerance
    )


def parse_colour(value: str | None) -> Colour | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value in ("", "none", "transparent"):
        return None
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits[:3])
        if len(digits) >= 6:
            try:
                return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
            except ValueError:
                return None
    match = re.match(r"rgba?\(([^)]*)\)", value)
    if match:
        parts = [p.strip() for p in re.split(r"[,\s/]+", match.group(1)) if p.strip()]
        try:
            return tuple(
                round(float(p.rstrip("%")) * (2.55 if p.endswith("%") else 1)) for p in parts[:3]
            )  # type: ignore[return-value]
        except ValueError:
            return None
    return _NAMED_COLOURS.get(value)


def _alpha_of(value: str | None) -> float:
    if value is None:
        return 1.0
    value = value.strip().lower()
    match = re.match(r"rgba\(([^)]*)\)", value)
    if match:
        parts = [p for p in re.split(r"[,\s/]+", match.group(1)) if p]
        if len(parts) == 4:
            return float(parts[3].rstrip("%")) / (100 if parts[3].endswith("%") else 1)
    if value.startswith("#") and len(value) in (5, 9):
        return int(value[-2:] if len(value) == 9 else value[-1] * 2, 16) / 255
    return 1.0


def _spells(lines: list[TextLine], wanted: str) -> bool:
    texts = [normalise(line.text).casefold() for line in lines]
    for start in range(len(texts)):
        joined = ""
        for end in range(start, len(texts)):
            joined = f"{joined} {texts[end]}".strip()
            if joined == wanted:
                return True
            if not wanted.startswith(joined):
                break
    return False


def _within(group: tuple[int, ...], ancestor: tuple[int, ...]) -> bool:
    return group[: len(ancestor)] == ancestor


def _union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


# ── markup traversal ───────────────────────────────────────────────────────────


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)", value)
    return float(match.group(1)) if match else default


def _root_size(root: ET.Element) -> tuple[float, float, tuple[float, float, float, float]]:
    vb_raw = root.get("viewBox")
    vb = tuple(float(v) for v in re.split(r"[\s,]+", vb_raw.strip())) if vb_raw else None
    width = (
        _number(root.get("width"), 0.0)
        if root.get("width") and "%" not in root.get("width", "")
        else 0.0
    )
    height = (
        _number(root.get("height"), 0.0)
        if root.get("height") and "%" not in root.get("height", "")
        else 0.0
    )
    if vb is None:
        vb = (0.0, 0.0, width, height)
    return (width or vb[2], height or vb[3], vb)  # type: ignore[return-value]


def _css_rules(root: ET.Element) -> list[tuple[frozenset[str], dict[str, str]]]:
    text = " ".join((el.text or "") for el in root.iter() if _local(el.tag) == "style")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"@font-face\s*\{[^}]*\}", "", text)
    text = re.sub(r"@media[^{]*\{((?:[^{}]*\{[^}]*\})*)\s*\}", r"\1", text)
    rules = []
    for selectors, body in re.findall(r"([^{}]+)\{([^}]*)\}", text):
        decls = _declarations(body)
        for selector in selectors.split(","):
            last = selector.strip().split()[-1] if selector.strip() else ""
            classes = frozenset(re.findall(r"\.([\w-]+)", last))
            if classes:
                rules.append((classes, decls))
    return rules


def _declarations(body: str) -> dict[str, str]:
    decls = {}
    for part in body.split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            decls[key.strip().lower()] = value.strip()
    return decls


def _translate(transform: str | None) -> tuple[float, float]:
    if not transform:
        return (0.0, 0.0)
    dx = dy = 0.0
    for args in re.findall(r"translate\(([^)]*)\)", transform):
        nums = [float(n) for n in re.split(r"[\s,]+", args.strip()) if n]
        dx += nums[0] if nums else 0.0
        dy += nums[1] if len(nums) > 1 else 0.0
    return (dx, dy)


class _Walker:
    def __init__(self, render: Render, rules: list) -> None:
        self.render = render
        self.rules = rules
        self.order = 0
        self.unit = 0
        self.groups = 0

    def style(self, el: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
        computed = {k: v for k, v in inherited.items() if k in _INHERITED or k.startswith("--")}
        for attr in _PRESENTATION:
            if el.get(attr) is not None:
                computed[attr] = el.get(attr)  # type: ignore[assignment]
        classes = set((el.get("class") or "").split())
        for selector_classes, decls in self.rules:
            if selector_classes <= classes:
                computed.update(decls)
        computed.update(_declarations(el.get("style") or ""))
        return {key: _resolve_var(value, computed) for key, value in computed.items()}

    def next_order(self) -> int:
        self.order += 1
        return self.order

    def walk(
        self,
        el: ET.Element,
        inherited: dict,
        offset: tuple[float, float],
        group: tuple[int, ...],
        alpha: float,
        depth: int = 0,
    ) -> None:
        tag = _local(el.tag)
        if tag in _SKIP_TAGS:
            return
        style = self.style(el, inherited)
        if style.get("display") == "none" or style.get("visibility") == "hidden":
            return
        alpha *= _number(style.get("opacity"), 1.0)
        dx, dy = _translate(el.get("transform"))
        offset = (offset[0] + dx, offset[1] + dy)
        if tag == "svg" and depth > 0:
            vb = el.get("viewBox")
            nums = [float(v) for v in re.split(r"[\s,]+", vb.strip())] if vb else [0.0, 0.0]
            offset = (
                offset[0] + _number(el.get("x")) - nums[0],
                offset[1] + _number(el.get("y")) - nums[1],
            )
        if tag in _SHAPE_TAGS:
            self.shape(el, tag, style, offset, group, alpha)
        elif tag == "text":
            self.text(el, style, offset, group, alpha)
        elif tag == "foreignObject":
            self.foreign(el, style, offset, group, alpha)
        else:
            if tag == "g":
                self.groups += 1
                group = group + (self.groups,)
            for child in el:
                self.walk(child, style, offset, group, alpha, depth + 1)

    def shape(
        self,
        el: ET.Element,
        tag: str,
        style: dict,
        offset: tuple[float, float],
        group: tuple,
        alpha: float,
    ) -> None:
        box = _shape_box(el, tag, offset)
        if box is None:
            return
        default_fill = "none" if tag in ("line", "polyline", "image", "use") else "black"
        fill_raw = style.get("fill", default_fill)
        fill = parse_colour(fill_raw)
        stroke = parse_colour(style.get("stroke"))
        stroke_width = _number(style.get("stroke-width"), 1.0) if stroke is not None else 0.0
        dash = (style.get("stroke-dasharray") or "none").strip()
        dashed = (
            "solid" if dash in ("none", "0", "") else ("dotted" if _is_dotted(dash) else "dashed")
        )
        heads = sum(
            1 for key in ("marker-start", "marker-end") if style.get(key) not in (None, "", "none")
        )
        order = self.next_order()
        if heads and tag in ("path", "line", "polyline"):
            self.render.arrows.append(Arrow(group, heads, stroke, stroke_width, dashed, box, ""))
            return
        if tag == "path" and fill is not None and not _closed_path(el.get("d") or ""):
            fill = None
        fill_alpha = _number(style.get("fill-opacity"), 1.0) * alpha * _alpha_of(fill_raw)
        icon = None
        if tag in ("image", "use"):
            href = el.get("href") or el.get("{http://www.w3.org/1999/xlink}href") or ""
            icon = f"data:{len(href)}" if href.startswith("data:") else href[:96]
        self.render.shapes.append(
            Shape(
                tag,
                _geometry(el, tag),
                fill,
                fill_alpha,
                stroke,
                stroke_width,
                dashed,
                icon,
                box,
                group,
                order,
            )
        )

    def text(
        self, el: ET.Element, style: dict, offset: tuple[float, float], group: tuple, alpha: float
    ) -> None:
        x = _number(el.get("x")) + offset[0]
        y = _number(el.get("y")) + offset[1]
        tspans = [child for child in el if _local(child.tag) == "tspan"]
        if not tspans:
            self.add_line("".join(el.itertext()), x, y, style, group, alpha)
            return
        if (el.text or "").strip():
            self.add_line(el.text or "", x, y, style, group, alpha)
        line_y = y
        for span in tspans:
            span_style = self.style(span, style)
            span_x = _number(span.get("x")) + offset[0] if span.get("x") else x
            if span.get("y"):
                line_y = _number(span.get("y")) + offset[1]
            dy_raw = span.get("dy") or ""
            em = (_font_size(span_style) or 0.0) if "em" in dy_raw else 1.0
            line_y += _number(dy_raw, 0.0) * em
            self.add_line("".join(span.itertext()), span_x, line_y, span_style, group, alpha)

    def add_line(
        self, text: str, x: float, y: float, style: dict, group: tuple, alpha: float
    ) -> None:
        if not normalise(text):
            return
        size = _font_size(style)
        estimate = size or 12.0
        width = 0.45 * estimate * len(normalise(text))
        anchor = style.get("text-anchor") or "start"
        x0 = x - width / 2 if anchor == "middle" else (x - width if anchor == "end" else x)
        box = (x0, y - 0.7 * estimate, x0 + width, y + 0.15 * estimate)
        opacity = alpha * _number(style.get("fill-opacity"), 1.0)
        self.unit += 1
        self._attach_label(group, text)
        self.render.lines.append(
            TextLine(
                normalise(text),
                x,
                y,
                size,
                parse_colour(style.get("fill")),
                opacity,
                group,
                self.next_order(),
                box,
                self.unit,
            )
        )

    def _attach_label(self, group: tuple, text: str) -> None:
        arrows = self.render.arrows
        for index in range(len(arrows) - 1, -1, -1):
            arrow = arrows[index]
            if arrow.group == group:
                label = normalise(f"{arrow.label} {text}")
                arrows[index] = Arrow(
                    arrow.group,
                    arrow.heads,
                    arrow.stroke,
                    arrow.stroke_width,
                    arrow.dashed,
                    arrow.box,
                    label,
                )
                return

    def foreign(
        self, el: ET.Element, style: dict, offset: tuple[float, float], group: tuple, alpha: float
    ) -> None:
        x = _number(el.get("x")) + offset[0]
        y = _number(el.get("y")) + offset[1]
        box = (x, y, x + _number(el.get("width")), y + _number(el.get("height")))
        self.unit += 1
        for node, node_style in self._html_blocks(el, style):
            text = normalise("".join(node.itertext()))
            if not text:
                continue
            colour = parse_colour(node_style.get("color") or node_style.get("fill"))
            self._attach_label(group, text)
            self.render.lines.append(
                TextLine(
                    text,
                    x,
                    y,
                    _font_size(node_style),
                    colour,
                    alpha,
                    group,
                    self.next_order(),
                    box,
                    self.unit,
                )
            )

    def _html_blocks(self, el: ET.Element, style: dict):
        """Innermost block-level HTML elements, with their resolved style."""
        pending = [(child, self.style(child, style)) for child in el]
        while pending:
            node, node_style = pending.pop(0)
            nested_blocks = [c for c in node if _local(c.tag) in _BLOCK_HTML]
            if not nested_blocks:
                yield node, node_style
                continue
            pending[0:0] = [(child, self.style(child, node_style)) for child in node]


def _resolve_var(value: str, computed: dict[str, str]) -> str:
    for _ in range(4):
        match = re.search(r"var\((--[\w-]+)(?:\s*,\s*([^)]*))?\)", value)
        if not match:
            break
        value = value.replace(match.group(0), computed.get(match.group(1), match.group(2) or ""))
    return value


def _font_size(style: dict) -> float | None:
    raw = style.get("font-size")
    if raw is None:
        return None
    raw = raw.strip().lower()
    if raw.endswith("pt"):
        return _number(raw) * 4 / 3
    if raw.endswith("em") or raw.endswith("rem"):
        return _number(raw) * 16
    if raw.endswith("%"):
        return _number(raw) * 16 / 100
    value = _number(raw, -1.0)
    return value if value > 0 else None


def _is_dotted(dash: str) -> bool:
    nums = [float(n) for n in re.findall(r"[\d.]+", dash)]
    return bool(nums) and nums[0] <= 2.0


def _closed_path(d: str) -> bool:
    return "z" in d.lower()


def _geometry(el: ET.Element, tag: str) -> str:
    if tag == "rect":
        return "rounded-rect" if _number(el.get("rx")) > 0 or _number(el.get("ry")) > 0 else "rect"
    if tag in ("circle", "ellipse"):
        return "ellipse"
    if tag in ("polygon", "polyline"):
        pairs = re.findall(r"[-\d.]+[\s,]+[-\d.]+", el.get("points") or "")
        return f"{tag}{len(pairs)}"
    if tag == "path":
        return "path:" + re.sub(r"[^A-Za-z]", "", el.get("d") or "").upper()
    return tag


def _shape_box(el: ET.Element, tag: str, offset: tuple[float, float]) -> Box | None:
    ox, oy = offset
    if tag in ("rect", "image", "use"):
        x, y = _number(el.get("x")) + ox, _number(el.get("y")) + oy
        return (x, y, x + _number(el.get("width")), y + _number(el.get("height")))
    if tag == "circle":
        cx, cy, r = _number(el.get("cx")) + ox, _number(el.get("cy")) + oy, _number(el.get("r"))
        return (cx - r, cy - r, cx + r, cy + r)
    if tag == "ellipse":
        cx, cy = _number(el.get("cx")) + ox, _number(el.get("cy")) + oy
        rx, ry = _number(el.get("rx")), _number(el.get("ry"))
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    if tag == "line":
        xs = [_number(el.get("x1")) + ox, _number(el.get("x2")) + ox]
        ys = [_number(el.get("y1")) + oy, _number(el.get("y2")) + oy]
        return (min(xs), min(ys), max(xs), max(ys))
    if tag in ("polygon", "polyline"):
        nums = [float(n) for n in re.findall(r"-?[\d.]+(?:e-?\d+)?", el.get("points") or "")]
        return _points_box(nums, ox, oy)
    if tag == "path":
        return _path_box(el.get("d") or "", ox, oy)
    return None


def _points_box(nums: list[float], ox: float, oy: float) -> Box | None:
    xs, ys = nums[0::2], nums[1::2]
    if not xs or not ys:
        return None
    return (min(xs) + ox, min(ys) + oy, max(xs) + ox, max(ys) + oy)


def _path_box(d: str, ox: float, oy: float) -> Box | None:
    xs: list[float] = []
    ys: list[float] = []
    cx = cy = 0.0
    for cmd, args in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d):
        nums = [float(n) for n in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", args)]
        relative = cmd.islower()
        upper = cmd.upper()
        if upper == "H":
            for n in nums:
                cx = cx + n if relative else n
                xs.append(cx)
                ys.append(cy)
        elif upper == "V":
            for n in nums:
                cy = cy + n if relative else n
                xs.append(cx)
                ys.append(cy)
        elif upper == "A":
            for i in range(0, len(nums) - 6, 7):
                cx = cx + nums[i + 5] if relative else nums[i + 5]
                cy = cy + nums[i + 6] if relative else nums[i + 6]
                xs.append(cx)
                ys.append(cy)
        elif upper != "Z":
            step = {"M": 2, "L": 2, "T": 2, "C": 6, "S": 4, "Q": 4}[upper]
            for i in range(0, len(nums) - step + 1, step):
                chunk = nums[i : i + step]
                base_x, base_y = (cx, cy) if relative else (0.0, 0.0)
                for j in range(0, step, 2):
                    xs.append(base_x + chunk[j])
                    ys.append(base_y + chunk[j + 1])
                cx, cy = base_x + chunk[-2], base_y + chunk[-1]
    if not xs:
        return None
    return (min(xs) + ox, min(ys) + oy, max(xs) + ox, max(ys) + oy)


def _find_canvas(render: Render, vb: tuple) -> None:
    """The first filled shape spanning the whole drawing is the canvas."""
    x0, y0, w, h = vb
    for shape in sorted(render.shapes, key=lambda s: s.order):
        b = shape.box
        spans = b[2] - b[0] >= w * 0.98 and b[3] - b[1] >= h * 0.98
        if spans and shape.fill is not None and shape.fill_alpha >= 0.99:
            render.canvas = shape.fill
            render.canvas_order = shape.order
            return
