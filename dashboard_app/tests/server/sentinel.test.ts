import { mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { parseMetricsLog } from "@/server/view-models/metrics";
import {
  countNotReached,
  getSentinelData,
  getSentinelSignal,
  isPartialReport,
  reportTimestampFromFileName,
  runStampFromFileName
} from "@/server/view-models/sentinel";
import { extractSections, parseSentinelLog } from "@/server/sentinel/extract-sections";

// ---------------------------------------------------------------------------
// extractSections
// ---------------------------------------------------------------------------

describe("extractSections", () => {
  // Mirrors the real sentinel report structure: preamble sections precede Findings,
  // and additional sections follow after the Suggested block (terminated by a ## heading).
  const FIXTURE_BODY = `
## Ecosystem Health: B

### Summary

Preamble text here.

---

## Metrics

| Metric | Value |
|--------|-------|
| Skills | 42    |

---

## Findings

### Critical (blocks correct behavior)

*None.*

### Important (degrades quality or efficiency)

| # | Check | Finding |
|---|-------|---------|
| I1 | AC07 | Some important finding |

### Suggested (improves but not urgent)

| # | Check | Finding |
|---|-------|---------|
| S1 | F07 | Some suggested finding |

---

## Pipeline Discipline

Post-finding content here.
`.trim();

  it("extracts all three sections from a complete report body", () => {
    const result = extractSections(FIXTURE_BODY);

    expect(result.critical).toContain("Critical");
    expect(result.critical).toContain("*None.*");

    expect(result.important).toContain("Important");
    expect(result.important).toContain("AC07");

    expect(result.suggested).toContain("Suggested");
    expect(result.suggested).toContain("F07");
  });

  it("rest excludes the three sections but includes preamble and other sections", () => {
    const result = extractSections(FIXTURE_BODY);

    expect(result.rest).toContain("Preamble text here.");
    expect(result.rest).toContain("## Metrics");
    expect(result.rest).toContain("## Pipeline Discipline");
    expect(result.rest).toContain("Post-finding content here.");

    expect(result.rest).not.toContain("*None.*");
    expect(result.rest).not.toContain("AC07");
    expect(result.rest).not.toContain("F07");
  });

  it("returns empty string for a missing section", () => {
    const bodyWithoutSuggested = `
### Critical (blocks correct behavior)

*None.*

### Important (degrades quality or efficiency)

Some important text.
`.trim();

    const result = extractSections(bodyWithoutSuggested);

    expect(result.suggested).toBe("");
    expect(result.critical).toContain("Critical");
    expect(result.important).toContain("Important");
  });

  it("rest contains the full body when no finding sections are present", () => {
    const bodyNoSections = "## Overview\n\nJust a summary.\n";

    const result = extractSections(bodyNoSections);

    expect(result.critical).toBe("");
    expect(result.important).toBe("");
    expect(result.suggested).toBe("");
    expect(result.rest).toContain("Just a summary.");
  });

  it("matching is case-insensitive for section headings", () => {
    const body = "### CRITICAL (blocks correct behavior)\n\nFound critical.\n### important\n\nFound important.\n";

    const result = extractSections(body);

    expect(result.critical).toContain("Found critical.");
    expect(result.important).toContain("Found important.");
  });
});

// ---------------------------------------------------------------------------
// parseSentinelLog
// ---------------------------------------------------------------------------

describe("parseSentinelLog", () => {
  const FIXTURE_LOG = `
# Sentinel Log

| Timestamp            | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File                              |
|----------------------|--------------|-----------|-------------------|---------------------|------------------------------------------|
| 2026-02-08T14:30:00Z | B            | 31        | 0/5/6             | B                   | SENTINEL_REPORT_2026-02-08_14-30-00.md   |
| 2026-03-16T11:02:14Z | A            | 47        | 0/0/5             | A                   | SENTINEL_REPORT_2026-03-16_11-02-14.md   |
| 2026-03-20T01:19:06Z | B            | 49        | 1/3/6             | A                   | SENTINEL_REPORT_2026-03-20_01-19-06.md   |
`.trim();

  it("parses a well-formed log table into typed SentinelLogPoint array", () => {
    const result = parseSentinelLog(FIXTURE_LOG);

    expect(result).toHaveLength(3);

    const first = result[0];
    expect(first?.timestamp).toBe("2026-02-08T14:30:00Z");
    expect(first?.grade).toBe("B");
    expect(first?.critical).toBe(0);
    expect(first?.important).toBe(5);
    expect(first?.suggested).toBe(6);
    expect(first?.coherence).toBe("B");
  });

  it("extracts the Report File column as the report join key", () => {
    const result = parseSentinelLog(FIXTURE_LOG);

    expect(result[0]?.reportFile).toBe("SENTINEL_REPORT_2026-02-08_14-30-00.md");
    expect(result[2]?.reportFile).toBe("SENTINEL_REPORT_2026-03-20_01-19-06.md");
  });

  it("strips markdown link syntax from a linked Report File cell", () => {
    const linkedLog = `
| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |
|-----------|--------------|-----------|-------------------|---------------------|-------------|
| 2026-05-01T00:00:00Z | A | 30 | 0/0/1 | A | [SENTINEL_REPORT_2026-05-01_00-00-00.md](SENTINEL_REPORT_2026-05-01_00-00-00.md) |
`.trim();

    expect(parseSentinelLog(linkedLog)[0]?.reportFile).toBe(
      "SENTINEL_REPORT_2026-05-01_00-00-00.md"
    );
  });

  it("parses a row with non-zero critical count", () => {
    const result = parseSentinelLog(FIXTURE_LOG);

    const withCritical = result[2];
    expect(withCritical?.critical).toBe(1);
    expect(withCritical?.important).toBe(3);
    expect(withCritical?.suggested).toBe(6);
    expect(withCritical?.coherence).toBe("A");
  });

  it("returns an empty array for an empty or headerless body", () => {
    expect(parseSentinelLog("")).toHaveLength(0);
    expect(parseSentinelLog("# Title\n\nNo table here.")).toHaveLength(0);
  });

  it("coerces missing or garbage cells to null", () => {
    const logWithGarbage = `
| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |
|-----------|--------------|-----------|-------------------|---------------------|-------------|
| 2026-05-01T00:00:00Z |  | 30 | not/a/number | B | REPORT.md |
`.trim();

    const result = parseSentinelLog(logWithGarbage);

    expect(result).toHaveLength(1);
    const row = result[0];
    expect(row?.grade).toBeNull();
    expect(row?.critical).toBeNull();
    expect(row?.important).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// parseMetricsLog
// ---------------------------------------------------------------------------

describe("parseMetricsLog", () => {
  const FIXTURE_LOG = `
| schema_version | timestamp | commit_sha | window_days | sloc_total | file_count | language_count | ccn_p95 | cognitive_p95 | cyclic_deps | churn_total_90d | change_entropy_90d | truck_factor | hotspot_top_score | hotspot_gini | coverage_line_pct | report_file |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0.0 | 2026-04-24T23:22:44.289638+00:00 | ee61f06c | 30 | 83355 | 510 | 13 | 8.0 | 10.0 | 0 | 95101 | 319.93 | 1 | 58023.0 | 0.6802 | 0.7986 | [METRICS_REPORT_2026-04-24_23-22-51.md](METRICS_REPORT_2026-04-24_23-22-51.md) |
| 1.0.0 | 2026-05-09T06:07:59.311418+00:00 | 912ee1ae | 30 | 108725 | 679 | 15 | 8.0 | 9.0 | 0 | 98081 | 255.81 | 1 | 21399.0 | 0.6224 | 0.5408 | [METRICS_REPORT_2026-05-09_06-08-07.md](METRICS_REPORT_2026-05-09_06-08-07.md) |
`.trim();

  it("parses a well-formed log table into typed MetricsLogPoint array", () => {
    const result = parseMetricsLog(FIXTURE_LOG);

    expect(result).toHaveLength(2);

    const first = result[0];
    expect(first?.timestamp).toBe("2026-04-24T23:22:44.289638+00:00");
    expect(first?.sloc_total).toBe(83355);
    expect(first?.file_count).toBe(510);
    expect(first?.language_count).toBe(13);
    expect(first?.ccn_p95).toBe(8.0);
    expect(first?.coverage_line_pct).toBe(0.7986);
    expect(first?.cyclic_deps).toBe(0);
    expect(first?.truck_factor).toBe(1);
  });

  it("strips markdown link syntax from report_file cell", () => {
    const result = parseMetricsLog(FIXTURE_LOG);

    expect(result[0]?.report_file).toBe("METRICS_REPORT_2026-04-24_23-22-51.md");
    expect(result[1]?.report_file).toBe("METRICS_REPORT_2026-05-09_06-08-07.md");
  });

  it("coerces blank or non-numeric cells to null", () => {
    const logWithGaps = `
| schema_version | timestamp | commit_sha | window_days | sloc_total | file_count | language_count | ccn_p95 | cognitive_p95 | cyclic_deps | churn_total_90d | change_entropy_90d | truck_factor | hotspot_top_score | hotspot_gini | coverage_line_pct | report_file |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0.0 |  | abc | not-a-number | | 100 | | 5.0 | | 0 | | | 1 | | | | |
`.trim();

    const result = parseMetricsLog(logWithGaps);

    expect(result).toHaveLength(1);
    const row = result[0];
    expect(row?.timestamp).toBeNull();
    expect(row?.window_days).toBeNull();
    expect(row?.sloc_total).toBeNull();
    expect(row?.file_count).toBe(100);
    expect(row?.language_count).toBeNull();
    expect(row?.ccn_p95).toBe(5.0);
  });

  it("returns an empty array for an empty or headerless body", () => {
    expect(parseMetricsLog("")).toHaveLength(0);
    expect(parseMetricsLog("# Title\n\nNo table.")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Digest facts: timestamp, partial mark, not-reached count
// ---------------------------------------------------------------------------

describe("reportTimestampFromFileName", () => {
  it("reads the filename stamp as local wall-clock time, never UTC", () => {
    expect(reportTimestampFromFileName("SENTINEL_REPORT_2026-10-01_09-30-00.md")).toBe(
      new Date(2026, 9, 1, 9, 30, 0).toISOString()
    );
  });

  it("returns null for a name without a valid stamp", () => {
    expect(reportTimestampFromFileName("SENTINEL_REPORT_latest.md")).toBeNull();
    expect(reportTimestampFromFileName("SENTINEL_REPORT_2026-13-45_99-99-99.md")).toBeNull();
  });
});

describe("runStampFromFileName", () => {
  it("is the filename's wall-clock text to the minute", () => {
    expect(runStampFromFileName("SENTINEL_REPORT_2026-09-11_17-10-27.md")).toBe("2026-09-11 17:10");
  });

  it("returns null for a name without a valid stamp", () => {
    expect(runStampFromFileName("SENTINEL_REPORT_latest.md")).toBeNull();
    expect(runStampFromFileName("SENTINEL_REPORT_2026-13-45_99-99-99.md")).toBeNull();
  });

  it("keeps a wall-clock time that does not exist locally on a spring-forward day", () => {
    // 02:30 on 2026-03-08 never happens in America/Los_Angeles; the producer still wrote it.
    expect(runStampFromFileName("SENTINEL_REPORT_2026-03-08_02-30-00.md")).toBe("2026-03-08 02:30");
  });

  it("gives the same text in every zone", () => {
    const original = process.env.TZ;
    try {
      const stamps = ["UTC", "Asia/Tokyo", "America/Los_Angeles"].map((zone) => {
        process.env.TZ = zone;
        return runStampFromFileName("SENTINEL_REPORT_2026-10-01_23-30-00.md");
      });
      expect(new Set(stamps)).toEqual(new Set(["2026-10-01 23:30"]));
    } finally {
      if (original === undefined) {
        delete process.env.TZ;
      } else {
        process.env.TZ = original;
      }
    }
  });
});

describe("isPartialReport", () => {
  it("is true when the title line carries [PARTIAL]", () => {
    expect(isPartialReport("# Sentinel Report [PARTIAL]\n\nbody")).toBe(true);
  });

  it("is false when only the body mentions the mark", () => {
    expect(isPartialReport("# Sentinel Report\n\nThis was not a [PARTIAL] run.")).toBe(false);
  });
});

describe("countNotReached", () => {
  it("counts one check per marker line", () => {
    const body = [
      "- **CA02** — not performed (time budget) — **[not reached]**.",
      "- **P04** — not performed — **[not reached]**."
    ].join("\n");

    expect(countNotReached(body)).toBe(2);
  });

  it("counts every check id written before a shared marker", () => {
    expect(countNotReached("- **TT01/TT02/TT04/TT05** — validation skipped — **[not reached]**.")).toBe(4);
  });

  it("ignores ids cited only in the commentary after a table-row marker", () => {
    const body = [
      "| AC02 | [not reached] | extraction failed; parity covered by AC13 |",
      "| N06, T05, T06 | [not reached] | not run; BC05 covers the duplication |"
    ].join("\n");

    expect(countNotReached(body)).toBe(4);
  });

  it("treats a marker quoted in backticks as prose", () => {
    expect(countNotReached("Checks marked `[not reached]`: none (AC01 ran).")).toBe(0);
    expect(countNotReached("**`[not reached]`**: **AC02**, **N06**.")).toBe(0);
  });

  it("counts a check once however often its marker repeats", () => {
    const body = ["- **AC02** — **[not reached]**", "| AC02 | [not reached] | again |"].join("\n");

    expect(countNotReached(body)).toBe(1);
  });

  it("counts a marker naming no check as one unnamed check", () => {
    expect(countNotReached("The dimension was skipped — **[not reached]**.")).toBe(1);
  });

  it("is zero when no marker appears", () => {
    expect(countNotReached("Every catalog check reached a verdict.")).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// getSentinelData over a fixture project root
// ---------------------------------------------------------------------------

describe("getSentinelData digest fields", () => {
  const roots: string[] = [];

  afterEach(async () => {
    await Promise.all(roots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
  });

  async function buildRoot(): Promise<string> {
    const root = await mkdtemp(path.join(os.tmpdir(), "dashboard-sentinel-digest-"));
    roots.push(root);
    const dir = path.join(root, ".ai-state", "sentinel_reports");
    await mkdir(dir, { recursive: true });
    await writeFile(
      path.join(dir, "SENTINEL_REPORT_2026-10-01_09-30-00.md"),
      [
        "# Sentinel Report [PARTIAL]",
        "",
        "## Ecosystem Health: C",
        "",
        "- **CA02** — skipped — **[not reached]**.",
        "- **P04** — skipped — **[not reached]**.",
        ""
      ].join("\n")
    );
    await writeFile(
      path.join(dir, "SENTINEL_LOG.md"),
      [
        "# Sentinel Log",
        "",
        "| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |",
        "|---|---|---|---|---|---|",
        "| 2026-10-01 09:30:00 | C [PARTIAL] | 40 | 1/2/3 | A | SENTINEL_REPORT_2026-10-01_09-30-00.md |",
        ""
      ].join("\n")
    );
    return root;
  }

  it("derives the partial mark and not-reached count for each report", async () => {
    const { reports } = await getSentinelData(await buildRoot());

    expect(reports).toHaveLength(1);
    expect(reports[0]).toMatchObject({ isPartial: true, notReachedCount: 2 });
  });

  it("stamps a report with its file's modification time, not the zone-less filename stamp", async () => {
    const root = await buildRoot();
    const written = new Date("2026-10-01T19:30:00.000Z");
    await utimes(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-10-01_09-30-00.md"),
      written,
      written
    );

    const { reports } = await getSentinelData(root);

    expect(reports[0]?.fileTimestamp).toBe(written.toISOString());
    expect(reports[0]?.fileTimestamp).not.toBe(
      reportTimestampFromFileName("SENTINEL_REPORT_2026-10-01_09-30-00.md")
    );
  });

  it("names each report's run from its filename, however git set the file times", async () => {
    const root = await buildRoot();
    const reportsDir = path.join(root, ".ai-state", "sentinel_reports");
    await writeFile(path.join(reportsDir, "SENTINEL_REPORT_2026-09-11_17-10-27.md"), "# Sentinel Report\n");
    const checkout = new Date("2026-10-02T18:26:00.000Z");
    for (const name of ["SENTINEL_REPORT_2026-09-11_17-10-27.md", "SENTINEL_REPORT_2026-10-01_09-30-00.md"]) {
      await utimes(path.join(reportsDir, name), checkout, checkout);
    }

    const { reports } = await getSentinelData(root);

    expect(reports.map((report) => report.fileTimestamp)).toEqual([checkout.toISOString(), checkout.toISOString()]);
    expect(reports.map((report) => report.runStamp)).toEqual(["2026-10-01 09:30", "2026-09-11 17:10"]);
  });

  it("exposes the log's path so a consumer can stamp its modification time", async () => {
    const root = await buildRoot();

    const { log } = await getSentinelData(root);

    expect(log?.path).toBe(path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_LOG.md"));
  });

  it("reads the signal's grade letter from the log row naming the newest report", async () => {
    expect(await getSentinelSignal(await buildRoot())).toEqual({ grade: "C" });
  });

  it("grades a newest report that no log row names as not graded, never as the previous run", async () => {
    const root = await buildRoot();
    await writeFile(
      path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-10-02_09-30-00.md"),
      "# Sentinel Report [PARTIAL]\n"
    );

    expect(await getSentinelSignal(root)).toEqual({ grade: null });
  });

  it("falls back to the log's last row when no report file exists", async () => {
    const root = await buildRoot();
    await rm(path.join(root, ".ai-state", "sentinel_reports", "SENTINEL_REPORT_2026-10-01_09-30-00.md"));

    expect(await getSentinelSignal(root)).toEqual({ grade: "C" });
  });

  it("has no grade when the project has no sentinel directory", async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "dashboard-sentinel-signal-"));
    roots.push(root);
    await mkdir(path.join(root, ".ai-state"), { recursive: true });

    expect(await getSentinelSignal(root)).toEqual({ grade: null });
  });

  it("reduces a partial run's grade cell to its letter in the log series and the highlight", async () => {
    const { logSeries, reports } = await getSentinelData(await buildRoot());

    expect(logSeries[0]?.grade).toBe("C");
    expect(reports[0]?.highlight).toMatchObject({ coherence: "A", critical: 1, grade: "C" });
  });
});
