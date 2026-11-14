"""The one owner of the skill-delivery decision: whether a delegation is served the refactoring skill.

The marker grammar is not defined here. It is the plan reader's `REFACTORING_TAG_PATTERN` in
`scripts/_plan_steps.py`, re-exported below as `MARKER_PATTERN`, so a plan step and a delegation
are matched by the same compiled object and no second copy of the grammar can drift.

Stdlib-only and Python 3.9-safe, like the hook modules that import script modules. The `scripts`
directory is found the way `hooks/guard_decision_records.py` finds it: next to the hook in the
plugin, or one level up from a mutation sensor's copy.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NoReturn, Optional, TypeVar, Union

from _rule_delivery import FRONTMATTER_RE

SCRIPTS_DIR = "scripts"
AGENTS_DIR = "agents"
SKILLS_DIR = "skills"
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


# --- What a served spawn receives: the block, the failure notice and the arrival matcher ---------

# The label and end lines carry no marker text: a relayed block must never mark a later delegation
# (`test__skill_delivery_block.py` pins that against `MARKER_PATTERN`).
_DIGEST_LENGTH = 8
_LABEL_SENTENCE = (
    "This delegation carries the refactoring phase marker, so the skill text below is delivered "
    "with it. It is reference material for your step, not part of the delegation."
)
END_LINE = f"[End of skill delivery: {REFACTORING_SKILL}]"
# What the matcher reads back: the label's digest, and the end line on a line of its own.
_LABEL_LINE = re.compile(
    rf"^\[Skill delivery: {REFACTORING_SKILL} (?P<digest>[0-9a-f]{{{_DIGEST_LENGTH}}})\]",
    re.MULTILINE,
)
_END_LINE = re.compile(rf"^{re.escape(END_LINE)}$", re.MULTILINE)


def body_digest(body: str) -> str:
    """The first eight hex digits of the body's SHA-256: the label's proof of which text arrived."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def render_block(body: str, base_dir: Path) -> str:
    """The skill text, delivered whole: the body appears in the block as one unaltered substring.

    `base_dir` is the skill's absolute directory, which the body's relative links resolve against.
    """
    label = f"[Skill delivery: {REFACTORING_SKILL} {body_digest(body)}] {_LABEL_SENTENCE}"
    return f"{label}\nBase directory for this skill: {base_dir}\n\n{body}\n{END_LINE}"


def render_notice(reason: str, skill_path: Path) -> str:
    """The trailing segment of a failed delivery: where the skill is, and no instruction."""
    return (
        f"[Skill delivery failed: {REFACTORING_SKILL} ({reason})] The {REFACTORING_SKILL} skill's "
        f"text was not delivered with this delegation; it is at {skill_path}."
    )


def shows_arrival(record: str, installed_body: Optional[str] = None) -> bool:  # noqa: UP045
    """Whether a spawn's record holds a delivered block: a label line, then the end line.

    With `installed_body` the label's digest must also be that body's. A notice, a bare body or a
    quoted label (the label not at the start of a line) shows no arrival.
    """
    for label in _LABEL_LINE.finditer(record):
        if installed_body is not None and label["digest"] != body_digest(installed_body):
            continue
        if _END_LINE.search(record, label.end()):
            return True
    return False


# --- The reading edge: the skill's body, whole or not at all -------------------------------------

SKILL_FILE = "SKILL.md"
# The skill's one reference file. Its presence stands for the whole directory being the installed
# skill, so every relative link of the body resolves against the base directory the block names.
REFERENCE_FILE = Path("references") / "patterns.md"
# The body is delivered whole, so a file over the limit is refused, never cut.
MAX_SKILL_BYTES = 64 * 1024
# A FIFO nobody writes or a hung mount must end the read, not the hook.
READ_TIMEOUT_SECONDS = 1.0
_HEADER_OPENING = "---\n"
_HEADER_CLOSING = "\n---\n"

BodyUnreadableReason = Literal["skill-unreadable", "skill-read-timeout"]


@dataclass(frozen=True)
class BodyUnreadable:
    """The skill's body cannot be delivered whole, so none of it is."""

    reason: BodyUnreadableReason


BodyRead = Union[str, BodyUnreadable]  # noqa: UP007
_UNREADABLE = BodyUnreadable("skill-unreadable")


def read_body(skill_dir: Path) -> BodyRead:
    """The text of `<skill_dir>/SKILL.md` after its metadata header, or why it cannot be read."""
    timed_out: BodyRead = BodyUnreadable("skill-read-timeout")
    return _within_timeout(lambda: _read_body_unbounded(skill_dir), timed_out)


_Read = TypeVar("_Read")


