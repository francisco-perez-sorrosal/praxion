"""Constructors for the clauses of the role check table that read a document or a spawn.

Like :mod:`~praxion_evals.adherence.checks_roles`, each constructor returns a
:class:`~praxion_evals.adherence.model.MechanicalCheck` whose ``violation`` canary it
builds from its own arguments, so a clause cannot exist without the evidence that
proves it fires. They are the ones the roles that audit, advise and report need: a
report's fields, a ledger confined to the rows a role may write, a workflow file's
security items, a fan-out and what each spawn is told.

A document is named as :func:`~praxion_evals.adherence.checks_common.document_path`
reads it: a bare name in the task's slug directory, otherwise a repository path, and
either may hold ``*`` where the definition leaves a name open.
"""

from __future__ import annotations

import os
import re
from collections.abc import Collection, Mapping, Sequence

import yaml

from praxion_evals.adherence.checks_common import (
    _repo_relative,  # an absolute tool path as the scratch repository names it
    document_files,
    synthetic_evidence,
)
from praxion_evals.adherence.checks_roles import (
    CANARY_SLUG,
    canary_path,
    clause,
    has_content,
    section_body,
    session_cwd,
    slug_document,
)
from praxion_evals.adherence.model import (
    BindsFor,
    CheckOutcome,
    Failed,
    MechanicalCheck,
    NotApplicable,
    Passed,
    Role,
    RuleRef,
    SessionEvidence,
    Withheld,
)
from praxion_evals.live.session import ToolUse

SPAWN_TOOLS = ("Agent", "Task")  # the name a subagent spawn carries, by Claude Code version
MARKDOWN_ROW = "|"
_READ_LINE_NUMBER = re.compile(r"^\s*\d+[\t→]")  # what the Read tool puts before each line


# ---------------------------------------------------------------------------
# A document matches a pattern, or its fields are present
# ---------------------------------------------------------------------------


