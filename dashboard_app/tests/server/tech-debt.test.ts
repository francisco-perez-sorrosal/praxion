/**
 * The tech-debt summary: only the rows still being worked (open or in-flight)
 * count, by severity; a ledger that is absent reads as absent, not as zero debt.
 */

import { mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { countActiveDebt, getTechDebtSummary } from "@/server/view-models/tech-debt";

const HEADER = [
  "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |",
  "|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|"
];

function row(id: string, severity: string, status: string, notes = "a note"): string {
  return `| ${id} | ${severity} | complexity | code-to-goals | x.py | code-quality |  | verifier | 2026-09-01 | 2026-09-01 | implementer | ${status} |  | ${notes} | ${id}-key |`;
}

const ledger = (...rows: string[]): string => ["# Tech Debt Ledger", "", ...HEADER, ...rows, ""].join("\n");

describe("countActiveDebt", () => {
  it("counts open and in-flight rows by severity", () => {
    const counts = countActiveDebt(
      ledger(row("td-001", "important", "open"), row("td-002", "important", "in-flight"), row("td-003", "suggested", "open"))
    );

    expect(counts).toEqual({ bySeverity: { important: 2, suggested: 1 }, inFlight: 1, open: 2 });
  });

  it("ignores rows that are resolved or won't-fix", () => {
    const counts = countActiveDebt(ledger(row("td-001", "critical", "resolved"), row("td-002", "important", "wontfix")));

    expect(counts).toEqual({ bySeverity: {}, inFlight: 0, open: 0 });
  });

  it("is not thrown off by a literal pipe in the notes column", () => {
    const counts = countActiveDebt(ledger(row("td-001", "important", "open", "uses a | b | c in prose")));

    expect(counts).toEqual({ bySeverity: { important: 1 }, inFlight: 0, open: 1 });
  });

  it("ignores table rows that are not ledger rows and files with no table", () => {
    expect(countActiveDebt(ledger("| n/a | important | open |"))).toEqual({ bySeverity: {}, inFlight: 0, open: 0 });
    expect(countActiveDebt("# Tech Debt Ledger\n\nNothing filed.\n")).toEqual({ bySeverity: {}, inFlight: 0, open: 0 });
  });

  it("files a row with no severity under unrated", () => {
    expect(countActiveDebt(ledger(row("td-001", "", "open"))).bySeverity).toEqual({ unrated: 1 });
  });
});

describe("getTechDebtSummary", () => {
  const roots: string[] = [];

  async function projectWith(ledgerBody: string | null): Promise<string> {
    const root = await mkdtemp(path.join(os.tmpdir(), "tech-debt-"));
    roots.push(root);
    await mkdir(path.join(root, ".ai-state"), { recursive: true });
    if (ledgerBody !== null) {
      await writeFile(path.join(root, ".ai-state", "TECH_DEBT_LEDGER.md"), ledgerBody);
    }
    return root;
  }

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
  });

  it("is absent when the project has no ledger", async () => {
    expect(await getTechDebtSummary(await projectWith(null))).toBeNull();
  });

  it("reports the counts with the ledger's path and modification time", async () => {
    const root = await projectWith(ledger(row("td-001", "important", "open")));
    const stamp = new Date("2026-09-27T10:00:00Z");
    await utimes(path.join(root, ".ai-state", "TECH_DEBT_LEDGER.md"), stamp, stamp);

    const summary = await getTechDebtSummary(root);

    expect(summary).toMatchObject({ bySeverity: { important: 1 }, mtime: stamp.toISOString(), open: 1 });
    expect(summary?.path.endsWith(path.join(".ai-state", "TECH_DEBT_LEDGER.md"))).toBe(true);
  });
});
