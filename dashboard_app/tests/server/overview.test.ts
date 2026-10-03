/**
 * The Overview composition: one digest per artifact family, the attention
 * lines and the recent-activity list derived from them, and the guarantee that
 * a family which cannot be read costs only its own tile.
 *
 * The roots are built at run time by the acceptance fixtures (full, partial,
 * empty) with a frozen `now`, so every number below is a known quantity.
 */

import { mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardMetricsData } from "@/lib/metrics";
import type { PraxionEvalRun } from "@/lib/praxion-evals";
import type { DecisionRecord } from "@/server/view-models/overview";
import {
  composeOverview,
  digestDecisions,
  digestEvals,
  digestMetrics,
  digestSentinel,
  getOverviewData,
  overviewRefreshSeconds
} from "@/server/view-models/overview";
import type { SentinelData, SentinelReport } from "@/server/view-models/sentinel";

import {
  at,
  buildProjectRoot,
  FIXED_NOW,
  removeProjectRoots,
  sentinelFamily,
  techDebtLedger
} from "../acceptance/drivers/fixture-project";
import { cleanProject, emptyProject, fullProject, partialProject } from "../acceptance/drivers/project-presets";

const outsideDirs: string[] = [];

afterEach(async () => {
  vi.restoreAllMocks();
  await removeProjectRoots();
  await Promise.all(outsideDirs.splice(0).map((dir) => rm(dir, { force: true, recursive: true })));
});

// ─── A project with every family ──────────────────────────────────────────────

describe("getOverviewData for a project with every family", () => {
  it("digests the newest sentinel run with its counts, partial mark and trend", async () => {
    const { sentinel } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(sentinel).toMatchObject({
      coherence: "A",
      critical: 1,
      grade: "C",
      important: 2,
      isPartial: true,
      notReachedCount: 3,
      suggested: 3
    });
    expect(sentinel?.series.map((point) => point.grade)).toEqual(["A", "B", "C"]);
  });

  it("counts scored metrics indicators only and reads the readiness headline", async () => {
    const { metrics } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(metrics).toMatchObject({
      degraded: false,
      healthLabel: "WORSENING",
      readiness: { level: 3, passPct: 0.82 },
      tones: { bad: 6, good: 0, steady: 2 }
    });
  });

  it("digests the latest quality-eval run with its failures grouped by check", async () => {
    const { evals } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(evals?.latest).toMatchObject({ costUsd: 0.4321, fail: 3, pass: 1187, warn: 64 });
    expect(evals?.failGroups.map(({ check, count }) => [check, count])).toEqual([
      ["adr_body_sections", 2],
      ["task_artifact_manifest", 1]
    ]);
    expect(evals?.runs).toHaveLength(3);
  });

  it("lists the active workshops newest first and counts the stale and finished ones", async () => {
    const { workshops } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(workshops?.active.map((workshop) => workshop.slug)).toEqual(["alpha-active", "beta-active"]);
    expect(workshops?.active[0]).toMatchObject({ currentStep: "Wire the alpha reader", progress: { done: 2, total: 5 } });
    expect(workshops).toMatchObject({ doneCount: 2, staleCount: 1 });
  });

  it("names the three highest-numbered decisions and splits every record by category", async () => {
    const { decisions } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(decisions).toMatchObject({ drafts: 2, finalized: 4 });
    expect(decisions?.latest.map((decision) => decision.id)).toEqual(["dec-012", "dec-010", "dec-009"]);
    expect(decisions?.byCategory).toEqual({ architectural: 2, behavioral: 2, configuration: 1, implementation: 1 });
  });

  it("counts the active tech-debt rows by severity", async () => {
    const { debt } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(debt).toEqual({ bySeverity: { important: 1, suggested: 1 }, inFlight: 0, open: 2 });
  });

  it("raises one attention line per condition, most urgent first", async () => {
    const { attention } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(attention.map((line) => [line.tone, line.text])).toEqual([
      ["bad", "1 critical sentinel finding"],
      ["warn", "2 important sentinel findings"],
      ["warn", "Sentinel report is partial — 3 checks not reached"],
      ["bad", "Metrics health is worsening"],
      ["bad", "3 quality-eval failures across 2 checks"],
      ["warn", "1 important tech-debt row open or in flight"]
    ]);
    expect(attention.find((line) => /tech-debt/.test(line.text))?.href).toBeNull();
    expect(attention.find((line) => /sentinel finding/.test(line.text))?.href).toBe("/sentinel");
  });

  it("lists one entry per family, newest first, and stamps the page with the newest", async () => {
    const { activity, dataAsOf } = await getOverviewData(await fullProject(), FIXED_NOW);

    expect(activity.map((entry) => entry.family)).toEqual([
      "workshops",
      "sentinel",
      "evals",
      "metrics",
      "decisions",
      "architecture",
      "documentation",
      "roadmap"
    ]);
    expect(activity[0]).toMatchObject({ label: "Workshop alpha-active", mtime: "2026-10-02T12:00:00.000Z" });
    expect(activity.find((entry) => entry.family === "decisions")?.mtime).toBe("2026-09-25T10:00:00.000Z");
    expect(dataAsOf).toBe("2026-10-02T12:00:00.000Z");
  });
});

