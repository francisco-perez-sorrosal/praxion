"""Driver for the Ralph-lite recipe as a reader finds it: by walking the tier selection.

A reader choosing a process opens the tier-selection text every session loads -- the
coordination protocol's process calibration -- and either finds the recipe there or
follows the link the text gives on the line that names it. This driver reads those
files as text, the way that reader does, and returns the recipe's section: from the
heading that names "Ralph-lite" to the next heading of the same or a higher level.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TIER_SELECTION_TEXT = REPO_ROOT / "rules" / "swe" / "swe-agent-coordination-protocol.md"
RECIPE_NAME = "Ralph-lite"

_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def selection_text() -> str:
    return TIER_SELECTION_TEXT.read_text(encoding="utf-8")


def lines_naming_the_recipe(text: str) -> list[str]:
    return [line for line in text.splitlines() if RECIPE_NAME.lower() in line.lower()]


def _section_named(text: str) -> str | None:
    lines = text.splitlines()
    for start, line in enumerate(lines):
        heading = _HEADING.match(line)
        if heading and RECIPE_NAME.lower() in heading.group(2).lower():
            level = len(heading.group(1))
            end = next(
                (
                    i
                    for i in range(start + 1, len(lines))
                    if (h := _HEADING.match(lines[i])) and len(h.group(1)) <= level
                ),
                len(lines),
            )
            return "\n".join(lines[start:end])
    return None


def recipe_section() -> str:
    """The recipe as the reader reaches it from the tier-selection text."""
    text = selection_text()
    in_place = _section_named(text)
    if in_place is not None:
        return in_place
    for line in lines_naming_the_recipe(text):
        for target in _LINK.findall(line):
            path = (TIER_SELECTION_TEXT.parent / target).resolve()
            if path.is_file():
                found = _section_named(path.read_text(encoding="utf-8"))
                if found is not None:
                    return found
    raise AssertionError(
        f"walking {TIER_SELECTION_TEXT.relative_to(REPO_ROOT)} reaches no section headed "
        f"{RECIPE_NAME!r}, in place or through a link on a line naming it"
    )
