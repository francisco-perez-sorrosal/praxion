"""What an implementation plan declares for each of its steps.

`parse_plan_steps` reads a plan's text into one frozen `PlanStep` per step. The
readers are pure -- text in, values out, no file opened, no command run -- so the
reconciler and the step-loop driver share one grammar for a plan.

Normative grammar of a step: a heading `##`-`####` `Step <id>` (digits and an
optional lowercase letter) opens it, and it runs to the line before the next
heading of the same or a shallower level, so prose between steps is never part
of one. Annotations sit in the heading and each field is one line under it, the
label optionally bold and case-insensitive; a line in a code fence is no field:

    ### Step <id>: <title> [depends-on: <id>, <id>] [parallel-group: <name>]
    **Assignee**: implementer
    **Read-only**: `tests/a.py`, `tests/b.py::test_x`

Any assignee but `implementer` (or none) is another assignee: the loop never runs
the step. A `tier: H` line routes to `opus`, else `sonnet`, never `haiku`; a
`review:` line reads `force` or `off`, else absent. A dependency that names no step, or a cycle,
is recorded as written: whoever selects a step reports it. `Read-only:` entries
are the backticked spans (a path, `path::function` or a node id) or, with no
backtick, the comma-separated words; each holds a `/` or `::`. A `contract:`
clause names a contract the step uses and never turns green, so it is no entry.

Normative grammar of the `Files:` field -- one logical line under a step
heading (or checklist step line), the label optionally bold, case-insensitive:

    **Files**: `scripts/a.py`, `scripts/b.py`

A value that wraps mid-list ends its line with a trailing comma; every further
line ending in a comma continues the same value, and a step heading or
checklist step line always closes it. A bare `none` or `n/a` declares zero
files. A candidate path is admitted only when it uses path-safe characters, holds
a `/` or `.`, has no trailing `/`, and is not a pointer into the pipeline's own
`.ai-work/` bookkeeping; parenthetical rationale is dropped before tokenizing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal, Union

from _loop_fields import CheckLine, parse_step_checks
from _step_schema import (
    STEP_ID_RE,
    StepBlock,
    checklist_step_id,
    split_step_blocks,
    step_id_from_heading,
)

DIGEST_LENGTH = 12
UNASSIGNED = "unassigned"

Routing = Literal["opus", "sonnet"]
ReviewOverride = Literal["force", "off", "absent"]


@dataclass(frozen=True)
class Implementer:
    """The step is the implementer's, so the step-loop driver runs it."""


@dataclass(frozen=True)
class OtherAssignee:
    """Any other assignee, by name (`unassigned` when the step names none)."""

    name: str


Assignee = Union[Implementer, OtherAssignee]  # noqa: UP007 -- runtime value, 3.9 floor


@dataclass(frozen=True)
class PlanStep:
    """One plan step as declared: the block verbatim and every field read from it.

    `digest` hashes `block`, so it changes when and only when the block's text
    does; the constructor refuses a digest or an id that breaks that.
    """

    id: str
    title: str
    block: str
    digest: str
    depends_on: tuple[str, ...]
    parallel_group: str | None
    assignee: Assignee
    routing: Routing
    review: ReviewOverride
    files: tuple[str, ...]
    read_only: tuple[str, ...]
    check: CheckLine | None

    def __post_init__(self) -> None:
        if STEP_ID_RE.match(self.id) is None:
            raise ValueError(f"not a step id: {self.id!r}")
        if self.digest != step_digest(self.block):
            raise ValueError("the digest is not the hash of the block")


