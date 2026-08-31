#!/usr/bin/env python3
"""Parse and validate the `.ai-state/` ledger files against their own schemas.

``.ai-state/`` is a data format with a specification and no parser.  Every
writer is an agent following prose; every invariant lives in a sibling markdown
file; the only feedback is whether a downstream reader happens to notice.  That
is why the same defect keeps arriving in new costumes.  This is the missing
parser.

Five defect shapes, each observed live in this repository rather than imagined:

``field-count``
    A row whose cell count differs from its table's declared schema.  A single
    literal ``|`` inside a free-text cell splits one row into two extra fields;
    the tech-debt pair's own finalize script skips such a row and reports it,
    but only at merge time, and only for that one file.

``unterminated-row``
    A data row that starts with ``|`` but does not end with one.  Both
    ``finalize_tech_debt_ledger.py`` and every published ``grep`` recipe require
    both delimiters, so such a row is *silently skipped* -- present to a human
    reader, absent from every count.

``stray-row``
    A data row outside the parsed data table.  ``CONSULT_LEDGER.md`` and
    ``CONSULT_COSTS.md`` both told their single writer to append "at the end of
    the file", which is not the end of the *table*: the files carry prose
    sections after their tables.  A row appended at EOF renders as a plausible
    table to a human and is invisible to every counting recipe and to the
    cost-coverage gate.  Note the structural asymmetry this check must survive:
    the tech-debt tables run to end-of-file, the CONSULT tables do not.

``literal-pipe``
    A cell containing an escaped ``\\|``.  The tech-debt schema specifies
    ``" // "`` as its notes separator *precisely* to avoid the Markdown table
    delimiter, so there this is blocking.  The CONSULT files document ``\\|`` as
    a legal escape, yet their own published reading recipes are ``cut -d'|'``
    one-liners that do not understand escapes -- an escaped pipe silently
    inflates their denominators, which is the fail-open direction their
    § Falsifier forbids.  Advisory there, and named as such.

``dedup_key`` (tech-debt pair only)
    Format (12 lowercase hex), value (recomputed from the documented formula),
    and uniqueness across the pair.  ``dedup_key`` drives the post-merge
    collapse and the re-open-on-recurrence semantics: a wrong key silently
    merges unrelated debt or silently fails to re-open a recurrence.

**Scope fidelity.**  The covered file set is an explicit registry, not a
directory scan -- most ``.ai-state/*.md`` files are not tables, and a scan
would either fire on prose or need a skip-list nobody maintains.  A registry
alone is a drift surface, though: a sixth ledger could ship ungated and nothing
would say so.  ``check_registry_coverage`` closes that by *failing* when a
top-level ``.ai-state/*.md`` file declares a ``**Schema**:`` line and is not
registered.  The registry is the contract; the discovery check is what stops
the contract from drifting below the filesystem.

Exit codes: 0 clean, 1 blocking violations found, 2 script error.

Usage:
    python3 scripts/check_state_ledgers.py            # --check (default)
    python3 scripts/check_state_ledgers.py --check
    python3 scripts/check_state_ledgers.py --json
    python3 scripts/check_state_ledgers.py --backfill  # repair dedup_key only
    python3 scripts/check_state_ledgers.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from _repo_root import resolve_repo_root as _resolve_repo_root
from state_ledger_schema import (
    HEX12,
    LEDGERS,
    PIPE_FORBID,
    SCHEMA_DECLARATION,
    STATE_DIR,
    TECH_DEBT_COLUMNS,
    DataRow,
    LedgerSpec,
    ParsedLedger,
    TableSpec,
    collision_blocked_ids,
    compute_dedup_key,
    dedup_rows,
    normalize_location,
    parse_all,
    parse_ledger,
    resolve_dedup_keys,
    split_row,
)

SCRIPT_DIR = Path(__file__).resolve().parent

# Re-exported so a reader (and the test suite) finds the whole vocabulary on the
# gate module. The definitions live in `state_ledger_schema.py`; naming them here
# keeps `from state_ledger_schema import *` out of the file and the linter quiet.
__all__ = [
    "LEDGERS",
    "TECH_DEBT_COLUMNS",
    "DataRow",
    "Finding",
    "LedgerSpec",
    "ParsedLedger",
    "TableSpec",
    "collision_blocked_ids",
    "compute_dedup_key",
    "dedup_rows",
    "normalize_location",
    "parse_all",
    "parse_ledger",
    "resolve_dedup_keys",
    "split_row",
]


@dataclass(frozen=True)
class Finding:
    """One violation. `blocking` False means reported and counted, never fatal."""

    kind: str
    path: str
    line: int
    row_id: str
    message: str
    blocking: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "row_id": self.row_id,
            "message": self.message,
            "blocking": self.blocking,
        }


# -- Checks -------------------------------------------------------------------


def _finding(row: DataRow, kind: str, message: str, blocking: bool = True) -> Finding:
    """Build a row-anchored Finding, filling path/line/id from the row itself."""
    return Finding(
        kind=kind,
        path=row.spec.path,
        line=row.line_no,
        row_id=row.row_id,
        message=message,
        blocking=blocking,
    )


def _row_shape_findings(row: DataRow) -> list[Finding]:
    """Shape violations for one data row: delimiters, placement, cell count."""
    findings: list[Finding] = []
    if not row.raw.strip().endswith("|"):
        findings.append(
            _finding(
                row,
                "unterminated-row",
                "data row does not end with `|`; finalize scripts and every published "
                "grep recipe require both delimiters, so this row is silently skipped "
                "by all of them",
            )
        )
    if row.table is None:
        findings.append(
            _finding(
                row,
                "stray-row",
                "data row sits outside the parsed data table (appended after a trailing "
                "prose section?); it renders to a human but is invisible to every "
                "counting recipe",
            )
        )
        return findings

    expected = len(row.table.columns)
    if len(row.cells) != expected:
        findings.append(
            _finding(
                row,
                "field-count",
                f"{len(row.cells)} cells, schema declares {expected} ({row.table.name}); "
                "an unescaped `|` in a free-text cell is the usual cause",
            )
        )
    return findings


def check_row_shape(parsed: list[ParsedLedger]) -> list[Finding]:
    """Flag rows with the wrong cell count, a missing trailing `|`, or no table."""
    findings: list[Finding] = []
    for ledger in parsed:
        findings.extend(
            Finding(
                kind="table-missing",
                path=ledger.spec.path,
                line=0,
                row_id="",
                message=(
                    f"no header row matching the declared `{name}` schema; "
                    "every data row in this file is unparseable"
                ),
            )
            for name in ledger.missing_tables
        )
        for row in ledger.rows:
            findings.extend(_row_shape_findings(row))
    return findings


def check_literal_pipes(parsed: list[ParsedLedger]) -> list[Finding]:
    """Flag cells carrying a `\\|` escape, per each ledger's own pipe policy."""
    findings: list[Finding] = []
    for ledger in parsed:
        forbid = ledger.spec.pipe_policy == PIPE_FORBID
        for row in ledger.rows:
            if not any("|" in cell for cell in row.cells):
                continue
            message = (
                "cell contains a literal `|`; the schema mandates ` // ` as the "
                "notes separator precisely to avoid the Markdown table delimiter"
                if forbid
                else "cell contains an escaped `\\|`; this file's own published "
                "`cut -d'|'` reading recipes do not understand the escape, so the "
                "row mis-splits and inflates their denominators"
            )
            findings.append(
                Finding(
                    kind="literal-pipe",
                    path=ledger.spec.path,
                    line=row.line_no,
                    row_id=row.row_id,
                    message=message,
                    blocking=forbid,
                )
            )
    return findings


