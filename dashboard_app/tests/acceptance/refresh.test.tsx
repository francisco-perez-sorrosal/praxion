// @vitest-environment jsdom
/**
 * Acceptance: only the status surfaces re-render on a timer — Workshops at
 * the configured poll interval, the Overview at four times that interval and
 * never more often than once a minute. Reference surfaces stay still.
 *
 * A page "re-renders" when it asks the App Router to refresh it.
 */

import { describe, expect, it, vi } from "vitest";

import { mountRoute, SURFACE_ROUTES, useDashboardHarness } from "./drivers/dashboard";
import { fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

describe("the Workshops surface", () => {
  it("re-renders once the configured poll interval elapses, not before", async () => {
    const page = await mountRoute("/workshops", await fullProject(), { pollSeconds: 20 });

    await page.advanceSeconds(19);
    expect(page.refreshCount()).toBe(0);
    await page.advanceSeconds(1);
    expect(page.refreshCount()).toBe(1);
  });
});

describe("the Overview", () => {
  it("re-renders at four times the configured poll interval", async () => {
    const page = await mountRoute("/", await fullProject(), { pollSeconds: 20 });

    await page.advanceSeconds(79);
    expect(page.refreshCount()).toBe(0);
    await page.advanceSeconds(1);
    expect(page.refreshCount()).toBe(1);
  });

  it("never re-renders more often than once a minute", async () => {
    const page = await mountRoute("/", await fullProject(), { pollSeconds: 5 });

    await page.advanceSeconds(59);
    expect(page.refreshCount()).toBe(0);
    await page.advanceSeconds(1);
    expect(page.refreshCount()).toBe(1);
  });
});

describe("the reference surfaces", () => {
  it.each(SURFACE_ROUTES.filter((route) => route !== "/workshops"))(
    "%s does not re-render while it stays open",
    async (route) => {
      const page = await mountRoute(route, await fullProject(), { pollSeconds: 5 });

      await page.advanceSeconds(600);
      expect(page.refreshCount()).toBe(0);
    }
  );
});