def step_digest(block: str) -> str:
    """The hash that names a step block's exact text."""
    return hashlib.sha256(block.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def parse_plan_steps(plan_text: str) -> tuple[PlanStep, ...]:
    """Every step of a plan in document order (steps sharing an id are all kept)."""
    return tuple(
        _read_step(opening, opening.step)
        for opening in split_step_blocks(plan_text)
        if opening.step is not None
    )


def _read_step(opening: StepBlock, label: str) -> PlanStep:
    block, lines = _close_section(opening.text.splitlines())
    fields = _read_fields(lines)
    return PlanStep(
        id=label.split()[-1],
        title=_clean_title(opening.title),
        block=block,
        digest=step_digest(block),
        depends_on=_read_depends_on(opening.title),
        parallel_group=_read_parallel_group(opening.title),
        assignee=_read_assignee(fields),
        routing="opus" if _first_word(fields, "tier") == "h" else "sonnet",
        review=_REVIEW_WORDS.get(_first_word(fields, "review"), "absent"),
        files=tuple(scan_step_files("\n".join(lines)).get(label, [])),
        read_only=tuple(
            entry for value in fields.get("read-only", []) for entry in _node_entries(value)
        ),
        check=parse_step_checks(block).get(label),
    )


_HEADING_RE = re.compile(r"^(#{1,6})[ \t]")
_CODE_FENCE_RE = re.compile(r"^[ \t]{0,3}(```|~~~)")


def _close_section(lines: list[str]) -> tuple[str, list[str]]:
    """The block text and its lines outside code fences (the only ones read for fields)."""
    level = len(lines[0]) - len(lines[0].lstrip("#"))
    unfenced = [lines[0]]
    end = len(lines)
    fence: str | None = None
    for index, line in enumerate(lines[1:], start=1):
        marker = _CODE_FENCE_RE.match(line)
        heading = _HEADING_RE.match(line)
        if marker:
            fence = None if fence == marker.group(1) else (fence or marker.group(1))
        elif fence is None and heading and len(heading[1]) <= level:
            end = index
            break
        elif fence is None:
            unfenced.append(line)
    return "\n".join(lines[:end]).rstrip(), unfenced


_TITLE_PREFIX_RE = re.compile(r"^Step\s+\d+[a-z]?\b\s*:?\s*")
_DEPENDS_ON_RE = re.compile(r"\[depends-on:([^\]]*)\]", re.IGNORECASE)
_PARALLEL_GROUP_RE = re.compile(r"\[parallel-group:([^\]]*)\]", re.IGNORECASE)


def _clean_title(heading_title: str) -> str:
    """The title alone: no `Step <id>` prefix and no dependency or group annotation."""
    bare = _PARALLEL_GROUP_RE.sub(" ", _DEPENDS_ON_RE.sub(" ", heading_title))
    return " ".join(_TITLE_PREFIX_RE.sub("", bare.strip()).split())


def _read_depends_on(heading_title: str) -> tuple[str, ...]:
    listed = (
        entry.strip()
        for value in _DEPENDS_ON_RE.findall(heading_title)
        for entry in value.split(",")
    )
    return tuple(entry for entry in listed if entry)


def _read_parallel_group(heading_title: str) -> str | None:
    annotation = _PARALLEL_GROUP_RE.search(heading_title)
    return (annotation[1].strip() or None) if annotation else None


# A one-line field, optionally a list item, its label optionally bold.
_FIELD_RE = re.compile(
    r"^\s*(?:[-*+]\s+)?\*{0,2}(?P<label>assignee|tier|review|read-only)\*{0,2}"
    r"\s*:\s*\*{0,2}\s*(?P<value>.*)$",
    re.IGNORECASE,
)
_REVIEW_WORDS: dict[str, ReviewOverride] = {"force": "force", "off": "off"}
# "contract: <path>::<symbol>, pinned by <test node>", with or without backticks.
_CONTRACT_CLAUSE_RE = re.compile(
    r"contract:\s*`?[^\s`,]+`?(?:\s*,\s*pinned by\s*`?[^\s`,]+`?)?", re.IGNORECASE
)


def _read_fields(lines: list[str]) -> dict[str, list[str]]:
    """Each field's values by lowercase label, in document order."""
    fields: dict[str, list[str]] = {}
    for field in filter(None, map(_FIELD_RE.match, lines)):
        fields.setdefault(field["label"].lower(), []).append(field["value"].strip())
    return fields


def _first_word(fields: dict[str, list[str]], label: str) -> str:
    """The first word of a field's first value, lowercase, without emphasis or punctuation."""
    words = fields.get(label, [""])[0].split()
    return words[0].strip("*`,.;:").lower() if words else ""


def _read_assignee(fields: dict[str, list[str]]) -> Assignee:
    name = _first_word(fields, "assignee") or UNASSIGNED
    return Implementer() if name == "implementer" else OtherAssignee(name)


def _node_entries(value: str) -> list[str]:
    """The outer-loop paths and node ids a `Read-only:` value declares."""
    value = _CONTRACT_CLAUSE_RE.sub(" ", value)
    if "`" in value:
        tokens = _BACKTICK_SPAN_RE.findall(value)
    else:
        tokens = _BARE_SEPARATOR_RE.split(RATIONALE_RE.sub(" ", value))
    candidates = (token.strip().rstrip(".,;:") for token in tokens)
    return [candidate for candidate in candidates if "/" in candidate or "::" in candidate]


# A "**Files**:" field line under a plan step (the reader the reconciler shares).
FILES_FIELD_RE = re.compile(r"^\s*\*{0,2}Files\*{0,2}\s*:\s*(?P<files>.+)$", re.IGNORECASE)

# A field value that, once leading markdown emphasis is stripped, declares no
# files at all.
FILES_NONE_RE = re.compile(r"^(none|n/a)\b", re.IGNORECASE)
# A path-safe token -- letters, digits, the punctuation a path or glob uses.
FILE_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]-]+$")
# A parenthetical span in a Files: value is rationale ("(see WIP.md)"), never
# a path -- dropped before tokenizing so its contents can't be mistaken for one.
RATIONALE_RE = re.compile(r"\([^)]*\)")

