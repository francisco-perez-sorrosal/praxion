import "server-only";

import path from "node:path";

import { fileMtime, readText } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { parseMarkdownTable } from "@/server/parsers/markdown-table";

export type TechDebtSummary = {
  /** Rows still being worked, by severity (`critical`, `important`, `suggested`, ...). */
  bySeverity: Record<string, number>;
  inFlight: number;
  mtime: string | null;
  open: number;
  path: string;
};

type DebtCounts = Pick<TechDebtSummary, "bySeverity" | "inFlight" | "open">;

const LEDGER_RELATIVE_PATH = [".ai-state", "TECH_DEBT_LEDGER.md"] as const;
const DEBT_ROW_ID = /^td-\d+/;
const OPEN_STATUS = "open";
const IN_FLIGHT_STATUS = "in-flight";

/**
 * Counts the active rows of a ledger table. Only `status` and `severity`
 * are read; both sit before the free-text `notes` column, so a literal pipe in
 * a note cannot shift them. Rows that do not start with a `td-NNN` id and rows
 * in any other status (resolved, wontfix) are ignored.
 */
export function countActiveDebt(body: string): DebtCounts {
  const counts: DebtCounts = { bySeverity: {}, inFlight: 0, open: 0 };
  for (const row of parseMarkdownTable(body)) {
    if (!DEBT_ROW_ID.test(row["id"] ?? "")) {
      continue;
    }
    const status = (row["status"] ?? "").toLowerCase();
    if (status !== OPEN_STATUS && status !== IN_FLIGHT_STATUS) {
      continue;
    }
    if (status === OPEN_STATUS) {
      counts.open += 1;
    } else {
      counts.inFlight += 1;
    }
    const severity = (row["severity"] ?? "").toLowerCase() || "unrated";
    counts.bySeverity[severity] = (counts.bySeverity[severity] ?? 0) + 1;
  }
  return counts;
}

/** The active tech-debt rows by severity; `null` when the ledger is absent or unreadable. */
export async function getTechDebtSummary(projectRoot: string): Promise<TechDebtSummary | null> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const ledgerPath = await assertAllowedArtifactPath(validatedRoot, path.join(validatedRoot, ...LEDGER_RELATIVE_PATH));
  const body = await readText(ledgerPath);
  if (body === null) {
    return null;
  }
  return { ...countActiveDebt(body), mtime: await fileMtime(ledgerPath), path: ledgerPath };
}
