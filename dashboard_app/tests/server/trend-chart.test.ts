import { describe, expect, it } from "vitest";

import { assignSeriesAxes, shapeChartData, type TrendSeries } from "@/components/viz/trend-chart";

function pts(...ys: number[]): TrendSeries["points"] {
  return ys.map((y, i) => ({ x: `2026-01-0${i + 1}`, y }));
}

// ---------------------------------------------------------------------------
// shapeChartData — pure data-shaping helper
// ---------------------------------------------------------------------------

describe("shapeChartData", () => {
  it("returns empty array for empty series list", () => {
    expect(shapeChartData([])).toEqual([]);
  });

  it("returns empty array when all series have no points", () => {
    const series: TrendSeries[] = [
      { label: "A", color: "#f00", points: [] },
      { label: "B", color: "#0f0", points: [] },
    ];
    expect(shapeChartData(series)).toEqual([]);
  });

  it("produces one row per distinct x value for a single series", () => {
    const series: TrendSeries[] = [
      {
        label: "Coverage",
        color: "#5b4fca",
        points: [
          { x: "2026-01-01", y: 80 },
          { x: "2026-01-02", y: 82 },
          { x: "2026-01-03", y: 85 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows).toHaveLength(3);
    expect(rows[0]).toEqual({ x: "2026-01-01", Coverage: 80 });
    expect(rows[1]).toEqual({ x: "2026-01-02", Coverage: 82 });
    expect(rows[2]).toEqual({ x: "2026-01-03", Coverage: 85 });
  });

  it("merges two series sharing all x values — no nulls", () => {
    const series: TrendSeries[] = [
      {
        label: "A",
        color: "#f00",
        points: [
          { x: "2026-01-01", y: 10 },
          { x: "2026-01-02", y: 20 },
        ],
      },
      {
        label: "B",
        color: "#0f0",
        points: [
          { x: "2026-01-01", y: 5 },
          { x: "2026-01-02", y: 15 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({ x: "2026-01-01", A: 10, B: 5 });
    expect(rows[1]).toEqual({ x: "2026-01-02", A: 20, B: 15 });
  });

  it("fills null for missing x values in multi-series merge", () => {
    // Series A has 2026-01-02 but Series B does not.
    // Series B has 2026-01-03 but Series A does not.
    const series: TrendSeries[] = [
      {
        label: "A",
        color: "#f00",
        points: [
          { x: "2026-01-01", y: 10 },
          { x: "2026-01-02", y: 20 },
        ],
      },
      {
        label: "B",
        color: "#0f0",
        points: [
          { x: "2026-01-01", y: 5 },
          { x: "2026-01-03", y: 30 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows).toHaveLength(3);
    // 2026-01-01: both present
    expect(rows[0]).toEqual({ x: "2026-01-01", A: 10, B: 5 });
    // 2026-01-02: A present, B missing → null
    expect(rows[1]).toEqual({ x: "2026-01-02", A: 20, B: null });
    // 2026-01-03: A missing → null, B present
    expect(rows[2]).toEqual({ x: "2026-01-03", A: null, B: 30 });
  });

  it("preserves x ordering from first-appearance across series", () => {
    // Series A introduces 2026-01-01 and 2026-01-03.
    // Series B introduces 2026-01-02 between them.
    const series: TrendSeries[] = [
      {
        label: "A",
        color: "#f00",
        points: [
          { x: "2026-01-01", y: 1 },
          { x: "2026-01-03", y: 3 },
        ],
      },
      {
        label: "B",
        color: "#0f0",
        points: [
          { x: "2026-01-01", y: 10 },
          { x: "2026-01-02", y: 20 },
          { x: "2026-01-03", y: 30 },
        ],
      },
    ];

    const rows = shapeChartData(series);
    const xValues = rows.map((r) => r["x"]);

    // First-appearance order: 2026-01-01 (series A), 2026-01-03 (series A), 2026-01-02 (series B)
    expect(xValues).toEqual(["2026-01-01", "2026-01-03", "2026-01-02"]);
  });

  it("propagates explicit null y values as null in output row", () => {
    // An explicit null y in a series point should appear as null in the row
    // (not as undefined — recharts uses null for gaps).
    const series: TrendSeries[] = [
      {
        label: "Metric",
        color: "#5b4fca",
        points: [
          { x: "run-1", y: 42 },
          { x: "run-2", y: null },
          { x: "run-3", y: 55 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows[0]).toEqual({ x: "run-1", Metric: 42 });
    expect(rows[1]).toEqual({ x: "run-2", Metric: null });
    expect(rows[2]).toEqual({ x: "run-3", Metric: 55 });
  });

  it("handles numeric x values correctly", () => {
    const series: TrendSeries[] = [
      {
        label: "Score",
        color: "#f00",
        points: [
          { x: 1, y: 100 },
          { x: 2, y: 200 },
          { x: 3, y: 300 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows).toHaveLength(3);
    expect(rows[0]).toEqual({ x: 1, Score: 100 });
    expect(rows[2]).toEqual({ x: 3, Score: 300 });
  });

  it("deduplicates x values within a single series — last write wins", () => {
    // If a series has duplicate x values (malformed input), the first-seen x
    // appears in xOrder once; the last point at that x wins in the lookup map.
    const series: TrendSeries[] = [
      {
        label: "A",
        color: "#f00",
        points: [
          { x: "run-1", y: 10 },
          { x: "run-1", y: 20 }, // duplicate x
          { x: "run-2", y: 30 },
        ],
      },
    ];

    const rows = shapeChartData(series);

    expect(rows).toHaveLength(2);
    expect(rows[0]?.["x"]).toBe("run-1");
    // The Map<x, y> has the last value for the duplicate key: 20
    expect(rows[0]?.["A"]).toBe(20);
    expect(rows[1]).toEqual({ x: "run-2", A: 30 });
  });
});

// ---------------------------------------------------------------------------
// assignSeriesAxes — magnitude-based dual-axis assignment
// ---------------------------------------------------------------------------

describe("assignSeriesAxes", () => {
  it("keeps a single series on the left axis", () => {
    const axes = assignSeriesAxes([{ label: "A", color: "#000", points: pts(10, 20, 30) }]);
    expect(axes.get("A")).toBe("left");
  });

  it("keeps same-scale series together on the left axis", () => {
    const axes = assignSeriesAxes([
      { label: "CCN", color: "#000", points: pts(8, 9, 11) },
      { label: "Cognitive", color: "#111", points: pts(12, 14, 15) }
    ]);
    expect(axes.get("CCN")).toBe("left");
    expect(axes.get("Cognitive")).toBe("left");
  });

  it("splits a small-magnitude series onto the right axis", () => {
    const axes = assignSeriesAxes([
      { label: "Churn", color: "#000", points: pts(3000, 4200, 3800) },
      { label: "Entropy", color: "#111", points: pts(2.1, 3.4, 2.9) },
      { label: "Truck", color: "#222", points: pts(2, 3, 3) }
    ]);
    expect(axes.get("Churn")).toBe("left");
    expect(axes.get("Entropy")).toBe("right");
    expect(axes.get("Truck")).toBe("right");
  });

  it("honors an explicit per-series axis override", () => {
    const axes = assignSeriesAxes([
      { label: "A", color: "#000", points: pts(10), axis: "right" },
      { label: "B", color: "#111", points: pts(12) }
    ]);
    expect(axes.get("A")).toBe("right");
    expect(axes.get("B")).toBe("left");
  });

  it("defaults a series with no measurable magnitude to the left axis", () => {
    const axes = assignSeriesAxes([
      { label: "Big", color: "#000", points: pts(1000, 2000) },
      { label: "Tiny", color: "#111", points: pts(1, 2) },
      { label: "Empty", color: "#222", points: [] }
    ]);
    expect(axes.get("Empty")).toBe("left");
  });
});
