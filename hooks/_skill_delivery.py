"""The one owner of the skill-delivery decision: whether a delegation is served the refactoring skill.

The marker grammar is not defined here. It is the plan reader's `REFACTORING_TAG_PATTERN` in
`scripts/_plan_steps.py`, re-exported below as `MARKER_PATTERN`, so a plan step and a delegation
are matched by the same compiled object and no second copy of the grammar can drift.

Stdlib-only and Python 3.9-safe, like the hook modules that import script modules. The `scripts`
directory is found the way `hooks/guard_decision_records.py` finds it: next to the hook in the
plugin, or one level up from a mutation sensor's copy.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

from _rule_delivery import FRONTMATTER_RE

SCRIPTS_DIR = "scripts"
AGENTS_DIR = "agents"
REFACTORING_SKILL = "refactoring"

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

# The step-loop driver's pointer prompt, three lines (`scripts/_step_loop_render.py`
# `spawn_request`), and the opening line of the `<step>` element in the request it points at
# (`scripts/fixtures/step_loop_prompt_golden.md` pins that format). Change one, change the other.
_TASK_SLUG_LINE = re.compile(r"^Task slug: (\S+)$", re.MULTILINE)
_SPAWN_REQUEST_LINE = re.compile(r"^Spawn request: (\S+)$", re.MULTILINE)
_READ_LINE = re.compile(r"^Read (.+?) first\b", re.MULTILINE)
_STEP_OPENING = re.compile(r'^<step id="[^"]*">$', re.MULTILINE)
AI_WORK_DIR = ".ai-work"


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


@dataclass(frozen=True)
class StepRequest:
    """The route of a step-loop pointer whose rendered request heads a marked step."""

    request_id: str


Route = Union[OwnWords, StepRequest]  # noqa: UP007


@dataclass(frozen=True)
class Marked:
    route: Route


UnresolvableReason = Literal[
    "grammar-unavailable",
    "request-path-refused",
    "request-unreadable",
    "request-without-step",
]


@dataclass(frozen=True)
class Unresolvable:
    """A served role whose delegation cannot be classified, so the delivery must not guess."""

    reason: UnresolvableReason


# Union and Optional, not `|`: the hook modules run on Python 3.9, where `|` between classes
# fails at runtime in an alias like these.
Verdict = Union[NotServed, Unmarked, Marked, Unresolvable]  # noqa: UP007

# Reads the rendered request a step-loop pointer names: None when it cannot be read.
RequestReader = Callable[[Path], Optional[str]]  # noqa: UP045


def classify(
    agent_type: str,
    prompt: str,
    read_request: RequestReader,
    cwd: Optional[Path] = None,  # noqa: UP045
) -> Verdict:
    """Judge one delegation. Pure: its inputs are its arguments and the import-time `MARKER_PATTERN`.

    A broken installation (no grammar) is `Unresolvable` for a served role, never a guess either way.
    `cwd` is the spawn's working directory, against which a relative pointer path is resolved;
    without it only an absolute path can be followed.
    """
    if agent_type not in SERVED_ROLES:
        return NotServed(agent_type)
    if MARKER_PATTERN is None:
        return Unresolvable("grammar-unavailable")
    words = own_words(prompt)
    if MARKER_PATTERN.search(words):
        return Marked(OwnWords())
    pointer = _step_loop_pointer(words)
    if pointer is None:
        return Unmarked()
    return _classify_request(pointer, read_request, cwd, MARKER_PATTERN)


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


# --- The step-loop route: a pointer prompt, decided by the heading of the step it points at ------


@dataclass(frozen=True)
class _Pointer:
    slug: str
    request_id: str
    read_path: str


def _step_loop_pointer(words: str) -> Optional[_Pointer]:  # noqa: UP045
    """The pointer the driver's three lines make, or None when any of them is missing."""
    slug, request_id, read = (
        pattern.search(words) for pattern in (_TASK_SLUG_LINE, _SPAWN_REQUEST_LINE, _READ_LINE)
    )
    if not (slug and request_id and read):
        return None
    return _Pointer(slug.group(1), request_id.group(1), read.group(1))


def _classify_request(
    pointer: _Pointer,
    read_request: RequestReader,
    cwd: Optional[Path],  # noqa: UP045
    marker: re.Pattern[str],
) -> Verdict:
    path = _request_path(pointer, cwd)
    if path is None:
        return Unresolvable("request-path-refused")
    request = read_request(path)
    if request is None:
        return Unresolvable("request-unreadable")
    heading = _step_heading(request)
    if heading is None:
        return Unresolvable("request-without-step")
    if marker.search(heading):
        return Marked(StepRequest(pointer.request_id))
    return Unmarked()


