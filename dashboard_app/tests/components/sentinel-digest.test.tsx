// @vitest-environment jsdom
import { cleanup, fireEvent, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SentinelClient } from "@/app/sentinel/sentinel-client";
import type { SentinelLogPoint, SentinelReport } from "@/server/view-models/sentinel";

const NEWEST_FILE = "SENTINEL_REPORT_2026-10-01_09-30-00.md";
const OLDER_FILE = "SENTINEL_REPORT_2026-09-20_09-30-00.md";
const BODY_SENTENCE = "Only the full report carries this sentence.";

function point(day: string, grade: string, file: string, counts: [number, number, number]): SentinelLogPoint {
  return {
    coherence: "A",
    critical: counts[0],
    grade,
    important: counts[1],
    reportFile: file,
    suggested: counts[2],
    timestamp: `${day} 09:30:00`
  };
}

function report(overrides: Partial<SentinelReport> & Pick<SentinelReport, "fileName">): SentinelReport {
  return {
    body: "",
    data: {},
    highlight: null,
    isPartial: false,
    notReachedCount: 0,
    path: `/fixture/${overrides.fileName}`,
    reportTimestamp: null,
    sections: { critical: "", important: "", suggested: "", rest: BODY_SENTENCE },
    ...overrides
  };
}

const OLDER_POINT = point("2026-09-20", "B", OLDER_FILE, [0, 1, 2]);
const NEWEST_POINT = point("2026-10-01", "C", NEWEST_FILE, [0, 4, 14]);

const NEWEST = report({
  fileName: NEWEST_FILE,
  highlight: NEWEST_POINT,
  isPartial: true,
  notReachedCount: 2,
  reportTimestamp: "2026-10-01T09:30:00.000Z",
  sections: {
    critical: "#### Critical\n\nCritical table",
    important: "#### Important\n\nImportant table",
    suggested: "#### Suggested\n\nSuggested table",
    rest: BODY_SENTENCE
  }
});
const OLDER = report({
  fileName: OLDER_FILE,
  highlight: OLDER_POINT,
  reportTimestamp: "2026-09-20T09:30:00.000Z"
});

function renderDigest(reports: SentinelReport[], logSeries: SentinelLogPoint[]) {
  return render(<SentinelClient reports={reports} logSeries={logSeries} />);
}

function disclosure(container: HTMLElement, label: string): HTMLDetailsElement {
  const summary = Array.from(container.querySelectorAll("summary")).find((el) => el.textContent?.includes(label));
  if (!summary?.parentElement) {
    throw new Error(`No disclosure labelled ${label}`);
  }
  return summary.parentElement as HTMLDetailsElement;
}

afterEach(cleanup);

describe("the sentinel digest", () => {
  it("leads with the grade letter, the coherence grade, the partial badge and the not-reached caption", () => {
    const { container } = renderDigest([NEWEST, OLDER], [OLDER_POINT, NEWEST_POINT]);
    const summary = within(container.querySelector('[aria-label="Sentinel report summary"]') as HTMLElement);

    expect(summary.getByText("C").getAttribute("data-tone")).toBe("warn");
    expect(summary.getByText("Coherence A")).toBeTruthy();
    expect(summary.getByText("PARTIAL")).toBeTruthy();
    expect(summary.getByText("2 checks not reached")).toBeTruthy();
  });

  it("tones the three finding counts by whether they are non-zero", () => {
    const { container } = renderDigest([NEWEST], [NEWEST_POINT]);
    const tones = Array.from(container.querySelectorAll(".stat-tile")).map((tile) => {
      const label = tile.querySelector(".stat-tile__label") as HTMLElement;
      label.querySelector(".stat-tile__glyph")?.remove();
      return [label.textContent, tile.querySelector(".stat-tile__value [data-tone]")?.getAttribute("data-tone")];
    });

    expect(tones).toEqual([
      ["Health", "warn"],
      ["Critical", "good"],
      ["Important", "warn"],
      ["Suggested", "info"]
    ]);
  });

  it.each([
    ["A", "good"],
    ["B", "info"],
    ["C", "warn"],
    ["D", "bad"],
    ["F", "bad"]
  ])("shows grade %s with the %s tone", (grade, tone) => {
    const graded = point("2026-10-01", grade, NEWEST_FILE, [0, 1, 1]);
    const { container } = renderDigest([report({ fileName: NEWEST_FILE, highlight: graded })], [graded]);

    const hero = container.querySelector(".stat-tile__value--grade");
    expect(hero?.textContent).toBe(grade);
    expect(hero?.getAttribute("data-tone")).toBe(tone);
  });

  it("shows no partial badge and no caption for a complete report that reached every check", () => {
    const complete = report({ fileName: NEWEST_FILE, highlight: NEWEST_POINT });
    const { container } = renderDigest([complete], [NEWEST_POINT]);

    expect(container.textContent).not.toMatch(/partial|not reached/i);
  });

  it("names a report without a log row as not graded instead of inventing a grade", () => {
    const { container } = renderDigest([report({ fileName: NEWEST_FILE })], []);

    expect(container.querySelector(".stat-tile__value--word")?.textContent).toBe("Not graded");
    expect(container.textContent).toContain("No runs in SENTINEL_LOG.md yet.");
  });

  it("labels the trend and names every run's date", () => {
    const { container } = renderDigest([NEWEST, OLDER], [OLDER_POINT, NEWEST_POINT]);
    const trend = container.querySelector('[aria-label*="trend"]') as HTMLElement;

    expect(trend.textContent).toContain("2026-09-20");
    expect(trend.textContent).toContain("2026-10-01");
  });
});

describe("the sentinel disclosures", () => {
  it("opens critical findings and closes important, suggested and the full report when something is critical", () => {
    const critical = point("2026-10-01", "D", NEWEST_FILE, [1, 2, 3]);
    const { container } = renderDigest([{ ...NEWEST, highlight: critical }], [critical]);

    expect(disclosure(container, "Critical").open).toBe(true);
    expect(disclosure(container, "Important").open).toBe(false);
    expect(disclosure(container, "Suggested").open).toBe(false);
    expect(disclosure(container, "Full report").open).toBe(false);
  });

  it("opens the important findings when nothing is critical", () => {
    const { container } = renderDigest([NEWEST], [NEWEST_POINT]);

    expect(disclosure(container, "Important").open).toBe(true);
    expect(disclosure(container, "Critical").open).toBe(false);
  });

  it("keeps the report body inside the closed full-report disclosure", () => {
    const { container } = renderDigest([NEWEST], [NEWEST_POINT]);
    const full = disclosure(container, "Full report");

    expect(full.open).toBe(false);
    expect(full.textContent).toContain(BODY_SENTENCE);
    expect(container.querySelector(".sentinel-client")?.textContent?.split(BODY_SENTENCE)).toHaveLength(2);
  });
});

describe("the report selector", () => {
  it("lists every report newest first and switches the digest on change", () => {
    const { container } = renderDigest([NEWEST, OLDER], [OLDER_POINT, NEWEST_POINT]);
    const select = container.querySelector("select") as HTMLSelectElement;

    expect(Array.from(select.options).map((option) => option.value)).toEqual([NEWEST_FILE, OLDER_FILE]);
    expect(select.value).toBe(NEWEST_FILE);

    fireEvent.change(select, { target: { value: OLDER_FILE } });

    expect(container.querySelector(".stat-tile__value--grade")?.textContent).toBe("B");
    expect(container.textContent).not.toContain("PARTIAL");
  });
});