def _within_timeout(read: Callable[[], _Read], on_timeout: _Read) -> _Read:
    """What `read` returns within `READ_TIMEOUT_SECONDS`, else `on_timeout`.

    The read runs in a daemon thread: one stuck opening a FIFO is abandoned and cannot keep the
    process from exiting, which a bounded `open` could not promise for every kind of hung file.
    """
    outcome: list[_Read] = []
    reader = threading.Thread(target=lambda: outcome.append(read()), daemon=True)
    reader.start()
    reader.join(READ_TIMEOUT_SECONDS)
    return outcome[0] if outcome else on_timeout


def _read_body_unbounded(skill_dir: Path) -> BodyRead:
    try:
        if not (skill_dir / REFERENCE_FILE).is_file():
            return _UNREADABLE
        with open(skill_dir / SKILL_FILE, "rb") as skill_file:
            raw = skill_file.read(MAX_SKILL_BYTES + 1)
        if len(raw) > MAX_SKILL_BYTES:
            return _UNREADABLE
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _UNREADABLE
    return _after_header(text)


def _after_header(text: str) -> BodyRead:
    """Everything after the first closing line of the metadata header; unreadable without one."""
    if not text.startswith(_HEADER_OPENING):
        return _UNREADABLE
    closing = text.find(_HEADER_CLOSING)
    if closing == -1:
        return _UNREADABLE
    return text[closing + len(_HEADER_CLOSING) :]


# --- The request edge: the rendered request a step-loop pointer names ----------------------------

# The heading is in the request's first lines, so a larger request is read in part, not refused.
MAX_REQUEST_BYTES = 64 * 1024


def read_request(path: Path) -> Optional[str]:  # noqa: UP045
    """The request's text, or None when it cannot be read within the second.

    A link on the way to the file is refused: `_request_path` checked the path lexically, which a
    symlinked `.ai-work` or slug directory would defeat.
    """
    return _within_timeout(lambda: _read_request_unbounded(path), None)


def _read_request_unbounded(path: Path) -> Optional[str]:  # noqa: UP045
    if any(link.is_symlink() for link in (path, path.parent, path.parent.parent)):
        return None
    try:
        with open(path, "rb") as request_file:
            raw = request_file.read(MAX_REQUEST_BYTES)
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


# --- Outcome: what a delivery is -----------------------------------------------------------------

SkipReason = Literal["not-served", "unmarked", "preloaded"]
FailureReason = Literal[
    "skill-unreadable",
    "skill-read-timeout",
    "definition-unreadable",
    "request-unresolvable",
    "grammar-unavailable",
    "input-malformed",
    "internal-error",
]


@dataclass(frozen=True)
class Skipped:
    """Nothing is added to the spawn and nothing is recorded."""

    why: SkipReason


@dataclass(frozen=True)
class Served:
    """The spawn receives `block` after its delegation; one `served` row records it."""

    block: str
    body_digest: str
    route: Route


@dataclass(frozen=True)
class Failed:
    """The skill could not be delivered: one `failed` row and one stderr line record why.

    `cause` names the exception behind an `internal-error` on the stderr line only: the row's
    reasons are a closed set, and two failures of one reason are the same failure.
    """

    reason: FailureReason
    cause: str = field(default="", compare=False)


Outcome = Union[Skipped, Served, Failed]  # noqa: UP007
Recorded = Union[Served, Failed]  # noqa: UP007


def decide(verdict: Verdict, preload: PreloadState, skill_dir: Path) -> Outcome:
    """The decision table, total over every verdict and preload state.

    Reads the body only for a marked delegation to a definition that does not preload the skill.
    A preload wins over an unresolvable delegation, so a broken installation changes nothing
    while the definitions still carry the skill.
    """
    if isinstance(verdict, NotServed):
        return Skipped("not-served")
    if isinstance(verdict, Unmarked):
        return Skipped("unmarked")
    if isinstance(preload, Preloaded):
        return Skipped("preloaded")
    if isinstance(verdict, Unresolvable):
        return Failed(_failure_of(verdict))
    if isinstance(preload, DefinitionUnreadable):
        # Not knowing whether a preload carries the skill, add nothing rather than risk two copies.
        return Failed("definition-unreadable")
    if isinstance(preload, NotPreloaded):
        return _serve(verdict.route, skill_dir)
    _assert_never(preload)


def _failure_of(verdict: Unresolvable) -> FailureReason:
    if verdict.reason == "grammar-unavailable":
        return "grammar-unavailable"
    return "request-unresolvable"


def _serve(route: Route, skill_dir: Path) -> Outcome:
    body = read_body(skill_dir)
    if isinstance(body, BodyUnreadable):
        return Failed(body.reason)
    return Served(render_block(body, skill_dir), body_digest(body), route)


def _assert_never(unhandled: NoReturn) -> NoReturn:
    """Marks a cell the table forgot: a type checker rejects the call, a run raises."""
    raise AssertionError(f"unhandled cell: {unhandled!r}")


# --- The delivery edge: every read, and the one row and stderr line a failure leaves -------------


@dataclass(frozen=True)
class _Delegation:
    agent_type: str
    prompt: str
    cwd: Optional[Path]  # noqa: UP045


