"""The generic constructors the role check table is built from.

A role's clause is a row in :mod:`~praxion_evals.adherence.catalog`, not a function
of its own: each row is one of the constructors below applied to its arguments. A
constructor returns a :class:`~praxion_evals.adherence.model.MechanicalCheck`
whose ``violation`` canary it builds from the same arguments, so a row cannot
exist without the evidence that proves the check fires.

Every check is a pure function of the session's recorded evidence except
:func:`script_exits_zero`, which runs an existing Praxion script as a subprocess
over the scratch repository (never imports it) and reads only its exit code.
"""

from __future__ import annotations

import atexit
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from praxion_evals.adherence.checks_common import (
    WRITE_TOOLS,
    _always_binds,  # the binding of a rule that holds for every task of the role
    _repo_relative,  # an absolute tool path as the scratch repository names it
    _within_any,  # a path equal to or under one of the places
    slug_dir,
    synthetic_evidence,
    written_paths,
)
from praxion_evals.adherence.model import (
    BindsFor,
    CheckErrored,
    CheckOutcome,
    Failed,
    MechanicalCheck,
    NotApplicable,
    Passed,
    Role,
    RuleRef,
    SessionEvidence,
    TaskFacts,
)
from praxion_evals.live.session import InitInfo, ToolUse

CANARY_SLUG = "canary-task"
CHECKOUT_ROOT = Path(__file__).resolve().parents[4]  # the checkout whose scripts a canary runs
SCRIPT_TIMEOUT_S = 60
SCRIPT_EXIT_CLEAN = 0
SCRIPT_EXIT_VIOLATIONS = 1  # Praxion's check scripts: 0 clean, 1 violations, 2 script error
REPO_PLACEHOLDER = "{repo}"
OUTPUT_TAIL_LINES = 6

ToolMatcher = Callable[[SessionEvidence, ToolUse], bool]


# ---------------------------------------------------------------------------
# Reading a Markdown document
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")
_FENCES = ("```", "~~~")
PLACEHOLDERS = frozenset({"[pending]", "[not reached]"})  # what an unfilled skeleton holds


@dataclass(frozen=True)
class Section:
    """A heading a document must carry, with a body that is more than a placeholder."""

    heading: str
    content: re.Pattern[str] | None = None  # what the body must also match, when given


def section_body(text: str, heading: str) -> list[str] | None:
    """Lines under the heading titled ``heading``, to the next heading as high or higher."""
    lines = text.splitlines()
    marks = list(_heading_marks(lines))
    for position, (index, level, title) in enumerate(marks):
        if title == heading:
            end = next((i for i, lvl, _ in marks[position + 1 :] if lvl <= level), len(lines))
            return lines[index + 1 : end]
    return None


def _heading_marks(lines: Sequence[str]) -> Iterator[tuple[int, int, str]]:
    """``(line index, level, title)`` of each heading outside a fenced code block."""
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(_FENCES):
            fenced = not fenced
        elif not fenced and (heading := _HEADING.match(line)):
            yield index, len(heading.group(1)), heading.group(2)


def has_content(body: Sequence[str]) -> bool:
    """True when the body holds a line that is not blank, a heading or a placeholder."""
    return any(
        line.strip() and line.strip() not in PLACEHOLDERS and not _HEADING.match(line)
        for line in body
    )


def first_line(text: str) -> str:
    """The title: the first line with anything on it."""
    return next((line for line in text.splitlines() if line.strip()), "")


# ---------------------------------------------------------------------------
# Shared parts of a constructor
# ---------------------------------------------------------------------------


def _document(evidence: SessionEvidence, document: str) -> tuple[str, str]:
    """The repo-relative path of a document in the task's slug directory, and its text."""
    path = f"{slug_dir(evidence.slug)}/{document}"
    return path, evidence.repo.files.get(path, "")


def _cwd(evidence: SessionEvidence) -> str | None:
    return evidence.envelope.init.cwd if evidence.envelope.init else None


def _clause(
    name: str,
    rule: RuleRef,
    binds: BindsFor | None,
    evaluate: Callable[[SessionEvidence], CheckOutcome],
    violation: Callable[[], SessionEvidence],
) -> MechanicalCheck:
    return MechanicalCheck(
        name=name,
        rule=rule,
        common=False,
        binds=binds or _always_binds,
        evaluate=evaluate,
        violation=violation,
    )


def with_cwd(evidence: SessionEvidence, cwd: Path) -> SessionEvidence:
    """The same evidence with the session recorded as having run in ``cwd``."""
    init = InitInfo(
        model=None, plugins=(), mcp_servers=(), api_key_source=None, claude_code_version=None,
        cwd=str(cwd),
    )  # fmt: skip
    return replace(evidence, envelope=replace(evidence.envelope, init=init))


# ---------------------------------------------------------------------------
# A document carries its required sections, each with content
# ---------------------------------------------------------------------------


