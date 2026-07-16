#!/usr/bin/env python3
"""Reconcile the tech-debt ledger pair (`TECH_DEBT_LEDGER.md` + `TECH_DEBT_RESOLVED.md`).

Reads both files' Markdown tables (14 row fields + structural `dedup_key` per table row), groups rows across the pair by
`dedup_key`, picks one survivor per group with status precedence (`resolved >
in-flight > open > wontfix`) and tie-break by newer `last-seen`, then routes
each survivor to the correct file: terminal-status (`resolved` / `wontfix`)
to RESOLVED, active-status (`open` / `in-flight`) to LEDGER. Cross-file
`dedup_key` matches trigger **re-open**: the historical resolved row moves
back to LEDGER with `status = open`, the recurrence-driving row collapses
into it, and a recurrence note is appended. Idempotent; an advisory file
lock serializes concurrent post-merge invocations.

Invocation modes:

    finalize_tech_debt_ledger.py                 # --merged (default)
    finalize_tech_debt_ledger.py --all           # run regardless of merge state
    finalize_tech_debt_ledger.py --dry-run       # print the plan, do not write
    finalize_tech_debt_ledger.py --verbose       # debug logging

Exit codes:

    0 -- success, or no changes (idempotent no-op)
    1 -- manual intervention required (malformed row, id collision, I/O error)

Design notes:
- Single-purpose script: only ledger-pair reconciliation.
- Advisory `fcntl` lock serializes concurrent runs from hook + command.
- Byte-equivalent output when no changes are needed (idempotency contract).
- RESOLVED.md is treated as empty when absent; created lazily only when a
  terminal row needs to land there.
- The lock file path is shared across the pair so worktree merges that touch
  both files cannot interleave writes.
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

from _repo_root import is_plugin_cache_path
from _repo_root import resolve_repo_root as _resolve_repo_root

# -- Constants ----------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
LEDGER_PATH = REPO_ROOT / ".ai-state" / "TECH_DEBT_LEDGER.md"
RESOLVED_PATH = REPO_ROOT / ".ai-state" / "TECH_DEBT_RESOLVED.md"
LOCK_PATH = REPO_ROOT / ".ai-state" / ".tech_debt_ledger_finalize.lock"


def resolve_repo_root(cli_repo_root: str | None) -> Path:
    """Resolve the repo root via the shared resolver, logging the fallback."""

    def _log_fallback(fallback: Path) -> None:
        logger.warning(
            "finalize_tech_debt_ledger: could not resolve repo root from "
            "--repo-root or git; falling back to script-relative %s",
            fallback,
        )

    return _resolve_repo_root(cli_repo_root, script_dir=SCRIPT_DIR, on_fallback=_log_fallback)


def _apply_repo_root(root: Path) -> None:
    """Rebind the module-level path constants to a resolved repo root."""
    global REPO_ROOT, LEDGER_PATH, RESOLVED_PATH, LOCK_PATH
    REPO_ROOT = root
    LEDGER_PATH = root / ".ai-state" / "TECH_DEBT_LEDGER.md"
    RESOLVED_PATH = root / ".ai-state" / "TECH_DEBT_RESOLVED.md"
    LOCK_PATH = root / ".ai-state" / ".tech_debt_ledger_finalize.lock"


# Schema-defined column order. Canonical field definitions:
# skills/software-planning/references/tech-debt-ledger.md § Schema
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

TERMINAL_STATUSES: frozenset[str] = frozenset({"resolved", "wontfix"})

NOTES_SEPARATOR = " // "
LOCATION_SEPARATOR = ", "
RECURRENCE_NOTE_PREFIX = "recurrence: re-opened "

# Default header used when RESOLVED.md must be created lazily.
DEFAULT_RESOLVED_HEADER = (
    "# Resolved Tech Debt\n"
    "\n"
    "<!-- Sibling of TECH_DEBT_LEDGER.md holding rows with terminal status (resolved / wontfix).\n"
    "     Rows arrive via scripts/finalize_tech_debt_ledger.py migration when status transitions\n"
    "     to a terminal value. Schema, lifecycle, and re-open semantics are defined canonically\n"
    "     in skills/software-planning/references/tech-debt-ledger.md. Do not duplicate\n"
    "     the schema here — the skill reference is the single source of truth. -->\n"
    "\n"
    "**Schema**: 14 row fields + 1 structural `dedup_key`. See "
    "[`skills/software-planning/references/tech-debt-ledger.md`](../skills/software-planning/references/tech-debt-ledger.md) "
    "§ Schema for field definitions.\n"
    "\n"
    "**Rows arrive here automatically** when status transitions to `resolved` or `wontfix`. "
    "The pair forms one logical namespace with `TECH_DEBT_LEDGER.md`: `id` and `dedup_key` "
    "are unique across both files. Cross-file `dedup_key` matches trigger re-open (the "
    "historical resolved row moves back to LEDGER).\n"
    "\n"
    "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |\n"
    "|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|\n"
)

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

    Returns empty parts when `path` is absent — callers treat that as an
    empty ledger rather than an error, so a missing RESOLVED.md is benign.
    """
    if not path.is_file():
        return "", [], []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    header_end_index = _locate_separator_index(lines)
    if header_end_index is None:
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
    """Return the precedence rank of a status (lower == higher precedence)."""
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
    """Invert ISO-date ordering so `min(..., key=)` prefers the later date."""
    if not iso_date:
        return (1, "")
    negated = "".join(chr(126 - ord(ch)) if " " <= ch <= "~" else ch for ch in iso_date)
    return (0, negated)


