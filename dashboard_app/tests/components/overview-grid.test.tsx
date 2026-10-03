// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewGrid } from "@/components/overview/overview-grid";
import type { OverviewData } from "@/server/view-models/overview";

// Recharts needs layout the DOM does not have; the trends are not under test here.
vi.mock("@/components/viz/sparkline", () => ({ Sparkline: () => null }));
vi.mock("@/components/viz/grade-sparkline", () => ({ GradeSparkline: () => null }));

const NOW = new Date("2026-10-02T15:00:00Z");

const EVAL_RUN = {
  authRoute: "",
  costUsd: 0.43,
  families: "1",
  fail: 3,
  pass: 1187,
  reportFile: null,
  target: "t",
  timestamp: "2026-09-30T08-00-00Z",
  warn: 64
};

const FULL: OverviewData = {
  activity: [
    { family: "workshops", href: "/workshops", label: "Workshop alpha", mtime: "2026-10-02T12:00:00.000Z" },
    { family: "roadmap", href: "/roadmap", label: "Roadmap", mtime: "2026-09-05T10:00:00.000Z" }
  ],
  attention: [
    { href: "/sentinel", text: "1 critical sentinel finding", tone: "bad" },
    { href: null, text: "1 important tech-debt row open or in flight", tone: "warn" }
  ],
  dataAsOf: "2026-10-02T12:00:00.000Z",
  debt: { bySeverity: { important: 1 }, inFlight: 0, open: 1 },
  decisions: {
    byCategory: { architectural: 2, behavioral: 1 },
    drafts: 1,
    finalized: 3,
    latest: [{ date: "2026-09-04", id: "dec-012", status: "accepted", title: "Twelve architectural split" }]
  },
  evals: { failGroups: [], latest: EVAL_RUN, runs: [EVAL_RUN], timestamp: EVAL_RUN.timestamp },
  metrics: {
    degraded: false,
    healthLabel: "WORSENING",
    readiness: { level: 3, passPct: 0.82 },
    timestamp: null,
    tones: { bad: 6, good: 0, steady: 2 }
  },
  sentinel: {
    coherence: "A",
    critical: 1,
    grade: "C",
    important: 2,
    isPartial: true,
    notReachedCount: 3,
    series: [],
    suggested: 3,
    timestamp: null
  },
  workshops: {
    active: [{ currentStep: "Wire the alpha reader", progress: { done: 2, total: 5 }, slug: "alpha-active", updatedAt: "2026-10-02T12:00:00.000Z" }],
    doneCount: 2,
    staleCount: 1
  }
};

const ABSENT: OverviewData = {
  activity: [],
  attention: [],
  dataAsOf: null,
  debt: null,
  decisions: null,
  evals: null,
  metrics: null,
  sentinel: null,
  workshops: null
};

function renderGrid(data: OverviewData) {
  return render(<OverviewGrid data={data} now={NOW} />);
}

/** The card (article or section) headed by the given name. */
function cardNamed(name: RegExp): HTMLElement {
  const heading = screen.getByRole("heading", { name });
  return heading.closest("article, section") as HTMLElement;
}

/** Every toned element of the card as [text, tone]. */
function tonesIn(card: HTMLElement): Array<[string | null, string | null]> {
  return Array.from(card.querySelectorAll("[data-tone]")).map((el) => [el.textContent, el.getAttribute("data-tone")]);
}

afterEach(cleanup);

describe("OverviewGrid pulse row", () => {
  it.each([
    [/^sentinel$/i, "/sentinel"],
    [/^metrics$/i, "/metrics"],
    [/^quality evals$/i, "/evals"],
    [/^agent readiness$/i, "/metrics"]
  ])("renders the %s tile as a link to its surface", (name, href) => {
    renderGrid(FULL);

    expect(within(cardNamed(name)).getByRole("link").getAttribute("href")).toBe(href);
  });

  it("shows the sentinel grade with its partial badge and counts", () => {
    renderGrid(FULL);
    const tile = cardNamed(/^sentinel$/i);

    expect(within(tile).getByText("C").getAttribute("class")).toContain("stat-tile__value--grade");
    expect(within(tile).getByText("PARTIAL")).toBeTruthy();
    expect(within(tile).getByText("critical", { exact: false }).textContent).toBe("1 critical");
  });

  it("shows the quality-eval failure count with the other verdicts and the cost", () => {
    renderGrid(FULL);
    const tile = cardNamed(/^quality evals$/i);

    expect(tonesIn(tile)).toEqual([
      ["3 FAIL", "bad"],
      ["1187 PASS", "good"],
      ["64 WARN", "warn"]
    ]);
    expect(tile.textContent).toContain("$0.43");
  });

  it("never presents an eval run whose counts are unreadable as passing", () => {
    const unreadable = { ...EVAL_RUN, fail: null, pass: null, warn: null };
    renderGrid({ ...FULL, evals: { failGroups: [], latest: unreadable, runs: [unreadable], timestamp: unreadable.timestamp } });
    const tile = cardNamed(/^quality evals$/i);

    expect(tonesIn(tile)).toEqual([["No counts", "neutral"]]);
    expect(tile.textContent).not.toContain("PASS");
  });

  it("words the metrics health with the indicator counts, tone included", () => {
    renderGrid(FULL);
    const tile = cardNamed(/^metrics$/i);

    expect(tonesIn(tile)).toEqual([
      ["Worsening ↘", "bad"],
      ["0 improving", "neutral"],
      ["2 steady", "neutral"],
      ["6 worsening", "bad"]
    ]);
  });

  it("shows the readiness level with its pass percentage", () => {
    renderGrid(FULL);

    expect(cardNamed(/^agent readiness$/i).textContent).toMatch(/Level 3.*82 % of criteria pass/);
  });

  it("explains a first metrics snapshot instead of counting indicators", () => {
    renderGrid({ ...FULL, metrics: { ...FULL.metrics!, healthLabel: "BASELINE CAPTURED" } });
    const tile = cardNamed(/^metrics$/i);

    expect(tonesIn(tile)).toEqual([["Baseline captured", "info"]]);
    expect(tile.textContent).toContain("First snapshot");
    expect(tile.textContent).not.toContain("worsening");
  });
});