def _dedup_value_finding(
    row: DataRow, written: str, expected: str, blocked: dict[str, str]
) -> Finding:
    """Classify one non-conforming `dedup_key` cell into its finding."""
    if row.row_id in blocked:
        shape = "" if HEX12.match(written) else " (and is not 12 lowercase hex)"
        return Finding(
            kind="dedup-collision-blocked",
            path=row.spec.path,
            line=row.line_no,
            row_id=row.row_id,
            message=(
                f"`dedup_key` {written!r} does not match the formula ({expected})"
                f"{shape}, and MUST NOT be repaired: {blocked[row.row_id]} would hold "
                "the same key, so recomputing would let the next finalize run collapse "
                "two distinct findings into one -- erasing a td-NNN. The formula cannot "
                "distinguish them; the stale key is the only thing keeping them apart"
            ),
            blocking=False,
        )
    if not HEX12.match(written):
        return Finding(
            kind="dedup-format",
            path=row.spec.path,
            line=row.line_no,
            row_id=row.row_id,
            message=(
                f"`dedup_key` is {written!r}; the schema requires 12 lowercase hex "
                f"characters (expected {expected}). Fix: --backfill"
            ),
        )
    return Finding(
        kind="dedup-mismatch",
        path=row.spec.path,
        line=row.line_no,
        row_id=row.row_id,
        message=(
            f"`dedup_key` is {written}, formula yields {expected}; a wrong key silently "
            "merges unrelated debt or fails to re-open a recurrence. Fix: --backfill"
        ),
    )