def document_mentions(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    pattern: re.Pattern[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The document the session left holds text matching ``pattern``."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = slug_document(evidence, document)
        if not text.strip():
            return Failed(f"{path} was never written or is empty")
        if not pattern.search(text):
            return Failed(f"{path} lacks {pattern.pattern!r}")
        return Passed()

    def violation() -> SessionEvidence:
        return _with_document(role, document, "# Draft\n\n[pending]\n")

    return clause(name, rule, binds, evaluate, violation)


def fields_per_section(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    parents: Mapping[str, Sequence[str]],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Each of the ``parents`` sections the document carries holds every field named for it,
    each with content; at least one parent must be there."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = slug_document(evidence, document)
        if not text.strip():
            return Failed(f"{path} was never written or is empty")
        present = {parent: body for parent in parents if (body := section_body(text, parent))}
        if not present:
            return Failed(f"{path} has none of {', '.join(repr(p) for p in parents)}")
        gaps = [
            f"{parent!r} lacks {field!r}"
            for parent, body in present.items()
            for field in parents[parent]
            if not _field_has_content("\n".join(body), field)
        ]
        return Failed(f"{path}: {'; '.join(gaps)}") if gaps else Passed()

    def violation() -> SessionEvidence:
        parent = next(iter(parents))
        return _with_document(role, document, f"## {parent}\n\nno fields here\n")

    return clause(name, rule, binds, evaluate, violation)


def _field_has_content(parent_text: str, field: str) -> bool:
    body = section_body(parent_text, field)
    return body is not None and has_content(body)


def labelled_values(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    label: str,
    allowed: Collection[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Every ``**label**: value`` line in the document holds one of ``allowed`` (any case)."""
    line = re.compile(rf"^\s*(?:[-*]\s+)?\*\*{re.escape(label)}(?::\*\*|\*\*:)\s*(\S.*?)\s*$", re.M)

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = slug_document(evidence, document)
        if not text.strip():
            return Failed(f"{path} was never written or is empty")
        stray = sorted({v for v in line.findall(text) if v.lower() not in allowed})
        return Failed(f"{path}: {label} is {', '.join(stray)}") if stray else Passed()

    def violation() -> SessionEvidence:
        return _with_document(role, document, f"- **{label}**: canary-invented-value\n")

    return clause(name, rule, binds, evaluate, violation)


# ---------------------------------------------------------------------------
# A log gains a row for the report, and a ledger holds only the rows a role may write
# ---------------------------------------------------------------------------


def log_row_for_report(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    report: str,
    log: str,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The log the session left has a table row that names the report it wrote."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        report_path, report_text = slug_document(evidence, report)
        log_path, log_text = slug_document(evidence, log)
        if not report_text.strip():
            return Failed(f"{report_path} was never written, so no row can name it")
        if not log_text.strip():
            return Failed(f"{log_path} was not appended to")
        file_name = os.path.basename(report_path)
        rows = [r for r in log_text.splitlines() if r.lstrip().startswith(MARKDOWN_ROW)]
        if not any(file_name in row for row in rows):
            return Failed(f"{log_path} has no row naming {file_name}")
        return Passed()

    def violation() -> SessionEvidence:
        return _with_document(role, report, "# Report\n")

    return clause(name, rule, binds, evaluate, violation)


def ledger_rows_confined(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    ledger: str,
    source: str,
    classes: Collection[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Each row of the ledger whose ``source`` is ``source`` has a ``class`` in ``classes``.

    The classes are those of the checks the role may file a row for. A session that left
    the ledger alone has nothing to confine.
    """

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = slug_document(evidence, ledger)
        if not text.strip():
            return NotApplicable(f"the {role} left {path} unchanged")
        stray = sorted(
            {c for s, c in _ledger_cells(text, "source", "class") if s == source} - set(classes)
        )
        return Failed(f"{path}: {source} rows of class {', '.join(stray)}") if stray else Passed()

    def violation() -> SessionEvidence:
        rows = f"| id | class | source |\n|---|---|---|\n| td-901 | canary-class | {source} |\n"
        return _with_document(role, ledger, rows)

    return clause(name, rule, binds, evaluate, violation)


def _ledger_cells(text: str, *columns: str) -> list[tuple[str, ...]]:
    """The named cells of each table row, read by the header's column names."""
    index: list[int] | None = None
    cells: list[tuple[str, ...]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith(MARKDOWN_ROW):
            continue
        row = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if index is None:
            if all(column in row for column in columns):
                index = [row.index(column) for column in columns]
        elif row and row[0].startswith("td-") and len(row) > max(index):
            cells.append(tuple(row[i] for i in index))
    return cells


# ---------------------------------------------------------------------------
# A report is the return, not a file
# ---------------------------------------------------------------------------


def returns_instead_of_writing(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    pattern: re.Pattern[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The session leaves no ``document`` and its return holds text matching ``pattern``."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        problems = [f"wrote {path}" for path in document_files(evidence, document)]
        if evidence.role_return is None or not pattern.search(evidence.role_return):
            problems.append(f"the return lacks {pattern.pattern!r}")
        return Failed("; ".join(problems)) if problems else Passed()

    def violation() -> SessionEvidence:
        return _with_document(role, document, "# Report\n")

    return clause(name, rule, binds, evaluate, violation)


# ---------------------------------------------------------------------------
# The workflow files a role writes follow its security items
# ---------------------------------------------------------------------------

WORKFLOW_FILE = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
FULL_SHA = re.compile(r"@[0-9a-f]{40}$")
CHECKOUT_ACTION = "actions/checkout"
PERSIST_CREDENTIALS = "persist-credentials"
BAD_WORKFLOW = (
    "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
    "      - uses: actions/checkout@v4\n"
)


def workflow_security(name: str, rule: RuleRef, role: Role) -> MechanicalCheck:
    """Every workflow file the session wrote pins its actions to a full SHA, sets empty
    top-level ``permissions``, a ``timeout-minutes`` on each job and ``persist-credentials:
    false`` on each checkout; a session that wrote none has nothing to hold to this."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        files = {p: t for p, t in sorted(evidence.repo.files.items()) if WORKFLOW_FILE.match(p)}
        if not files:
            return NotApplicable(f"the {role} wrote no workflow file")
        problems = [
            f"{path}: {p}" for path, text in files.items() for p in _workflow_problems(text)
        ]
        return Failed("; ".join(problems[:5])) if problems else Passed()

    def violation() -> SessionEvidence:
        return _with_document(role, ".github/workflows/ci.yml", BAD_WORKFLOW)

    return clause(name, rule, None, evaluate, violation)


def _workflow_problems(text: str) -> list[str]:
    try:
        workflow = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return [f"not valid YAML ({type(error).__name__})"]
    if not isinstance(workflow, dict):
        return ["not a workflow mapping"]
    problems = [] if workflow.get("permissions") == {} else ["no top-level `permissions: {}`"]
    jobs = workflow.get("jobs")
    for job_name, job in jobs.items() if isinstance(jobs, dict) else ():
        if isinstance(job, dict):
            problems.extend(_job_problems(str(job_name), job))
    return problems


def _job_problems(job_name: str, job: Mapping[str, object]) -> list[str]:
    reusable = job.get("uses")
    steps = job.get("steps")
    uses = [reusable] if isinstance(reusable, str) else []
    problems = (
        [] if reusable or "timeout-minutes" in job else [f"job {job_name}: no timeout-minutes"]
    )
    for step in steps if isinstance(steps, list) else ():
        if not isinstance(step, dict) or not isinstance(step.get("uses"), str):
            continue
        uses.append(step["uses"])
        if step["uses"].startswith(CHECKOUT_ACTION) and _persists_credentials(step):
            problems.append(f"job {job_name}: checkout without `persist-credentials: false`")
    return problems + [
        f"job {job_name}: {u} is not pinned to a full SHA" for u in uses if _loose(u)
    ]


def _persists_credentials(step: Mapping[str, object]) -> bool:
    options = step.get("with")
    return not (isinstance(options, dict) and options.get(PERSIST_CREDENTIALS) is False)


def _loose(action: str) -> bool:
    """A remote action reference that is not pinned to a 40-character commit."""
    return not action.startswith(("./", "docker://")) and not FULL_SHA.search(action)


# ---------------------------------------------------------------------------
# A role's spawns of another role: how many, and what each is told
# ---------------------------------------------------------------------------


def _spawns(evidence: SessionEvidence, subagent: str) -> list[ToolUse]:
    return [
        use
        for use in evidence.role_tool_uses
        if use.name in SPAWN_TOOLS and use.input.get("subagent_type") == subagent
    ]


def spawn_fan_out(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    subagent: str,
    wave: int,
    total: int,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The role spawns ``subagent`` at most ``wave`` at a time and ``total`` in all.

    The recorded stream orders the spawns but not the results between them, so where a
    wave ends is not readable: more than ``total`` fails, no more than ``wave`` passes, and
    a count between is withheld rather than guessed.
    """

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        count = len(_spawns(evidence, subagent))
        if count > total:
            return Failed(f"{count} {subagent} spawns against a cap of {total} in all")
        if count > wave:
            return Withheld(f"{count} spawns recorded; the stream does not show where a wave ends")
        return Passed()

    def violation() -> SessionEvidence:
        spawns = [_spawn(index, subagent, "audit a lens") for index in range(total + 1)]
        return _with_tool_uses(role, spawns)

    return clause(name, rule, binds, evaluate, violation)


def spawn_prompts_carry(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    subagent: str,
    deliverable: re.Pattern[str],
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """Each prompt the role gives a ``subagent`` holds the task slug and names the ``deliverable``."""

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        spawns = _spawns(evidence, subagent)
        if not spawns:
            return NotApplicable(f"the {role} spawned no {subagent}")
        slug_line = f"Task slug: {evidence.slug}"
        problems = [
            f"spawn {position} {gap}"
            for position, use in enumerate(spawns, start=1)
            for gap in _prompt_gaps(str(use.input.get("prompt", "")), slug_line, deliverable)
        ]
        return Failed("; ".join(problems[:5])) if problems else Passed()

    def violation() -> SessionEvidence:
        return _with_tool_uses(role, [_spawn(0, subagent, "audit a lens")])

    return clause(name, rule, binds, evaluate, violation)


def _prompt_gaps(prompt: str, slug_line: str, deliverable: re.Pattern[str]) -> list[str]:
    gaps = [] if slug_line in prompt else [f"lacks {slug_line!r}"]
    return gaps if deliverable.search(prompt) else [*gaps, f"lacks {deliverable.pattern!r}"]


def _spawn(index: int, subagent: str, prompt: str) -> ToolUse:
    return ToolUse(
        f"canary-spawn-{index}", "Agent", {"subagent_type": subagent, "prompt": prompt}, None
    )


# ---------------------------------------------------------------------------
# A log that holds prior entries keeps them verbatim and gains one
# ---------------------------------------------------------------------------


def log_preserved(
    name: str,
    rule: RuleRef,
    role: Role,
    *,
    document: str,
    section: str,
    binds: BindsFor | None = None,
) -> MechanicalCheck:
    """The entries of ``section`` as the role first read the document all survive it, and it adds one.

    The prior entries are the ones in the result of the role's first Read of the document;
    a session that never read it has no prior state to compare, which is withheld.
    """

    def evaluate(evidence: SessionEvidence) -> CheckOutcome:
        path, text = slug_document(evidence, document)
        prior = _entries_first_read(evidence, path, section)
        if prior is None:
            return Withheld(f"the session never read {path}, so its prior {section} is unknown")
        kept = _entries(text, section)
        lost = [entry for entry in prior if entry not in kept]
        if lost:
            return Failed(f"{section} lost or rewrote {len(lost)} prior entries: {lost[0][:60]!r}")
        if len(kept) <= len(prior):
            return Failed(f"{section} gained no entry in {path}")
        return Passed()

    def violation() -> SessionEvidence:
        path = canary_path(document)
        read = ToolUse("canary-read", "Read", {"file_path": path}, None)
        shown = f"     1\t## {section}\n     2\t- 2026-01-01 decided x\n"
        return _with_document(
            role,
            document,
            f"## {section}\n- 2026-01-02 rewrote the entry\n",
            tool_uses=[read],
            tool_results={read.id: shown},
        )

    return clause(name, rule, binds, evaluate, violation)


def _entries_first_read(evidence: SessionEvidence, path: str, section: str) -> list[str] | None:
    cwd = session_cwd(evidence)
    for use in evidence.role_tool_uses:
        if use.name == "Read" and _repo_relative(str(use.input.get("file_path", "")), cwd) == path:
            shown = evidence.envelope.tool_results.get(use.id, "")
            return _entries(_without_line_numbers(shown), section)
    return None


def _without_line_numbers(read_result: str) -> str:
    return "\n".join(_READ_LINE_NUMBER.sub("", line) for line in read_result.splitlines())


def _entries(text: str, section: str) -> list[str]:
    return [line.strip() for line in section_body(text, section) or () if line.lstrip()[:2] == "- "]


# ---------------------------------------------------------------------------
# Canary evidence
# ---------------------------------------------------------------------------


def _with_document(
    role: Role,
    document: str,
    text: str,
    *,
    tool_uses: Sequence[ToolUse] = (),
    tool_results: Mapping[str, str] | None = None,
) -> SessionEvidence:
    return synthetic_evidence(
        role,
        slug=CANARY_SLUG,
        files={canary_path(document): text},
        tool_uses=tool_uses,
        tool_results=tool_results,
    )


def _with_tool_uses(role: Role, tool_uses: Sequence[ToolUse]) -> SessionEvidence:
    return synthetic_evidence(role, slug=CANARY_SLUG, tool_uses=tool_uses)
