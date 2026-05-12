/**
 * Behavioral tests for getSidebarSignals — the small server view-model that
 * composes the active-workshop count and the latest sentinel grade for the
 * sidebar badge and chip.
 *
 * Fixture pattern: mkdtemp temp project root seeded with the exact directory
 * structure that workshops.ts / sentinel.ts read, matching the pattern
 * established in workshops.test.ts and secondary-surfaces.test.ts.
 *
 * Imports are deferred into each test body so pytest collection succeeds before
 * the implementation file exists (concurrent BDD/TDD RED handshake).
 */

import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

// ─── Temp-root bookkeeping ────────────────────────────────────────────────────

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

/**
 * Seeds a bare valid Praxion project root: only .ai-state/ present,
 * satisfying validateProjectRoot without any workshop or sentinel data.
 */
async function seedBareProjectRoot(root: string): Promise<void> {
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
}

afterEach(async () => {
  await Promise.all(
    tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true }))
  );
});

// ─── Workshop fixture helpers ─────────────────────────────────────────────────

/**
 * Writes a WIP.md file for an in-progress workshop.
 * Mirrors the fixture pattern in workshops.test.ts.
 */
async function writeInProgressWip(workshopDir: string): Promise<void> {
  await writeFile(
    path.join(workshopDir, "WIP.md"),
    `## Current Step\n\nDo the thing\n\n## Status\n\n[IN-PROGRESS] - Work underway\n\n## Progress\n\n- [x] Step alpha: Earlier step\n- [ ] Step beta: Do the thing\n`
  );
}

/**
 * Writes a WIP.md for a completed workshop.
 */
async function writeCompleteWip(workshopDir: string): Promise<void> {
  await writeFile(
    path.join(workshopDir, "WIP.md"),
    `## Current Step\n\nAll done\n\n## Status\n\n[COMPLETE]\n\n## Progress\n\n- [x] Step alpha: All done\n`
  );
}

// ─── Sentinel fixture helpers ─────────────────────────────────────────────────

/**
 * Builds a SENTINEL_LOG.md body with one row per entry in the provided array.
 * Timestamps are used as-is (lexicographic sort = chronological for ISO strings).
 */
function buildSentinelLogBody(entries: Array<{ timestamp: string; grade: string }>): string {
  const header = [
    "# Sentinel Log",
    "",
    "| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |",
    "|-----------|--------------|-----------|-------------------|---------------------|-------------|"
  ].join("\n");

  const rows = entries
    .map(
      ({ timestamp, grade }) =>
        `| ${timestamp} | ${grade} | 30 | 0/2/3 | ${grade} | SENTINEL_REPORT_fake.md |`
    )
    .join("\n");

  return `${header}\n${rows}\n`;
}

/**
 * Seeds a sentinel_reports directory with a SENTINEL_LOG.md and the specified
 * report files. Each report file is a minimal markdown body that isSentinelReport
 * matches (SENTINEL_REPORT_YYYY-MM-DD_HH-MM-SS.md).
 */
async function seedSentinelReports(
  root: string,
  reports: Array<{ filename: string; grade: string }>,
  logEntries?: Array<{ timestamp: string; grade: string }>
): Promise<void> {
  const reportsDir = path.join(root, ".ai-state", "sentinel_reports");
  await mkdir(reportsDir, { recursive: true });

  for (const { filename, grade } of reports) {
    await writeFile(
      path.join(reportsDir, filename),
      `## Ecosystem Health: ${grade}\n\nReport content.\n`
    );
  }

  const entries =
    logEntries ??
    reports.map((r, i) => ({
      timestamp: `2026-05-${String(10 + i).padStart(2, "0")}T09:00:00Z`,
      grade: r.grade
    }));

  await writeFile(path.join(reportsDir, "SENTINEL_LOG.md"), buildSentinelLogBody(entries));
}

// ─── getSidebarSignals ────────────────────────────────────────────────────────

