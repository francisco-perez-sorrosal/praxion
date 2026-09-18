#!/usr/bin/env python3
"""SessionStart hook: re-orient a window the harness has just compacted.

Praxion never triggers compaction itself, so this hook only ever runs after an
event Praxion did not choose -- the harness reaching its own default ceiling, a
threshold the operator set, or a manual `/compact`. By then the window's
judgement state is already gone and cannot be recovered. What can still be done
is stop the surviving session from wandering, by naming where the work is: this
repairs orientation, never continuity. Continuity is the handoff's job, which is
why an existing `HANDOFF.md` is named *first* in the pointer set -- a window that
reads the plan first re-derives exactly what the handoff was written to hand it,
and misses the operating constraints that live nowhere else on disk.

Behavior contract:
- Exactly one stdin field is read, ``source``. Every other payload field is
  treated as untrusted and possibly absent: the orientation is derived from the
  filesystem alone, so an undocumented payload shape cannot break it. The read
  is belt-and-braces alongside the ``matcher: "compact"`` registration.
- Two output states, never a partial third: nothing on stdout + exit 0, or one
  ``additionalContext`` envelope + exit 0. Any failure at all -- no `.ai-work/`,
  no task directory, an unreadable or unparseable document, any exception --
  degrades to the former.
- The block is capped at ``MAX_CONTEXT_BYTES`` so the restore never becomes a
  context cost of the kind it exists to avoid.
- The block names no orchestration action anywhere -- in the hook's own wording,
  which carries none by construction, and in everything it quotes. Both lines
  taken from the step record are filtered against ``ORCHESTRATION_VERBS``: a
  directive-bearing next action is replaced by its location, and a
  directive-bearing step title is reduced to its bare identifier. So the same
  text is correct in a main window and in a subagent window.

Synchronous hook (``async: false`` -- an async hook drops ``additionalContext``
delivery), registered on ``SessionStart`` with ``matcher: "compact"``. Exit 0
unconditionally: a broken hook must never block or corrupt a post-compaction
turn.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The `.ai-work/` walk-up is the same one the pre-compaction snapshot performs;
# importing it keeps a single definition of "which pipeline tree am I in".
from precompact_state import _find_ai_work

# -- Constants ----------------------------------------------------------------

COMPACT_SOURCE = "compact"

# One ceiling, one marker: the restore is only worth having while it costs less
# than the documents it points at.
MAX_CONTEXT_BYTES = 1024
TRUNCATION_MARKER = "…[truncated]"

HEADER = "# Pipeline orientation (post-compaction)"

WIP_DOC = "WIP.md"
HANDOFF_DOC = "HANDOFF.md"

# Read order for the non-handoff pointers. The handoff, when present, is named
# ahead of all of these -- see the module docstring.
POINTER_DOCS = ("IMPLEMENTATION_PLAN.md", WIP_DOC, "SYSTEMS_PLAN.md")

CURRENT_STEP_HEADING = "current step"
NEXT_ACTION_HEADING = "next action"
UNCHECKED_ITEM_PREFIX = "- [ ]"

READINESS_PREFIX = "readiness:"
OVERRIDDEN_READINESS = "overridden"
HANDOFF_SCAN_LINES = 20

# Words that would make the block read as an instruction rather than a report.
# The hook's own wording carries none of them; this set is the enforcement point
# for both lines quoted from the step record, each of which a reader could act on.
ORCHESTRATION_VERBS = ("spawn", "proceed to verification", "commit")

# A step title's identifier ends at whichever of these comes first, so the
# position survives even when the rest of the title has to be withheld.
TITLE_SEPARATORS = (":", "—")
TITLE_WITHHELD_MARKER = "(title withheld: contains a directive)"


# -- Composition ---------------------------------------------------------------


def _compose_orientation(ai_work: Path) -> str:
    """Build the orientation block, or "" when there is no position to report."""
    task_dirs = _task_dirs(ai_work)
    if not task_dirs:
        return ""

    task_dir = _newest(task_dirs)
    wip_text = (task_dir / WIP_DOC).read_text(encoding="utf-8")
    current_step = _current_step(wip_text)
    if not current_step:
        return ""

    lines = [
        HEADER,
        "",
        f"Task slug: {task_dir.name}",
        f"Current step: {_position_label(current_step)}",
    ]
    lines.extend(_pointer_lines(task_dir))

    next_action_line = _next_action_line(wip_text)
    if next_action_line:
        lines.append(next_action_line)

    others = [other.name for other in task_dirs if other != task_dir]
    if others:
        lines.append(f"Other pipelines in .ai-work/: {', '.join(others)}")

    return _truncate("\n".join(lines))


def _pointer_lines(task_dir: Path) -> list[str]:
    """Name the documents to re-read, handoff first when one exists."""
    lines: list[str] = []

    handoff = task_dir / HANDOFF_DOC
    if handoff.exists():
        note = ""
        if _handoff_readiness(handoff) == OVERRIDDEN_READINESS:
            note = f" — readiness: {OVERRIDDEN_READINESS}, re-derive its position from the tree"
        lines.append(f"Read first: {_relative(handoff)}{note}")

    present = [task_dir / doc for doc in POINTER_DOCS if (task_dir / doc).exists()]
    if present:
        lines.append("Then on demand: " + ", ".join(_relative(doc) for doc in present))

    return lines


def _position_label(current_step: str) -> str:
    """The step as displayed: verbatim when verb-free, else its identifier only.

    A step *title* can borrow orchestration vocabulary -- an integration
    checkpoint whose title names the merge it ends with, say. The position is
    what the restored window needs and is safe to state in any window; the
    directive riding along in the title is not, and this block lands in subagent
    windows as readily as in the orchestrator's. So the identifier is kept and
    the rest of the title withheld, rather than dropping the line or quoting it
    whole.
    """
    if not _contains_orchestration_verb(current_step):
        return current_step
    return f"{_step_identifier(current_step)} {TITLE_WITHHELD_MARKER}".strip()


def _step_identifier(current_step: str) -> str:
    """The step title's leading identifier -- its text before the first separator.

    "" when the title has no separator, or when the identifier itself carries a
    directive: withholding the whole line is the safe direction to fail.
    """
    cuts = [current_step.index(sep) for sep in TITLE_SEPARATORS if sep in current_step]
    identifier = current_step[: min(cuts)].strip() if cuts else ""
    return "" if _contains_orchestration_verb(identifier) else identifier


def _next_action_line(wip_text: str) -> str:
    """The recorded next action, named by location when quoting it would direct.

    The next action is an instruction by construction, so nothing of it survives
    the filter -- unlike a step title, it has no position to preserve. The
    pointer line above always names the step record, so the fallback costs the
    reader one file read and never loses the information.
    """
    next_action = _section_first_line(wip_text, NEXT_ACTION_HEADING)
    if not next_action:
        return ""
    if _contains_orchestration_verb(next_action):
        return "Next action: see the step record named above"
    return f"Next action (recorded): {next_action}"


def _contains_orchestration_verb(text: str) -> bool:
    """True when quoting this text would make the block read as a directive."""
    lowered = text.lower()
    return any(verb in lowered for verb in ORCHESTRATION_VERBS)


def _truncate(block: str) -> str:
    """Cap the block at the byte ceiling, marking the cut explicitly.

    Decoding with ``errors="ignore"`` drops a multi-byte character the slice
    split, so the result is always valid UTF-8 within the ceiling.
    """
    encoded = block.encode("utf-8")
    if len(encoded) <= MAX_CONTEXT_BYTES:
        return block
    budget = MAX_CONTEXT_BYTES - len(TRUNCATION_MARKER.encode("utf-8"))
    return encoded[:budget].decode("utf-8", errors="ignore") + TRUNCATION_MARKER


# -- Filesystem ----------------------------------------------------------------


def _task_dirs(ai_work: Path) -> list[Path]:
    """Task directories holding a step record -- the only ones with a position.

    Sorted lexicographically, which is what makes `_newest`'s tie-break
    deterministic.
    """
    return sorted(
        task_dir
        for task_dir in ai_work.iterdir()
        if task_dir.is_dir() and not task_dir.name.startswith(".") and (task_dir / WIP_DOC).exists()
    )


def _newest(task_dirs: list[Path]) -> Path:
    """The task directory whose step record was written last.

    Exactly one pipeline is elaborated; the rest are named by slug only. `max`
    returns the first maximal element, so a tie resolves to the lexicographically
    smallest slug given an already-sorted input.
    """
    return max(task_dirs, key=lambda task_dir: (task_dir / WIP_DOC).stat().st_mtime)


def _relative(path: Path) -> str:
    """Path as written from the session's own directory, so it resolves as-is."""
    return os.path.relpath(path, Path.cwd())


