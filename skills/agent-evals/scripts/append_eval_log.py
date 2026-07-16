#!/usr/bin/env python3
"""Producer for the append-only `.ai-state/eval_ledger/EVAL_LOG.md` leaderboard.

Co-located with the schema it implements: `../references/run-ledger-schema.md`
§ EVAL_LOG.md Column Set defines the eleven-column contract this module
writes. Call `append_eval_log_row` once per kept eval run (the same event
that writes the project-root `EVAL_RESULTS.md`).

Stdlib-only. No third-party imports.
"""

from __future__ import annotations

from pathlib import Path

# Column order mirrors run-ledger-schema.md's documented header row exactly.
# Changing this tuple is a schema change -- update the schema doc first.
EVAL_LOG_COLUMNS = (
    "run_id",
    "task",
    "generation",
    "primary_metric",
    "held_out_delta",
    "model_id",
    "prompt_hash",
    "dataset_sha",
    "cost_usd",
    "git_sha",
    "store_uri",
)

# Columns stored as short prefixes of a full-length hash/SHA, per
# run-ledger-schema.md's documented widths.
SHORT_PREFIX_WIDTHS = {
    "prompt_hash": 8,
    "dataset_sha": 8,
    "git_sha": 7,
}

_LEDGER_RELATIVE_PATH = Path(".ai-state") / "eval_ledger" / "EVAL_LOG.md"


def append_eval_log_row(project_root: Path, row_fields: dict) -> None:
    """Append one schema-conformant row to `.ai-state/eval_ledger/EVAL_LOG.md`.

    `row_fields` must supply the 11 EVAL_LOG.md columns (see
    run-ledger-schema.md § EVAL_LOG.md Column Set): run_id, task, generation,
    primary_metric, held_out_delta, model_id, prompt_hash, dataset_sha,
    cost_usd, git_sha, store_uri. `prompt_hash`/`dataset_sha`/`git_sha` are
    passed as full-length strings; this helper truncates them to the
    documented short prefixes (8/8/7 chars) before writing.

    Creates `.ai-state/eval_ledger/` and writes the canonical 11-column
    header + separator on first write; subsequent calls append only (existing
    rows are never rewritten).

    Raises ValueError naming the missing field(s) if `row_fields` is missing
    any of the 11 required keys -- checked before any directory or file is
    created, so a rejected call has no filesystem side effect.
    """
    missing = [column for column in EVAL_LOG_COLUMNS if column not in row_fields]
    if missing:
        raise ValueError(f"append_eval_log_row: missing required field(s): {', '.join(missing)}")

    ledger_path = project_root / _LEDGER_RELATIVE_PATH
    if not ledger_path.exists():
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(_header_block(), encoding="utf-8")

    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(_format_row(row_fields) + "\n")


def _header_block() -> str:
    """Canonical header + dash separator row, matching the schema's column order."""
    header = "| " + " | ".join(EVAL_LOG_COLUMNS) + " |"
    separator = "|" + "|".join("---" for _ in EVAL_LOG_COLUMNS) + "|"
    return header + "\n" + separator + "\n"


def _format_row(row_fields: dict) -> str:
    """Render one data row, truncating hash-like fields to their short prefix width."""
    cells = []
    for column in EVAL_LOG_COLUMNS:
        value = str(row_fields[column])
        width = SHORT_PREFIX_WIDTHS.get(column)
        cells.append(value[:width] if width is not None else value)
    return "| " + " | ".join(cells) + " |"
