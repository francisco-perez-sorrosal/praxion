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

import { mkdir, mkdtemp, readdir, rm, symlink, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { FIXED_NOW, removeProjectRoots } from "../acceptance/drivers/fixture-project";
import { cleanProject, emptyProject, fullProject } from "../acceptance/drivers/project-presets";

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
  vi.restoreAllMocks();
  await removeProjectRoots();
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
 * Row i names `reportFiles[i]`: the digest binds a log row to its report by file name.
 */
function buildSentinelLogBody(
  entries: Array<{ timestamp: string; grade: string }>,
  reportFiles: readonly string[]
): string {
  const header = [
    "# Sentinel Log",
    "",
    "| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |",
    "|-----------|--------------|-----------|-------------------|---------------------|-------------|"
  ].join("\n");

  const rows = entries
    .map(
      ({ timestamp, grade }, index) =>
        `| ${timestamp} | ${grade} | 30 | 0/2/3 | ${grade} | ${reportFiles[index] ?? "SENTINEL_REPORT_fake.md"} |`
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

  await writeFile(
    path.join(reportsDir, "SENTINEL_LOG.md"),
    buildSentinelLogBody(
      entries,
      reports.map((report) => report.filename)
    )
  );
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

  it("reads the newest report as not graded when the log has no row for it", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const root = await createTempProjectRoot("sidebar-signals-sentinel-unlogged-");
    await seedBareProjectRoot(root);
    await seedSentinelReports(
      root,
      [{ filename: "SENTINEL_REPORT_2026-05-10_09-00-00.md", grade: "B" }],
      [{ timestamp: "2026-05-10T09:00:00Z", grade: "B" }]
    );
    // A newer run cut short before the log append: a report, but no row naming it.
    await writeFile(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-05-11_09-00-00.md"),
      "# Sentinel Report [PARTIAL]\n\nTruncated.\n"
    );

    const signals = await getSidebarSignals(root);

    expect(signals.sentinelGrade).toBeNull();
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

// ─── The signals the Overview shares ──────────────────────────────────────────

describe("getSidebarSignals — workshop recency", () => {
  const NOW = new Date("2026-10-02T15:00:00Z");

  async function seedWorkshop(root: string, slug: string, touched: Date): Promise<void> {
    const dir = path.join(root, ".ai-work", slug);
    await mkdir(dir, { recursive: true });
    await writeInProgressWip(dir);
    await utimes(path.join(dir, "WIP.md"), touched, touched);
  }

  it("counts only the workshops touched within the Active window", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");
    const root = await createTempProjectRoot("sidebar-signals-recency-");
    await seedBareProjectRoot(root);
    await seedWorkshop(root, "recent", new Date("2026-10-01T15:00:00Z"));
    await seedWorkshop(root, "edge", new Date("2026-09-25T15:00:00Z"));
    await seedWorkshop(root, "abandoned", new Date("2026-09-10T15:00:00Z"));

    const signals = await getSidebarSignals(root, NOW);

    expect(signals.activeWorkshops).toBe(2);
  });
});

describe("getSidebarSignals — metrics health and quality-eval failures", () => {
  it("reads the quality-eval failure count and the metrics health word from the fixtures", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const signals = await getSidebarSignals(await fullProject(), FIXED_NOW);

    expect(signals).toEqual({ activeWorkshops: 2, evalFails: 3, metricsHealth: "WORSENING", sentinelGrade: "C" });
  });

  it("words a project with a single metrics snapshot as the baseline", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const signals = await getSidebarSignals(await cleanProject(), FIXED_NOW);

    expect(signals.metricsHealth).toBe("BASELINE CAPTURED");
  });

  it("omits every signal whose family is absent", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");

    const signals = await getSidebarSignals(await emptyProject(), FIXED_NOW);

    expect(signals).toEqual({ activeWorkshops: 0, evalFails: null, metricsHealth: null, sentinelGrade: null });
  });

  it("keeps the other signals when one reader throws", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const root = await fullProject();
    const outside = await createTempProjectRoot("sidebar-signals-outside-");
    const escaped = path.join(outside, "report.md");
    await writeFile(escaped, "# Quality eval\n");
    const reportsDir = path.join(root, ".ai-state", "praxion_eval_reports");
    const log = path.join(reportsDir, "PRAXION_EVAL_LOG.md");
    await rm(log);
    await symlink(escaped, log);

    const signals = await getSidebarSignals(root, FIXED_NOW);

    expect(signals).toEqual({ activeWorkshops: 2, evalFails: null, metricsHealth: "WORSENING", sentinelGrade: "C" });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("sidebar quality evals unreadable"), expect.any(String));
  });

  it("takes the failure count from the log row even when the newest report cannot be read", async () => {
    const { getSidebarSignals } = await import("@/server/view-models/sidebar-signals");
    const root = await fullProject();
    const outside = await createTempProjectRoot("sidebar-signals-outside-");
    const escaped = path.join(outside, "report.md");
    await writeFile(escaped, "# Quality eval\n");
    const reportsDir = path.join(root, ".ai-state", "praxion_eval_reports");
    const newest = (await readdir(reportsDir)).filter((name) => name.startsWith("PRAXION_EVAL_REPORT_")).sort().at(-1);
    if (newest === undefined) {
      throw new Error("the full project fixture has no quality-eval report");
    }
    await rm(path.join(reportsDir, newest));
    await symlink(escaped, path.join(reportsDir, newest));

    const signals = await getSidebarSignals(root, FIXED_NOW);

    expect(signals.evalFails).toBe(3);
  });
});
