import "server-only";

import path from "node:path";

import type { EvalLeaderboardData, EvalLogRow } from "@/lib/evals";
import { sortEvalRows } from "@/lib/evals";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";
import { parseMarkdownTable } from "@/server/parsers/markdown-table";

function toStringCell(cell: string | undefined): string | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  return cell.trim();
}

function toNumberCell(cell: string | undefined): number | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  const parsed = Number(cell.trim());
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Parses the EVAL_LOG.md append-only table into a typed array of eval rows.
 * Numeric columns that are blank or non-numeric coerce to null.
 * Mirrors the parseMetricsLog pattern from the metrics view-model.
 */
export function parseEvalsLog(body: string): EvalLogRow[] {
  const rows = parseMarkdownTable(body);
  return rows.map((row): EvalLogRow => ({
    run_id: toStringCell(row["run_id"]),
    task: toStringCell(row["task"]),
    generation: toNumberCell(row["generation"]),
    primary_metric: toNumberCell(row["primary_metric"]),
    held_out_delta: toNumberCell(row["held_out_delta"]),
    model_id: toStringCell(row["model_id"]),
    prompt_hash: toStringCell(row["prompt_hash"]),
    dataset_sha: toStringCell(row["dataset_sha"]),
    cost_usd: toNumberCell(row["cost_usd"]),
    git_sha: toStringCell(row["git_sha"]),
    store_uri: toStringCell(row["store_uri"])
  }));
}

/**
 * Reads `.ai-state/eval_ledger/EVAL_LOG.md`, parses the 11-column Markdown
 * table, and returns typed `EvalLeaderboardData` sorted descending by
 * `primary_metric`. When the file is absent or empty, returns an empty rows
 * array — the component renders the empty-state gracefully.
 */
export async function getEvalsData(projectRoot: string): Promise<EvalLeaderboardData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const logPath = path.join(validatedRoot, ".ai-state", "eval_ledger", "EVAL_LOG.md");

  const allowedPath = await assertAllowedArtifactPath(validatedRoot, logPath);
  const logFile = await readMarkdown(allowedPath);

  if (!logFile) {
    return { rows: [] };
  }

  const parsed = parseEvalsLog(logFile.body);
  const sorted = sortEvalRows(parsed, "primary_metric");

  return { rows: sorted };
}