def _request_path(pointer: _Pointer, cwd: Optional[Path]) -> Optional[Path]:  # noqa: UP045
    """The pointer's path, only when it names `.ai-work/<slug>/PROMPT_<id>.md`; else None.

    Lexical, so a prompt cannot steer the hook to a file it names: `..` is folded away before the
    check. A symlinked directory is the reading edge's to refuse.
    """
    path = Path(pointer.read_path)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = cwd / path
    path = Path(os.path.normpath(path))
    expected = (AI_WORK_DIR, pointer.slug, f"PROMPT_{pointer.request_id}.md")
    return path if path.parts[-3:] == expected else None


def _step_heading(request: str) -> Optional[str]:  # noqa: UP045
    """The first non-blank line after the request's first `<step>` opening, when it is a heading.

    Only this line decides the verdict: the step's body, quoted attempts and corrections follow it
    and may quote the marker without marking.
    """
    opening = _STEP_OPENING.search(request)
    if opening is None:
        return None
    for line in request[opening.end() :].splitlines():
        if line.strip():
            return line if line.startswith("#") else None
    return None


# --- The preload state: whether the installed definition already carries the skill ---------------

# The first `skills:` key at column 0 of a definition's frontmatter, and what the keyless forms
# of a value look like: a block-list item, a comment, and the YAML scalars no list can start with.
_SKILLS_KEY = re.compile(r"^skills:[ \t]*(.*)$", re.MULTILINE)
_BLOCK_ITEM = re.compile(r"^-\s+(.*)$")
_COMMENT = re.compile(r"(^|\s)#.*$")
_NOT_A_LIST = re.compile(r"^[|>{&*!]")


@dataclass(frozen=True)
class Preloaded:
    """The definition lists the skill, so the harness preloads it and a delivery would double it."""


@dataclass(frozen=True)
class NotPreloaded:
    """The definition is readable and does not list the skill: the delivery must serve it."""


PreloadUnreadableReason = Literal[
    "definition-unreadable",
    "frontmatter-missing",
    "skills-unparseable",
]


@dataclass(frozen=True)
class DefinitionUnreadable:
    """The state cannot be told, so the delivery must neither serve on a guess nor skip on one."""

    reason: PreloadUnreadableReason


PreloadState = Union[Preloaded, NotPreloaded, DefinitionUnreadable]  # noqa: UP007


def preload_state(plugin_root: Path, role: str) -> PreloadState:
    """Whether `<plugin_root>/agents/<role>.md` preloads the refactoring skill.

    The installed plugin's definition is the one the harness takes the preload from, so it is the
    only source: never the project's files, never a flag. `role` is the definition's file stem.
    """
    try:
        definition = (plugin_root / AGENTS_DIR / f"{role}.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return DefinitionUnreadable("definition-unreadable")
    frontmatter = FRONTMATTER_RE.match(definition)
    if frontmatter is None:
        return DefinitionUnreadable("frontmatter-missing")
    skills = _listed_skills(frontmatter.group())
    if skills is None:
        return DefinitionUnreadable("skills-unparseable")
    return Preloaded() if REFACTORING_SKILL in skills else NotPreloaded()


def _listed_skills(frontmatter: str) -> Optional[list[str]]:  # noqa: UP045
    """The names the first `skills:` key lists: none without the key; None when it is unparseable.

    Reads the forms a definition uses: `[a, b]`, a bare `a, b`, and a block list of `- a` lines.
    Anything else, a multi-line inline list included, is unparseable and never guessed at.
    """
    key = _SKILLS_KEY.search(frontmatter)
    if key is None:
        return []
    value = _without_comment(key.group(1))
    if not value:
        return _block_items(frontmatter[key.end() :].splitlines())
    if _NOT_A_LIST.match(value):
        return None
    if value.startswith("["):
        if not value.endswith("]"):
            return None
        value = value[1:-1]
    return _names(value.split(","))


def _block_items(lines: list[str]) -> Optional[list[str]]:  # noqa: UP045
    """The `- name` items under a bare `skills:` key, which ends at the next unindented line."""
    items = []
    for line in lines:
        content = _without_comment(line)
        if not content:
            continue
        item = _BLOCK_ITEM.match(content)
        if item:
            items.append(item.group(1))
        elif line[0].isspace():
            return None
        else:
            break
    return _names(items)


def _without_comment(text: str) -> str:
    return _COMMENT.sub("", text).strip()


def _names(raw: list[str]) -> list[str]:
    return [name for name in (item.strip().strip("'\"") for item in raw) if name]
