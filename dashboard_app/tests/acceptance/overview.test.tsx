// @vitest-environment jsdom
/**
 * Acceptance: the dashboard root is an Overview composed from every surface.
 *
 * Driven through the root route against fixture project roots (see
 * drivers/project-presets.ts for what FULL and CLEAN hold).
 */

import { describe, expect, it, vi } from "vitest";

import {
  bodyTextOf,
  cardTitled,
  entryFor,
  hasToken,
  headingOrder,
  labelledNumber,
  linksTo,
  renderRoute,
  SURFACE_ROUTES,
  textOf,
  useDashboardHarness
} from "./drivers/dashboard";
import { cleanProject, fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

function requireCard(page: HTMLElement, title: RegExp): HTMLElement {
  const card = cardTitled(page, title);
  if (!card) throw new Error(`No Overview card titled ${title} in: ${textOf(page).slice(0, 400)}`);
  return card;
}

describe("the dashboard root", () => {
  it("renders an Overview page instead of redirecting to another surface", async () => {
    const page = await renderRoute("/", await fullProject());

    expect(textOf(page.querySelector("h1"))).toMatch(/overview/i);
  });

  it("presents the pulse tiles, then in-flight, decisions, attention, recent activity and explore, in that order", async () => {
    const page = await renderRoute("/", await fullProject());

    const positions = headingOrder(page, [
      /sentinel/i,
      /metrics/i,
      /eval/i,
      /readiness/i,
      /in.?flight/i,
      /decision/i,
      /attention/i,
      /recent/i,
      /explore/i
    ]);

    expect(positions.every((p) => p >= 0), `missing card heading, positions ${positions}`).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });
});

describe("the Overview pulse row", () => {
  it("shows the sentinel grade with its critical, important and suggested counts, linking to Sentinel", async () => {
    const page = await renderRoute("/", await fullProject());
    const tile = requireCard(page, /sentinel/i);

    // newest FULL sentinel run: grade C, findings 1 / 2 / 3
    expect(hasToken(textOf(tile), "C")).toBe(true);
    expect(labelledNumber(tile, /critical/i)).toBe(1);
    expect(labelledNumber(tile, /important/i)).toBe(2);
    expect(labelledNumber(tile, /suggested/i)).toBe(3);
    expect(linksTo(tile, "/sentinel")).toBe(true);
  });

  it("shows the metrics health word with the counts of improving, steady and worsening indicators, linking to Metrics", async () => {
    const page = await renderRoute("/", await fullProject());
    const tile = requireCard(page, /metrics/i);

    // FULL's newer snapshot worsens six indicators and leaves the rest unchanged
    expect(textOf(tile)).toMatch(/worsening/i);
    expect(labelledNumber(tile, /improving/i)).toBe(0);
    expect(labelledNumber(tile, /steady|stable/i)).toBeGreaterThanOrEqual(2);
    expect(labelledNumber(tile, /worsening/i)).toBe(6);
    expect(linksTo(tile, "/metrics")).toBe(true);
  });

  it("shows the latest quality-eval run's pass, warn and fail counts and its cost, linking to Evals", async () => {
    const page = await renderRoute("/", await fullProject());
    const tile = requireCard(page, /eval/i);

    expect(labelledNumber(tile, /pass/i)).toBe(1187);
    expect(labelledNumber(tile, /warn/i)).toBe(64);
    expect(labelledNumber(tile, /fail/i)).toBe(3);
    expect(textOf(tile)).toMatch(/\$\s?0\.43/);
    expect(linksTo(tile, "/evals")).toBe(true);
  });

  it("shows the agent readiness level and pass percentage, linking to Metrics", async () => {
    const page = await renderRoute("/", await fullProject());
    const tile = requireCard(page, /readiness/i);

    expect(textOf(tile)).toMatch(/\bL\s?3\b|level\s*3\b/i);
    expect(textOf(tile)).toMatch(/\b82(\.\d+)?\s?%/);
    expect(linksTo(tile, "/metrics")).toBe(true);
  });
});

describe("the Overview cards", () => {
  it("lists the workshops active in the last seven days with step and progress, and counts the stale and finished ones", async () => {
    const page = await renderRoute("/", await fullProject());
    const card = requireCard(page, /in.?flight/i);

    const alpha = entryFor(card, "alpha-active");
    const beta = entryFor(card, "beta-active");
    expect(textOf(alpha)).toContain("Wire the alpha reader");
    expect(textOf(alpha)).toMatch(/\b2\s*(\/|of)\s*5\b/);
    expect(textOf(beta)).toContain("Draft the beta tests");
    expect(textOf(beta)).toMatch(/\b1\s*(\/|of)\s*3\b/);
    expect(textOf(card)).not.toContain("gamma-stale");
    expect(textOf(card)).not.toContain("delta-done");
    expect(labelledNumber(card, /stale/i)).toBe(1);
    expect(labelledNumber(card, /done|finished/i)).toBe(2);
    expect(linksTo(card, "/workshops")).toBe(true);
  });

  it("counts finalized and draft decisions, names the three highest-numbered ones newest first, and splits by category", async () => {
    const page = await renderRoute("/", await fullProject());
    const card = requireCard(page, /decision/i);
    const text = textOf(card);

    expect(labelledNumber(card, /finali[sz]ed/i)).toBe(4);
    expect(labelledNumber(card, /draft/i)).toBe(2);
    // dec-012, dec-010, dec-009 by number — not dec-007, though it was modified last
    expect(text.indexOf("Twelve architectural split")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("Ten behavioral rule")).toBeGreaterThan(text.indexOf("Twelve architectural split"));
    expect(text.indexOf("Nine architectural boundary")).toBeGreaterThan(text.indexOf("Ten behavioral rule"));
    expect(text).not.toContain("Seven implementation choice");
    expect(text).toMatch(/architectural/i);
    expect(text).toMatch(/behavioral/i);
    expect(linksTo(card, "/adrs")).toBe(true);
  });

  it("raises one attention line per condition that needs an operator", async () => {
    const page = await renderRoute("/", await fullProject());
    const lines = Array.from(requireCard(page, /attention/i).querySelectorAll("li")).map(textOf);

    // FULL: a critical finding, important findings, a partial report, worsening
    // metrics, quality-eval failures and an important open tech-debt row
    expect(lines).toHaveLength(6);
    for (const condition of [/critical/i, /important/i, /partial/i, /worsening/i, /fail/i, /debt/i]) {
      expect(lines.some((line) => condition.test(line)), `no attention line for ${condition}`).toBe(true);
    }
  });

  it("raises no attention line when nothing needs an operator", async () => {
    const page = await renderRoute("/", await cleanProject());

    expect(requireCard(page, /attention/i).querySelectorAll("li")).toHaveLength(0);
  });

  it("lists the newest artifact of each family with its age, newest first", async () => {
    const page = await renderRoute("/", await fullProject());
    const items = Array.from(requireCard(page, /recent/i).querySelectorAll("li")).map(textOf);

    const families: Array<[string, RegExp]> = [
      ["workshops", /alpha-active|workshop/i],
      ["sentinel", /sentinel/i],
      ["evals", /eval/i],
      ["metrics", /metric/i],
      ["decisions", /decision|\badr|dec-\d/i],
      ["architecture", /design|architecture/i],
      ["documentation", /doc_manifest|documentation|guide\.md/i],
      ["roadmap", /roadmap/i]
    ];
    const order = items
      .map((item) => families.find(([, pattern]) => pattern.test(item))?.[0])
      .filter((family): family is string => family !== undefined);

    expect(order).toEqual(families.map(([family]) => family));
    expect(items.every((item) => /\bago\b|just now/i.test(item)), `items without an age: ${items}`).toBe(true);
  });

  it("links every surface from the explore grid with a sentence on what it holds", async () => {
    const page = await renderRoute("/", await fullProject());
    const grid = requireCard(page, /explore/i);

    for (const route of SURFACE_ROUTES) {
      const link = grid.querySelector(`a[href="${route}"]`);
      expect(link, `explore grid has no link to ${route}`).not.toBeNull();
      const entry = link?.closest("li, article") ?? link;
      expect(bodyTextOf(entry as Element).split(/\s+/).length, `no sentence for ${route}`).toBeGreaterThanOrEqual(5);
    }
  });
});
