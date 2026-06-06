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
