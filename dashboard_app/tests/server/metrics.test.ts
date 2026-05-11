import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { formatMetricDelta, getMetricTone, sliceSnapshotsUpTo } from "@/lib/metrics";
import { getMetricsData } from "@/server/view-models/metrics";

const tempRoots: string[] = [];

function buildMetricsReport({
  churn,
  coverage,
  fileCount,
  hotspotScore,
  sloc,
  timestamp
}: {
  churn: number;
  coverage: number;
  fileCount: number;
  hotspotScore: number;
  sloc: number;
  timestamp: string;
}) {
  return JSON.stringify({
    aggregate: {
      ccn_p95: 8,
      change_entropy_90d: 0.62,
      churn_total_90d: churn,
      cognitive_p95: 9,
      commit_sha: "abc123def456",
      coverage_line_pct: coverage,
      cyclic_deps: 0,
      file_count: fileCount,
      hotspot_gini: 0.42,
      hotspot_top_score: hotspotScore,
      language_count: 4,
      schema_version: "1.0.0",
      sloc_total: sloc,
      timestamp,
      truck_factor: 2,
      window_days: 30
    },
    coverage: {
      data: {
        artifact_path: "coverage.xml"
      },
      status: "ok"
    },
    hotspots: {
      top_n: [
        {
          churn_90d: 80,
          complexity: 12,
          hotspot_score: hotspotScore,
          path: "src/core.ts",
          rank: 1
        }
      ]
    },
    run_metadata: {
      wall_clock_seconds: 5.8
    },
    schema_version: "1.0.0",
    tool_availability: {
      coverage: {
        details: {},
        hint: null,
        reason: null,
        status: "available",
        version: "current"
      },
      git: {
        details: {},
        hint: null,
        reason: null,
        status: "available",
        version: "2.44.0"
      }
    },
    trends: {
      deltas: {
        coverage_line_pct: {
          current: coverage,
          delta: 0.02,
          delta_pct: 0.03,
          prior: coverage - 0.02
        },
        hotspot_top_score: {
          current: hotspotScore,
          delta: -30,
          delta_pct: -0.08,
          prior: hotspotScore + 30
        }
      }
    }
  });
}

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

async function seedProjectRoot(root: string): Promise<void> {
  await mkdir(path.join(root, ".ai-state", "metrics_reports"), { recursive: true });
  await mkdir(path.join(root, ".ai-work"), { recursive: true });
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("metrics dashboard data", () => {
  it("loads full snapshot history and sentrux history in chronological order", async () => {
    const root = await createTempProjectRoot("dashboard-metrics-history-");
    await seedProjectRoot(root);

    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-05-10_09-00-00.json"),
      buildMetricsReport({
        churn: 1200,
        coverage: 0.73,
        fileCount: 120,
        hotspotScore: 950,
        sloc: 18000,
        timestamp: "2026-05-10T09:00:00Z"
      })
    );
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-05-11_09-00-00.json"),
      buildMetricsReport({
        churn: 1350,
        coverage: 0.75,
        fileCount: 128,
        hotspotScore: 920,
        sloc: 19200,
        timestamp: "2026-05-11T09:00:00Z"
      })
    );
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_LOG.md"),
      "# Metrics history\n"
    );
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "SENTRUX_HISTORY.md"),
      [
        "| timestamp | commit_sha | quality_signal | rules_checked | rules_pass | files_kept | import_edges | call_edges | inherit_edges | exit_code |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        "| 2026-05-10T09:00:00Z | abc123def456 | 7100 | 14 | true | 120 | 44 | 300 | 9 | 0 |",
        "| 2026-05-11T09:00:00Z | abc123def456 | 7250 | 14 | true | 128 | 48 | 315 | 11 | 0 |"
      ].join("\n")
    );

    const metrics = await getMetricsData(root);

    expect(metrics.snapshots.map((snapshot) => snapshot.fileName)).toEqual([
      "METRICS_REPORT_2026-05-10_09-00-00.json",
      "METRICS_REPORT_2026-05-11_09-00-00.json"
    ]);
    expect(metrics.latest?.aggregate.sloc_total).toBe(19200);
    expect(metrics.latest?.toolAvailability.coverage.status).toBe("available");
    expect(metrics.latest?.hotspots[0]?.path).toBe("src/core.ts");
    expect(metrics.sentrux.history).toHaveLength(2);
    expect(metrics.sentrux.latest?.qualitySignal).toBe(7250);
    expect(metrics.sentrux.latest?.rulesPass).toBe(true);
  });

  it("keeps pure metric helper behavior stable for dashboard selection and tone cues", () => {
    const snapshots = [
      { id: "first" },
      { id: "second" },
      { id: "third" }
    ] as Array<{ id: string }>;

    expect(sliceSnapshotsUpTo(snapshots, "second").map((snapshot) => snapshot.id)).toEqual([
      "first",
      "second"
    ]);
    expect(getMetricTone("coverage_line_pct", 0.02)).toBe("good");
    expect(getMetricTone("hotspot_top_score", 20)).toBe("bad");
    expect(formatMetricDelta("coverage_line_pct", 0.015)).toBe("+1.5 pts");
  });
});
