// @vitest-environment jsdom
/**
 * Acceptance: every surface and every Overview tile degrades to an
 * informative empty state, and one unreadable family never blanks another.
 */

import { describe, expect, it, vi } from "vitest";

import {
  ALL_ROUTES,
  bodyTextOf,
  cardTitled,
  entryFor,
  hasToken,
  navLink,
  renderRoute,
  renderShellDocument,
  sidebarOf,
  textOf,
  useDashboardHarness
} from "./drivers/dashboard";
import { emptyProject, fullProjectWithUnreadableEvalLog, partialProject } from "./drivers/project-presets";

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

describe("a project whose state directory is empty", () => {
  it.each(ALL_ROUTES)("renders %s with content rather than failing", async (route) => {
    const page = await renderRoute(route, await emptyProject());

    expect(textOf(page.querySelector("h1")).length).toBeGreaterThan(0);
    expect(textOf(page).length).toBeGreaterThan(textOf(page.querySelector("h1")).length);
  });

  it("shows, on each Overview tile, what produces its data", async () => {
    const page = await renderRoute("/", await emptyProject());

    const producers: Array<[RegExp, RegExp]> = [
      [/sentinel/i, /sentinel/i],
      [/metrics/i, /\/project-metrics/],
      [/eval/i, /\/eval-praxion/],
      [/readiness/i, /\/project-metrics/],
      [/in.?flight/i, /\.ai-work/],
      [/decision/i, /\.ai-state\/decisions|\badrs?\b/i]
    ];
    for (const [title, producer] of producers) {
      const tile = requireCard(page, title);
      expect(bodyTextOf(tile), `tile ${title} does not name ${producer}`).toMatch(producer);
    }
  });
});

describe("a project holding only some artifact families", () => {
  it("shows the families it has and names the producers of the ones it lacks", async () => {
    // PARTIAL: sentinel and workshops only
    const page = await renderRoute("/", await partialProject());

    expect(hasToken(textOf(requireCard(page, /sentinel/i)), "C")).toBe(true);
    expect(entryFor(requireCard(page, /in.?flight/i), "alpha-active")).not.toBeNull();
    expect(bodyTextOf(requireCard(page, /metrics/i))).toMatch(/\/project-metrics/);
    expect(bodyTextOf(requireCard(page, /eval/i))).toMatch(/\/eval-praxion/);
  });
});

describe("a project with one unreadable artifact family", () => {
  it("keeps every other Overview tile populated", async () => {
    const page = await renderRoute("/", await fullProjectWithUnreadableEvalLog());

    expect(hasToken(textOf(requireCard(page, /sentinel/i)), "C")).toBe(true);
    expect(textOf(requireCard(page, /metrics/i))).toMatch(/worsening/i);
    expect(entryFor(requireCard(page, /in.?flight/i), "alpha-active")).not.toBeNull();
    expect(textOf(requireCard(page, /eval/i))).not.toContain("1187");
  });

  it("keeps the sidebar signals of the readable families", async () => {
    const shell = await renderShellDocument(await fullProjectWithUnreadableEvalLog());

    expect(hasToken(textOf(navLink(sidebarOf(shell), "/sentinel")), "C")).toBe(true);
  });

  it("still renders the surface whose family is unreadable", async () => {
    const page = await renderRoute("/evals", await fullProjectWithUnreadableEvalLog());

    expect(textOf(page.querySelector("h1"))).toMatch(/evals/i);
  });
});
