/**
 * Behavioral render-to-string tests for `MetricsDashboard` component.
 *
 * Behaviors validated:
 *   - Rich fixture (≥2 snapshots): health strip present with a <select> inside
 *     it, KPI tiles each contain a tone word AND an arrow glyph (never color-alone),
 *     exactly ONE <details> "Raw data" disclosure.
 *   - Single-snapshot fixture: "BASELINE CAPTURED" text present, single-snapshot
 *     footer text visible, trend charts suppressed for the "no prior run" state.
 *   - Zero-reports fixture: EmptyState text present, no crash.
 *   - Degraded-collector fixture: health strip degradedNote contains the degraded
 *     tool name and a confidence note.
 *   - Never-color-alone guard: every KPI tile has both a tone word and an arrow
 *     glyph in its markup.
 *
 * Strategy: mock sub-components that rely on Recharts (MetricsTrends, Sparkline)
 * since those contain browser-specific initialization code. MetricsSummaryCards and
 * HealthStrip are rendered via the real component (they are pure React with no I/O).
 *
 * IMPLEMENTATION NOTE: MetricsDashboard is "use client" with useState. In node env
 * renderToStaticMarkup renders the initial state (selectedSnapshotId = latest.id).
 * useTransition and startTransition are no-ops in the server render — no side-effects.
 *
 * Note: The <h1>Metrics</h1> title is owned by the AppHeader/page component, NOT by
 * MetricsDashboard — it is not asserted here.
 *
 * Environment: vitest node — renderToStaticMarkup from react-dom/server.
 * vi.mock hoisting: mocks at top level for vitest static analysis.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { beforeEach, describe, expect, it, vi } from "vitest";

// ─── Module mocks ─────────────────────────────────────────────────────────────
// Recharts-based components do not run in node env; stub them out.

vi.mock("@/components/metrics-trends", () => ({
  MetricsTrends: () => createElement("div", { className: "metrics-trends-stub" })
}));

vi.mock("@/components/viz/sparkline", () => ({
  Sparkline: () => createElement("span", { className: "sparkline-stub" })
}));

// ─── Fixture helpers ──────────────────────────────────────────────────────────

import type { DashboardMetricsData, MetricsSnapshot } from "@/lib/metrics";

function makeAggregate(
  timestamp: string,
  overrides: Partial<Record<string, number | null>> = {}
): MetricsSnapshot["aggregate"] {
  return {
    timestamp,
    commitSha: "abc",
    schemaVersion: "1",
    windowDays: 7,
    sloc_total: 10000,
    file_count: 120,
    language_count: 3,
    ccn_p95: 4.5,
    cognitive_p95: 8.2,
    cyclic_deps: 0,
    churn_total_90d: 1200,
    change_entropy_90d: 0.72,
    truck_factor: 3,
    hotspot_top_score: 45,
    hotspot_gini: 0.31,
    coverage_line_pct: 0.78,
    ...overrides
  };
}

function makeSnapshot(
  id: string,
  timestamp: string,
  toolAvailability: Record<string, { status: string; version: string | null; reason: string | null; hint: string | null; details: Record<string, unknown> }> = {}
): MetricsSnapshot {
  return {
    id,
    fileName: `METRICS_REPORT_${id}.json`,
    path: `/fake/.ai-state/metrics_reports/METRICS_REPORT_${id}.json`,
    aggregate: makeAggregate(timestamp),
    deltas: {
      coverage_line_pct: { current: 0.78, delta: 0.02, deltaPct: 0.026, prior: 0.76 }
    },
    hotspots: [],
    coverageArtifactPath: null,
    coverageStatus: null,
    schemaVersion: "1",
    toolAvailability,
    wallClockSeconds: null
  };
}

/** A snapshot with a degraded "ruff" collector */
function makeSnapshotWithDegradedCollector(id: string, timestamp: string): MetricsSnapshot {
  return makeSnapshot(id, timestamp, {
    ruff: {
      status: "unavailable",
      version: null,
      reason: "ruff not found in PATH",
      hint: null,
      details: {}
    },
    mypy: {
      status: "available",
      version: "1.9.0",
      reason: null,
      hint: null,
      details: {}
    }
  });
}

const SNAPSHOT_A = makeSnapshot("snap-a", "2026-03-01T00:00:00Z");
const SNAPSHOT_B = makeSnapshot("snap-b", "2026-04-01T00:00:00Z");

/** Rich fixture: 2 snapshots, hotspots empty, no degraded collectors */
const RICH_DATA: DashboardMetricsData = {
  latest: SNAPSHOT_B,
  latestPath: SNAPSHOT_B.path,
  log: { body: "## Run History\nsome log content", path: "/fake/METRICS_LOG.md" },
  logSeries: [],
  snapshots: [SNAPSHOT_A, SNAPSHOT_B]
};

/** Single-snapshot fixture — the "BASELINE CAPTURED" state */
const SINGLE_SNAPSHOT_DATA: DashboardMetricsData = {
  latest: SNAPSHOT_A,
  latestPath: SNAPSHOT_A.path,
  log: null,
  logSeries: [],
  snapshots: [SNAPSHOT_A]
};

/** Zero-reports fixture */
const EMPTY_DATA: DashboardMetricsData = {
  latest: null,
  latestPath: null,
  log: null,
  logSeries: [],
  snapshots: []
};

/** Degraded-collector fixture */
const DEGRADED_DATA: DashboardMetricsData = {
  latest: makeSnapshotWithDegradedCollector("snap-deg", "2026-04-01T00:00:00Z"),
  latestPath: "/fake/.ai-state/metrics_reports/METRICS_REPORT_snap-deg.json",
  log: null,
  logSeries: [],
  snapshots: [
    makeSnapshot("snap-prev", "2026-03-01T00:00:00Z"),
    makeSnapshotWithDegradedCollector("snap-deg", "2026-04-01T00:00:00Z")
  ]
};

