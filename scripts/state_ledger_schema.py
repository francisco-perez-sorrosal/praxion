#!/usr/bin/env python3
"""The `.ai-state/` ledger format: registry, parser, and `dedup_key` derivation.

This module answers *what a ledger is*; the sibling `check_state_ledgers.py`
answers *what to do when one is wrong*. The seam is deliberate -- the format
description is what a future consumer (the dashboard, a finalize pass, a
managed-project variant of the gate) needs to import without also pulling in a
CLI, a backfill mode, and a set of failure messages.

Stdlib-only, side-effect-free, and it never decides anything: no exit codes, no
findings, no writes. Every judgement about a parsed row lives in the gate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

STATE_DIR = ".ai-state"

# A data row's first cell matches one of these. Used as the row oracle: it is
# what separates a schema row from a prose table sharing the same file.
TD_ID = r"td-\d{3,}"
ISO_UTC = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"

# Pipe policies. `forbid` == blocking (the tech-debt schema mandates " // ");
# `warn` == advisory (the CONSULT files document the escape but read with `cut`).
PIPE_FORBID = "forbid"
PIPE_WARN = "warn"

TECH_DEBT_NAMESPACE = "tech-debt"


@dataclass(frozen=True)
class TableSpec:
    """One Markdown data table inside a ledger file."""

    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class LedgerSpec:
    """A registered `.ai-state/` ledger and the schema its rows must satisfy."""

    path: str
    row_signature: str
    tables: tuple[TableSpec, ...]
    pipe_policy: str
    dedup_namespace: str = ""


# Column order for the tech-debt pair. Mirrors `FIELD_ORDER` in
# `scripts/finalize_tech_debt_ledger.py`; a drift test pins the two together
# rather than one importing the other, so this registry stays uniform across
# all five ledgers instead of special-casing the one with a Python sibling.
TECH_DEBT_COLUMNS: tuple[str, ...] = (
    "id",
    "severity",
    "class",
    "direction",
    "location",
    "goal-ref-type",
    "goal-ref-value",
    "source",
    "first-seen",
    "last-seen",
    "owner-role",
    "status",
    "resolved-by",
    "notes",
    "dedup_key",
)

CONSULT_LEDGER_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "challenge-id",
    "claim",
    "decision-at-stake",
    "disposition",
    "rationale-ref",
    "model",
    "difficulty",
)

CONSULT_COSTS_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "tokens",
    "model",
    "difficulty",
    "notes",
)

SEALED_PRIORS_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "prior-id",
    "source",
    "concern",
)

CHALLENGE_CLASSIFICATION_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "task-slug",
    "discipline",
    "stage",
    "challenge-id",
    "classification",
    "matched-prior-id",
    "seal-witness",
    "prompt-areas",
)

LEDGERS: tuple[LedgerSpec, ...] = (
    LedgerSpec(
        path=f"{STATE_DIR}/TECH_DEBT_LEDGER.md",
        row_signature=TD_ID,
        tables=(TableSpec("active", TECH_DEBT_COLUMNS),),
        pipe_policy=PIPE_FORBID,
        dedup_namespace=TECH_DEBT_NAMESPACE,
    ),
    LedgerSpec(
        path=f"{STATE_DIR}/TECH_DEBT_RESOLVED.md",
        row_signature=TD_ID,
        tables=(TableSpec("terminal", TECH_DEBT_COLUMNS),),
        pipe_policy=PIPE_FORBID,
        dedup_namespace=TECH_DEBT_NAMESPACE,
    ),
    LedgerSpec(
        path=f"{STATE_DIR}/CONSULT_LEDGER.md",
        row_signature=ISO_UTC,
        tables=(TableSpec("dispositions", CONSULT_LEDGER_COLUMNS),),
        pipe_policy=PIPE_WARN,
    ),
    LedgerSpec(
        path=f"{STATE_DIR}/CONSULT_COSTS.md",
        row_signature=ISO_UTC,
        tables=(TableSpec("cost-series", CONSULT_COSTS_COLUMNS),),
        pipe_policy=PIPE_WARN,
    ),
    LedgerSpec(
        path=f"{STATE_DIR}/CONSULT_PRIORS.md",
        row_signature=ISO_UTC,
        tables=(
            TableSpec("sealed-priors", SEALED_PRIORS_COLUMNS),
            TableSpec("challenge-classification", CHALLENGE_CLASSIFICATION_COLUMNS),
        ),
        pipe_policy=PIPE_WARN,
    ),
)

# The discovery signal for `check_registry_coverage`: every registered ledger
# declares its schema with this line, and no other top-level `.ai-state/*.md`
# file does. A new ledger written to the same convention is therefore visible
# to the gate the moment it lands.
SCHEMA_DECLARATION = re.compile(r"^\*\*Schema\*\*:", re.MULTILINE)

# Split on an *unescaped* pipe, so a documented `\|` escape stays inside its
# cell. Splitting naively would report every correctly-escaped row as a
# field-count violation -- the gate firing on correct work.
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEPARATOR_ROW = re.compile(r"^\|[\s:|-]+\|?\s*$")
HEX12 = re.compile(r"^[0-9a-f]{12}$")
_LOCATION_RANGE = re.compile(r":\d+(?:-\d+)?$")


@dataclass(frozen=True)
class DataRow:
    """One schema row: a line whose first cell matches its ledger's signature."""

    spec: LedgerSpec
    table: TableSpec | None  # None == the row sits outside every registered table
    line_no: int
    raw: str
    cells: tuple[str, ...]

    @property
    def row_id(self) -> str:
        return self.cells[0] if self.cells else ""

    def value(self, column: str) -> str:
        """Return this row's cell for `column`, or "" when the row is short."""
        if self.table is None or column not in self.table.columns:
            return ""
        index = self.table.columns.index(column)
        return self.cells[index] if index < len(self.cells) else ""


