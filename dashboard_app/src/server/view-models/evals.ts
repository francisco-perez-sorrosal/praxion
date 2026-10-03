import "server-only";

import path from "node:path";

import type { EvalLedger, EvalLogRow, LedgerTable } from "@/lib/evals";
import { detectLedgerShape, sortEvalRows, toNumberCell, toStringCell } from "@/lib/evals";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";
import { parseMarkdownTable } from "@/server/parsers/markdown-table";

const LEDGER_RELATIVE_PATH = ".ai-state/eval_ledger/EVAL_LOG.md";

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

/** The cells of the first table line in the body (its header row); empty when there is no table. */
function firstTableHeader(body: string): string[] {
  const headerLine = body
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("|"));
  return headerLine === undefined
    ? []
    : headerLine.split("|").slice(1, -1).map((cell) => cell.trim());
}

function hasAnyValue(row: EvalLogRow): boolean {
  return Object.values(row).some((value) => value !== null);
}

function toLedgerTable(body: string, headers: string[]): LedgerTable {
  const rows = parseMarkdownTable(body)
    .map((record) => headers.map((header) => record[header] ?? ""))
    .filter((cells) => cells.some((cell) => cell !== ""));
  return { headers, rows };
}

/**
 * Classifies the ledger body by its header and keeps only that shape's payload.
 * A leaderboard drops rows with no value at all, so no row of placeholder dashes
 * can reach the page.
 */
export function parseEvalLedger(body: string, ledgerPath: string): EvalLedger {
  const headers = firstTableHeader(body);
  const shape = detectLedgerShape(headers);
  if (shape === "leaderboard") {
    const rows = sortEvalRows(parseEvalsLog(body).filter(hasAnyValue), "primary_metric");
    return { shape, path: ledgerPath, rows };
  }
  if (shape === "table") {
    return { shape, path: ledgerPath, table: toLedgerTable(body, headers) };
  }
  return { shape };
}

/**
 * Reads `.ai-state/eval_ledger/EVAL_LOG.md` and returns it in its own shape
 * (`path` is project-relative, for display):
 * leaderboard rows ranked by `primary_metric`, any other table as written, or
 * `absent` when the file is missing, unreadable or holds no table.
 */
export async function getEvalsData(projectRoot: string): Promise<EvalLedger> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const logPath = path.join(validatedRoot, LEDGER_RELATIVE_PATH);

  const allowedPath = await assertAllowedArtifactPath(validatedRoot, logPath);
  const logFile = await readMarkdown(allowedPath);

  return logFile ? parseEvalLedger(logFile.body, LEDGER_RELATIVE_PATH) : { shape: "absent" };
}