def _earliest_first_seen(rows: list[LedgerRow]) -> str:
    """Return the lexicographically earliest non-empty first-seen across rows."""
    values = [row.get("first-seen") for row in rows if row.get("first-seen")]
    if not values:
        return ""
    return min(values)


def _latest_last_seen(rows: list[LedgerRow]) -> str:
    """Return the lexicographically latest non-empty last-seen across rows."""
    values = [row.get("last-seen") for row in rows if row.get("last-seen")]
    if not values:
        return ""
    return max(values)


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


def _is_terminal(status: str) -> bool:
    """Return True if status is a terminal value (resolved / wontfix)."""
    return status in TERMINAL_STATUSES


def _detect_id_collisions(rows: list[LedgerRow]) -> dict[str, list[str]]:
    """Return ids that label 2+ distinct findings (a true `id` collision).

    Two rows sharing an `id` with the SAME `dedup_key` are the same finding
    (a legitimate collapse candidate) -- not a collision. Two rows sharing an
    `id` with DIFFERENT `dedup_key`s means one `td-NNN` number was assigned
    to two unrelated findings (precedent: the td-038/td-039 collisions,
    renumbered to td-053/td-054). Checked across the full pair so a
    collision spanning LEDGER and RESOLVED is caught too.
    """
    dedup_keys_by_id: dict[str, set[str]] = {}
    for row in rows:
        dedup_keys_by_id.setdefault(row.get("id"), set()).add(row.get("dedup_key"))
    return {
        row_id: sorted(dedup_keys)
        for row_id, dedup_keys in dedup_keys_by_id.items()
        if len(dedup_keys) > 1
    }


# -- Pair reconciliation ------------------------------------------------------


def reconcile_pair(
    active_rows: list[LedgerRow], resolved_rows: list[LedgerRow]
) -> tuple[list[LedgerRow], list[LedgerRow]]:
    """Group rows across the pair by dedup_key; route survivors by terminal status.

    Cross-file `dedup_key` matches trigger re-open: the historical resolved
    row moves back to LEDGER with `status = open`, the recurrence-driving row
    collapses into it, and a recurrence note is appended.

    Within-file collapses follow standard precedence (`resolved > in-flight >
    open > wontfix`, tie-break by newer `last-seen`); the survivor is then
    routed to LEDGER or RESOLVED based on its final status.

    Order is preserved by first-appearance per output file: rows that stay in
    their source file keep their position; rows that move (re-open or first-
    time migration) append to the destination file.
    """
    tagged = [(row, "active") for row in active_rows] + [(row, "resolved") for row in resolved_rows]

    groups: dict[str, list[tuple[LedgerRow, str]]] = {}
    key_order: list[str] = []
    for row, source_tag in tagged:
        key = row.get("dedup_key")
        if key not in groups:
            groups[key] = []
            key_order.append(key)
        groups[key].append((row, source_tag))

    new_active: list[LedgerRow] = []
    new_resolved: list[LedgerRow] = []
    for key in key_order:
        group = groups[key]
        sources_present = {tag for _, tag in group}
        if sources_present == {"active", "resolved"} or sources_present == {
            "resolved",
            "active",
        }:
            survivor = _reopen_collapse(group)
            new_active.append(survivor)
            continue

        rows_only = [row for row, _ in group]
        if len(rows_only) == 1:
            survivor = rows_only[0]
        else:
            survivor = _collapse_group(rows_only)

        if _is_terminal(survivor.get("status")):
            new_resolved.append(survivor)
        else:
            new_active.append(survivor)

    return new_active, new_resolved


