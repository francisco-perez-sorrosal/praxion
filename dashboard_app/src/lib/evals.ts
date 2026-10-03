/**
 * Shared types and pure helper functions for the eval leaderboard surface.
 *
 * Types mirror the 11-column EVAL_LOG.md schema defined in
 * `skills/agent-evals/references/run-ledger-schema.md § EVAL_LOG.md Column Set`.
 */

/** One row from EVAL_LOG.md. Numeric cells that are absent or non-numeric coerce to null. */
export type EvalLogRow = {
  run_id: string | null;
  task: string | null;
  generation: number | null;
  primary_metric: number | null;
  held_out_delta: number | null;
  model_id: string | null;
  prompt_hash: string | null;
  dataset_sha: string | null;
  cost_usd: number | null;
  git_sha: string | null;
  store_uri: string | null;
};

/** Props passed to the EvalLeaderboard component. */
export type EvalLeaderboardData = {
  rows: EvalLogRow[];
};

/** A ledger table of any other shape, kept as the cells it was written with. */
export type LedgerTable = {
  headers: string[];
  rows: string[][];
};

/**
 * What `.ai-state/eval_ledger/EVAL_LOG.md` holds (`path` is project-relative): the experiment leaderboard
 * (header carries a `run_id` column), a plain table of any other shape, or
 * nothing. A sum type so a shape never carries another shape's payload.
 */
export type EvalLedger =
  | { shape: "absent" }
  | { shape: "leaderboard"; path: string; rows: EvalLogRow[] }
  | { shape: "table"; path: string; table: LedgerTable };

export type LedgerShape = EvalLedger["shape"];

const LEADERBOARD_KEY_COLUMN = "run_id";

/** Selects the ledger shape from its header cells: `run_id` means leaderboard. */
export function detectLedgerShape(headerCells: readonly string[]): LedgerShape {
  const cells = headerCells.map((cell) => cell.trim().toLowerCase()).filter((cell) => cell !== "");
  if (cells.length === 0) {
    return "absent";
  }
  return cells.includes(LEADERBOARD_KEY_COLUMN) ? "leaderboard" : "table";
}

/** Trimmed text of a table cell; blank or missing cells are `null`. */
export function toStringCell(cell: string | undefined): string | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  return cell.trim();
}

/** Numeric table cell; blank, missing and non-numeric cells are `null`. */
export function toNumberCell(cell: string | undefined): number | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  const parsed = Number(cell.trim());
  return Number.isFinite(parsed) ? parsed : null;
}

const EVAL_STAMP = /^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-\d{2}Z$/;

/** `2026-10-03T01-22-07Z` (the stamp in quality-eval filenames) as `2026-10-03 01:22 UTC`. */
export function formatEvalTimestamp(stamp: string): string {
  const match = EVAL_STAMP.exec(stamp);
  return match ? `${match[1]} ${match[2]}:${match[3]} UTC` : stamp;
}

export type EvalSortKey = "primary_metric" | "generation" | "cost_usd";

/**
 * Sorts eval rows descending by the given key. Rows with null values for
 * the sort key are placed at the end (after non-null values).
 */
export function sortEvalRows(rows: EvalLogRow[], key: EvalSortKey): EvalLogRow[] {
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av === null && bv === null) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    // All three sort keys are numeric — descending order.
    return bv - av;
  });
}

/**
 * Filters eval rows to those whose `task` column contains the given substring
 * (case-insensitive). Returns the full list when `taskFilter` is empty or null.
 */
export function filterEvalRowsByTask(rows: EvalLogRow[], taskFilter: string | null): EvalLogRow[] {
  if (!taskFilter || taskFilter.trim() === "") {
    return rows;
  }
  const lower = taskFilter.toLowerCase();
  return rows.filter((row) => row.task?.toLowerCase().includes(lower) ?? false);
}

/**
 * Formats a numeric metric value for display. Returns "—" for null/undefined.
 * Floats render to 3 decimal places; integers render without decimals.
 */
export function formatEvalMetric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}

/**
 * Formats a USD cost value for display. Returns "—" for null/undefined.
 * Renders to 2 decimal places with a $ prefix.
 */
export function formatEvalCost(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `$${value.toFixed(2)}`;
}
