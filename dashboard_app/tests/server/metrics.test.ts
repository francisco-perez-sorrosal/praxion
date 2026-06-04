import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { type DashboardMetricsData, formatMetricDelta, getMetricTone, sliceLogSeriesUpTo, sliceSnapshotsUpTo } from "@/lib/metrics";
import type { MetricsLogPoint } from "@/lib/metrics";
import { buildReadiness, getMetricsData } from "@/server/view-models/metrics";

describe("metrics dashboard data", () => {
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

function makeLogPoint(timestamp: string | null): MetricsLogPoint {
  return {
    timestamp,
    commit_sha: null,
    window_days: null,
    sloc_total: null,
    file_count: null,
    language_count: null,
    ccn_p95: null,
    cognitive_p95: null,
    cyclic_deps: null,
    churn_total_90d: null,
    change_entropy_90d: null,
    truck_factor: null,
    hotspot_top_score: null,
    hotspot_gini: null,
    coverage_line_pct: null,
    report_file: null
  };
}

describe("sliceLogSeriesUpTo", () => {
  const rows = [
    makeLogPoint("2026-01-01T00:00:00Z"),
    makeLogPoint("2026-02-01T00:00:00Z"),
    makeLogPoint("2026-03-01T00:00:00Z"),
    makeLogPoint("2026-04-01T00:00:00Z")
  ];

  it("returns all rows when untilTimestamp is null", () => {
    expect(sliceLogSeriesUpTo(rows, null)).toHaveLength(4);
  });

  it("returns only rows at or before the given timestamp", () => {
    const result = sliceLogSeriesUpTo(rows, "2026-02-01T00:00:00Z");
    expect(result).toHaveLength(2);
    expect(result[0]?.timestamp).toBe("2026-01-01T00:00:00Z");
    expect(result[1]?.timestamp).toBe("2026-02-01T00:00:00Z");
  });

  it("returns empty array when timestamp is before all rows", () => {
    const result = sliceLogSeriesUpTo(rows, "2025-12-31T23:59:59Z");
    expect(result).toHaveLength(0);
  });

  it("drops rows with null timestamps when filtering", () => {
    const rowsWithNull = [
      makeLogPoint(null),
      makeLogPoint("2026-02-01T00:00:00Z"),
      makeLogPoint("2026-03-01T00:00:00Z")
    ];
    const result = sliceLogSeriesUpTo(rowsWithNull, "2026-02-15T00:00:00Z");
    expect(result).toHaveLength(1);
    expect(result[0]?.timestamp).toBe("2026-02-01T00:00:00Z");
  });
});

const tempRoots: string[] = [];

async function createTempProjectRoot(prefix: string): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  tempRoots.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(tempRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
});

describe("Sentrux excision — metrics view-model", () => {
  it("getMetricsData result has no sentrux key at runtime", async () => {
    const root = await createTempProjectRoot("metrics-sentrux-test-");
    await mkdir(path.join(root, ".ai-state", "metrics_reports"), { recursive: true });

    const result = await getMetricsData(root);

    expect(Object.keys(result)).not.toContain("sentrux");
  });

  it("DashboardMetricsData type has no sentrux property at compile time", () => {
    const data: DashboardMetricsData = {
      latest: null,
      latestPath: null,
      log: null,
      logSeries: [],
      snapshots: []
    };

    // Negative compile-time assertion: accessing .sentrux must be a type error.
    // @ts-expect-error — sentrux was removed from DashboardMetricsData; this line must not typecheck.
    const _unused = data.sentrux;
    void _unused;

    expect(Object.keys(data)).not.toContain("sentrux");
  });
});

// ─── buildReadiness view-model tests ─────────────────────────────────────────

const FULL_READINESS_BLOCK = {
  status: "ok",
  duration_seconds: 0.12,
  issues: [],
  data: {
    level: 3,
    pass_pct: 0.82,
    note: null,
    pillars: [
      {
        id: "style_validation",
        name: "Style & Validation",
        pass_pct: 1.0,
        numerator: 1,
        denominator: 1,
        level_pass: [true, true, true, false, false]
      }
    ],
    manageability: {
      pass_pct: 0.75,
      numerator: 3,
      denominator: 4,
      note: "Praxion-native; not in 8-pillar level"
    },
    criteria: [
      {
        id: "c.style.linter_config",
        pillar: "style_validation",
        level: 1,
        scope: "repo",
        applicable: true,
        passed: true,
        llm: false,
        rationale: "ruff config present"
      },
      {
        id: "c.docs.readme_quality",
        pillar: "documentation",
        level: 2,
        scope: "repo",
        applicable: true,
        passed: null,
        llm: true,
        rationale: null
      }
    ],
    llm: { status: "llm_skipped", model: null, grounded_on: null }
  }
};

describe("buildReadiness — absent block returns null", () => {
  it("returns null when raw block is undefined", () => {
    expect(buildReadiness(undefined)).toBeNull();
  });

  it("returns null when data field is missing", () => {
    expect(buildReadiness({})).toBeNull();
  });

  it("returns null when level is missing", () => {
    expect(buildReadiness({ data: { pass_pct: 0.5, manageability: { numerator: 1, denominator: 2, pass_pct: 0.5 } } })).toBeNull();
  });

  it("returns null when pass_pct is missing", () => {
    expect(buildReadiness({ data: { level: 3, manageability: { numerator: 1, denominator: 2, pass_pct: 0.5 } } })).toBeNull();
  });

  it("returns null when manageability is missing", () => {
    expect(buildReadiness({ data: { level: 3, pass_pct: 0.5 } })).toBeNull();
  });
});

describe("buildReadiness — full valid block parses correctly", () => {
  it("parses level and pass_pct from the data block", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result).not.toBeNull();
    expect(result?.level).toBe(3);
    expect(result?.pass_pct).toBe(0.82);
  });

  it("parses pillars array with correct shape", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result?.pillars).toHaveLength(1);
    const pillar = result?.pillars[0];
    expect(pillar?.id).toBe("style_validation");
    expect(pillar?.name).toBe("Style & Validation");
    expect(pillar?.pass_pct).toBe(1.0);
    expect(pillar?.level_pass).toEqual([true, true, true, false, false]);
  });

  it("parses criteria array with correct shape including null passed for llm criteria", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result?.criteria).toHaveLength(2);
    const mechanical = result?.criteria[0];
    expect(mechanical?.id).toBe("c.style.linter_config");
    expect(mechanical?.passed).toBe(true);
    expect(mechanical?.llm).toBe(false);
    const llmCrit = result?.criteria[1];
    expect(llmCrit?.id).toBe("c.docs.readme_quality");
    expect(llmCrit?.passed).toBeNull();
    expect(llmCrit?.llm).toBe(true);
  });

  it("parses manageability sub-score separately from pillars", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result?.manageability.pass_pct).toBe(0.75);
    expect(result?.manageability.numerator).toBe(3);
    expect(result?.manageability.denominator).toBe(4);
    expect(result?.manageability.note).toBe("Praxion-native; not in 8-pillar level");
  });

  it("parses llm sub-block with llm_skipped status", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result?.llm.status).toBe("llm_skipped");
    expect(result?.llm.model).toBeNull();
    expect(result?.llm.grounded_on).toBeNull();
  });

  it("preserves null note field", () => {
    const result = buildReadiness(FULL_READINESS_BLOCK);
    expect(result?.note).toBeNull();
  });
});

