#!/usr/bin/env python3
"""Collapse duplicate rows in `.ai-state/TECH_DEBT_LEDGER.md` at merge-to-main.

Reads the ledger's 15-column Markdown table, groups rows by `dedup_key`, picks
one survivor per group by status precedence (`resolved > in-flight > open >
wontfix`) breaking ties by newer `last-seen`, merges non-conflicting fields
(earliest `first-seen`; `notes` concatenated with ` | `; `location` union-sorted),
and writes the collapsed table back in place. The script is idempotent and
acquires an advisory file lock so concurrent post-merge invocations serialize.

Invocation modes:

    finalize_tech_debt_ledger.py                 # --merged (default)
    finalize_tech_debt_ledger.py --all           # run regardless of merge state
    finalize_tech_debt_ledger.py --dry-run       # print the plan, do not write
    finalize_tech_debt_ledger.py --verbose       # debug logging

Exit codes:

    0 -- success, or no rows to collapse (idempotent no-op)
    1 -- manual intervention required (malformed row, I/O error)

Design notes -- modeled on `scripts/finalize_adrs.py`:
- Single-purpose script: only ledger dedupe, no orthogonal concerns.
- Advisory `fcntl` lock serializes concurrent runs from hook + command.
- Byte-equivalent output when no collapse is possible (idempotency contract).
- Malformed rows trigger a loud non-zero exit; the hook wrapper chooses the
  non-blocking semantics (`2>&1 || echo ...`) so a single bad row does not
  abort the merge but does not get silently discarded either.
"""

from __future__ import annotations

import argparse
import fcntl
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LEDGER_PATH = REPO_ROOT / ".ai-state" / "TECH_DEBT_LEDGER.md"
LOCK_PATH = REPO_ROOT / ".ai-state" / ".tech_debt_ledger_finalize.lock"

