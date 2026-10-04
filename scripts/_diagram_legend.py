"""The title block and the legend of a diagram, as D2 fields.

Pure: what a view draws (its drawings and line styles) in, D2 field mappings out.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from _diagram_tokens import (
    CANVAS,
    CATEGORY_RANK,
    EDGE_FONT_SIZE,
    EDGE_LABEL_INK,
    INK,
    LEGEND_STROKE,
    LINE_DRAWINGS,
    LINE_ORDER,
    UNCATEGORISED_NAME,
    LineDrawing,
    Token,
    quote,
)

TITLE_FONT_SIZE = 24
LEGEND_DOT = 8
LEGEND_COLUMNS = 3
# D2 pads a grid container by its gaps, so the vertical one is also the bottom margin.
LEGEND_HORIZONTAL_GAP = 56
# One width for every legend, so every render is as wide as the legend and a thin flow is not
# a strip: 1250 plus the canvas padding stays under the width at which 14 px text falls below 10.
LEGEND_WIDTH = 1250
LEGEND_VERTICAL_GAP = 12

LEGEND_KEY = "Legend"
TITLE_KEY = "Title"
FRAME_SUFFIX = " (boundary)"


@dataclass(frozen=True)
class LegendEntry:
    label: str
    drawing_class: str | None


def legend_selection(
    drawn: Iterable[Token], lines_used: Iterable[str]
) -> tuple[list[Token], list[LineDrawing]]:
    """Boxes in vocabulary order, then frames; the line drawings the view uses in their order."""
    unknown_rank = len(CATEGORY_RANK)

    def order(token: Token) -> tuple:
        last = token.category == UNCATEGORISED_NAME
        return (token.frame, last, CATEGORY_RANK.get(token.category, unknown_rank), token.category)

    used = set(lines_used)
    drawings = sorted(set(drawn), key=order)
    return drawings, [LINE_DRAWINGS[line] for line in LINE_ORDER if line in used]


def legend_entries_of(drawings: Sequence[Token], lines: Sequence[LineDrawing]) -> list[LegendEntry]:
    entries = [LegendEntry(_legend_label(token), token.drawing_class) for token in drawings]
    return entries + [LegendEntry(line.meaning, None) for line in lines]


def _legend_label(token: Token) -> str:
    return token.category + (FRAME_SUFFIX if token.frame else "")


def title_fields(text: str) -> dict:
    return {
        "label": quote(text),
        "shape": "text",
        "near": "top-center",
        "style": {"font-size": TITLE_FONT_SIZE, "bold": "true", "font-color": quote(INK)},
    }


def legend_fields(drawings: Sequence[Token], lines: Sequence[LineDrawing]) -> dict:
    """A grid of one sample per drawing, then one per line meaning."""
    fields: dict = {
        "label": quote(LEGEND_KEY),
        "near": "bottom-center",
        "grid-columns": LEGEND_COLUMNS,
        "width": LEGEND_WIDTH,
        "horizontal-gap": LEGEND_HORIZONTAL_GAP,
        "vertical-gap": LEGEND_VERTICAL_GAP,
        "style": {
            "fill": quote(CANVAS),
            "stroke": quote(LEGEND_STROKE),
            "stroke-width": 1,
            "font-color": quote(INK),
        },
    }
    for token in drawings:
        drawing_class = token.drawing_class
        fields[drawing_class] = {"label": quote(_legend_label(token)), "class": drawing_class}
    for line in lines:
        fields[f"{line.drawing_class}_sample"] = _line_sample(line)
    return fields


def _line_sample(line: LineDrawing) -> dict:
    """A dot and an unlabelled arrow ending at the meaning, left to right in its own cell.

    The meaning is the arrow's target and not its label, so the caption stays off the line.
    """
    dot = {
        "label": '""',
        "shape": "circle",
        "width": LEGEND_DOT,
        "height": LEGEND_DOT,
        "style": {"fill": quote(line.stroke), "stroke": quote(line.stroke)},
    }
    invisible = {"fill": "transparent", "stroke-width": 0}
    caption = {
        "label": quote(line.meaning),
        "style": {**invisible, "font-size": EDGE_FONT_SIZE, "font-color": quote(EDGE_LABEL_INK)},
    }
    return {
        "label": '""',
        "direction": "right",
        "style": invisible,
        "tail": dot,
        "caption": caption,
        "tail -> caption": {"class": line.drawing_class},
    }
