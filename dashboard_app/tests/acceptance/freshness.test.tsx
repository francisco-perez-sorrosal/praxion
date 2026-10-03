// @vitest-environment jsdom
/**
 * Acceptance: every surface header says how fresh its data is — the newest
 * modification time among the artifacts it read — and says nothing when it
 * read nothing.
 *
 * FULL's newest artifact per family (see drivers/project-presets.ts); each
 * family is older than some other family, so a surface that stamped the
 * project-wide newest time would be caught.
 */

import { describe, expect, it, vi } from "vitest";

import {
  ALL_ROUTES,
  dataAsOf,
  mentionsDate,
  renderRoute,
  type Route,
  useDashboardHarness
} from "./drivers/dashboard";
import { emptyProject, fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

const NEWEST_READ: Array<[Route, string]> = [
  ["/", "2026-10-02T12:00:00.000Z"], // alpha-active's WIP.md, newest of all
  ["/workshops", "2026-10-02T12:00:00.000Z"], // alpha-active's WIP.md
  ["/sentinel", "2026-10-01T09:30:00.000Z"], // the newest (selected) report
  ["/evals", "2026-09-30T08:00:00.000Z"], // the newest quality-eval report and log
  ["/metrics", "2026-09-28T12:00:00.000Z"], // the newest metrics snapshot and log
  ["/adrs", "2026-09-25T10:00:00.000Z"], // dec-007, the last decision modified
  ["/architecture", "2026-09-14T10:00:00.000Z"], // docs/architecture.md
  ["/documentation", "2026-09-08T10:00:00.000Z"], // the manifest and docs/guide.md
  ["/roadmap", "2026-09-05T10:00:00.000Z"] // ROADMAP.md
];

describe("the data-as-of stamp", () => {
  it.each(NEWEST_READ)("on %s is the newest modification time among what it read", async (route, newest) => {
    const page = await renderRoute(route, await fullProject());

    expect(dataAsOf(page)?.at.toISOString()).toBe(newest);
  });

  it.each(ALL_ROUTES)("is omitted on %s when the surface read nothing", async (route) => {
    const page = await renderRoute(route, await emptyProject());

    expect(dataAsOf(page)).toBeNull();
  });

  it("shows the time of day for data from today", async () => {
    // the frozen clock reads 2026-10-02 15:00Z; alpha-active was touched at 12:00Z
    const stamp = dataAsOf(await renderRoute("/", await fullProject()));

    expect(stamp?.text).toMatch(/\b12[:.]00\b|\b12\s?(pm|PM)\b/);
    expect(stamp?.text).not.toMatch(/2026/);
  });

  it("shows the date for data from an earlier day", async () => {
    const stamp = dataAsOf(await renderRoute("/roadmap", await fullProject()));

    expect(mentionsDate(stamp?.text ?? "", "2026-09-05")).toBe(true);
  });
});
