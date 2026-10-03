// @vitest-environment jsdom
/**
 * Acceptance: workshops are grouped by recency (active, stale, done) with
 * their age and step progress, and the sidebar count follows the same rule.
 *
 * FULL's workshops, relative to the frozen clock:
 *   alpha-active  in progress, WIP touched 3 h ago, 2 of 5 steps
 *   beta-active   in progress, WIP 20 d old but PROGRESS touched 2 d ago, 1 of 3
 *   gamma-stale   in progress, last touched 12 d ago, 4 of 6
 *   delta-done    finished 1 d ago
 *   epsilon-done  finished 30 d ago
 */

import { describe, expect, it, vi } from "vitest";

import {
  disclosureLabelled,
  entryFor,
  groupLabelled,
  navLink,
  renderRoute,
  renderShellDocument,
  sidebarOf,
  textOf,
  useDashboardHarness
} from "./drivers/dashboard";
import { fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

const ACTIVE = /^\s*active\b/i;
const STALE = /^\s*stale\b/i;
const DONE = /^\s*(done|finished)\b/i;

const SLUGS = ["alpha-active", "beta-active", "gamma-stale", "delta-done", "epsilon-done"];

function requireGroup(page: Element, label: RegExp): Element {
  const group = groupLabelled(page, label);
  if (!group) throw new Error(`No workshop group labelled ${label} in: ${textOf(page).slice(0, 400)}`);
  return group;
}

function slugsIn(group: Element | null): string[] {
  return SLUGS.filter((slug) => textOf(group).includes(slug));
}

describe("the workshop groups", () => {
  it("puts unfinished workshops active in the last seven days in Active", async () => {
    const page = await renderRoute("/workshops", await fullProject());

    expect(slugsIn(requireGroup(page, ACTIVE))).toEqual(["alpha-active", "beta-active"]);
  });

  it("puts unfinished workshops idle for more than seven days in Stale, closed by default", async () => {
    const page = await renderRoute("/workshops", await fullProject());

    expect(slugsIn(requireGroup(page, STALE))).toEqual(["gamma-stale"]);
    expect(disclosureLabelled(page, STALE)?.open).toBe(false);
  });

  it("puts finished workshops in Done, however recent, closed by default", async () => {
    const page = await renderRoute("/workshops", await fullProject());

    expect(slugsIn(requireGroup(page, DONE))).toEqual(["delta-done", "epsilon-done"]);
    expect(disclosureLabelled(page, DONE)?.open).toBe(false);
  });

  it("takes a workshop's last activity from its newest artifact, not only its WIP", async () => {
    const page = await renderRoute("/workshops", await fullProject());

    expect(textOf(entryFor(requireGroup(page, ACTIVE), "beta-active"))).toMatch(/\b2\s*d(ays?)?\s+ago/i);
  });
});

describe("each workshop entry", () => {
  it.each([
    { slug: "alpha-active", group: ACTIVE, age: /\b3\s*h(ours?|rs?)?\s+ago/i, progress: /\b2\s*(\/|of)\s*5\b/ },
    { slug: "beta-active", group: ACTIVE, age: /\b2\s*d(ays?)?\s+ago/i, progress: /\b1\s*(\/|of)\s*3\b/ },
    { slug: "gamma-stale", group: STALE, age: /\b12\s*d(ays?)?\s+ago/i, progress: /\b4\s*(\/|of)\s*6\b/ }
  ])("shows $slug's relative age and its step progress", async ({ slug, group, age, progress }) => {
    const page = await renderRoute("/workshops", await fullProject());

    const entry = entryFor(requireGroup(page, group), slug);
    expect(textOf(entry)).toMatch(age);
    expect(textOf(entry)).toMatch(progress);
  });
});

describe("the default selection", () => {
  it("selects the most recently active workshop", async () => {
    const page = await renderRoute("/workshops", await fullProject());

    const selected = page.querySelector("[aria-selected='true'], [aria-current='true']");
    expect(textOf(selected)).toContain("alpha-active");
  });
});

describe("the sidebar workshop count", () => {
  it("agrees with the number of workshops in the Active group", async () => {
    const root = await fullProject();
    const page = await renderRoute("/workshops", root);
    const sidebar = sidebarOf(await renderShellDocument(root, "/workshops"));

    const activeCount = slugsIn(requireGroup(page, ACTIVE)).length;
    expect(activeCount).toBe(2);
    expect(textOf(navLink(sidebar, "/workshops")).match(/\d+/g)).toEqual([String(activeCount)]);
  });
});