// ─── A calm project, a partial one and an empty one ───────────────────────────

describe("getOverviewData when nothing needs an operator", () => {
  it("raises no attention line and words a single snapshot as the baseline", async () => {
    const { attention, metrics } = await getOverviewData(await cleanProject(), FIXED_NOW);

    expect(attention).toEqual([]);
    expect(metrics?.healthLabel).toBe("BASELINE CAPTURED");
  });
});

describe("getOverviewData for a project holding only some families", () => {
  it("reads the families present and leaves the others absent, not zero", async () => {
    const overview = await getOverviewData(await partialProject(), FIXED_NOW);

    expect(overview.sentinel?.grade).toBe("C");
    expect(overview.workshops?.active).toHaveLength(2);
    expect([overview.metrics, overview.evals, overview.decisions, overview.debt]).toEqual([null, null, null, null]);
    expect(overview.activity.map((entry) => entry.family)).toEqual(["workshops", "sentinel"]);
  });
});

describe("getOverviewData for a project whose state directory is empty", () => {
  it("has no digest, no attention, no activity and no data-as-of stamp", async () => {
    const overview = await getOverviewData(await emptyProject(), FIXED_NOW);

    expect(overview).toEqual({
      activity: [],
      attention: [],
      dataAsOf: null,
      debt: null,
      decisions: null,
      evals: null,
      metrics: null,
      sentinel: null,
      workshops: { active: [], doneCount: 0, staleCount: 0 }
    });
  });
});

// ─── A reader that throws ─────────────────────────────────────────────────────

describe("getOverviewData when one family's reader throws", () => {
  /** A ledger that is a symlink out of the project root: the allowlist check rejects it. */
  async function rootWithEscapingLedger(): Promise<string> {
    const outside = await mkdtemp(path.join(os.tmpdir(), "overview-outside-"));
    outsideDirs.push(outside);
    const root = await buildProjectRoot(
      [
        ...sentinelFamily([{ at: at("2026-10-01T09:30:00Z"), coherence: "A", critical: 0, grade: "B", important: 1, suggested: 2 }]),
        techDebtLedger([], at("2026-09-27T10:00:00Z"))
      ],
      "overview-escape-"
    );
    const ledger = path.join(root, ".ai-state", "TECH_DEBT_LEDGER.md");
    const elsewhere = path.join(outside, "elsewhere.md");
    await writeFile(elsewhere, "| id | severity | status |\n");
    await rm(ledger);
    await symlink(elsewhere, ledger);
    return root;
  }

  it("reports the failure and leaves every other family intact", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    const overview = await getOverviewData(await rootWithEscapingLedger(), FIXED_NOW);

    expect(overview.debt).toBeNull();
    expect(overview.sentinel?.grade).toBe("B");
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("tech debt unreadable"), expect.any(String));
  });
});

// ─── Pure derivations ─────────────────────────────────────────────────────────

describe("overviewRefreshSeconds", () => {
  it.each([
    [20, 80],
    [15, 60],
    [5, 60],
    [300, 1200]
  ])("polls at four times %is, never under a minute: %is", (poll, expected) => {
    expect(overviewRefreshSeconds(poll)).toBe(expected);
  });
});

function record(overrides: Partial<DecisionRecord> & Pick<DecisionRecord, "path">): DecisionRecord {
  return { data: {}, isDraft: false, ...overrides };
}

describe("digestDecisions", () => {
  it("is absent when there are no records", () => {
    expect(digestDecisions([])).toBeNull();
  });

  it("orders by decision number, not by file order, and reads a YAML date as a day", () => {
    const digest = digestDecisions([
      record({ data: { date: new Date("2026-09-02T00:00:00Z"), id: "dec-009", title: "Nine" }, path: "/d/009-nine.md" }),
      record({ data: { date: "2026-09-04", id: "dec-100", status: "accepted", title: "Hundred" }, path: "/d/100-hundred.md" }),
      record({ data: { id: "dec-020", title: "Twenty" }, path: "/d/020-twenty.md" })
    ]);

    expect(digest?.latest.map((decision) => decision.id)).toEqual(["dec-100", "dec-020", "dec-009"]);
    expect(digest?.latest[0]).toMatchObject({ date: "2026-09-04", status: "accepted" });
    expect(digest?.latest[2]?.date).toBe("2026-09-02");
  });

  it("falls back to the file name for the number and title, and groups an uncategorized record", () => {
    const digest = digestDecisions([
      record({ path: "/d/007-seven-things.md" }),
      record({ data: { category: "behavioral" }, isDraft: true, path: "/d/drafts/2026-draft.md" })
    ]);

    expect(digest?.latest).toEqual([{ date: null, id: "007-seven-things", status: null, title: "007-seven-things" }]);
    expect(digest).toMatchObject({ byCategory: { behavioral: 1, uncategorized: 1 }, drafts: 1, finalized: 1 });
  });
});

