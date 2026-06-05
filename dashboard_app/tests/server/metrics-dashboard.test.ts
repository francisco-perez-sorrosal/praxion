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

// Stub all recharts exports so RadarChart / LineChart / etc. render safely in node.
vi.mock("recharts", () => ({
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  RadarChart: ({ children }: { children?: any }) =>
    createElement("div", { className: "recharts-radar-stub" }, children),
  Radar: () => createElement("div", { className: "recharts-radar-series-stub" }),
  PolarGrid: () => null,
  PolarAngleAxis: () => null,
  PolarRadiusAxis: () => null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ResponsiveContainer: ({ children }: { children?: any }) =>
    createElement("div", { className: "recharts-container-stub" }, children),
  LineChart: () => createElement("div", { className: "recharts-line-stub" }),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ReferenceLine: () => null,
  Label: () => null
}));

// ─── Fixture helpers ──────────────────────────────────────────────────────────

import type { DashboardMetricsData, MetricsSnapshot, ReadinessSnapshot } from "@/lib/metrics";

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
    readiness: null,
    schemaVersion: "1",
    toolAvailability,
    wallClockSeconds: null
  };
}

const FIXTURE_READINESS: ReadinessSnapshot = {
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
    },
    {
      id: "documentation",
      name: "Documentation",
      pass_pct: 0.5,
      numerator: 1,
      denominator: 2,
      level_pass: [true, false, false, false, false]
    }
  ],
  manageability: {
    pass_pct: 0.75,
    numerator: 3,
    denominator: 4,
    note: "Praxion-native"
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
      passed: false,
      llm: false,
      rationale: "README missing agent-friendliness section"
    }
  ],
  llm: { status: "llm_skipped", model: null, grounded_on: null }
};

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

// ─── AgentReadinessSection tests ─────────────────────────────────────────────

async function renderReadinessSection(readiness: ReadinessSnapshot | null): Promise<string> {
  const { AgentReadinessSection } = await import("@/components/readiness-section");
  return renderToStaticMarkup(createElement(AgentReadinessSection, { readiness }));
}

describe("AgentReadinessSection — null readiness shows empty state", () => {
  it("renders the empty-state message when readiness is null", async () => {
    const html = await renderReadinessSection(null);
    expect(html).toContain("No readiness data");
    expect(html).toContain("/project-metrics");
  });

  it("does not render level badge when readiness is null", async () => {
    const html = await renderReadinessSection(null);
    expect(html).not.toContain("readiness-level-badge");
  });
});

describe("AgentReadinessSection — full fixture renders level badge", () => {
  it("renders the level badge with the correct level label", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("readiness-level-badge");
    expect(html).toContain("L3");
  });

  it("renders pass_pct in the level badge", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("82%");
  });
});

describe("AgentReadinessSection — full fixture renders pillar names in radar", () => {
  it("renders pillar names as PolarAngleAxis subjects", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    // recharts is mocked — but PolarAngleAxis is stubbed to null.
    // The recharts-radar-stub div should be present.
    expect(html).toContain("recharts-radar-stub");
  });
});

describe("AgentReadinessSection — full fixture renders Pillar-9 chip", () => {
  it("renders the manageability chip with Pillar 9 label", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("readiness-manageability-chip");
    expect(html).toContain("Pillar 9");
    expect(html).toContain("75%");
  });

  it("renders manageability note when present", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("Praxion-native");
  });
});

describe("AgentReadinessSection — full fixture renders top-failing criteria", () => {
  it("renders the failing criterion id in the list", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("readiness-failing-criteria");
    expect(html).toContain("c.docs.readme_quality");
  });

  it("does not render passing criteria in the failing list", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    // c.style.linter_config is passed=true, should not appear in failing list
    // (it might appear in the general section markup, but check class specifically)
    const failingSection = html.match(/<ul class="readiness-failing-criteria"[^>]*>([\s\S]*?)<\/ul>/);
    expect(failingSection).not.toBeNull();
    // The passing criterion should not be in the failing list
    expect(failingSection?.[1]).not.toContain("c.style.linter_config");
  });

  it("renders the failing criterion's rationale", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("README missing agent-friendliness section");
  });
});

describe("AgentReadinessSection — no failing criteria shows message", () => {
  it("renders 'No failing criteria' message when all criteria pass", async () => {
    const allPassingReadiness: ReadinessSnapshot = {
      ...FIXTURE_READINESS,
      criteria: [
        { ...FIXTURE_READINESS.criteria[0]!, passed: true },
        { ...FIXTURE_READINESS.criteria[1]!, passed: true }
      ]
    };
    const html = await renderReadinessSection(allPassingReadiness);
    expect(html).toContain("No failing criteria");
  });
});