def check_dedup_keys(parsed: list[ParsedLedger]) -> list[Finding]:
    """Validate `dedup_key` format, value, and uniqueness across the pair."""
    rows = dedup_rows(parsed)
    resolved = resolve_dedup_keys(rows)
    blocked = collision_blocked_ids(parsed)
    findings: list[Finding] = []

    seen: dict[str, DataRow] = {}
    for row in rows:
        written = row.value("dedup_key")
        expected = resolved[row.row_id]

        if written != expected:
            # The collision test is applied BEFORE the format test on purpose. A
            # collision-blocked row is unrepairable by construction, so reporting
            # its (real) format deviation as blocking would leave the gate red
            # with no legal fix -- and a gate nobody can satisfy gets disabled.
            findings.append(_dedup_value_finding(row, written, expected, blocked))

        prior = seen.get(written)
        if prior is not None:
            findings.append(
                Finding(
                    kind="dedup-duplicate",
                    path=row.spec.path,
                    line=row.line_no,
                    row_id=row.row_id,
                    message=(
                        f"`dedup_key` {written} is already held by {prior.row_id} "
                        f"({prior.spec.path}:{prior.line_no}); the next finalize run "
                        "would collapse the two rows into one"
                    ),
                )
            )
        else:
            seen[written] = row
    return findings


def check_registry_coverage(repo_root: Path) -> list[Finding]:
    """Flag a top-level `.ai-state/*.md` ledger that this gate does not cover.

    The registry above is the contract; without this check it is also a drift
    surface, since a sixth ledger could ship ungated and nothing would say so.
    """
    registered = {spec.path for spec in LEDGERS}
    state_dir = repo_root / STATE_DIR
    if not state_dir.is_dir():
        return []

    findings: list[Finding] = []
    for path in sorted(state_dir.glob("*.md")):
        relative = f"{STATE_DIR}/{path.name}"
        if relative in registered:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not SCHEMA_DECLARATION.search(body):
            continue
        findings.append(
            Finding(
                kind="unregistered-ledger",
                path=relative,
                line=0,
                row_id="",
                message=(
                    "declares a `**Schema**:` line but is absent from LEDGERS in "
                    "scripts/check_state_ledgers.py, so none of its rows are validated"
                ),
            )
        )
    return findings


def run_checks(repo_root: Path) -> list[Finding]:
    """Run every check over `repo_root`, returning findings in file order."""
    parsed = parse_all(repo_root)
    return [
        *check_row_shape(parsed),
        *check_literal_pipes(parsed),
        *check_dedup_keys(parsed),
        *check_registry_coverage(repo_root),
    ]


# -- Backfill -----------------------------------------------------------------