@dataclass(frozen=True)
class ParsedLedger:
    """A registered ledger after parsing: its rows plus any table it is missing."""

    spec: LedgerSpec
    present: bool
    rows: tuple[DataRow, ...]
    missing_tables: tuple[str, ...]


# -- Parsing ------------------------------------------------------------------


def split_row(line: str) -> list[str]:
    """Split a `| a | b |` line into stripped cells, honouring `\\|` escapes."""
    parts = _UNESCAPED_PIPE.split(line.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [cell.strip() for cell in parts]


def _table_ranges(lines: list[str], spec: LedgerSpec) -> dict[str, tuple[int, int]]:
    """Locate each registered table by its header row; return 1-based line spans.

    A table's span runs from its header to the last consecutive `|`-prefixed
    line, so it terminates at a blank line or a `##` heading -- or at EOF. Both
    shapes occur: the tech-debt tables run to end-of-file, the CONSULT tables
    are followed by prose.
    """
    wanted = {table.name: list(table.columns) for table in spec.tables}
    spans: dict[str, tuple[int, int]] = {}
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_row(line)
        for name, columns in wanted.items():
            if name in spans or cells != columns:
                continue
            end = index
            while end + 1 < len(lines) and lines[end + 1].lstrip().startswith("|"):
                end += 1
            spans[name] = (index + 1, end + 1)
    return spans


def parse_ledger(repo_root: Path, spec: LedgerSpec) -> ParsedLedger:
    """Parse one registered ledger into its data rows plus any missing table."""
    path = repo_root / spec.path
    if not path.is_file():
        return ParsedLedger(spec=spec, present=False, rows=(), missing_tables=())

    lines = path.read_text(encoding="utf-8").splitlines()
    spans = _table_ranges(lines, spec)
    signature = re.compile(rf"^{spec.row_signature}$")

    rows: list[DataRow] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("|") or _SEPARATOR_ROW.match(stripped):
            continue
        cells = split_row(line)
        if not cells or not signature.match(cells[0]):
            continue
        line_no = index + 1
        table = next(
            (
                table
                for table in spec.tables
                if table.name in spans and spans[table.name][0] <= line_no <= spans[table.name][1]
            ),
            None,
        )
        rows.append(DataRow(spec=spec, table=table, line_no=line_no, raw=line, cells=tuple(cells)))

    missing = tuple(table.name for table in spec.tables if table.name not in spans)
    return ParsedLedger(spec=spec, present=True, rows=tuple(rows), missing_tables=missing)


def parse_all(repo_root: Path) -> list[ParsedLedger]:
    """Parse every registered ledger under `repo_root`."""
    return [parse_ledger(repo_root, spec) for spec in LEDGERS]


# -- dedup_key ----------------------------------------------------------------


def normalize_location(cell: str) -> str:
    """Sorted, comma-joined path list with line ranges stripped.

    Two rows differing only in line range or path order must produce the same
    key -- that is what makes the key a *structural* identity of the finding
    rather than a hash of how it happened to be written down.
    """
    paths = [_LOCATION_RANGE.sub("", part.strip()) for part in cell.split(",") if part.strip()]
    return ",".join(sorted(paths))


def compute_dedup_key(row: DataRow, discriminator: str = "") -> str:
    """Recompute a tech-debt row's `dedup_key` from the documented formula.

    ``sha1(class|normalize(location)|direction|goal-ref-type|goal-ref-value)[:12]``
    -- canonical definition in
    ``skills/software-planning/references/tech-debt-ledger.md`` § Schema. The
    formula is not re-derived here: it was confirmed by brute-forcing 56
    variants against the full row set, and scores highest of all 56.

    ``discriminator``, when non-empty, appends one more field to the hashed
    payload. It exists solely for ``resolve_dedup_keys`` below, which mints it
    from a colliding row's own `notes` cell -- never call this with a
    discriminator directly. Leaving it "" (the default) reproduces the
    original 5-tuple formula byte-for-byte, which is what keeps every
    already-conforming key in the corpus unaffected by this parameter's mere
    existence.
    """
    fields = (
        row.value("class"),
        normalize_location(row.value("location")),
        row.value("direction"),
        row.value("goal-ref-type"),
        row.value("goal-ref-value"),
    )
    if discriminator:
        fields = (*fields, discriminator)
    payload = "|".join(fields)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]  # noqa: S324 - identity, not security