def required_sections(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    sections: Sequence[Section],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = _document(evidence, document)
        if not text.strip():
            return Failed(f"{path} was never written or is empty")
        problems = [problem for s in sections if (problem := _section_problem(text, s))]
        return Failed(f"{path}: {'; '.join(problems)}") if problems else Passed()

    def violation() -> SessionEvidence:
        unfilled = "\n\n".join(f"## {s.heading}\n\n[pending]" for s in sections)
        path = f"{slug_dir(CANARY_SLUG)}/{document}"
        return synthetic_evidence(role, slug=CANARY_SLUG, files={path: unfilled})

    return _clause(name, rule, binds, evaluate, violation)


def _section_problem(text: str, section: Section) -> str | None:
    body = section_body(text, section.heading)
    if body is None:
        return f"no section {section.heading!r}"
    if not has_content(body):
        return f"section {section.heading!r} has no content"
    if section.content and not section.content.search("\n".join(body)):
        return f"section {section.heading!r} lacks {section.content.pattern!r}"
    return None


# ---------------------------------------------------------------------------
# A document is opened with a marker in its title and ends without it
# ---------------------------------------------------------------------------


def title_marker_first_unmarked_last(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    marker: str,
    within_first: int,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Its first recorded Write carries ``marker`` in the title, within the role's first
    ``within_first`` tool calls, and the file the session leaves carries none."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, final = _document(evidence, document)
        problems = _opening_problems(evidence, path, marker, within_first)
        if not final.strip():
            problems.append(f"{path} is missing or empty at the end")
        elif marker in first_line(final):
            problems.append(f"the title still carries {marker}: {first_line(final)[:80]!r}")
        return Failed("; ".join(problems)) if problems else Passed()

    def violation() -> SessionEvidence:
        path = f"{slug_dir(CANARY_SLUG)}/{document}"
        opened = ToolUse("canary-open", "Write", {"file_path": path, "content": "# Report\n"}, None)
        return synthetic_evidence(
            role, slug=CANARY_SLUG, files={path: "# Report\n"}, tool_uses=[opened]
        )

    return _clause(name, rule, binds, evaluate, violation)


def _opening_problems(
    evidence: SessionEvidence, path: str, marker: str, within_first: int
) -> list[str]:
    cwd = _cwd(evidence)
    first = next(
        (
            (position, use)
            for position, use in enumerate(evidence.role_tool_uses, start=1)
            if use.name in WRITE_TOOLS
            and _repo_relative(str(use.input.get(WRITE_TOOLS[use.name], "")), cwd) == path
        ),
        None,
    )
    if first is None:
        return [f"no Write or Edit of {path} was recorded, so its opening state is unknown"]
    position, use = first
    if use.name != "Write":
        return [f"the first recorded change to {path} was an {use.name}, not a Write"]
    problems = []
    if position > within_first:
        problems.append(f"first written at tool call {position}, after the first {within_first}")
    if marker not in first_line(str(use.input.get("content", ""))):
        problems.append(f"opened without {marker} in its title")
    return problems


# ---------------------------------------------------------------------------
# One recorded tool use comes before another
# ---------------------------------------------------------------------------


def tool_order(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    earlier: ToolMatcher,
    earlier_label: str,
    later: ToolMatcher,
    later_label: str,
    earlier_sample: ToolUse,
    later_sample: ToolUse,
    facts: TaskFacts | None = None,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The role makes an ``earlier`` use, and no ``later`` use precedes the first of them.

    ``facts`` are the task facts the matchers read; the samples build the canary,
    which records the ``later`` use first.
    """

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        uses = evidence.role_tool_uses
        first = _first_index(uses, lambda use: earlier(evidence, use))
        other = _first_index(uses, lambda use: later(evidence, use))
        if first is None:
            return Failed(f"the session never {earlier_label}")
        if other is not None and other < first:
            return Failed(
                f"{later_label} (tool call {other + 1}) came before the first "
                f"{earlier_label} (tool call {first + 1})"
            )
        return Passed()

    def violation() -> SessionEvidence:
        return synthetic_evidence(
            role, slug=CANARY_SLUG, tool_uses=[later_sample, earlier_sample], facts=facts
        )

    return _clause(name, rule, binds, evaluate, violation)


def _first_index(uses: Sequence[ToolUse], matches: Callable[[ToolUse], bool]) -> int | None:
    return next((index for index, use in enumerate(uses) if matches(use)), None)


# ---------------------------------------------------------------------------
# No change lands under a forbidden path
# ---------------------------------------------------------------------------


def path_scope(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    forbidden: Sequence[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Nothing the session changed lies at or under any of the ``forbidden`` paths."""
    places = tuple(place.rstrip("/") for place in forbidden)

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        hits = sorted(path for path in written_paths(evidence) if _within_any(path, places))
        return Failed(f"changed {', '.join(hits[:5])}") if hits else Passed()

    def violation() -> SessionEvidence:
        planted = f"{places[0]}/canary_planted_change.txt"
        return synthetic_evidence(role, slug=CANARY_SLUG, files={planted: "changed\n"})

    return _clause(name, rule, binds, evaluate, violation)


# ---------------------------------------------------------------------------
# A closed vocabulary of tags
# ---------------------------------------------------------------------------

_TAG = re.compile(r"\[([A-Z][A-Z0-9]*(?:[ -][A-Z0-9]+)*)\](?!\()")


def closed_tag_set(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    section: str,
    allowed: Collection[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Every bracketed upper-case tag in the document's ``section`` is one of ``allowed``."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = _document(evidence, document)
        body = section_body(text, section)
        if body is None:
            return Failed(f"{path} has no section {section!r}")
        stray = sorted({tag for tag in _TAG.findall("\n".join(body)) if tag not in allowed})
        return (
            Failed(f"{path}: tags outside the closed set: {', '.join(stray)}")
            if stray
            else Passed()
        )

    def violation() -> SessionEvidence:
        path = f"{slug_dir(CANARY_SLUG)}/{document}"
        invented = f"## {section}\n\n| 1 | WARN | [CANARY-INVENTED-TAG] an invented tag |\n"
        return synthetic_evidence(role, slug=CANARY_SLUG, files={path: invented})

    return _clause(name, rule, binds, evaluate, violation)


# ---------------------------------------------------------------------------
# A count stays within a limit
# ---------------------------------------------------------------------------


def count_limit(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    matcher: ToolMatcher,
    limit: int,
    label: str,
    sample: ToolUse,
    facts: TaskFacts | None = None,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The role makes at most ``limit`` tool uses that ``matcher`` accepts."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        count = sum(1 for use in evidence.role_tool_uses if matcher(evidence, use))
        return Failed(f"{count} {label}, against a limit of {limit}") if count > limit else Passed()

    def violation() -> SessionEvidence:
        uses = [replace(sample, id=f"canary-use-{index}") for index in range(limit + 1)]
        return synthetic_evidence(role, slug=CANARY_SLUG, tool_uses=uses, facts=facts)

    return _clause(name, rule, binds, evaluate, violation)


# ---------------------------------------------------------------------------
# An existing Praxion script exits zero over the scratch repository
# ---------------------------------------------------------------------------


def script_exits_zero(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    script: str,
    arguments: Sequence[str],
    planted: Mapping[str, str],
    watched: Sequence[str] = (),
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """``scripts/<script>`` exits 0 over the scratch repository (``{repo}`` in ``arguments``).

    The script is the plugin copy's, run as a subprocess and never imported. With
    ``watched`` paths given, the check applies only when the session changed one of
    them. Exit 1 is a violation (``failed``); a script that is absent, times out or
    exits otherwise cannot judge this repository, which is ``errored``, never ``failed``.
    ``planted`` is the scratch repository's files in the canary.
    """

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        if watched and not any(_within_any(path, watched) for path in written_paths(evidence)):
            return NotApplicable(f"the {role} changed none of {', '.join(watched)}")
        return _run_script(evidence, script, arguments)

    def violation() -> SessionEvidence:
        repo = Path(tempfile.mkdtemp(prefix="adherence-canary-"))
        atexit.register(shutil.rmtree, repo, ignore_errors=True)
        for relative, text in planted.items():
            (repo / relative).parent.mkdir(parents=True, exist_ok=True)
            (repo / relative).write_text(text, encoding="utf-8")
        evidence = synthetic_evidence(
            role, slug=CANARY_SLUG, files=planted, places=(repo, CHECKOUT_ROOT)
        )
        return with_cwd(evidence, repo)

    return _clause(name, rule, binds, evaluate, violation)


def _run_script(evidence: SessionEvidence, script: str, arguments: Sequence[str]) -> CheckOutcome:
    repo = _cwd(evidence)
    path = evidence.plugin_copy / "scripts" / script
    if repo is None:
        return CheckErrored("the session's working directory was not recorded")
    if not path.is_file():
        return CheckErrored(f"scripts/{script} is not in the plugin copy {evidence.plugin_copy}")
    command = [sys.executable, str(path), *(a.replace(REPO_PLACEHOLDER, repo) for a in arguments)]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=SCRIPT_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return CheckErrored(f"scripts/{script} could not run: {type(error).__name__}: {error}")
    if done.returncode == SCRIPT_EXIT_CLEAN:
        return Passed()
    tail = " | ".join((done.stdout or done.stderr).strip().splitlines()[-OUTPUT_TAIL_LINES:])
    if done.returncode == SCRIPT_EXIT_VIOLATIONS:
        return Failed(f"scripts/{script} exited 1: {tail}")
    return CheckErrored(f"scripts/{script} exited {done.returncode}: {tail}")
