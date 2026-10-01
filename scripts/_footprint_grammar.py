"""Footprint criteria: the contract that bounds what a change may cost.

This module is the shared contract of `check_footprint_criteria.py`.

A footprint is a measurable cost a change can move: always-loaded tokens, prompt
size, suite time. A change that moves one carries a quantitative criterion in
its spec, the plan measures it, and the verifier fails a missing or
out-of-bound value. This command owns the three grammars that carry that
through, and does the mechanical half of the judgment: which footprints moved,
and whether each bounded footprint has a valid, fresh measurement. Whether a
value is within its limit stays with the verifier. The instruments measure and
never judge, and this command never runs one.

This docstring is the one normative text for the grammars, the finding table and
the stages. The reference and the agent prompts point here; a test parses the
finding table below and compares it row by row with `FINDING_TABLE`. The
command's own contract (arguments, exit codes, `--json`) is in the docstring of
`check_footprint_criteria.py`.

Inactive by construction. With no registry and no footprint table in the spec,
`active` is false and there are no findings: a footprint-free change pays nothing.

Grammar 1, spec tables. Both sit inside `## Acceptance Criteria` of
`.ai-work/<slug>/SYSTEMS_PLAN.md`, are optional, and are read by header name
(a new optional column goes after the last one; a renamed header is a break):

    ### Footprint Criteria
    | Id | Footprint | Metric | Comparator | Limit | Against | Command |
    | FC-01 | prompt-size | longest prompt, in lines | at or below | 400 lines | baseline: 398 lines | `python3 scripts/check_agent_prompt_size.py --json` |

    ### Footprints Not Measured
    | Footprint | Reason |
    | spawn-count | the only spawn-count command counts a pipeline that has already run |

  - Id is `FC-` and two or more ASCII digits, and is unique in the spec.
  - Every cell is non-empty after trimming; a literal pipe is written `\\|`.
    Metric, Comparator, Limit and the text after the Against prefix must hold
    substance: a cell that is a placeholder (below) is `missing-cell`.
  - Against is `baseline: <text>` or `reference: <text>` (case-insensitive prefix,
    non-empty text). A baseline obliges a baseline measurement row; a reference
    does not (the limit is absolute, or the command compares against a reference
    revision itself).
  - Command holds exactly one backticked span; its text is the command.
  - A text is a placeholder when it holds no letter or digit, or when every word
    in it is one of `na`, `n/a`, `none`, `none yet`, `not applicable`, `nil`,
    `pending`, `tbd`, `tbc`, `tba` or `todo`, ignoring case, spacing, punctuation
    and backticks: so `-`, `—`, `?`, `n/a.`, `N / A`, `` `tbd` ``, `n/a, tbd` and
    `none (tbd)` all are. The list is finite, a declared limit: a synonym outside
    it (`to be determined`, `TBD for now`) reads as a real reason, and the
    verifier's judgment catches it. A declaration reason that is a placeholder is
    `reasonless`: it counts as a missing criterion.
  - A footprint is bounded or declared, never both (`bounded-and-declared`).
    Footprint names match the registry by trimmed, case-insensitive equality.
  - A heading with no table, or a table with no rows, is `empty-table`.
  - A section's one table is the first table outside code; the other
    pipe-row lines in the section (rows after a blank, comment or prose line, a
    second table) are `stray-row`, never dropped silently. A row with more cells
    than the header is `extra-cell` (an unescaped pipe would truncate it).
  - A table with the seven criteria columns anywhere in the plan outside its own
    `###` section (a renamed or re-levelled heading) is `misplaced-table`;
    otherwise the spec would read as footprint-free. Inside
    `## Acceptance Criteria` so is a `Footprint | Reason` table; outside it that
    two-column shape is generic and never reported. The finding gives the line:
    to quote an example, fence it.
  - Code is never read or reported: fenced blocks (an outer fence encloses an
    inner one) and indented blocks are examples. The reading rules for code,
    sections and tables are in `_markdown_tables.py`.
  - Header names are matched case-insensitively. Everything else is matched
    exactly, not case-folded or coerced: ids and heads are ASCII.

Grammar 2, registry. `.ai-state/FOOTPRINTS.md`, optional, per project, owned by
the project and only read here. The first table in the file outside code;
other pipe rows and a file with no table are reported (`malformed`):

    | Footprint | Paths | Command | Reading |
    | prompt-size | agents/*.md, !agents/README.md | `python3 scripts/check_agent_prompt_size.py --json` | line counts |
    | hook-latency | hooks/*.py, hooks/hooks.json | none | — |

  - Footprint is lowercase kebab-case and unique.
  - Paths is a comma-separated list of `fnmatch` globs over repo-relative POSIX
    paths, where `*` crosses `/`; a leading `!` excludes. At least one include
    glob is required.
  - A lone `!` is `malformed`.
  - Command is one backticked span, or the word `none` (no instrument exists);
    a backticked `none` means the same and is read as no command.
  - Reading is free text and optional.
  - An absent registry is the legal state `NoRegistry`. A defective row never
    disables the check silently: it is reported (FP05) and that row is skipped.

Grammar 3, measurement log. `.ai-work/<slug>/MEASUREMENTS.md`, append-only, one
row per reading, written by the measurement steps of the plan:

    | Criterion | Phase | Value | Reading | Head | Taken | Command |
    | FC-01 | baseline | 398 lines | measured | f4d953a6 | 2026-10-01T09:16Z | `python3 scripts/check_agent_prompt_size.py --json` |

  - Criterion is a spec id; Phase is exactly `baseline` or `final`.
  - Reading is exactly `measured`, `estimate`, or `none: <reason>` (a withheld
    reading, with a reason that is not a placeholder). Value must hold substance
    unless the reading is `none: <reason>`.
  - Head is the 8-character `git rev-parse --short=8 HEAD` (lowercase hex) at
    measurement time; Taken is UTC ISO-8601 to the minute, in this exact shape:
    `2026-10-01T09:16Z`.
  - Command is the exact command run, one backticked span. It must contain the
    criterion's command text: a filled-in `--compare-ref <sha>` is the same
    instrument.
  - Identity: the latest row per (criterion, phase) in document order is
    authoritative; earlier rows are history and are never edited. No log, and a
    log with no rows yet, are not defects. Content that holds no table is
    `bad-header`; pipe rows outside the one table read are `stray-row`.

Findings. A row that breaks its grammar becomes a finding, never an exception.
Each finding is `{code, severity, footprint, criterion, reason, message}`;
severity is `fail`, `warn` or `info`, and comes from this table:

    code  name          severity  stages              reasons
    FP01  unbounded     warn      plan, verify        unbounded
    FP02  malformed     fail      spec, plan, verify  bad-header, empty-table, missing-cell,
                                                      bad-id, duplicate-id, bad-against,
                                                      command-span, reasonless,
                                                      bounded-and-declared, unknown-criterion,
                                                      bad-phase, bad-reading, bad-head,
                                                      bad-taken, misplaced-table,
                                                      stray-row, extra-cell
    FP03  unmeasured    fail      verify              missing-final, missing-baseline,
                                                      no-reading, stale-final, late-baseline,
                                                      incomparable, wrong-command
    FP04  unregistered  info      spec, plan, verify  unregistered
    FP05  registry      warn      spec, plan, verify  malformed, duplicate, dead-glob

  - FP01: a registry footprint moved by the given paths or the diff has no row in
    either table. The finding names the footprint and the matching paths.
  - FP02: a spec or log row breaks its grammar. `unknown-criterion` is a log row
    that names no spec id. `misplaced-table`, `stray-row` and `extra-cell` mean
    content the parser would otherwise have ignored.
  - FP03: no valid measurement. `stale-final`: a change touched the footprint's
    paths after the final row's head. `late-baseline`: a change touched them
    between the base and the baseline row's head. `incomparable`: baseline and
    final differ in reading kind. `wrong-command`: the log command does not
    contain the criterion's command.
  - FP04: a spec footprint is not in the registry, or there is no registry.
    Freshness then falls back to "any tracked change outside `.ai-state/`" and
    late-baseline is not checked.
  - FP05: a registry row is malformed, duplicated, or an include glob matches no
    tracked file (`dead-glob`).

Stages, a closed set:

  - spec: FP02 over the spec tables, plus FP04 and FP05.
  - plan: the spec checks, plus FP01 over `--paths`.
  - verify: the plan checks over the diff in place of `--paths`, plus FP03 and
    the log's FP02.

Stdlib-only and Python 3.9-safe (no runtime `X | Y` unions, no `match`, no
slotted dataclasses): the command runs under whichever bare `python3` the
project has. Tests: `scripts/test__footprint_grammar.py`,
`scripts/test__markdown_tables.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, Union

from _markdown_tables import (
    Block,
    Table,
    as_table,
    blocks,
    find_section,
    has_content,
    slice_lines,
    split_lines,
    stray_messages,
    subsection,
    table_and_strays,
)

# --- vocabulary -----------------------------------------------------------------------------

STAGES = ("spec", "plan", "verify")
PHASES = ("baseline", "final")
PLACEHOLDER_REASONS = frozenset(
    ("-", "—", "?", "n/a", "na", "none", "none yet", "not applicable", "nil", "pending")
    + ("tbd", "tbc", "tba", "todo")
)

FAIL, WARN, INFO = "fail", "warn", "info"


@dataclass(frozen=True)
class FindingSpec:
    code: str
    name: str
    severity: str
    stages: tuple[str, ...]
    reasons: tuple[str, ...]


FINDING_TABLE = (
    FindingSpec("FP01", "unbounded", WARN, ("plan", "verify"), ("unbounded",)),
    FindingSpec(
        "FP02",
        "malformed",
        FAIL,
        STAGES,
        (
            "bad-header",
            "empty-table",
            "missing-cell",
            "bad-id",
            "duplicate-id",
            "bad-against",
            "command-span",
            "reasonless",
            "bounded-and-declared",
            "unknown-criterion",
            "bad-phase",
            "bad-reading",
            "bad-head",
            "bad-taken",
            "misplaced-table",
            "stray-row",
            "extra-cell",
        ),
    ),
    FindingSpec(
        "FP03",
        "unmeasured",
        FAIL,
        ("verify",),
        (
            "missing-final",
            "missing-baseline",
            "no-reading",
            "stale-final",
            "late-baseline",
            "incomparable",
            "wrong-command",
        ),
    ),
    FindingSpec("FP04", "unregistered", INFO, STAGES, ("unregistered",)),
    FindingSpec("FP05", "registry", WARN, STAGES, ("malformed", "duplicate", "dead-glob")),
)
_SPEC_BY_CODE = {spec.code: spec for spec in FINDING_TABLE}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    footprint: str | None
    criterion: str | None
    reason: str
    message: str


def make_finding(
    code: str,
    reason: str,
    message: str,
    *,
    footprint: str | None = None,
    criterion: str | None = None,
) -> Finding:
    """A finding whose severity comes from the table; an unknown code or reason is a bug."""
    spec = _SPEC_BY_CODE.get(code)
    if spec is None or reason not in spec.reasons:
        raise ValueError(f"{code}/{reason} is not in FINDING_TABLE")
    return Finding(code, spec.severity, footprint, criterion, reason, message)


# --- parsed values --------------------------------------------------------------------------


@dataclass(frozen=True)
class Baseline:
    """The limit is judged against a baseline reading taken before the change."""

    text: str


@dataclass(frozen=True)
class Reference:
    """The limit is absolute, or the command compares against a reference itself."""

    text: str


Against = Union[Baseline, Reference]  # noqa: UP007 -- a runtime alias: `X | Y` needs 3.10


@dataclass(frozen=True)
class Criterion:
    id: str
    footprint: str
    metric: str
    comparator: str
    limit: str
    against: Against
    command: str


@dataclass(frozen=True)
class NotMeasured:
    footprint: str
    reason: str


@dataclass(frozen=True)
class SpecTables:
    criteria: tuple[Criterion, ...]
    not_measured: tuple[NotMeasured, ...]
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Footprint:
    name: str
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...]
    command: str | None  # None: no instrument exists
    reading: str


@dataclass(frozen=True)
class Registry:
    footprints: tuple[Footprint, ...]


@dataclass(frozen=True)
class NoRegistry:
    """No `.ai-state/FOOTPRINTS.md`: a legal state, not a defect."""


@dataclass(frozen=True)
class RegistryParse:
    registry: Registry | NoRegistry
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class Measured:
    """The instrument labelled its reading as measured."""


@dataclass(frozen=True)
class Estimate:
    """The instrument labelled its reading as an estimate."""


@dataclass(frozen=True)
class NoReading:
    """The instrument withheld a reading, for a stated reason."""

    reason: str


Reading = Union[Measured, Estimate, NoReading]  # noqa: UP007 -- a runtime alias: `X | Y` needs 3.10


@dataclass(frozen=True)
class Measurement:
    criterion: str
    phase: str
    value: str
    reading: Reading
    head: str
    taken: str
    command: str


@dataclass(frozen=True)
class LogParse:
    measurements: tuple[Measurement, ...]
    findings: tuple[Finding, ...]


# --- parsers --------------------------------------------------------------------------------

ACCEPTANCE_HEADING = "Acceptance Criteria"
CRITERIA_HEADING = "Footprint Criteria"
DECLARATIONS_HEADING = "Footprints Not Measured"

_CRITERIA_COLUMNS = ("id", "footprint", "metric", "comparator", "limit", "against", "command")
_CRITERIA_SUBSTANTIVE = ("metric", "comparator", "limit")
_DECLARATION_COLUMNS = ("footprint", "reason")
_REGISTRY_COLUMNS = ("footprint", "paths", "command")
_LOG_COLUMNS = ("criterion", "phase", "value", "reading", "head", "taken", "command")

# Every token pattern is ASCII-only and matched in full: `\d` would admit full-width digits.
_CRITERION_ID = re.compile(r"FC-[0-9]{2,}")
_FOOTPRINT_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_HEAD = re.compile(r"[0-9a-f]{8}")
_TAKEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z")
_TAKEN_FORMAT = "%Y-%m-%dT%H:%MZ"
_AGAINST_PREFIX = re.compile(r"(?is)(baseline|reference):\s*(.*)")
_BACKTICKED = re.compile(r"`([^`]+)`")
_NON_SUBSTANCE = re.compile(r"[\W_]+")
_PLACEHOLDER_WORDS = {_NON_SUBSTANCE.sub("", word) for word in PLACEHOLDER_REASONS} - {""}
# A text reduced to its letters and digits is a placeholder when it is a run of placeholder words
# (`n/a, tbd` -> `natbd`); longest first, so that `none yet` is not read as `none` and a stray `yet`.
_PLACEHOLDER_RUN = re.compile(
    "(?:" + "|".join(sorted(_PLACEHOLDER_WORDS, key=len, reverse=True)) + ")*"
)
_NONE_PREFIX = "none:"


def footprint_key(name: str) -> str:
    """The form in which footprint names are compared: trimmed, case-insensitive."""
    return name.strip().lower()


def parse_spec_tables(plan_text: str) -> SpecTables:
    """Both optional tables of `## Acceptance Criteria`, with a finding per broken row."""
    lines = split_lines(plan_text)
    acceptance = find_section(lines, 2, ACCEPTANCE_HEADING)
    criteria_span = subsection(lines, acceptance, CRITERIA_HEADING)
    declared_span = subsection(lines, acceptance, DECLARATIONS_HEADING)
    criteria, findings = _parse_criteria(slice_lines(lines, criteria_span))
    declared, declaration_findings = _parse_declarations(slice_lines(lines, declared_span))
    recognised = [span for span in (criteria_span, declared_span) if span is not None]
    findings += declaration_findings + _misplaced_tables(lines, recognised, acceptance)
    bounded = {footprint_key(c.footprint) for c in criteria}
    kept = []
    for item in declared:
        if footprint_key(item.footprint) in bounded:
            findings.append(
                _malformed(
                    "bounded-and-declared",
                    f"{item.footprint} has a criterion and is also declared not measured",
                    footprint=item.footprint,
                )
            )
        else:
            kept.append(item)
    return SpecTables(tuple(criteria), tuple(kept), tuple(findings))


def parse_registry(text: str | None) -> RegistryParse:
    """The footprint registry; `None` (no file) is the legal `NoRegistry` state."""
    if text is None:
        return RegistryParse(NoRegistry(), ())
    table, strays = table_and_strays(split_lines(text))
    findings = [_registry_defect("malformed", message) for message in stray_messages(strays)]
    if table is None or not table.rows:
        what = "has no table" if table is None else "has no rows"
        findings.append(_registry_defect("malformed", f"registry {what}"))
        return RegistryParse(Registry(()), tuple(findings))
    rows, defects = _read_rows(table, _REGISTRY_COLUMNS, optional=("reading",))
    findings += [_registry_defect("malformed", d.message, d.key) for d in defects]
    footprints: dict[str, Footprint] = {}
    for number, row in rows:
        built = _footprint(row)
        if isinstance(built, _Bad):
            message = f"row {number}: {built.message}"
            findings.append(_registry_defect("malformed", message, row["footprint"]))
        elif built.name in footprints:
            message = f"row {number}: {built.name} is listed twice"
            findings.append(_registry_defect("duplicate", message, built.name))
        else:
            footprints[built.name] = built
    return RegistryParse(Registry(tuple(footprints.values())), tuple(findings))


def parse_measurements(text: str) -> LogParse:
    """The measurement log rows, with a finding per row or block that breaks the grammar."""
    lines = split_lines(text)
    table, strays = table_and_strays(lines)
    findings = [_malformed("stray-row", message) for message in stray_messages(strays)]
    if table is None:
        if not strays and has_content(lines):
            findings.append(_malformed("bad-header", "the log has content but no table"))
        return LogParse((), tuple(findings))
    rows, defects = _read_rows(table, _LOG_COLUMNS)
    findings += [_malformed(d.reason, d.message, criterion=d.key) for d in defects]
    measurements = []
    for number, row in rows:
        built = _measurement(row)
        if isinstance(built, _Bad):
            message = f"log row {number}: {built.message}"
            findings.append(_malformed(built.reason, message, criterion=row["criterion"]))
        else:
            measurements.append(built)
    return LogParse(tuple(measurements), tuple(findings))


def latest(measurements: tuple[Measurement, ...]) -> dict[tuple[str, str], Measurement]:
    """The authoritative row per (criterion, phase): the last one in document order."""
    return {(m.criterion, m.phase): m for m in measurements}


# --- spec sections --------------------------------------------------------------------------


def _parse_criteria(section: list[str] | None) -> tuple[list[Criterion], list[Finding]]:
    if section is None:
        return [], []
    rows, findings = _section_rows(
        section, CRITERIA_HEADING, _CRITERIA_COLUMNS, _CRITERIA_SUBSTANTIVE, "criterion"
    )
    criteria: list[Criterion] = []
    seen: set[str] = set()
    for number, row in rows:
        built = _criterion(row, seen)
        if isinstance(built, _Bad):
            message = f"{CRITERIA_HEADING} row {number}: {built.message}"
            findings.append(_malformed(built.reason, message, criterion=row["id"]))
        else:
            seen.add(built.id)
            criteria.append(built)
    return criteria, findings


def _parse_declarations(section: list[str] | None) -> tuple[list[NotMeasured], list[Finding]]:
    if section is None:
        return [], []
    rows, findings = _section_rows(
        section, DECLARATIONS_HEADING, _DECLARATION_COLUMNS, (), "footprint"
    )
    declared = []
    for number, row in rows:
        if _is_placeholder(row["reason"]):
            message = (
                f"{DECLARATIONS_HEADING} row {number}: reason {row['reason']!r} is a placeholder"
            )
            findings.append(_malformed("reasonless", message, footprint=row["footprint"]))
        else:
            declared.append(NotMeasured(row["footprint"], row["reason"]))
    return declared, findings


def _section_rows(
    section: list[str],
    heading: str,
    columns: tuple[str, ...],
    substantive: tuple[str, ...],
    key_field: str,
) -> tuple[list[tuple[int, dict[str, str]]], list[Finding]]:
    """The complete rows of the one table under `heading`, and a finding for all else in it."""
    table, strays = table_and_strays(section)
    findings = [_malformed("stray-row", f"{heading}: {m}") for m in stray_messages(strays)]
    if table is None or not table.rows:
        findings.append(_malformed("empty-table", f"{heading} holds no table rows"))
        return [], findings
    rows, defects = _read_rows(table, columns, substantive=substantive)
    for defect in defects:
        message = f"{heading} {defect.message}"
        findings.append(_malformed(defect.reason, message, **{key_field: defect.key}))
    return rows, findings


def _misplaced_tables(
    lines: list[str], recognised: list[tuple[int, int]], acceptance: tuple[int, int] | None
) -> list[Finding]:
    """Tables that carry a spec table's columns but sit outside the section that is read.

    A renamed section heading otherwise leaves the spec reading as footprint-free.
    """
    found = []
    for block in blocks(lines):
        table = as_table(block)
        if table is None or any(_inside(block, span) for span in recognised):
            continue
        heading = _heading_for_columns(table.header, _inside(block, acceptance))
        if heading is not None:
            message = (
                f"line {block.start + 1}: a '{heading}' table sits outside a '### {heading}' "
                "section; put a quoted example in a code fence"
            )
            found.append(_malformed("misplaced-table", message))
    return found


def _inside(block: Block, span: tuple[int, int] | None) -> bool:
    return span is not None and span[0] <= block.start < span[1]


def _heading_for_columns(header: tuple[str, ...], in_acceptance: bool) -> str | None:
    """The generic two-column shape only counts inside `## Acceptance Criteria`."""
    if all(column in header for column in _CRITERIA_COLUMNS):
        return CRITERIA_HEADING
    if in_acceptance and header == _DECLARATION_COLUMNS:
        return DECLARATIONS_HEADING
    return None


# --- row validators: one enforcer per invariant ---------------------------------------------


@dataclass(frozen=True)
class _Bad:
    reason: str
    message: str


def _criterion(row: dict[str, str], seen: set[str]) -> Criterion | _Bad:
    if not _CRITERION_ID.fullmatch(row["id"]):
        return _Bad("bad-id", f"id {row['id']!r} does not match FC-<2+ ASCII digits>")
    if row["id"] in seen:
        return _Bad("duplicate-id", f"id {row['id']} is used twice")
    against = _against(row["against"])
    if against is None:
        return _Bad(
            "bad-against",
            f"against {row['against']!r} is not 'baseline: <text>' or 'reference: <text>'",
        )
    command = _single_span(row["command"])
    if command is None:
        return _Bad("command-span", _span_message(row["command"]))
    return Criterion(
        row["id"],
        row["footprint"],
        row["metric"],
        row["comparator"],
        row["limit"],
        against,
        command,
    )


def _footprint(row: dict[str, str]) -> Footprint | _Bad:
    name = row["footprint"]
    if not _FOOTPRINT_NAME.fullmatch(name):
        return _Bad("malformed", f"name {name!r} is not lowercase kebab-case")
    globs = [g.strip() for g in row["paths"].split(",") if g.strip()]
    include = tuple(g for g in globs if not g.startswith("!"))
    exclude = tuple(g[1:].strip() for g in globs if g.startswith("!"))
    if "" in exclude:
        return _Bad("malformed", f"{name} has an empty exclude glob ('!' alone)")
    if not include:
        return _Bad("malformed", f"{name} has no include glob")
    command = _footprint_command(row["command"])
    if isinstance(command, _Bad):
        return _Bad("malformed", f"{name}: {command.message}")
    return Footprint(name, include, exclude, command, row.get("reading", ""))


def _footprint_command(cell: str) -> str | _Bad | None:
    """The one backticked span, or None for `none` (bare or backticked): no instrument."""
    span = _single_span(cell)
    if cell.strip().lower() == "none" or (span is not None and span.lower() == "none"):
        return None
    if span is None:
        return _Bad("command-span", "command must be one backticked span or 'none'")
    return span


def _measurement(row: dict[str, str]) -> Measurement | _Bad:
    if not _CRITERION_ID.fullmatch(row["criterion"]):
        return _Bad("bad-id", f"criterion {row['criterion']!r} does not match FC-<2+ ASCII digits>")
    if row["phase"] not in PHASES:
        return _Bad("bad-phase", f"phase {row['phase']!r} is not exactly baseline or final")
    reading = _reading(row["reading"])
    if isinstance(reading, _Bad):
        return reading
    if not isinstance(reading, NoReading) and _is_placeholder(row["value"]):
        return _Bad("missing-cell", f"value {row['value']!r} is a placeholder for a reading")
    if not _HEAD.fullmatch(row["head"]):
        return _Bad("bad-head", f"head {row['head']!r} is not 8 lowercase hex characters")
    if not _is_utc_minute(row["taken"]):
        return _Bad("bad-taken", f"taken {row['taken']!r} is not UTC ISO-8601 to the minute")
    command = _single_span(row["command"])
    if command is None:
        return _Bad("command-span", _span_message(row["command"]))
    return Measurement(
        row["criterion"], row["phase"], row["value"], reading, row["head"], row["taken"], command
    )


def _reading(cell: str) -> Reading | _Bad:
    text = cell.strip()
    if text == "measured":
        return Measured()
    if text == "estimate":
        return Estimate()
    if text == "none" or text.startswith(_NONE_PREFIX):
        reason = text[len(_NONE_PREFIX) :].strip()
        if _is_placeholder(reason):
            return _Bad(
                "reasonless", "a withheld reading needs 'none: <reason>' with a real reason"
            )
        return NoReading(reason)
    return _Bad(
        "bad-reading", f"reading {cell!r} is not exactly measured, estimate or 'none: <reason>'"
    )


def _against(cell: str) -> Against | None:
    match = _AGAINST_PREFIX.fullmatch(cell.strip())
    if match is None or _is_placeholder(match.group(2)):
        return None
    text = match.group(2).strip()
    return Baseline(text) if match.group(1).lower() == "baseline" else Reference(text)


def _single_span(cell: str) -> str | None:
    """The text of the cell's one backticked span; a dangling backtick is not a span."""
    spans = _BACKTICKED.findall(cell)
    if len(spans) != 1 or cell.count("`") != 2:
        return None
    return spans[0].strip() or None