def backfill_dedup_keys(repo_root: Path) -> list[tuple[str, str, str, str]]:
    """Rewrite mismatched `dedup_key` cells; returns (path, id, old, new) tuples.

    Refuses every row in `collision_blocked_ids` -- the refusal is in code, not
    in the operator's head, so a later run cannot quietly undo the reasoning.
    Only the `dedup_key` cell is touched; no other byte of a row changes.
    """
    parsed = parse_all(repo_root)
    resolved = resolve_dedup_keys(dedup_rows(parsed))
    blocked = collision_blocked_ids(parsed)
    updated: list[tuple[str, str, str, str]] = []

    for ledger in parsed:
        if not ledger.spec.dedup_namespace or not ledger.present:
            continue
        path = repo_root / ledger.spec.path
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False

        for row in ledger.rows:
            if row.table is None or len(row.cells) != len(row.table.columns):
                continue
            written = row.value("dedup_key")
            expected = resolved[row.row_id]
            if written == expected or row.row_id in blocked:
                continue
            index = row.line_no - 1
            suffix = "\n" if lines[index].endswith("\n") else ""
            cells = list(row.cells)
            cells[row.table.columns.index("dedup_key")] = expected
            lines[index] = "| " + " | ".join(cells) + " |" + suffix
            updated.append((ledger.spec.path, row.row_id, written, expected))
            changed = True

        if changed:
            path.write_text("".join(lines), encoding="utf-8")
    return updated


# -- Reporting ----------------------------------------------------------------


def _summarize(parsed: list[ParsedLedger]) -> dict[str, int]:
    """Row and conformance counts, for the human report and the JSON payload."""
    rows = dedup_rows(parsed)
    resolved = resolve_dedup_keys(rows)
    conforming = sum(1 for row in rows if row.value("dedup_key") == resolved[row.row_id])
    return {
        "ledgers": len(parsed),
        "rows": sum(len(ledger.rows) for ledger in parsed),
        "dedup_rows": len(rows),
        "dedup_conforming": conforming,
    }


def run_check(repo_root: Path, as_json: bool) -> int:
    """--check mode: report findings, exit 1 when any of them blocks."""
    findings = run_checks(repo_root)
    parsed = parse_all(repo_root)
    counts = _summarize(parsed)
    blocking = [finding for finding in findings if finding.blocking]

    if as_json:
        payload = {
            "status": "violations" if blocking else "clean",
            "counts": {**counts, "findings": len(findings), "blocking": len(blocking)},
            "findings": [finding.as_dict() for finding in findings],
        }
        print(json.dumps(payload, indent=2))
        return 1 if blocking else 0

    for finding in findings:
        label = "FAIL" if finding.blocking else "warn"
        where = f"{finding.path}:{finding.line}" if finding.line else finding.path
        subject = f" [{finding.row_id}]" if finding.row_id else ""
        print(f"{label} {finding.kind} {where}{subject}: {finding.message}")

    print(
        f"\nchecked {counts['ledgers']} ledger(s), {counts['rows']} data row(s); "
        f"dedup_key conformance {counts['dedup_conforming']}/{counts['dedup_rows']}."
    )
    if blocking:
        print(f"{len(blocking)} blocking finding(s); state-ledger schema check failed.")
        return 1
    advisory = len(findings) - len(blocking)
    if advisory:
        print(f"{advisory} advisory finding(s); no blocking violations.")
    return 0


def run_backfill(repo_root: Path) -> int:
    """--backfill mode: repair repairable `dedup_key` cells and report the rest."""
    updated = backfill_dedup_keys(repo_root)
    for path, row_id, old, new in updated:
        print(f"{path} [{row_id}] dedup_key {old} -> {new}")
    if not updated:
        print("no repairable dedup_key mismatches; nothing written.")
    else:
        print(f"\nbackfilled {len(updated)} dedup_key cell(s).")

    blocked = collision_blocked_ids(parse_all(repo_root))
    for row_id, holder in sorted(blocked.items()):
        print(f"skipped [{row_id}]: recomputed key already held by {holder}")
    return 0


# -- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_state_ledgers",
        description=(
            "Validate every registered .ai-state/ ledger against its declared schema: "
            "field count, row-inside-table, literal pipes, and tech-debt dedup_key."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Report findings and exit 1 on any blocking one (default mode).",
    )
    mode.add_argument(
        "--backfill",
        action="store_true",
        help="Repair mismatched tech-debt dedup_key cells (skips collision-blocked rows).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable findings.")
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help="Repo root whose .ai-state/ to validate (default: resolved from git).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        repo_root = _resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
        if args.backfill:
            return run_backfill(repo_root)
        return run_check(repo_root, as_json=args.json)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