describe("getSidebarSignals", () => {
  it("returns the count of active workshops when the project has in-progress tasks", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-active-workshops-");
    await seedBareProjectRoot(root);
    await mkdir(path.join(root, ".ai-work"), { recursive: true });

    const workshop1 = path.join(root, ".ai-work", "task-alpha");
    const workshop2 = path.join(root, ".ai-work", "task-beta");
    await mkdir(workshop1, { recursive: true });
    await mkdir(workshop2, { recursive: true });
    await writeInProgressWip(workshop1);
    await writeInProgressWip(workshop2);

    const signals = await getSidebarSignals(root);

    expect(signals.activeWorkshops).toBeGreaterThanOrEqual(1);
  });

  it("returns activeWorkshops of 0 when no .ai-work directory exists", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-no-workshops-");
    await seedBareProjectRoot(root);
    // Deliberately no .ai-work directory

    const signals = await getSidebarSignals(root);

    expect(signals.activeWorkshops).toBe(0);
  });

  it("returns the latest sentinel grade when a sentinel report and log exist", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-sentinel-grade-");
    await seedBareProjectRoot(root);
    await seedSentinelReports(
      root,
      [{ filename: "SENTINEL_REPORT_2026-05-10_09-00-00.md", grade: "B" }],
      [{ timestamp: "2026-05-10T09:00:00Z", grade: "B" }]
    );

    const signals = await getSidebarSignals(root);

    expect(signals.sentinelGrade).toBe("B");
  });

  it("returns the newest grade when multiple sentinel reports exist", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-sentinel-latest-");
    await seedBareProjectRoot(root);
    await seedSentinelReports(
      root,
      [
        { filename: "SENTINEL_REPORT_2026-05-10_09-00-00.md", grade: "B" },
        { filename: "SENTINEL_REPORT_2026-05-11_14-30-00.md", grade: "A" }
      ],
      [
        { timestamp: "2026-05-10T09:00:00Z", grade: "B" },
        { timestamp: "2026-05-11T14:30:00Z", grade: "A" }
      ]
    );

    const signals = await getSidebarSignals(root);

    // The newest entry (A) must win — not an earlier one (B)
    expect(signals.sentinelGrade).toBe("A");
    expect(signals.sentinelGrade).not.toBe("B");
  });

  it("returns sentinelGrade null when no sentinel reports exist", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-no-sentinel-");
    await seedBareProjectRoot(root);
    // No sentinel_reports directory seeded

    const signals = await getSidebarSignals(root);

    expect(signals.sentinelGrade).toBeNull();
  });

  it("returns zero activeWorkshops and null grade for a bare project root", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-bare-project-");
    await seedBareProjectRoot(root);
    // Neither .ai-work nor sentinel_reports seeded

    const signals = await getSidebarSignals(root);

    expect(signals.activeWorkshops).toBe(0);
    expect(signals.sentinelGrade).toBeNull();
  });

  it("does not throw when the project root has no .ai-state/sentinel_reports directory", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-missing-sentinel-dir-");
    await seedBareProjectRoot(root);
    await mkdir(path.join(root, ".ai-work"), { recursive: true });

    const workshop = path.join(root, ".ai-work", "task-omega");
    await mkdir(workshop, { recursive: true });
    await writeInProgressWip(workshop);

    // Must not throw; sentinelGrade degrades to null; activeWorkshops is numeric
    const signals = await getSidebarSignals(root);
    expect(signals.sentinelGrade).toBeNull();
    expect(typeof signals.activeWorkshops).toBe("number");
  });

  it("degrades to sentinelGrade null when the sentinel log cannot be parsed", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-malformed-sentinel-");
    await seedBareProjectRoot(root);

    const reportsDir = path.join(root, ".ai-state", "sentinel_reports");
    await mkdir(reportsDir, { recursive: true });

    // Malformed log: no recognizable table rows
    await writeFile(
      path.join(reportsDir, "SENTINEL_LOG.md"),
      "# Sentinel Log\n\nNo table data here — just prose.\n"
    );
    await writeFile(
      path.join(reportsDir, "SENTINEL_REPORT_2026-05-10_10-00-00.md"),
      "## Ecosystem Health: C\n\nReport content.\n"
    );

    const signals = await getSidebarSignals(root);

    // No parseable grade in the log → null (no crash)
    expect(signals.sentinelGrade).toBeNull();
  });

  it("returns a structure consistent with what workshops and sentinel view-models return for the same root", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");
    const { getWorkshopsData } = await import("@/server/view-models/workshops");
    const { getSentinelData } = await import("@/server/view-models/sentinel");

    const root = await createTempProjectRoot("sidebar-signals-composition-");
    await seedBareProjectRoot(root);
    await mkdir(path.join(root, ".ai-work"), { recursive: true });

    const workshop = path.join(root, ".ai-work", "task-composed");
    await mkdir(workshop, { recursive: true });
    await writeInProgressWip(workshop);

    await seedSentinelReports(
      root,
      [{ filename: "SENTINEL_REPORT_2026-05-12_08-00-00.md", grade: "A" }],
      [{ timestamp: "2026-05-12T08:00:00Z", grade: "A" }]
    );

    const [signals, workshops, sentinelData] = await Promise.all([
      getSidebarSignals(root),
      getWorkshopsData(root),
      getSentinelData(root)
    ]);

    // activeWorkshops must not exceed the total workshop count
    expect(signals.activeWorkshops).toBeLessThanOrEqual(workshops.length);

    // sentinelGrade must match the latest grade in logSeries when one exists
    const latestLogEntry = sentinelData.logSeries[sentinelData.logSeries.length - 1];
    if (latestLogEntry?.grade !== null && latestLogEntry?.grade !== undefined) {
      expect(signals.sentinelGrade).toBe(latestLogEntry.grade);
    } else {
      expect(signals.sentinelGrade).toBeNull();
    }
  });
});