def _span_message(cell: str) -> str:
    return f"command {cell!r} must hold exactly one backticked span"


def _is_placeholder(text: str) -> bool:
    """No letter or digit, or only placeholder words once punctuation, case and spacing are gone."""
    return _PLACEHOLDER_RUN.fullmatch(_NON_SUBSTANCE.sub("", text.lower())) is not None


def _is_utc_minute(text: str) -> bool:
    if not _TAKEN.fullmatch(text):
        return False
    try:
        datetime.strptime(text, _TAKEN_FORMAT)
    except ValueError:
        return False
    return True


def _malformed(
    reason: str, message: str, *, footprint: str | None = None, criterion: str | None = None
) -> Finding:
    return make_finding("FP02", reason, message, footprint=footprint, criterion=criterion)


def _registry_defect(reason: str, message: str, footprint: str | None = None) -> Finding:
    return make_finding("FP05", reason, message, footprint=footprint)


class _Defect(NamedTuple):
    reason: str
    message: str
    key: str | None


def _read_rows(
    table: Table,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    substantive: tuple[str, ...] = (),
) -> tuple[list[tuple[int, dict[str, str]]], list[_Defect]]:
    """Complete rows as {column: cell} with their 1-based numbers, and a defect per unusable row.

    A row is unusable when a required cell is empty, a `substantive` cell is a
    placeholder, or it has more cells than the header (an unescaped pipe would
    otherwise truncate the last cell without a trace).
    """
    index = {name: position for position, name in enumerate(table.header)}
    missing = [name for name in required if name not in index]
    if missing:
        return [], [_Defect("bad-header", f"header lacks column(s): {', '.join(missing)}", None)]
    rows, defects = [], []
    for number, cells in enumerate(table.rows, start=1):
        row = {name: _cell(cells, index.get(name)) for name in (*required, *optional)}
        key = row[required[0]] or None
        empty = [name for name in required if not row[name]]
        hollow = [name for name in substantive if row[name] and _is_placeholder(row[name])]
        if len(cells) > len(table.header):
            message = f"row {number}: {len(cells)} cells under {len(table.header)} columns"
            defects.append(_Defect("extra-cell", f"{message} (write a literal pipe as \\|)", key))
        elif empty or hollow:
            names = ", ".join(empty + hollow)
            defects.append(
                _Defect("missing-cell", f"row {number}: empty or placeholder: {names}", key)
            )
        else:
            rows.append((number, row))
    return rows, defects


def _cell(cells: tuple[str, ...], position: int | None) -> str:
    return cells[position] if position is not None and position < len(cells) else ""