# Schema-defined column order. See rules/swe/agent-intermediate-documents.md
# § TECH_DEBT_LEDGER.md for the authoritative field definitions.
FIELD_ORDER: tuple[str, ...] = (
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
COLUMN_COUNT = len(FIELD_ORDER)

# Status precedence on collapse. `resolved` wins over every other status; ties
# are broken by newer `last-seen`.
STATUS_PRECEDENCE: tuple[str, ...] = ("resolved", "in-flight", "open", "wontfix")
_STATUS_RANK = {status: rank for rank, status in enumerate(STATUS_PRECEDENCE)}

NOTES_SEPARATOR = " // "
LOCATION_SEPARATOR = ", "

logger = logging.getLogger("finalize_tech_debt_ledger")


# -- Data classes -------------------------------------------------------------


@dataclass(frozen=True)
class LedgerRow:
    """One parsed ledger row. Field values preserve their as-written strings."""

    values: tuple[str, ...]

    def get(self, field: str) -> str:
        return self.values[FIELD_ORDER.index(field)]

    def with_updates(self, updates: dict[str, str]) -> LedgerRow:
        """Return a new row with the given field updates applied."""
        new_values = list(self.values)
        for field, value in updates.items():
            new_values[FIELD_ORDER.index(field)] = value
        return LedgerRow(values=tuple(new_values))


# -- Table parsing ------------------------------------------------------------


def _is_separator_line(line: str) -> bool:
    """Return True for the markdown-table separator `|---|---|...|` line."""
    stripped = line.strip()
    return stripped.startswith("|---") or stripped.startswith("| ---")


def _is_table_row(line: str) -> bool:
    """Return True for a non-empty line that looks like a table row."""
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _split_row(line: str) -> list[str]:
    """Split a `| a | b | c |` line into its cell values (stripped)."""
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def parse_ledger(path: Path) -> tuple[str, list[LedgerRow], list[str]]:
    """Split a ledger file into (header_text, parsed_rows, malformed_lines).

    The header text includes everything up to and including the table's
    separator line, preserving trailing whitespace exactly so the idempotency
    contract holds byte-for-byte when no collapse happens.

    Any data row whose cell count does not match the schema is returned in
    `malformed_lines` rather than parsed. A non-empty `malformed_lines` list
    is the caller's signal to exit with `MALFORMED_EXIT_CODE`.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    header_end_index = _locate_separator_index(lines)
    if header_end_index is None:
        # No separator found -- treat entire file as header; zero rows.
        return text, [], []

    header_text = "".join(lines[: header_end_index + 1])
    data_lines = lines[header_end_index + 1 :]

    rows: list[LedgerRow] = []
    malformed: list[str] = []
    for line in data_lines:
        if not _is_table_row(line):
            continue
        cells = _split_row(line)
        if len(cells) != COLUMN_COUNT:
            malformed.append(line)
            continue
        rows.append(LedgerRow(values=tuple(cells)))
    return header_text, rows, malformed


def _locate_separator_index(lines: list[str]) -> int | None:
    """Return the index of the markdown separator line, or None if absent."""
    for index, line in enumerate(lines):
        if _is_separator_line(line):
            return index
    return None


# -- Collapse logic -----------------------------------------------------------


def _status_rank(status: str) -> int:
    """Return the precedence rank of a status (lower == higher precedence).

    Unknown statuses sort after every declared status, which makes collapse
    prefer any declared status over drift.
    """
    return _STATUS_RANK.get(status, len(STATUS_PRECEDENCE))


def _pick_survivor(rows: list[LedgerRow]) -> LedgerRow:
    """Pick the survivor of a group by status precedence, tie-break newer last-seen."""
    return min(
        rows,
        key=lambda row: (
            _status_rank(row.get("status")),
            _negated(row.get("last-seen")),
        ),
    )


def _negated(iso_date: str) -> tuple[int, str]:
    """Invert ISO-date ordering so `min(..., key=)` prefers the later date.

    Returns a comparable tuple; `(0, iso_date)` for the negated representation
    ensures lexicographic descending order while being robust to unparsed dates
    (they sort at the end, preserving determinism).
    """
    # The actual trick: since all our last-seen values are ISO YYYY-MM-DD,
    # lexicographic descending = chronological descending. To flip ordering
    # inside `min`, return the negated string via a custom ordering key.
    # We cannot negate a string directly, so we use a sentinel that inverts
    # the comparison: empty-string-padded fixed-width reversal.
    if not iso_date:
        return (1, "")  # unparsed dates sort last inside min()
    # Compute "negated" key by inverting each character relative to '~' (ASCII 126).
    negated = "".join(chr(126 - ord(ch)) if " " <= ch <= "~" else ch for ch in iso_date)
    return (0, negated)


def _earliest_first_seen(rows: list[LedgerRow]) -> str:
    """Return the lexicographically earliest non-empty first-seen across rows."""
    values = [row.get("first-seen") for row in rows if row.get("first-seen")]
    if not values:
        return ""
    return min(values)


def _merge_notes(survivor: LedgerRow, discarded: list[LedgerRow]) -> str:
    """Concatenate survivor + discarded notes with NOTES_SEPARATOR; dedupe."""
    seen: set[str] = set()
    ordered: list[str] = []
    for row in [survivor, *discarded]:
        note = row.get("notes").strip()
        if not note or note in seen:
            continue
        seen.add(note)
        ordered.append(note)
    return NOTES_SEPARATOR.join(ordered)


def _merge_locations(rows: list[LedgerRow]) -> str:
    """Sorted-union merge of `location` cells across rows (paths split on comma)."""
    paths: set[str] = set()
    for row in rows:
        cell = row.get("location")
        for path in cell.split(","):
            stripped = path.strip()
            if stripped:
                paths.add(stripped)
    return LOCATION_SEPARATOR.join(sorted(paths))


def collapse_rows(rows: list[LedgerRow]) -> list[LedgerRow]:
    """Collapse rows sharing a dedup_key; preserve first-appearance order.

    The returned list contains one row per unique dedup_key, in the order the
    dedup_key first appeared in the input. For singleton groups (key appears
    once) the original row is returned unchanged, preserving byte-equivalence.
    """
    groups: dict[str, list[LedgerRow]] = {}
    key_order: list[str] = []
    for row in rows:
        key = row.get("dedup_key")
        if key not in groups:
            groups[key] = []
            key_order.append(key)
        groups[key].append(row)

    collapsed: list[LedgerRow] = []
    for key in key_order:
        group = groups[key]
        if len(group) == 1:
            collapsed.append(group[0])
            continue
        survivor = _pick_survivor(group)
        discarded = [row for row in group if row is not survivor]
        merged = survivor.with_updates(
            {
                "first-seen": _earliest_first_seen(group),
                "location": _merge_locations(group),
                "notes": _merge_notes(survivor, discarded),
            }
        )
        collapsed.append(merged)
    return collapsed


# -- Table rendering ----------------------------------------------------------


def render_row(row: LedgerRow) -> str:
    """Render a parsed row back to its canonical `| a | b | ... |\\n` form."""
    return "| " + " | ".join(row.values) + " |\n"


def render_ledger(header_text: str, rows: list[LedgerRow]) -> str:
    """Assemble the full ledger text from header + rows."""
    return header_text + "".join(render_row(row) for row in rows)


# -- Concurrency --------------------------------------------------------------


@contextmanager
def acquire_lock(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive advisory lock for the duration of the context.

    Mirrors `scripts/finalize_adrs.py::acquire_lock` -- creates the lock file
    if missing, releases on exit, and never leaks the file descriptor.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


# -- Orchestration ------------------------------------------------------------


def finalize_ledger(ledger_path: Path, dry_run: bool = False) -> int:
    """Collapse duplicates in the ledger at `ledger_path`. Returns an exit code.

    Idempotency: when the collapse produces bytes identical to the input, the
    file is not rewritten and the function returns 0 without further work.
    """
    if not ledger_path.is_file():
        logger.info(
            "finalize_tech_debt_ledger: ledger missing at %s (no-op)", ledger_path
        )
        return 0

    original_bytes = ledger_path.read_bytes()
    header_text, rows, malformed = parse_ledger(ledger_path)

    if malformed:
        for line in malformed:
            logger.error(
                "finalize_tech_debt_ledger: malformed row (%d columns expected, "
                "row will be skipped for manual intervention): %r",
                COLUMN_COUNT,
                line.rstrip("\n"),
            )
        return 1

    collapsed = collapse_rows(rows)
    collapsed_text = render_ledger(header_text, collapsed)
    collapsed_bytes = collapsed_text.encode("utf-8")

    if collapsed_bytes == original_bytes:
        logger.info(
            "finalize_tech_debt_ledger: nothing to collapse (%d row(s))", len(rows)
        )
        return 0

    row_delta = len(rows) - len(collapsed)
    if dry_run:
        logger.info(
            "finalize_tech_debt_ledger: --dry-run; would collapse %d row(s) -> %d row(s) "
            "(%d duplicate(s) merged); no changes written",
            len(rows),
            len(collapsed),
            row_delta,
        )
        return 0

    ledger_path.write_bytes(collapsed_bytes)
    logger.info(
        "finalize_tech_debt_ledger: collapsed %d row(s) -> %d row(s) (%d duplicate(s) merged)",
        len(rows),
        len(collapsed),
        row_delta,
    )
    return 0


# -- CLI ----------------------------------------------------------------------


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="finalize_tech_debt_ledger",
        description=(
            "Collapse duplicate rows in .ai-state/TECH_DEBT_LEDGER.md "
            "by dedup_key; status precedence resolved > in-flight > open > "
            "wontfix, tie-break by newer last-seen."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--merged",
        action="store_true",
        help="Run after a merge (default mode; retained for parity with finalize_adrs.py).",
    )
    mode_group.add_argument(
        "--all",
        action="store_true",
        help="Run the dedupe unconditionally (same behavior as --merged today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing the ledger.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. Never raises; logs errors and exits with a code."""
    args = _parse_args(argv)
    _configure_logging(args.verbose)

    try:
        with acquire_lock(LOCK_PATH):
            code = finalize_ledger(LEDGER_PATH, dry_run=args.dry_run)
    except OSError as exc:
        logger.error("finalize_tech_debt_ledger: %s", exc)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
