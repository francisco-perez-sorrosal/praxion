"""The one reader of a `resident_of:` frontmatter key.

A path-scoped rule may keep a one-line projection of itself that stays always loaded; the
projection declares which rule it stands for with `resident_of: <repository-relative path>`.
The kernel tooling asks here to treat such a file as a projection, not an independent source. The
Cursor exporter and the Codex bridge check the key themselves, so they still run from a copy that
carries their own directory alone; parity tests hold both checks equal to this reader.

Stdlib-only and Python 3.9-safe.
"""

from __future__ import annotations

import re

_DELIMITER = "---"
_KEY = re.compile(r"""^["']?resident_of["']?\s*:\s*(.*?)\s*$""")  # top level only: no leading space
_QUOTES = "\"'"


def resident_parent(text: str) -> str | None:
    """The rule path a file's frontmatter names in `resident_of`, or None when it names none."""
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != _DELIMITER:
        return None
    closing = next((i for i in range(1, len(lines)) if lines[i].rstrip() == _DELIMITER), None)
    if closing is None:  # never closed: not frontmatter
        return None
    for line in lines[1:closing]:
        match = _KEY.match(line)
        if match:
            return match.group(1).strip(_QUOTES) or None
    return None