def deliver(payload: Any, plugin_root: Path, environ: Mapping[str, str]) -> Outcome:
    """Decide one spawn call's delivery, perform every read and leave its record. Never raises.

    `payload` is the hook's stdin object. The order is role, preload state, classification: the
    marker grammar is consulted only for a served role whose definition does not preload the
    skill, so a broken installation changes no spawn while the definitions preload.
    """
    try:
        outcome = _outcome(payload, plugin_root)
    except Exception as error:
        outcome = Failed("internal-error", type(error).__name__)
    _report(outcome, payload, environ)
    return outcome


def _outcome(payload: Any, plugin_root: Path) -> Outcome:
    delegation = _delegation(payload)
    if delegation is None:
        return Failed("input-malformed")
    if delegation.agent_type not in SERVED_ROLES:
        return Skipped("not-served")
    preload = preload_state(plugin_root, delegation.agent_type.rpartition(":")[2])
    if isinstance(preload, Preloaded):
        return Skipped("preloaded")
    verdict = classify(delegation.agent_type, delegation.prompt, read_request, delegation.cwd)
    return decide(verdict, preload, skill_dir(plugin_root))


def skill_dir(plugin_root: Path) -> Path:
    """The installed skill's real directory: the block's base directory and the notice's pointer."""
    return (plugin_root / SKILLS_DIR / REFACTORING_SKILL).resolve()


def _delegation(payload: Any) -> Optional[_Delegation]:  # noqa: UP045
    """The Agent call's type, prompt and working directory; None when the input is not that shape.

    An absent `subagent_type` or `prompt` is the empty string, as the emitter reads them.
    """
    tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else None
    if not isinstance(tool_input, dict):
        return None
    agent_type, prompt = tool_input.get("subagent_type", ""), tool_input.get("prompt", "")
    if not (isinstance(agent_type, str) and isinstance(prompt, str)):
        return None
    cwd = _text(payload, "cwd")
    return _Delegation(agent_type, prompt, Path(cwd) if cwd else None)


def _text(mapping: Any, key: str) -> str:
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return value if isinstance(value, str) else ""


def _report(outcome: Outcome, payload: Any, environ: Mapping[str, str]) -> None:
    """A served or failed outcome leaves its row; a failure also leaves a stderr line."""
    if isinstance(outcome, Skipped):
        return
    if isinstance(outcome, Failed):
        _say(_failure_line(outcome))
    try:
        _record(outcome, payload, environ)
    except Exception as error:
        _say(f"skill delivery row not recorded: {REFACTORING_SKILL} ({type(error).__name__})")


def _say(line: str) -> None:
    # A closed or broken stderr leaves nowhere to say it; the delivery goes on without it.
    with contextlib.suppress(OSError, ValueError):
        print(line, file=sys.stderr)


def _failure_line(failed: Failed) -> str:
    line = f"skill delivery failed: {REFACTORING_SKILL} ({failed.reason})"
    if failed.reason == "grammar-unavailable":
        return f"{line}: {MARKER_IMPORT_ERROR}"
    if failed.cause:
        return f"{line}: {failed.cause}"
    return line


def _record(outcome: Recorded, payload: Any, environ: Mapping[str, str]) -> None:
    """Append the row at the log serving the spawn's directory; nowhere where none does.

    Imported here, not at the top: the log is a dependency of the record alone, and a failure to
    import it must cost the row, never the module.
    """
    from _observation_log import writer
    from _observation_log.location import locate
    from _observation_log.registry import EventClass

    # Input too malformed to name a directory is recorded where the harness runs handlers.
    location = locate(_text(payload, "cwd") or os.getcwd())
    if location is not None:
        row = delivery_row(outcome, payload, datetime.now(timezone.utc).isoformat())
        writer.record(location.state_dir, EventClass.SKILL_DELIVERY, row, env=environ)


# The route of a failure is not carried by `Failed`, so a failed row names none.
_UNKNOWN_ROUTE = "unknown"
_ROUTE_NAMES = {OwnWords: "own-words", StepRequest: "step-request"}


def delivery_row(outcome: Recorded, payload: Any, timestamp: str) -> dict:  # noqa: UP007
    """The `skill_delivery` row of a served or failed outcome. Pure: the timestamp is an argument."""
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    row = {
        "timestamp": timestamp,
        "session_id": _text(payload, "session_id"),
        "event_type": "skill_delivery",
        "agent_type": _text(tool_input, "subagent_type"),
        "skill": REFACTORING_SKILL,
        "tool_use_id": _text(payload, "tool_use_id"),
    }
    if isinstance(outcome, Served):
        route = _ROUTE_NAMES[type(outcome.route)]
        return {**row, "outcome": "served", "route": route, "body_digest": outcome.body_digest}
    return {**row, "outcome": "failed", "route": _UNKNOWN_ROUTE, "reason": outcome.reason}