def _handoff_readiness(handoff: Path) -> str:
    """The handoff header's readiness value, or "" when it carries none."""
    header = handoff.read_text(encoding="utf-8").splitlines()[:HANDOFF_SCAN_LINES]
    for line in header:
        stripped = line.strip().lower()
        if stripped.startswith(READINESS_PREFIX):
            return stripped[len(READINESS_PREFIX) :].strip()
    return ""


# -- Step-record parsing --------------------------------------------------------


def _current_step(wip_text: str) -> str:
    """The step in flight: the current-step section, else the first open item."""
    return _section_first_line(wip_text, CURRENT_STEP_HEADING) or _first_unchecked_item(wip_text)


def _section_first_line(text: str, heading: str) -> str:
    """First non-empty line under the named heading, or "" when absent."""
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            in_section = stripped.lstrip("#").strip().lower() == heading
            continue
        if in_section and stripped:
            return stripped
    return ""


def _first_unchecked_item(text: str) -> str:
    """First unchecked progress item, or "" when the record has none."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(UNCHECKED_ITEM_PREFIX):
            return stripped[len(UNCHECKED_ITEM_PREFIX) :].strip()
    return ""


# -- Payload and emit -----------------------------------------------------------


def _payload_source(raw: str) -> str:
    """The payload's `source`, or "" for empty, malformed, or non-object input."""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    source = payload.get("source") if isinstance(payload, dict) else None
    return source if isinstance(source, str) else ""


def _emit_additional_context(context: str) -> None:
    """Emit the block in the structured SessionStart envelope."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


def main() -> None:
    # One handler for the whole body, by contract: every failure path -- an
    # unreadable document, an unexpected payload, an exception this code does
    # not anticipate -- collapses to the same no-output state. A traceback on
    # stdout would corrupt the very turn this hook exists to help.
    try:
        raw = sys.stdin.read()
        if _payload_source(raw) != COMPACT_SOURCE:
            return

        ai_work = _find_ai_work()
        if ai_work is None:
            return

        block = _compose_orientation(ai_work)
        if block:
            _emit_additional_context(block)
    except Exception:
        pass


if __name__ == "__main__":
    main()
