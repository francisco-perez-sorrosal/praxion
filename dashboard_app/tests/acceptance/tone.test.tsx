// @vitest-environment jsdom
/**
 * Acceptance: grades, health words and verdicts map through one tone
 * vocabulary (good, info, warn, bad, neutral) on every surface, and no tone
 * is carried by colour alone.
 *
 * A displayed meaning exposes its tone as `data-tone` on the element that
 * shows it.
 */

import { describe, expect, it, vi } from "vitest";

import {
  cardTitled,
  navLink,
  renderRoute,
  renderShellDocument,
  type Route,
  sidebarOf,
  textOf,
  tonesShowing,
  useDashboardHarness,
  withoutDisclosure,
  withoutDisclosureBodies
} from "./drivers/dashboard";
import { at, buildProjectRoot, sentinelFamily } from "./drivers/fixture-project";
import { cleanProject, fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

function requireCard(page: Element, title: RegExp): Element {
  const card = cardTitled(page, title);
  if (!card) throw new Error(`No card titled ${title} in: ${textOf(page).slice(0, 400)}`);
  return card;
}

function projectGraded(grade: string): Promise<string> {
  return buildProjectRoot(
    sentinelFamily([
      { at: at("2026-10-01T09:30:00Z"), grade, coherence: grade, critical: 0, important: 1, suggested: 1 }
    ]),
    `acceptance-grade-${grade}-`
  );
}

describe("the grade tone", () => {
  it.each([
    ["A", "good"],
    ["B", "info"],
    ["C", "warn"],
    ["D", "bad"],
    ["F", "bad"]
  ])("is the same for grade %s on the sidebar, the Overview and the Sentinel digest: %s", async (grade, tone) => {
    const root = await projectGraded(grade);
    const sidebarEntry = navLink(sidebarOf(await renderShellDocument(root)), "/sentinel");
    const overviewTile = requireCard(await renderRoute("/", root), /sentinel/i);
    const digest = withoutDisclosureBodies(await renderRoute("/sentinel", root));

    for (const [where, scope] of [
      ["sidebar", sidebarEntry],
      ["overview", overviewTile],
      ["sentinel digest", digest]
    ] as const) {
      const tones = tonesShowing(scope, grade);
      expect(tones.length, `no toned grade ${grade} on the ${where}`).toBeGreaterThan(0);
      expect(new Set(tones), `grade ${grade} on the ${where}`).toEqual(new Set([tone]));
    }
  });
});

describe("the metrics health-word tone", () => {
  it.each([
    ["worsening", fullProject, /worsening/i, "bad"],
    ["baseline captured", cleanProject, /baseline captured/i, "info"]
  ] as const)("maps %s the same on the sidebar and the Overview", async (_word, build, word, tone) => {
    const root = await build();
    const sidebarEntry = navLink(sidebarOf(await renderShellDocument(root)), "/metrics");
    const overviewTile = requireCard(await renderRoute("/", root), /metrics/i);

    for (const scope of [sidebarEntry, overviewTile]) {
      const tones = tonesShowing(scope, word);
      expect(tones.length, `no toned ${word} in ${textOf(scope)}`).toBeGreaterThan(0);
      expect(new Set(tones)).toEqual(new Set([tone]));
    }
  });
});

describe("the verdict tone", () => {
  it.each([
    [/\bpass/i, "good"],
    [/\bwarn/i, "warn"],
    [/\bfail/i, "bad"],
    [/\bskip/i, "neutral"]
  ])("maps the %s count of the eval digest to %s", async (verdict, tone) => {
    const digest = withoutDisclosure(await renderRoute("/evals", await fullProject()), /full report/i);

    const tones = tonesShowing(digest, verdict);
    expect(tones.length, `no toned ${verdict} count`).toBeGreaterThan(0);
    expect(new Set(tones)).toEqual(new Set([tone]));
  });
});

describe("tone is never carried by colour alone", () => {
  it.each(["/", "/sentinel", "/evals", "/workshops"] as Route[])(
    "every toned element on %s says its meaning in text or a label",
    async (route) => {
      const page = await renderRoute(route, await fullProject());

      const toned = Array.from(page.querySelectorAll("[data-tone]"));
      expect(toned.length, `no toned element on ${route}`).toBeGreaterThan(0);
      const silent = toned.filter((el) => textOf(el) === "" && !el.getAttribute("aria-label"));
      expect(silent.map((el) => el.outerHTML)).toEqual([]);
    }
  );

  it("every toned element in the sidebar says its meaning in text or a label", async () => {
    const sidebar = sidebarOf(await renderShellDocument(await fullProject()));

    const toned = Array.from(sidebar.querySelectorAll("[data-tone]"));
    expect(toned.length, "no toned sidebar signal").toBeGreaterThan(0);
    expect(toned.filter((el) => textOf(el) === "" && !el.getAttribute("aria-label")).map((el) => el.outerHTML)).toEqual([]);
  });
});
