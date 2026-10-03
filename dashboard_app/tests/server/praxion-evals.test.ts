import { cp, mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import { readFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { formatEvalTimestamp } from "@/lib/evals";
import {
  evalReportStamp,
  groupByCheck,
  parsePraxionEvalLog,
  parsePraxionEvalReport
} from "@/lib/praxion-evals";
import { getPraxionEvalsData } from "@/server/view-models/praxion-evals";

const FIXTURES = path.join(__dirname, "..", "fixtures", "praxion-evals");
const NEWEST_REPORT = "PRAXION_EVAL_REPORT_2026-10-03T01-22-07Z.md";
const OLDER_REPORT = "PRAXION_EVAL_REPORT_2026-09-07T21-32-00Z.md";

const fixture = (name: string): string => readFileSync(path.join(FIXTURES, name), "utf8");

// ---------------------------------------------------------------------------
// The run log
// ---------------------------------------------------------------------------

describe("parsePraxionEvalLog", () => {
  const runs = parsePraxionEvalLog(fixture("PRAXION_EVAL_LOG.md"));

  it("reads each row's counts, cost, families and report file", () => {
    const newest = runs.at(-1);

    expect(newest).toMatchObject({
      timestamp: "2026-10-03T01-22-07Z",
      authRoute: "messages-api",
      families: "family1+family2+family5+seeded-scenarios",
      pass: 1316,
      warn: 688,
      fail: 29,
      costUsd: 1.3077,
      reportFile: NEWEST_REPORT
    });
  });

  it("orders runs oldest first even when the log was appended out of order", () => {
    const stamps = runs.map((run) => run.timestamp);

    expect(stamps).toEqual([...stamps].sort());
  });

  it("strips the dollar sign from a zero cost instead of dropping it", () => {
    expect(runs[0]?.costUsd).toBe(0);
  });

  it("reads a non-numeric cost as null and takes the file from a markdown link", () => {
    const body = [
      "| Timestamp | Target | Auth route | Families | Pass | Warn | Fail | Cost (USD) | Report |",
      "|---|---|---|---|---|---|---|---|---|",
      "| 2026-10-01T00-00-00Z | /p | agent-sdk | family1 | 1 | 2 | 3 | n/a | [r](PRAXION_EVAL_REPORT_2026-10-01T00-00-00Z.md) |"
    ].join("\n");

    expect(parsePraxionEvalLog(body)[0]).toMatchObject({
      costUsd: null,
      reportFile: "PRAXION_EVAL_REPORT_2026-10-01T00-00-00Z.md"
    });
  });

  it("returns no runs for prose or an empty file, and skips a row without a timestamp", () => {
    const headerOnlyRow = "| Timestamp | Target |\n|---|---|\n|  | /p |";

    expect(parsePraxionEvalLog("")).toEqual([]);
    expect(parsePraxionEvalLog("# Log\n\nNothing yet.\n")).toEqual([]);
    expect(parsePraxionEvalLog(headerOnlyRow)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// A report
// ---------------------------------------------------------------------------

describe("parsePraxionEvalReport", () => {
  const report = parsePraxionEvalReport(fixture(NEWEST_REPORT), NEWEST_REPORT);

  it("reads the summary, judged, tokens, cost and target header lines", () => {
    expect(report).toMatchObject({
      timestamp: "2026-10-03T01-22-07Z",
      target: "git:a1f1b1b6008aeafe36d43f3585306c3efad4f45a (a1f1b1b)",
      summary: { pass: 1316, warn: 688, fail: 29, skip: 10 },
      judgedCalls: 489,
      cacheHits: 362,
      tokensIn: 993887,
      tokensOut: 62768,
      costUsd: 1.3077
    });
  });

  it("groups the failures by check, largest group first, naming the artifacts", () => {
    expect(report.failGroups.map((group) => [group.check, group.count])).toEqual([
      ["bc_surface_assumptions", 3],
      ["bc_stay_surgical", 2],
      ["scenario_lightweight_fix_llm", 1]
    ]);
    expect(report.failGroups[0]?.artifacts).toHaveLength(3);
    expect(new Set(report.failGroups[0]?.artifacts).size).toBe(3);
  });

  it("groups the warnings by check, ties broken by check name", () => {
    expect(report.warnGroups.map((group) => [group.check, group.count])).toEqual([
      ["affected_reqs_resolvability", 3],
      ["bc_tag_bloat", 2],
      ["adr_option_depth", 1]
    ]);
  });

  it("keeps the calibration notes as markdown and the checks in report order", () => {
    expect(report.calibrationNotes).toMatch(/^\*\*Family 1 — affected_reqs population gap/);
    expect(report.calibrationNotes).not.toContain("## Calibration Notes");
    expect(report.checks[0]?.verdict).toBe("PASS");
    expect(report.checks.at(-1)?.verdict).not.toBe("PASS");
  });

  it("reads a report without judged, tokens or calibration lines as null facts", () => {
    const older = parsePraxionEvalReport(fixture(OLDER_REPORT), OLDER_REPORT);

    expect(older.summary).toEqual({ pass: 1503, warn: 39, fail: 2, skip: 2 });
    expect(older).toMatchObject({
      judgedCalls: null,
      cacheHits: null,
      tokensIn: null,
      tokensOut: null,
      calibrationNotes: null,
      costUsd: 0
    });
  });

  it("returns no checks and no summary for a report with neither", () => {
    const bare = parsePraxionEvalReport("# Praxion Eval Report\n\nNothing ran.\n", NEWEST_REPORT);

    expect(bare).toMatchObject({ checks: [], failGroups: [], warnGroups: [], summary: null, target: null });
  });

  it("skips a malformed check row and treats a missing skip count as zero", () => {
    const body = [
      "**Summary**: 5 PASS / 1 WARN / 0 FAIL",
      "",
      "## Check Results",
      "",
      "| Check | Kind | Verdict | Artifact | Score | Findings |",
      "|---|---|---|---|---|---|",
      "|  | mechanical | PASS | a.md | N/A | no check name |",
      "| adr_x | mechanical |  | b.md | N/A | no verdict |",
      "| adr_x | mechanical | pass | c.md | N/A | kept |"
    ].join("\n");

    const parsed = parsePraxionEvalReport(body, NEWEST_REPORT);

    expect(parsed.summary).toEqual({ pass: 5, warn: 1, fail: 0, skip: 0 });
    expect(parsed.checks.map((entry) => [entry.artifact, entry.verdict])).toEqual([["c.md", "PASS"]]);
  });
});

describe("groupByCheck", () => {
  it("counts every row of a check but lists each artifact once", () => {
    const row = (artifact: string) => ({ check: "c", kind: "k", verdict: "FAIL", artifact, score: "", findings: "" });

    expect(groupByCheck([row("a"), row("a"), row("b")], "FAIL")).toEqual([
      { check: "c", count: 3, artifacts: ["a", "b"] }
    ]);
  });
});

describe("report naming", () => {
  it("recovers the stamp from a report file name and formats it for display", () => {
    expect(evalReportStamp(NEWEST_REPORT)).toBe("2026-10-03T01-22-07Z");
    expect(evalReportStamp("PRAXION_EVAL_LOG.md")).toBeNull();
    expect(formatEvalTimestamp("2026-10-03T01-22-07Z")).toBe("2026-10-03 01:22 UTC");
    expect(formatEvalTimestamp("not-a-stamp")).toBe("not-a-stamp");
  });
});

// ---------------------------------------------------------------------------
// The view-model over a project root
// ---------------------------------------------------------------------------

describe("getPraxionEvalsData", () => {
  const roots: string[] = [];

  async function projectWithReports(): Promise<string> {
    const root = await mkdtemp(path.join(os.tmpdir(), "praxion-evals-"));
    roots.push(root);
    const dir = path.join(root, ".ai-state", "praxion_eval_reports");
    await mkdir(dir, { recursive: true });
    await cp(FIXTURES, dir, { recursive: true });
    await utimes(path.join(dir, "PRAXION_EVAL_LOG.md"), new Date("2026-10-03T02:00:00Z"), new Date("2026-10-03T02:00:00Z"));
    await utimes(path.join(dir, NEWEST_REPORT), new Date("2026-10-03T01:30:00Z"), new Date("2026-10-03T01:30:00Z"));
    await utimes(path.join(dir, OLDER_REPORT), new Date("2026-09-07T22:00:00Z"), new Date("2026-09-07T22:00:00Z"));
    return root;
  }

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  });

  it("lists reports newest first and reads only the newest by default", async () => {
    const data = await getPraxionEvalsData(await projectWithReports());

    expect(data.reports.map((report) => report.timestamp)).toEqual(["2026-10-03T01-22-07Z", "2026-09-07T21-32-00Z"]);
    expect(data.selected?.timestamp).toBe("2026-10-03T01-22-07Z");
    expect(data.runs.map((run) => run.timestamp)).toHaveLength(5);
  });

  it("selects the requested run and falls back to the newest for an unknown one", async () => {
    const root = await projectWithReports();

    expect((await getPraxionEvalsData(root, "2026-09-07T21-32-00Z")).selected?.summary?.fail).toBe(2);
    expect((await getPraxionEvalsData(root, "1999-01-01T00-00-00Z")).selected?.timestamp).toBe("2026-10-03T01-22-07Z");
  });

  it("stamps the data with the newest of the log and the selected report", async () => {
    const root = await projectWithReports();

    expect((await getPraxionEvalsData(root)).dataAsOf).toBe("2026-10-03T02:00:00.000Z");
  });

  it("returns empty data for a project with no quality-eval files", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "praxion-evals-empty-"));
    roots.push(root);
    await mkdir(path.join(root, ".ai-state"), { recursive: true });

    expect(await getPraxionEvalsData(root)).toEqual({ dataAsOf: null, reports: [], runs: [], selected: null });
  });

  it("treats an unreadable log as no runs while still reading the reports", async () => {
    const root = await projectWithReports();
    const log = path.join(root, ".ai-state", "praxion_eval_reports", "PRAXION_EVAL_LOG.md");
    await rm(log);
    await mkdir(log);
    await writeFile(path.join(log, "keep"), "");

    const data = await getPraxionEvalsData(root);

    expect(data.runs).toEqual([]);
    expect(data.selected?.timestamp).toBe("2026-10-03T01-22-07Z");
  });
});