def _collapse_group(rows: list[LedgerRow]) -> LedgerRow:
    """Standard within-file collapse: precedence + field merge."""
    survivor = _pick_survivor(rows)
    discarded = [row for row in rows if row is not survivor]
    return survivor.with_updates(
        {
            "first-seen": _earliest_first_seen(rows),
            "location": _merge_locations(rows),
            "notes": _merge_notes(survivor, discarded),
        }
    )


def _reopen_collapse(group: list[tuple[LedgerRow, str]]) -> LedgerRow:
    """Build the re-open survivor: historical id+first-seen, active status+last-seen.

    The historical row (from RESOLVED) is the carrier of `id`, `first-seen`,
    and the original notes. The recurrence-driving row (from LEDGER) is the
    carrier of the new `last-seen` and the recurrence event itself. The
    survivor is routed to LEDGER with `status = open`, `resolved-by` cleared,
    and a recurrence-marker note appended after the merged notes block.
    """
    resolved_rows = [row for row, tag in group if tag == "resolved"]
    active_rows = [row for row, tag in group if tag == "active"]

    historical = _pick_survivor(resolved_rows) if len(resolved_rows) > 1 else resolved_rows[0]
    active_survivor = _pick_survivor(active_rows) if len(active_rows) > 1 else active_rows[0]

    recurrence_date = active_survivor.get("last-seen") or _latest_last_seen(active_rows)
    all_rows = resolved_rows + active_rows
    merged_notes = _merge_notes(historical, [r for r in all_rows if r is not historical])
    recurrence_marker = f"{RECURRENCE_NOTE_PREFIX}{recurrence_date}"
    final_notes = (
        f"{merged_notes}{NOTES_SEPARATOR}{recurrence_marker}" if merged_notes else recurrence_marker
    )

    return historical.with_updates(
        {
            "status": "open",
            "last-seen": recurrence_date,
            "resolved-by": "",
            "location": _merge_locations(all_rows),
            "notes": final_notes,
        }
    )


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
    """Acquire an exclusive advisory lock for the duration of the context."""
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


def finalize_pair(
    ledger_path: Path = LEDGER_PATH,
    resolved_path: Path = RESOLVED_PATH,
    dry_run: bool = False,
) -> int:
    """Reconcile the LEDGER + RESOLVED pair. Returns an exit code.

    Idempotency: when reconciliation produces bytes identical to both inputs,
    neither file is rewritten. RESOLVED.md is created lazily — only when the
    reconciled state has terminal-status rows to land there.
    """
    ledger_header, ledger_rows, ledger_malformed = parse_ledger(ledger_path)
    resolved_header, resolved_rows, resolved_malformed = parse_ledger(resolved_path)

    malformed = ledger_malformed + resolved_malformed
    if malformed:
        for line in malformed:
            logger.error(
                "finalize_tech_debt_ledger: malformed row (%d columns expected, "
                "row will be skipped for manual intervention): %r",
                COLUMN_COUNT,
                line.rstrip("\n"),
            )
        return 1

    id_collisions = _detect_id_collisions(ledger_rows + resolved_rows)
    if id_collisions:
        for row_id, dedup_keys in sorted(id_collisions.items()):
            logger.error(
                "finalize_tech_debt_ledger: id collision -- %r labels %d distinct "
                "findings (dedup_keys=%s); renumber one of them before finalizing",
                row_id,
                len(dedup_keys),
                dedup_keys,
            )
        return 1

    new_active, new_resolved = reconcile_pair(ledger_rows, resolved_rows)

    new_ledger_text = (
        render_ledger(ledger_header, new_active)
        if ledger_header
        else _render_with_default_ledger_header(new_active, ledger_path)
    )
    new_resolved_text = render_ledger(resolved_header or DEFAULT_RESOLVED_HEADER, new_resolved)

    ledger_changed = _bytes_changed(ledger_path, new_ledger_text)
    resolved_changed = _resolved_changed(resolved_path, new_resolved, new_resolved_text)

    if not ledger_changed and not resolved_changed:
        logger.info(
            "finalize_tech_debt_ledger: nothing to reconcile (active=%d, resolved=%d)",
            len(ledger_rows),
            len(resolved_rows),
        )
        return 0

    if dry_run:
        logger.info(
            "finalize_tech_debt_ledger: --dry-run; would reconcile "
            "active %d -> %d, resolved %d -> %d; no changes written",
            len(ledger_rows),
            len(new_active),
            len(resolved_rows),
            len(new_resolved),
        )
        return 0

    if ledger_changed and ledger_path.is_file():
        ledger_path.write_bytes(new_ledger_text.encode("utf-8"))
    if resolved_changed:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_bytes(new_resolved_text.encode("utf-8"))

    logger.info(
        "finalize_tech_debt_ledger: reconciled active %d -> %d, resolved %d -> %d",
        len(ledger_rows),
        len(new_active),
        len(resolved_rows),
        len(new_resolved),
    )
    return 0