function reportWith(overrides: Partial<SentinelReport>): SentinelReport {
  return {
    body: "",
    data: {},
    fileName: "SENTINEL_REPORT_2026-10-01_09-30-00.md",
    highlight: null,
    isPartial: false,
    notReachedCount: 0,
    path: "/r/SENTINEL_REPORT_2026-10-01_09-30-00.md",
    reportTimestamp: "2026-10-01T09:30:00.000Z",
    sections: { critical: "", important: "", rest: "", suggested: "" },
    ...overrides
  };
}

const LOG_POINT = {
  coherence: "B",
  critical: 0,
  grade: "D",
  important: 3,
  reportFile: null,
  suggested: 1,
  timestamp: "2026-09-30 09:00:00"
};

describe("digestSentinel", () => {
  it("is absent when neither a report nor a log row exists", () => {
    expect(digestSentinel({ log: null, logSeries: [], reports: [] })).toBeNull();
  });

  it("falls back to the log's last row when the newest report has no row of its own", () => {
    const data: SentinelData = { log: null, logSeries: [LOG_POINT], reports: [reportWith({})] };

    expect(digestSentinel(data)).toMatchObject({ grade: "D", important: 3, timestamp: "2026-10-01T09:30:00.000Z" });
  });

  it("reads a grade the log wrote as free text as not graded", () => {
    const data: SentinelData = {
      log: null,
      logSeries: [],
      reports: [reportWith({ highlight: { ...LOG_POINT, grade: "pending" } })]
    };

    expect(digestSentinel(data)?.grade).toBeNull();
  });

  it("keeps only the most recent runs for the trend", () => {
    const series = Array.from({ length: 12 }, (_, index) => ({ ...LOG_POINT, timestamp: `run-${index}` }));

    const digest = digestSentinel({ log: null, logSeries: series, reports: [] });

    expect(digest?.series.map((point) => point.timestamp)).toEqual(series.slice(-8).map((point) => point.timestamp));
  });
});

const EVAL_RUN: PraxionEvalRun = {
  authRoute: "",
  costUsd: 0.1,
  families: "1",
  fail: 4,
  pass: 10,
  reportFile: null,
  target: "t",
  timestamp: "2026-10-01T08-00-00Z",
  warn: 2
};

describe("digestEvals", () => {
  it("is absent when no run is logged", () => {
    expect(digestEvals({ dataAsOf: null, reports: [], runs: [], selected: null })).toBeNull();
  });

  it("uses the failure groups only of the report that belongs to the latest run", () => {
    const failGroups = [{ artifacts: ["a"], check: "c", count: 4 }];
    const selected = (timestamp: string) =>
      ({ failGroups, timestamp }) as unknown as NonNullable<Parameters<typeof digestEvals>[0]["selected"]>;

    const matching = digestEvals({ dataAsOf: null, reports: [], runs: [EVAL_RUN], selected: selected(EVAL_RUN.timestamp) });
    const other = digestEvals({ dataAsOf: null, reports: [], runs: [EVAL_RUN], selected: selected("older") });

    expect(matching?.failGroups).toEqual(failGroups);
    expect(other?.failGroups).toEqual([]);
  });
});

describe("composeOverview", () => {
  it("raises no quality-eval line for a run without failures", () => {
    const calm = composeOverview(
      {
        debt: null,
        decisions: null,
        evals: { touched: null, value: { dataAsOf: null, reports: [], runs: [{ ...EVAL_RUN, fail: 0 }], selected: null } },
        knowledge: { architecture: null, documentation: null, roadmap: null },
        metrics: null,
        sentinel: null,
        workshops: null
      },
      FIXED_NOW
    );

    expect(calm.attention).toEqual([]);
    expect(calm.evals?.latest.fail).toBe(0);
  });

  it("omits the not-reached count from the partial line when the report names none", () => {
    const data: SentinelData = {
      log: null,
      logSeries: [],
      reports: [reportWith({ highlight: { ...LOG_POINT, grade: "B", important: 0 }, isPartial: true })]
    };

    const overview = composeOverview(
      {
        debt: null,
        decisions: null,
        evals: null,
        knowledge: { architecture: null, documentation: null, roadmap: null },
        metrics: null,
        sentinel: { touched: null, value: data },
        workshops: null
      },
      FIXED_NOW
    );

    expect(overview.attention.map((line) => line.text)).toEqual(["Sentinel report is partial"]);
  });
});

describe("digestMetrics", () => {
  it("is absent when no snapshot was read", () => {
    const empty: DashboardMetricsData = { latest: null, latestPath: null, log: null, logSeries: [], snapshots: [] };

    expect(digestMetrics(empty)).toBeNull();
  });
});
