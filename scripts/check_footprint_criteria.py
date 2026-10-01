#!/usr/bin/env python3
"""Footprint criteria check: the contract that bounds what a change may cost.

    check_footprint_criteria.py <slug> [--stage spec|plan|verify] [--paths PATH ...]
            [--base-ref REF] [--repo-root DIR] [--json]

A footprint is a measurable cost a change can move: always-loaded tokens, prompt
size, suite time. A change that moves one carries a quantitative criterion in
its spec, the plan measures it, and the verifier fails a missing or
out-of-bound value. This command owns the three grammars that carry that
through, and does the mechanical half of the judgment: which footprints moved,
and whether each bounded footprint has a valid, fresh measurement. Whether a
value is within its limit stays with the verifier. The instruments measure and
never judge, and this command never runs one.

This docstring is the one normative text. The reference and the agent prompts
point here; `FINDING_TABLE` below is pinned against it by a test. The module
holds the contract (grammars, types, finding table). The judge, the git edge and
the CLI described below are added to the same file by later steps.

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

  - Id matches `FC-\\d{2,}` and is unique in the spec.
  - Every cell is non-empty after trimming; a literal pipe is written `\\|`.
  - Against is `baseline: <text>` or `reference: <text>` (case-insensitive prefix,
    non-empty text). A baseline obliges a baseline measurement row; a reference
    does not (the limit is absolute, or the command compares against a reference
    revision itself).
  - Command holds exactly one backticked span; its text is the command.
  - A reason that is a placeholder (`-`, `—`, `n/a`, `na`, `none`, `tbd`, `todo`,
    `?`, case-insensitive) is `reasonless`: it counts as a missing criterion.
  - A footprint is bounded or declared, never both (`bounded-and-declared`).
    Footprint names match the registry by trimmed, case-insensitive equality.
  - A heading with no table, or a table with no rows, is `empty-table`.

Grammar 2, registry. `.ai-state/FOOTPRINTS.md`, optional, per project, owned by
the project and only read here. The first table in the file:

    | Footprint | Paths | Command | Reading |
    | prompt-size | agents/*.md, !agents/README.md | `python3 scripts/check_agent_prompt_size.py --json` | line counts |
    | hook-latency | hooks/*.py, hooks/hooks.json | none | — |

  - Footprint is lowercase kebab-case and unique.
  - Paths is a comma-separated list of `fnmatch` globs over repo-relative POSIX
    paths, where `*` crosses `/`; a leading `!` excludes. At least one include
    glob is required.
  - Command is one backticked span, or the word `none` (no instrument exists).
  - Reading is free text and optional.
  - An absent registry is the legal state `NoRegistry`. A defective row never
    disables the check silently: it is reported (FP05) and that row is skipped.

Grammar 3, measurement log. `.ai-work/<slug>/MEASUREMENTS.md`, append-only, one
row per reading, written by the measurement steps of the plan:

    | Criterion | Phase | Value | Reading | Head | Taken | Command |
    | FC-01 | baseline | 398 lines | measured | f4d953a6 | 2026-10-01T09:16Z | `python3 scripts/check_agent_prompt_size.py --json` |

  - Criterion is a spec id; Phase is `baseline` or `final`.
  - Reading is `measured`, `estimate`, or `none: <reason>` (a withheld reading,
    with a reason that is not a placeholder).
  - Head is the 8-character `git rev-parse --short=8 HEAD` (lowercase hex) at
    measurement time; Taken is UTC ISO-8601 to the minute (`2026-10-01T09:16Z`).
  - Command is the exact command run, one backticked span. It must contain the
    criterion's command text: a filled-in `--compare-ref <sha>` is the same
    instrument.
  - Identity: the latest row per (criterion, phase) in document order is
    authoritative; earlier rows are history and are never edited. No log, and a
    log with no rows yet, are not defects.

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
                                                      bad-taken
    FP03  unmeasured    fail      verify              missing-final, missing-baseline,
                                                      no-reading, stale-final, late-baseline,
                                                      incomparable, wrong-command
    FP04  unregistered  info      spec, plan, verify  unregistered
    FP05  registry      warn      spec, plan, verify  malformed, duplicate, dead-glob

  - FP01: a registry footprint moved by the given paths or the diff has no row in
    either table. The finding names the footprint and the matching paths.
  - FP02: a spec or log row breaks its grammar. `unknown-criterion` is a log row
    that names no spec id.
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

CLI. `--stage` defaults to `verify`. `--paths` is required for `plan` and
rejected for the other stages. `--base-ref` is used only by `verify`; its default
is `git merge-base HEAD main`, and when that cannot be resolved the command exits
2 and asks for `--base-ref`. The repository root is `--repo-root`, else the git
toplevel of the working directory; it is never derived from this file's
location, because managed projects run the command through a `~/.local/bin`
symlink where that location is the plugin. The command reads
`.ai-work/<slug>/SYSTEMS_PLAN.md` (required), `.ai-state/FOOTPRINTS.md` and
`.ai-work/<slug>/MEASUREMENTS.md` (both if present). It runs only `git diff`,
`git ls-files`, `git rev-parse` and `git merge-base`, and never executes a
command named in a table or the registry.

Exit codes: `0` no `fail` finding (including the inactive case); `1` at least one
`fail` finding; `2` input error (bad arguments, the plan missing or without
`## Acceptance Criteria`, the base unresolvable); stderr names the input.

`--json` prints on stdout
`{"schema": 1, "slug", "stage", "active", "registry", "base_ref", "moved":
[{"footprint", "paths"}], "criteria", "not_measured", "measurements", "findings":
[{"code", "severity", "footprint", "criterion", "reason", "message"}]}`.
`active` is false exactly when there is no registry and the spec has neither
table.

Stdlib-only and Python 3.9-safe (no runtime `X | Y` unions, no `match`, no
slotted dataclasses): the command runs under whichever bare `python3` the
project has. Tests: `scripts/test_check_footprint_criteria.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple, Union

# --- vocabulary -----------------------------------------------------------------------------

STAGES = ("spec", "plan", "verify")
PHASES = ("baseline", "final")
PLACEHOLDER_REASONS = frozenset({"-", "—", "n/a", "na", "none", "tbd", "todo", "?"})

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
_DECLARATION_COLUMNS = ("footprint", "reason")
_REGISTRY_COLUMNS = ("footprint", "paths", "command")
_LOG_COLUMNS = ("criterion", "phase", "value", "reading", "head", "taken", "command")

_CRITERION_ID = re.compile(r"FC-\d{2,}")
_FOOTPRINT_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_HEAD = re.compile(r"[0-9a-f]{8}")
_TAKEN_FORMAT = "%Y-%m-%dT%H:%MZ"
_AGAINST_PREFIX = re.compile(r"(baseline|reference):\s*(.*)", re.IGNORECASE | re.DOTALL)
_BACKTICKED = re.compile(r"`([^`]+)`")


def footprint_key(name: str) -> str:
    """The form in which footprint names are compared: trimmed, case-insensitive."""
    return name.strip().lower()


def parse_spec_tables(plan_text: str) -> SpecTables:
    """Both optional tables of `## Acceptance Criteria`, with a finding per broken row."""
    acceptance = _section(_lines(plan_text), 2, ACCEPTANCE_HEADING) or []
    criteria, findings = _parse_criteria(_section(acceptance, 3, CRITERIA_HEADING))
    declared, declaration_findings = _parse_declarations(
        _section(acceptance, 3, DECLARATIONS_HEADING)
    )
    bounded = {footprint_key(c.footprint) for c in criteria}
    kept = []
    for item in declared:
        if footprint_key(item.footprint) in bounded:
            findings.append(
                make_finding(
                    "FP02",
                    "bounded-and-declared",
                    f"{item.footprint} has a criterion and is also declared not measured",
                    footprint=item.footprint,
                )
            )
        else:
            kept.append(item)
    return SpecTables(tuple(criteria), tuple(kept), tuple(findings + declaration_findings))


def parse_registry(text: str | None) -> RegistryParse:
    """The footprint registry; `None` (no file) is the legal `NoRegistry` state."""
    if text is None:
        return RegistryParse(NoRegistry(), ())
    table = _first_table(_lines(text))
    if table is None or not table.rows:
        what = "has no table" if table is None else "has no rows"
        return RegistryParse(Registry(()), (_registry_defect("malformed", f"registry {what}"),))
    rows, defects = _read_rows(table, _REGISTRY_COLUMNS, optional=("reading",))
    findings = [_registry_defect("malformed", d.message, d.key) for d in defects]
    footprints: dict[str, Footprint] = {}
    for number, row in rows:
        built = _footprint(row)
        if isinstance(built, _Bad):
            findings.append(
                _registry_defect("malformed", f"row {number}: {built.message}", row["footprint"])
            )
        elif built.name in footprints:
            findings.append(
                _registry_defect(
                    "duplicate", f"row {number}: {built.name} is listed twice", built.name
                )
            )
        else:
            footprints[built.name] = built
    return RegistryParse(Registry(tuple(footprints.values())), tuple(findings))


def parse_measurements(text: str) -> LogParse:
    """The measurement log rows, with a finding per row that breaks the grammar."""
    table = _first_table(_lines(text))
    if table is None:
        return LogParse((), ())
    rows, defects = _read_rows(table, _LOG_COLUMNS)
    findings = [_malformed(d.reason, d.message, criterion=d.key) for d in defects]
    measurements = []
    for number, row in rows:
        built = _measurement(row)
        if isinstance(built, _Bad):
            findings.append(
                _malformed(
                    built.reason, f"log row {number}: {built.message}", criterion=row["criterion"]
                )
            )
        else:
            measurements.append(built)
    return LogParse(tuple(measurements), tuple(findings))


def latest(measurements: tuple[Measurement, ...]) -> dict[tuple[str, str], Measurement]:
    """The authoritative row per (criterion, phase): the last one in document order."""
    return {(m.criterion, m.phase): m for m in measurements}


# --- row validators: one enforcer per invariant ---------------------------------------------


@dataclass(frozen=True)
class _Bad:
    reason: str
    message: str
    key: str | None = None


def _parse_criteria(section: list[str] | None) -> tuple[list[Criterion], list[Finding]]:
    if section is None:
        return [], []
    table = _first_table(section)
    if table is None or not table.rows:
        return [], [_malformed("empty-table", f"{CRITERIA_HEADING} holds no table rows")]
    rows, defects = _read_rows(table, _CRITERIA_COLUMNS)
    findings = [_malformed(d.reason, d.message, criterion=d.key) for d in defects]
    criteria: list[Criterion] = []
    seen = set()
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
    table = _first_table(section)
    if table is None or not table.rows:
        return [], [_malformed("empty-table", f"{DECLARATIONS_HEADING} holds no table rows")]
    rows, defects = _read_rows(table, _DECLARATION_COLUMNS)
    findings = [_malformed(d.reason, d.message, footprint=d.key) for d in defects]
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


def _criterion(row: dict[str, str], seen: set) -> Criterion | _Bad:
    if not _CRITERION_ID.fullmatch(row["id"]):
        return _Bad("bad-id", f"id {row['id']!r} does not match FC-<2+ digits>")
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
        return _Bad(
            "command-span", f"command {row['command']!r} must hold exactly one backticked span"
        )
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
    exclude = tuple(g[1:].strip() for g in globs if g.startswith("!") and g[1:].strip())
    if not include:
        return _Bad("malformed", f"{name} has no include glob")
    if row["command"].strip().lower() == "none":
        command = None
    else:
        command = _single_span(row["command"])
        if command is None:
            return _Bad("malformed", f"{name} command must be one backticked span or 'none'")
    return Footprint(name, include, exclude, command, row.get("reading", ""))


def _measurement(row: dict[str, str]) -> Measurement | _Bad:
    if not _CRITERION_ID.fullmatch(row["criterion"]):
        return _Bad("bad-id", f"criterion {row['criterion']!r} does not match FC-<2+ digits>")
    phase = row["phase"].lower()
    if phase not in PHASES:
        return _Bad("bad-phase", f"phase {row['phase']!r} is not baseline or final")
    reading = _reading(row["reading"])
    if isinstance(reading, _Bad):
        return reading
    if not _HEAD.fullmatch(row["head"]):
        return _Bad("bad-head", f"head {row['head']!r} is not 8 lowercase hex characters")
    if not _is_utc_minute(row["taken"]):
        return _Bad("bad-taken", f"taken {row['taken']!r} is not UTC ISO-8601 to the minute")
    command = _single_span(row["command"])
    if command is None:
        return _Bad(
            "command-span", f"command {row['command']!r} must hold exactly one backticked span"
        )
    return Measurement(
        row["criterion"], phase, row["value"], reading, row["head"], row["taken"], command
    )


def _reading(cell: str) -> Reading | _Bad:
    text = cell.strip().lower()
    if text == "measured":
        return Measured()
    if text == "estimate":
        return Estimate()
    if text == "none" or text.startswith("none:"):
        reason = cell.strip()[len("none:") :].strip()
        if _is_placeholder(reason):
            return _Bad(
                "reasonless", "a withheld reading needs 'none: <reason>' with a real reason"
            )
        return NoReading(reason)
    return _Bad("bad-reading", f"reading {cell!r} is not measured, estimate or 'none: <reason>'")


def _against(cell: str) -> Against | None:
    match = _AGAINST_PREFIX.fullmatch(cell.strip())
    if match is None or not match.group(2).strip():
        return None
    text = match.group(2).strip()
    return Baseline(text) if match.group(1).lower() == "baseline" else Reference(text)


def _single_span(cell: str) -> str | None:
    spans = _BACKTICKED.findall(cell)
    return spans[0].strip() if len(spans) == 1 and spans[0].strip() else None


def _is_placeholder(text: str) -> bool:
    return text.strip().lower() in PLACEHOLDER_REASONS or not text.strip()


def _is_utc_minute(text: str) -> bool:
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


# --- markdown reading: headings, tables ------------------------------------------------------

_HEADING = re.compile(r"(#{1,6})\s+(.+?)\s*$")
_FENCE = re.compile(r"\s{0,3}(```|~~~)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")


class _Table(NamedTuple):
    header: tuple[str, ...]  # lowercase, trimmed
    rows: tuple[tuple[str, ...], ...]  # trimmed cells, `\|` unescaped


def _lines(text: str) -> list[str]:
    return _HTML_COMMENT.sub("", text).splitlines()


def _section(lines: list[str], level: int, title: str) -> list[str] | None:
    """The lines under the heading `title` at `level`, up to the next heading of that level or higher."""
    wanted = title.strip().lower()
    inside: list[str] | None = None
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.fullmatch(line.strip())
        if heading is not None and len(heading.group(1)) <= level and inside is not None:
            return inside
        if inside is not None:
            inside.append(line)
        elif (
            heading
            and len(heading.group(1)) == level
            and heading.group(2).strip().lower() == wanted
        ):
            inside = []
    return inside


def _first_table(lines: list[str]) -> _Table | None:
    """The first table (a pipe row followed by a separator row) and the pipe rows after it."""
    for index, line in enumerate(lines[:-1]):
        if line.lstrip().startswith("|") and _is_separator(lines[index + 1]):
            rows = []
            for row in lines[index + 2 :]:
                if not row.lstrip().startswith("|"):
                    break
                rows.append(_cells(row))
            return _Table(tuple(c.lower() for c in _cells(line)), tuple(rows))
    return None


def _is_separator(line: str) -> bool:
    return line.lstrip().startswith("|") and all(_SEPARATOR_CELL.fullmatch(c) for c in _cells(line))


def _cells(line: str) -> tuple[str, ...]:
    body = line.strip()[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return tuple(cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT.split(body))


class _Defect(NamedTuple):
    reason: str
    message: str
    key: str | None


def _read_rows(
    table: _Table, required: tuple[str, ...], optional: tuple[str, ...] = ()
) -> tuple[list[tuple[int, dict[str, str]]], list[_Defect]]:
    """Complete rows as {column: cell} with their 1-based numbers, and a defect per incomplete row."""
    index = {name: position for position, name in enumerate(table.header)}
    missing = [name for name in required if name not in index]
    if missing:
        return [], [_Defect("bad-header", f"header lacks column(s): {', '.join(missing)}", None)]
    rows, defects = [], []
    for number, cells in enumerate(table.rows, start=1):
        row = {name: _cell(cells, index.get(name)) for name in (*required, *optional)}
        empty = [name for name in required if not row[name]]
        if empty:
            key = row.get(required[0]) or None
            defects.append(
                _Defect("missing-cell", f"row {number}: empty cell(s): {', '.join(empty)}", key)
            )
        else:
            rows.append((number, row))
    return rows, defects


def _cell(cells: tuple[str, ...], position: int | None) -> str:
    return cells[position] if position is not None and position < len(cells) else ""