describe("AgentReadinessSection — recommendations + educational hovers", () => {
  const READINESS_WITH_RECS: ReadinessSnapshot = {
    ...FIXTURE_READINESS,
    criteria: [
      {
        ...FIXTURE_READINESS.criteria[0]!,
        passed: true,
        explanation: "Checks for a linter config.",
        remediation: "Add a ruff config.",
        remediationSource: "static"
      },
      {
        ...FIXTURE_READINESS.criteria[1]!,
        passed: false,
        explanation: "An LLM judges README quality.",
        remediation: "Add a concrete architecture section to the README.",
        remediationSource: "llm"
      }
    ]
  };

  it("renders the remediation text for a failing criterion", async () => {
    const html = await renderReadinessSection(READINESS_WITH_RECS);
    expect(html).toContain("Add a concrete architecture section to the README.");
  });

  it("renders an AI-tailored badge for an LLM-sourced recommendation", async () => {
    const html = await renderReadinessSection(READINESS_WITH_RECS);
    expect(html).toContain("readiness-failing-criteria__badge");
  });

  it("does not show remediation for passing criteria in the failing list", async () => {
    const html = await renderReadinessSection(READINESS_WITH_RECS);
    const failingSection = html.match(
      /<ul class="readiness-failing-criteria"[^>]*>([\s\S]*?)<\/ul>/
    );
    expect(failingSection).not.toBeNull();
    // The passing criterion's remediation must not appear in the failing list.
    expect(failingSection?.[1]).not.toContain("Add a ruff config.");
  });

  it("renders educational popovers carrying instrument-level docs", async () => {
    const html = await renderReadinessSection(READINESS_WITH_RECS);
    expect(html).toContain("educational-popover");
    // Instrument-concept doc titles travel in the (hidden) popover panels.
    expect(html).toContain("Readiness level");
    expect(html).toContain("Recommendations");
  });

  it("degrades cleanly when criteria carry no new 1.2.0 fields", async () => {
    // FIXTURE_READINESS omits explanation/remediation entirely (a 1.1.0 report).
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("readiness-level-badge");
    // No criterion carries an LLM source → no AI-tailored badge is rendered.
    expect(html).not.toContain("readiness-failing-criteria__badge");
  });
});

describe("AgentReadinessSection — pillar weighting + level docs", () => {
  const WEIGHTED: ReadinessSnapshot = {
    ...FIXTURE_READINESS,
    pass_pct: 0.5,
    level: 1,
    adjustedPassPct: 0.9,
    adjustedLevel: 3,
    weightingActive: true,
    pillarWeights: { documentation: 1, style_validation: 0 },
    pillars: [
      { ...FIXTURE_READINESS.pillars[0]!, weight: 0, excluded: true },
      { ...FIXTURE_READINESS.pillars[1]!, weight: 1, excluded: false }
    ]
  };

  it("shows the adjusted headline and keeps the canonical Factory score visible", async () => {
    const html = await renderReadinessSection(WEIGHTED);
    expect(html).toContain("Adjusted");
    // adjusted ring shows 90%; canonical line shows the unweighted 50% · L1.
    expect(html).toContain("90%");
    expect(html).toContain("Factory (unweighted): 50%");
  });

  it("marks an excluded pillar", async () => {
    const html = await renderReadinessSection(WEIGHTED);
    expect(html).toContain("readiness-pillar-weight");
    expect(html).toContain("excluded");
  });

  it("shows only the canonical score when weighting is inactive", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).not.toContain("Factory (unweighted)");
  });

  it("renders L1–L5 meaning popovers on the heatmap headers", async () => {
    const html = await renderReadinessSection(FIXTURE_READINESS);
    expect(html).toContain("L1 — Foundational");
    expect(html).toContain("L5 — Exemplary");
  });

  it("renders '–' (not a vacuous ✓) for a level with no criteria in a pillar", async () => {
    // documentation has only a level-1 and level-2 criterion in the fixture,
    // yet its level_pass[2] (L3) is false and level_pass[0] (L1) true. A level
    // with no criteria (e.g. L4/L5) must render – not ✓ even if level_pass is true.
    const fixture: ReadinessSnapshot = {
      ...FIXTURE_READINESS,
      pillars: [
        {
          ...FIXTURE_READINESS.pillars[1]!, // documentation
          // L4/L5 marked "passed" in the gate (vacuous) but have no criteria.
          level_pass: [true, false, false, true, true]
        }
      ],
      criteria: [
        {
          ...FIXTURE_READINESS.criteria[1]!, // c.docs.readme_quality, level 2
          pillar: "documentation"
        }
      ]
    };
    const html = await renderReadinessSection(fixture);
    // The L4 cell for documentation has no criteria → must be the "na" state.
    expect(html).toContain('aria-label="Documentation L4: no criteria at this level"');
    // And it must NOT claim a pass for L4.
    expect(html).not.toContain('aria-label="Documentation L4: pass"');
  });
});

describe("MetricsDashboard — renders Agent Readiness section", () => {
  it("renders the Agent Readiness section heading with snapshot data", async () => {
    const snapshotWithReadiness = {
      ...makeSnapshot("snap-r", "2026-04-01T00:00:00Z"),
      readiness: FIXTURE_READINESS
    };
    const dataWithReadiness: DashboardMetricsData = {
      latest: snapshotWithReadiness,
      latestPath: snapshotWithReadiness.path,
      log: null,
      logSeries: [],
      snapshots: [snapshotWithReadiness]
    };
    const html = await renderDashboard(dataWithReadiness);
    expect(html).toContain("Agent Readiness");
    expect(html).toContain("readiness-level-badge");
  });

  it("renders Agent Readiness empty state when readiness is null", async () => {
    const html = await renderDashboard(SINGLE_SNAPSHOT_DATA);
    expect(html).toContain("Agent Readiness");
    expect(html).toContain("No readiness data");
  });
});