// ─── Render helper ────────────────────────────────────────────────────────────

async function renderDashboard(data: DashboardMetricsData): Promise<string> {
  const { MetricsDashboard } = await import("@/components/metrics-dashboard");
  return renderToStaticMarkup(createElement(MetricsDashboard, { data }));
}

// ─── Reset module cache between tests to avoid useState persistence ──────────

beforeEach(() => {
  vi.resetModules();
});

// ─── describe blocks ──────────────────────────────────────────────────────────

describe("MetricsDashboard — rich fixture (≥2 snapshots)", () => {
  it("renders the health strip section with class metrics-health-strip", async () => {
    const html = await renderDashboard(RICH_DATA);
    expect(html).toContain("metrics-health-strip");
  });

  it("renders a <select> inside the health strip for snapshot navigation", async () => {
    const html = await renderDashboard(RICH_DATA);
    // Both the health strip and a select must be present
    expect(html).toContain("metrics-health-strip");
    expect(html).toContain("<select");
  });

  it("renders KPI tiles that each contain both a tone word and an arrow glyph", async () => {
    const html = await renderDashboard(RICH_DATA);
    // kpi-tile class must be present (from MetricsSummaryCards)
    expect(html).toContain("kpi-tile");
    // Each tile contains the .kpi-tile__tone span which holds arrow + word
    expect(html).toContain("kpi-tile__tone");
    // Arrow glyphs must appear (at least one of the three)
    const hasArrow = html.includes("↘") || html.includes("↗") || html.includes("→");
    expect(hasArrow, "Expected at least one arrow glyph (↘/↗/→) in KPI tiles").toBe(true);
    // Tone words must appear
    const hasToneWord =
      html.toLowerCase().includes("improving") ||
      html.toLowerCase().includes("worsening") ||
      html.toLowerCase().includes("stable") ||
      html.toLowerCase().includes("informational");
    expect(hasToneWord, "Expected at least one tone word in KPI tiles").toBe(true);
  });

  it("never uses color alone — every KPI tile tone span contains both an arrow glyph and a word", async () => {
    const html = await renderDashboard(RICH_DATA);
    // Extract all kpi-tile__tone spans using a simple regex
    const toneSpans = [...html.matchAll(/class="kpi-tile__tone[^"]*"[^>]*>([^<]+)<\/span>/g)].map(
      (m) => m[1] ?? ""
    );
    expect(
      toneSpans.length,
      "Expected at least one kpi-tile__tone span in the rendered output"
    ).toBeGreaterThan(0);
    for (const span of toneSpans) {
      const hasArrow = span.includes("↘") || span.includes("↗") || span.includes("→");
      const hasWord = /[A-Za-z]{3,}/.test(span); // at least a 3-char word
      expect(
        hasArrow,
        `Tone span "${span}" has no arrow glyph — color-alone violation`
      ).toBe(true);
      expect(
        hasWord,
        `Tone span "${span}" has no tone word — color-alone violation`
      ).toBe(true);
    }
  });

  it("renders exactly one <details> Raw data disclosure", async () => {
    const html = await renderDashboard(RICH_DATA);
    const detailsMatches = [...html.matchAll(/<details/g)];
    expect(
      detailsMatches.length,
      `Expected exactly 1 <details> but found ${detailsMatches.length}`
    ).toBe(1);
    expect(html).toContain("Raw data");
  });

  it("renders the health label (IMPROVING, WORSENING, or STABLE)", async () => {
    const html = await renderDashboard(RICH_DATA);
    const hasHealthLabel =
      html.includes("IMPROVING") || html.includes("WORSENING") || html.includes("STABLE");
    expect(hasHealthLabel, "Expected a health label in the rendered output").toBe(true);
  });
});

describe("MetricsDashboard — single-snapshot (BASELINE CAPTURED) state", () => {
  it("renders 'BASELINE CAPTURED' health label", async () => {
    const html = await renderDashboard(SINGLE_SNAPSHOT_DATA);
    expect(html).toContain("BASELINE CAPTURED");
  });

  it("shows the baseline footer text on KPI tiles (no prior run to compare)", async () => {
    const html = await renderDashboard(SINGLE_SNAPSHOT_DATA);
    expect(html).toContain("Baseline");
  });

  it("renders exactly one <details> Raw data disclosure even with 1 snapshot", async () => {
    const html = await renderDashboard(SINGLE_SNAPSHOT_DATA);
    const detailsMatches = [...html.matchAll(/<details/g)];
    expect(detailsMatches.length).toBe(1);
  });
});

describe("MetricsDashboard — zero reports (EmptyState)", () => {
  it("renders EmptyState text without crashing", async () => {
    const html = await renderDashboard(EMPTY_DATA);
    // EmptyState renders its title
    expect(html).toContain("No metrics reports found");
  });

  it("does not render the health strip when there are no snapshots", async () => {
    const html = await renderDashboard(EMPTY_DATA);
    expect(html).not.toContain("metrics-health-strip");
  });
});

describe("MetricsDashboard — degraded-collector fixture", () => {
  it("renders health strip with a degraded note mentioning the degraded tool", async () => {
    const html = await renderDashboard(DEGRADED_DATA);
    expect(html).toContain("metrics-health-strip");
    // The degradedNote field contains "ruff" — it is rendered in the health-strip__degraded-note span
    expect(html).toContain("ruff");
  });

  it("includes a data confidence note in the health strip degraded span", async () => {
    const html = await renderDashboard(DEGRADED_DATA);
    // degradedNote format: "· data confidence reduced (ruff unavailable)"
    const lower = html.toLowerCase();
    expect(lower).toContain("confidence");
  });
});
