// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { MetricsViewRenderer } from "@/components/renderers/metrics-view";

afterEach(() => {
  cleanup();
});

// Trimmed METRICS_REPORT_*.json shape — mirrors the top-level keys read from
// .ai-state/metrics_reports/METRICS_REPORT_*.json (aggregate / schema_version /
// run_metadata.window_days). The renderer ignores the ~440 KB of per-file
// detail (hotspots, lizard, scc, ...) — that is the /metrics route's job.
const METRICS_BODY = JSON.stringify({
  schema_version: "1.3.0",
  aggregate: {
    coverage_line_pct: 74,
    ccn_p95: 11,
    cognitive_p95: 17,
    file_count: 481,
    cyclic_deps: 4
  },
  run_metadata: {
    window_days: 45
  }
});

describe("MetricsViewRenderer — metrics snapshot summary", () => {
  it("renders the aggregate stats and a link to the full metrics dashboard", () => {
    const { container } = render(<MetricsViewRenderer body={METRICS_BODY} />);

    const summary = container.querySelector(".renderer-metrics-summary");
    expect(summary).toBeTruthy();
    expect(summary?.textContent).toMatch(/74/);
    expect(summary?.textContent).toMatch(/481/);
    expect(summary?.textContent).toMatch(/1\.3\.0/);

    expect(container.querySelector('a[href="/metrics"]')).toBeTruthy();
  });

  it("falls back to the default shell when the JSON body is malformed", () => {
    const { container } = render(
      <MetricsViewRenderer body={"{ this is not valid JSON at all"} />
    );

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-metrics-summary")).toBeFalsy();
  });

  it("falls back to the default shell when valid JSON is missing the aggregate key", () => {
    const bodyWithoutAggregate = JSON.stringify({
      schema_version: "1.3.0",
      run_metadata: { window_days: 45 }
    });

    const { container } = render(
      <MetricsViewRenderer body={bodyWithoutAggregate} />
    );

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-metrics-summary")).toBeFalsy();
  });
});