_BACKTICK_SPAN_RE = re.compile(r"`([^`]+)`")
_BARE_SEPARATOR_RE = re.compile(r"[,\s]+")


def scan_step_files(text: str) -> dict[str, list[str]]:
    """Associate each ``Files:`` line of a plan/WIP text with its step.

    A ``Files:`` field that wraps mid-value ends its line with a trailing
    comma; every further line ending in a comma continues the same logical
    value, so the admission predicate in ``split_files`` sees the whole
    declaration rather than losing everything after the wrap.
    """
    lines = text.splitlines()
    result: dict[str, list[str]] = {}
    current: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        step_id = step_id_from_heading(line) or checklist_step_id(line)
        if step_id is not None:
            current = step_id
            index += 1
            continue
        field = FILES_FIELD_RE.match(line)
        if field and current:
            value, index = collect_files_value(field.group("files"), lines, index)
            result.setdefault(current, []).extend(split_files(value))
            continue
        index += 1
    return result


def collect_files_value(first: str, lines: list[str], index: int) -> tuple[str, int]:
    """Join a ``Files:`` value with its trailing-comma continuation lines,
    stopping at a step heading or checklist step line even when the current
    line still ends in a comma -- a plan heading always opens its own step.

    Returns the joined value and the index of the first line not consumed.
    """
    parts = [first]
    index += 1
    while parts[-1].rstrip().endswith(",") and index < len(lines):
        line = lines[index]
        if step_id_from_heading(line) is not None or checklist_step_id(line) is not None:
            break
        parts.append(line)
        index += 1
    return " ".join(parts), index


def split_files(raw: str) -> list[str]:
    """Split a ``Files:`` field value into the individual paths it declares.

    A bare ``none``/``n/a`` -- after stripping a bolded label's leading ``*``
    captured along with it -- declares zero files. Otherwise: strip
    parenthetical rationale spans; tokenize on backtick-quoted spans when the
    value contains any backtick, else on commas/whitespace; admit a candidate
    only when ``is_admitted_file`` accepts it.
    """
    value = raw.strip().lstrip("*").strip()
    if FILES_NONE_RE.match(value):
        return []
    value = RATIONALE_RE.sub(" ", value)
    tokens = _BACKTICK_SPAN_RE.findall(value) if "`" in value else _BARE_SEPARATOR_RE.split(value)
    candidates = (token.strip().strip("`").rstrip(".,;:") for token in tokens)
    return [c for c in candidates if c and is_admitted_file(c)]


def is_admitted_file(candidate: str) -> bool:
    """A path a step may be credited with: path-safe, shaped like a file, and
    not a pointer into this pipeline's own ``.ai-work/`` bookkeeping (a step may
    legitimately cite its own artifacts as rationale, but that is not a file it
    changed)."""
    return (
        bool(FILE_CANDIDATE_RE.match(candidate))
        and ("/" in candidate or "." in candidate)
        and not candidate.endswith("/")
        and not candidate.startswith(".ai-work/")
    )
