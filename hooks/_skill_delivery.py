"""The one owner of the skill-delivery decision: whether a delegation is served the refactoring skill.

The marker grammar is not defined here. It is the plan reader's `REFACTORING_TAG_PATTERN` in
`scripts/_plan_steps.py`, re-exported below as `MARKER_PATTERN`, so a plan step and a delegation
are matched by the same compiled object and no second copy of the grammar can drift.

Stdlib-only and Python 3.9-safe, like the hook modules that import script modules. The `scripts`
directory is found the way `hooks/guard_decision_records.py` finds it: next to the hook in the
plugin, or one level up from a mutation sensor's copy.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

SCRIPTS_DIR = "scripts"

# The only agent types a delegation can be served the skill for; every other role, the verifier
# the step loop spawns included, is never judged for the marker.
SERVED_ROLES = frozenset({"praxion:implementer", "praxion:test-engineer"})

# Stands in for every removed span. It is neither whitespace nor part of the marker grammar, so
# the text on either side of a removed span can never join into a marker.
REMOVED = "\ufffc"

# A fence opens with three or more backticks (no backtick in its info string, or it is an inline
# span) or three or more tildes. Any indentation is accepted: a fence nests inside list items.
_FENCE_OPENING = re.compile(r"^\s*(?:(`{3,})[^`]*|(~{3,}).*)$")
_QUOTED_LINE = re.compile(r"^\s*>")
# A span opens on a backtick run and closes on a run of exactly the same length; an unmatched
# run stays literal text. It may span lines.
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)


def _scripts_dir() -> Path:
    """The `scripts` directory that ships beside this hook: `../scripts` in the plugin."""
    hook_dir = Path(__file__).resolve().parent
    nearest, one_up = (root / SCRIPTS_DIR for root in (hook_dir.parent, hook_dir.parent.parent))
    return nearest if nearest.is_dir() else one_up


MARKER_PATTERN: re.Pattern[str] | None
MARKER_IMPORT_ERROR: str | None = None

try:
    # Appended, never inserted first: the script modules must not shadow the standard library.
    sys.path.append(str(_scripts_dir()))
    from _plan_steps import REFACTORING_TAG_PATTERN as MARKER_PATTERN
except Exception as error:  # fail-open: a broken installation degrades the delivery, never a spawn
    MARKER_PATTERN = None
    MARKER_IMPORT_ERROR = f"{type(error).__name__}: {error}"


# --- Verdict: what a delegation is judged to be --------------------------------------------------


@dataclass(frozen=True)
class NotServed:
    """The agent type is not one the skill is delivered to."""

    role: str


@dataclass(frozen=True)
class Unmarked:
    """A served role whose delegation carries no marker."""


@dataclass(frozen=True)
class OwnWords:
    """The route of a marker written in the delegation's own words."""


# Later routes join here as further members of this union.
Route = OwnWords


@dataclass(frozen=True)
class Marked:
    route: Route


UnresolvableReason = Literal["grammar-unavailable"]


@dataclass(frozen=True)
class Unresolvable:
    """A served role whose delegation cannot be classified, so the delivery must not guess."""

    reason: UnresolvableReason


# Union and Optional, not `|`: the hook modules run on Python 3.9, where `|` between classes
# fails at runtime in an alias like these.
Verdict = Union[NotServed, Unmarked, Marked, Unresolvable]  # noqa: UP007

# Reads the rendered request a step-loop pointer names; unused until that route exists.
RequestReader = Callable[[Path], Optional[str]]  # noqa: UP045


def classify(agent_type: str, prompt: str, read_request: RequestReader) -> Verdict:
    """Judge one delegation. Pure: its inputs are its arguments and the import-time `MARKER_PATTERN`.

    A broken installation (no grammar) is `Unresolvable` for a served role, never a guess either way.
    """
    if agent_type not in SERVED_ROLES:
        return NotServed(agent_type)
    if MARKER_PATTERN is None:
        return Unresolvable("grammar-unavailable")
    if MARKER_PATTERN.search(own_words(prompt)):
        return Marked(OwnWords())
    return Unmarked()


def own_words(prompt: str) -> str:
    """The prompt without fenced blocks, block-quoted lines and inline code spans.

    Quoted text (instructions, briefs, reviews that mention the marker) must not mark; nothing else
    is excluded, so a marker in plain prose marks.
    """
    return _INLINE_CODE.sub(REMOVED, _without_fenced_and_quoted_lines(prompt))


def _without_fenced_and_quoted_lines(prompt: str) -> str:
    kept = []
    open_fence = None
    for line in prompt.splitlines():
        if open_fence is not None:
            open_fence = None if _closes(open_fence, line) else open_fence
            kept.append(REMOVED)
            continue
        opening = _FENCE_OPENING.match(line)
        if opening:
            open_fence = opening.group(1) or opening.group(2)
        kept.append(REMOVED if opening or _QUOTED_LINE.match(line) else line)
    return "\n".join(kept)


def _closes(open_fence: str, line: str) -> bool:
    """A closing fence is a run of the opening character at least as long as the opening one.

    The length rule is what lets a longer outer fence enclose a shorter inner one.
    """
    run = line.strip()
    return len(run) >= len(open_fence) and set(run) == {open_fence[0]}