def _notes_digest(row: DataRow) -> str:
    """Short, stable discriminator derived from a row's own `notes` cell.

    `notes` is a field every producer already writes -- using it as the
    collision discriminator needs no new schema field and no write-time
    behavior change from any producer. Two colliding rows are indistinguishable
    by it only when their notes are themselves identical, which is the
    genuinely-unresolvable case `resolve_dedup_keys` still surfaces as blocked.
    """
    return hashlib.sha1(row.value("notes").encode("utf-8")).hexdigest()[:8]  # noqa: S324


def dedup_rows(parsed: list[ParsedLedger]) -> list[DataRow]:
    """Every well-formed row belonging to a `dedup_key`-bearing namespace."""
    return [
        row
        for ledger in parsed
        if ledger.spec.dedup_namespace
        for row in ledger.rows
        if row.table is not None and len(row.cells) == len(row.table.columns)
    ]


def resolve_dedup_keys(rows: list[DataRow]) -> dict[str, str]:
    """Map row id -> its correct `dedup_key`, discriminator included.

    The plain 5-tuple formula (`compute_dedup_key` with no discriminator) is
    unchanged and is what every singleton row -- the overwhelming majority --
    resolves to, byte-identical to before this function existed. A base
    5-tuple collision is a legitimate outcome: two genuinely distinct findings
    can share (class, location, direction, goal-ref-type, goal-ref-value);
    td-085 confirmed the formula is otherwise sound, so granularity, not
    correctness, is what needed fixing.

    Within a colliding group, at most one member can already validly hold the
    plain base key (its written `dedup_key` cell equals the base formula) --
    that member's resolved key is left as the plain base key, untouched. Every
    other member in the group is assigned a key discriminated by its own
    `notes` cell. A group with no existing holder (every member's written key
    already disagrees with the base formula, e.g. two mutually-wrong rows)
    discriminates every member. Members sharing identical `notes` still
    collide even after discrimination -- `collision_blocked_ids` below is what
    catches that genuinely unresolvable residue.
    """
    base_by_id = {row.row_id: compute_dedup_key(row) for row in rows}
    groups: dict[str, list[DataRow]] = {}
    for row in rows:
        groups.setdefault(base_by_id[row.row_id], []).append(row)

    resolved: dict[str, str] = {}
    for base, members in groups.items():
        if len(members) == 1:
            resolved[members[0].row_id] = base
            continue
        holder = next((member for member in members if member.value("dedup_key") == base), None)
        for member in members:
            if member is holder:
                resolved[member.row_id] = base
            else:
                resolved[member.row_id] = compute_dedup_key(
                    member, discriminator=_notes_digest(member)
                )
    return resolved


def collision_blocked_ids(parsed: list[ParsedLedger]) -> dict[str, str]:
    """Map row id -> the id it would still collide with after discrimination.

    A backfill that produced a duplicate key would be *worse* than the bad data
    it repaired: the next `finalize_tech_debt_ledger.py` run collapses rows
    sharing a key, merging two distinct findings, erasing one `td-NNN`, and (in
    one live case) destroying a `wontfix` tombstone the schema says is never
    removed. So the exemption is *derived* here rather than kept as a hand-
    maintained skip-list -- it updates itself, and every run names the reason.

    With the discriminator in `resolve_dedup_keys`, two rows can only land
    here when their base 5-tuple AND their `notes` cell are both identical --
    the discriminator has nothing left to distinguish them with.
    """
    rows = dedup_rows(parsed)
    resolved = resolve_dedup_keys(rows)

    by_resolved: dict[str, list[str]] = {}
    for row in rows:
        by_resolved.setdefault(resolved[row.row_id], []).append(row.row_id)

    blocked: dict[str, str] = {}
    for row in rows:
        if row.value("dedup_key") == resolved[row.row_id]:
            continue
        peers = [other for other in by_resolved[resolved[row.row_id]] if other != row.row_id]
        if peers:
            blocked[row.row_id] = peers[0]
    return blocked