def _render_with_default_ledger_header(rows: list[LedgerRow], ledger_path: Path) -> str:
    """Render LEDGER text when the file is missing entirely.

    The active LEDGER is expected to exist in any onboarded project; if the
    caller invokes the script against a filesystem with no LEDGER, return
    an empty string so the byte-equivalence check skips writing — we don't
    want this script silently bootstrapping a project's ledger pair.
    """
    if not rows:
        return ""
    # Best-effort: synthesize a minimal header when LEDGER must be written.
    return DEFAULT_RESOLVED_HEADER.replace(
        "# Resolved Tech Debt", "# Technical Debt Ledger"
    ) + "".join(render_row(row) for row in rows)


def _bytes_changed(path: Path, new_text: str) -> bool:
    """Compare new_text against current file contents; absent file = changed only when new_text non-empty."""
    if not path.is_file():
        return bool(new_text)
    return path.read_bytes() != new_text.encode("utf-8")


def _resolved_changed(path: Path, new_rows: list[LedgerRow], new_text: str) -> bool:
    """Resolved-file change check: never write an empty RESOLVED.md just to add a header."""
    if not path.is_file():
        return bool(new_rows)  # only create the file if there are rows to land
    return path.read_bytes() != new_text.encode("utf-8")


# Backwards-compatible alias retained for any caller that imported the old name.
def finalize_ledger(ledger_path: Path = LEDGER_PATH, dry_run: bool = False) -> int:
    """Compatibility shim for the pre-pair API. Routes to finalize_pair."""
    return finalize_pair(ledger_path=ledger_path, resolved_path=RESOLVED_PATH, dry_run=dry_run)


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
            "Reconcile the .ai-state/TECH_DEBT_LEDGER.md + TECH_DEBT_RESOLVED.md pair: "
            "collapse duplicates by dedup_key, route survivors by terminal status, "
            "handle re-open on cross-file dedup_key match."
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
        help="Run reconciliation unconditionally (same behavior as --merged today).",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        help=(
            "Repo root whose .ai-state/ ledger pair to reconcile. When omitted, "
            "resolved from `git rev-parse --show-toplevel` in the current "
            "directory. Required when the script runs from a symlinked plugin cache."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing the pair.",
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
    root = resolve_repo_root(args.repo_root)
    if is_plugin_cache_path(root):
        logger.error(
            "finalize_tech_debt_ledger: refusing to run against a plugin-cache "
            "path (%s); pass --repo-root or run from the consumer worktree",
            root,
        )
        sys.exit(1)
    _apply_repo_root(root)

    try:
        with acquire_lock(LOCK_PATH):
            code = finalize_pair(
                ledger_path=LEDGER_PATH,
                resolved_path=RESOLVED_PATH,
                dry_run=args.dry_run,
            )
    except OSError as exc:
        logger.error("finalize_tech_debt_ledger: %s", exc)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
