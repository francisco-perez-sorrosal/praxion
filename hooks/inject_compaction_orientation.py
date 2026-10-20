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

Loop mode: when the newest task is under the step-loop driver (its `WIP.md` names a
driver-issued request, or it has an `ITERATION_LEDGER.jsonl`), the step record's
current-step and next-action lines are stale by construction, so the block reports the
driver's own position instead, read from its read-only `status --json`. An unreadable
position is said to be unreadable and names the status command; it never falls back to
the stale lines. Outside a loop the block is unchanged byte for byte and no process
starts. Loop mode narrows the role-neutral clause of dec-387: the block now names the
driver's record command for an outstanding request, attributed to the driver and with its
placeholders kept. The command is harmless in a subagent window, where `record` refuses a
running agent.

Synchronous hook (``async: false`` -- an async hook drops ``additionalContext``
delivery), registered on ``SessionStart`` with ``matcher: "compact"``. Exit 0
unconditionally: a broken hook must never block or corrupt a post-compaction
turn.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
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

# -- Loop mode ----------------------------------------------------------------

ITERATION_LEDGER = "ITERATION_LEDGER.jsonl"
DRIVER_REQUEST_LINE = re.compile(r"^\s*-\s*Attempts:.*\brequest=", re.MULTILINE)

# The driver's own relative path; the plugin root is `CLAUDE_PLUGIN_ROOT`, else this tree.
DRIVER_RELATIVE = Path("scripts") / "step_loop.py"
STATUS_TIMEOUT_SECONDS = 6  # under the hook's registered 10 s

# Mirrors `ATTEMPT_CAP` in scripts/_loop_fields.py (the status object does not carry the
# cap); a parity test in test_orientation_loop_mode.py keeps the two equal.
ATTEMPT_CAP = 2


# -- Composition ---------------------------------------------------------------


def _compose_orientation(ai_work: Path) -> str:
    """Build the orientation block, or "" when there is no position to report."""
    task_dirs = _task_dirs(ai_work)
    if not task_dirs:
        return ""

    task_dir = _newest(task_dirs)
    wip_text = (task_dir / WIP_DOC).read_text(encoding="utf-8")
    if _under_the_driver(task_dir, wip_text):
        return _compose_loop_orientation(ai_work, task_dirs, task_dir)
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

    lines.extend(_other_pipelines_lines(task_dirs, task_dir))

    return _truncate("\n".join(lines))


def _compose_loop_orientation(ai_work: Path, task_dirs: list[Path], task_dir: Path) -> str:
    """The block for a task under the driver: its position, never the step record's."""
    lines = [HEADER, "", f"Task slug: {task_dir.name}"]
    lines.extend(_pointer_lines(task_dir))
    lines.extend(_position_lines(task_dir.name, ai_work.parent))
    lines.extend(_other_pipelines_lines(task_dirs, task_dir))
    return _truncate("\n".join(lines))


def _other_pipelines_lines(task_dirs: list[Path], task_dir: Path) -> list[str]:
    """The other pipelines, named by slug only."""
    others = [other.name for other in task_dirs if other != task_dir]
    return [f"Other pipelines in .ai-work/: {', '.join(others)}"] if others else []


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


# -- The driver's position ------------------------------------------------------


STOPPED_OUTCOMES = ("needs-human", "budget-exhausted")


@dataclass(frozen=True)
class DriverPosition:
    """What `status --json` says, parsed once at the boundary; the rest trusts it."""

    outcome: str
    step: str | None
    verdict: str
    attempts: int
    used: int
    budget: int
    cause: str | None
    request: str | None
    then: str | None

    @classmethod
    def parse(cls, doc: object) -> DriverPosition:
        """Raise on any shape the driver does not print; the caller maps that to unreadable."""
        if not isinstance(doc, dict):
            raise TypeError("status --json is not an object")
        step_id = doc["selected_step"]
        row = next((r for r in doc["steps"] if r["step"] == step_id), None)
        stop = doc["stop"]
        position = cls(
            outcome=str(doc["outcome"]),
            step=None if step_id is None else str(step_id),
            verdict=str(row["verdict"]) if row else "",
            attempts=int(row["attempts"]) if row else 0,
            used=int(doc["iterations"]["used"]),
            budget=int(doc["iterations"]["budget"]),
            cause=None if stop is None else str(stop["cause"]),
            request=doc["pending_request"],
            then=doc["then"],
        )
        if position.request is not None and not position.then:
            raise ValueError("an outstanding request without its record command")
        return position

    def lines(self) -> list[str]:
        """At most two lines: the position, then the outstanding request when there is one."""
        iterations = f"iterations {self.used}/{self.budget}"
        if self.outcome == "complete":
            return [f"Driver position: complete, {iterations}"]
        step = f"step {self.step}" if self.step else "no step"
        if self.outcome in STOPPED_OUTCOMES:
            return [f"Driver position: stopped at {step} (cause: {self.cause}), {iterations}"]
        position = (
            f"Driver position: {step} {self.verdict}, "
            f"attempts {self.attempts}/{ATTEMPT_CAP}, {iterations}"
        )
        if self.request is None:
            return [position]
        return [position, f"Outstanding request {self.request}; driver's command: {self.then}"]


def _under_the_driver(task_dir: Path, wip_text: str) -> bool:
    """A cheap file test, no process: a driver-issued request or an iteration ledger."""
    return bool(DRIVER_REQUEST_LINE.search(wip_text)) or (task_dir / ITERATION_LEDGER).exists()


def _position_lines(slug: str, root: Path) -> list[str]:
    """The driver's position in at most two lines; each line that would direct is
    replaced by its location, and an unreadable position says so."""
    status_command = f"step_loop.py status {slug}"
    position = _read_position(slug, root)
    if position is None:
        return [f"Driver position: could not be read; run {status_command}"]
    return [
        f"Driver position: see {status_command}" if _contains_orchestration_verb(line) else line
        for line in position.lines()
    ]


def _read_position(slug: str, root: Path) -> DriverPosition | None:
    """Run the driver's read-only status and parse it, whatever its exit code (2 is a
    stop); None when it is absent, fails, runs past its bound or prints what cannot be parsed."""
    plugin_root = Path(
        os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent
    )
    command = [
        "python3",
        str(plugin_root / DRIVER_RELATIVE),
        "status",
        slug,
        "--json",
        "--worktree-root",
        str(root),
    ]
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=root,
            timeout=STATUS_TIMEOUT_SECONDS,
        )
        return DriverPosition.parse(json.loads(done.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


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