describe("OverviewGrid cards", () => {
  it("lists the active workshop with its step, progress and age, and counts the rest", () => {
    renderGrid(FULL);
    const card = cardNamed(/in flight/i);

    expect(within(card).getByRole("link", { name: /alpha-active/ }).textContent).toContain("Wire the alpha reader");
    expect(card.textContent).toContain("2/5");
    expect(card.textContent).toContain("3 h ago");
    expect(card.textContent).toContain("1 stale");
    expect(card.textContent).toContain("2 done");
  });

  it("names the newest decisions and the category split", () => {
    renderGrid(FULL);
    const card = cardNamed(/decisions/i);

    expect(card.textContent).toContain("3 finalized");
    expect(card.textContent).toContain("1 draft");
    expect(card.textContent).toContain("Twelve architectural split");
    expect(within(card).getByRole("list", { name: /by category/i }).textContent).toContain("architectural · 2");
  });

  it("raises one list item per attention condition and links only those with a surface", () => {
    renderGrid(FULL);
    const items = within(cardNamed(/attention/i)).getAllByRole("listitem");

    expect(items.map((item) => item.textContent)).toEqual([
      "✕1 critical sentinel finding",
      "!1 important tech-debt row open or in flight"
    ]);
    expect(items.map((item) => item.querySelector("a")?.getAttribute("href") ?? null)).toEqual(["/sentinel", null]);
  });

  it("is calm, without list items, when nothing needs attention", () => {
    renderGrid({ ...FULL, attention: [] });
    const card = cardNamed(/attention/i);

    expect(within(card).queryAllByRole("listitem")).toEqual([]);
    expect(card.textContent).toContain("Nothing needs attention");
  });

  it("gives every recent-activity entry its age", () => {
    renderGrid(FULL);
    const entries = within(cardNamed(/recent activity/i)).getAllByRole("listitem");

    expect(entries.map((entry) => entry.textContent)).toEqual(["Workshop alpha3 h ago", "Roadmap27 d ago"]);
  });

  it("links every surface from the explore grid", () => {
    renderGrid(FULL);
    const hrefs = within(cardNamed(/explore/i))
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));

    expect(hrefs).toEqual([
      "/sentinel",
      "/metrics",
      "/evals",
      "/workshops",
      "/roadmap",
      "/architecture",
      "/adrs",
      "/documentation"
    ]);
  });
});

describe("OverviewGrid for families that were not read", () => {
  it.each([
    [/^sentinel$/i, /sentinel/],
    [/^metrics$/i, /\/project-metrics/],
    [/^quality evals$/i, /\/eval-praxion/],
    [/^agent readiness$/i, /\/project-metrics/]
  ])("names what produces the %s tile", (name, producer) => {
    renderGrid(ABSENT);
    const tile = cardNamed(name);

    expect(tile.textContent).toMatch(producer);
    expect(tile.textContent).toContain("Not run yet");
    expect(within(tile).getByRole("link")).toBeTruthy();
  });

  it("names the producers of the in-flight and decisions cards", () => {
    renderGrid(ABSENT);

    expect(cardNamed(/in flight/i).textContent).toContain(".ai-work/<task-slug>/");
    expect(cardNamed(/decisions/i).textContent).toContain(".ai-state/decisions/");
  });

  it("says there is no activity yet rather than rendering an empty list", () => {
    renderGrid(ABSENT);

    expect(within(cardNamed(/recent activity/i)).queryAllByRole("listitem")).toEqual([]);
    expect(cardNamed(/recent activity/i).textContent).toContain("No artifacts yet");
  });
});