describe("buildReadiness — partial/malformed block returns null", () => {
  it("returns null when data is a non-object primitive", () => {
    expect(buildReadiness({ data: "bad" })).toBeNull();
  });

  it("returns null when data is an array", () => {
    expect(buildReadiness({ data: [] })).toBeNull();
  });

  it("returns null when level is a string", () => {
    expect(
      buildReadiness({
        data: { level: "high", pass_pct: 0.5, manageability: { numerator: 1, denominator: 2, pass_pct: 0.5 } }
      })
    ).toBeNull();
  });
});

describe("buildReadiness — llm status variants", () => {
  function makeBlock(status: string) {
    return {
      data: {
        level: 2,
        pass_pct: 0.5,
        pillars: [],
        criteria: [],
        manageability: { numerator: 1, denominator: 2, pass_pct: 0.5, note: null },
        llm: { status, model: null, grounded_on: null }
      }
    };
  }

  it("accepts scored status", () => {
    const result = buildReadiness(makeBlock("scored"));
    expect(result?.llm.status).toBe("scored");
  });

  it("accepts llm_error status", () => {
    const result = buildReadiness(makeBlock("llm_error"));
    expect(result?.llm.status).toBe("llm_error");
  });

  it("accepts pending status", () => {
    const result = buildReadiness(makeBlock("pending"));
    expect(result?.llm.status).toBe("pending");
  });

  it("falls back to llm_skipped for unknown status string", () => {
    const result = buildReadiness(makeBlock("invalid_status"));
    expect(result?.llm.status).toBe("llm_skipped");
  });
});

describe("buildReadiness — getMetricsData integrates readiness field", () => {
  it("snapshot has readiness null when report has no readiness block", async () => {
    const root = await createTempProjectRoot("metrics-readiness-test-");
    await mkdir(path.join(root, ".ai-state", "metrics_reports"), { recursive: true });
    const { writeFile } = await import("node:fs/promises");
    const report = {
      aggregate: {
        timestamp: "2026-06-01T10:00:00Z",
        sloc_total: 1000,
        file_count: 50,
        schema_version: "1.0.0"
      }
    };
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-06-01_10-00-00.json"),
      JSON.stringify(report)
    );

    const result = await getMetricsData(root);
    expect(result.latest?.readiness).toBeNull();
  });

  it("snapshot has parsed ReadinessSnapshot when report has a valid readiness block", async () => {
    const root = await createTempProjectRoot("metrics-readiness-full-test-");
    await mkdir(path.join(root, ".ai-state", "metrics_reports"), { recursive: true });
    const { writeFile } = await import("node:fs/promises");
    const report = {
      aggregate: {
        timestamp: "2026-06-01T10:00:00Z",
        sloc_total: 1000,
        file_count: 50,
        schema_version: "1.1.0"
      },
      readiness: FULL_READINESS_BLOCK
    };
    await writeFile(
      path.join(root, ".ai-state", "metrics_reports", "METRICS_REPORT_2026-06-01_10-00-00.json"),
      JSON.stringify(report)
    );

    const result = await getMetricsData(root);
    expect(result.latest?.readiness).not.toBeNull();
    expect(result.latest?.readiness?.level).toBe(3);
    expect(result.latest?.readiness?.pillars).toHaveLength(1);
    expect(result.latest?.readiness?.criteria).toHaveLength(2);
  });
});
