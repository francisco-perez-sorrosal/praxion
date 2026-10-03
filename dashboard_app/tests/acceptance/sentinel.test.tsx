// @vitest-environment jsdom
/**
 * Acceptance: the Sentinel surface opens on a grade-first digest of the
 * selected report and keeps the report body one click away.
 */

import { describe, expect, it, vi } from "vitest";

import {
  accessibleTextOf,
  dataAsOf,
  disclosureLabelled,
  hasToken,
  isKeyboardReachable,
  labelledNumber,
  mentionsDate,
  regionLabelled,
  renderRoute,
  textOf,
  useDashboardHarness,
  withoutDisclosureBodies
} from "./drivers/dashboard";
import { at, buildProjectRoot, sentinelBodySentence, sentinelFamily, type SentinelRun } from "./drivers/fixture-project";
import { cleanProject, FULL_SENTINEL_RUNS, fullProject } from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

/** FULL's newest report: grade C [PARTIAL], coherence A, 1/2/3, three checks not reached. */
const NEWEST = FULL_SENTINEL_RUNS[2] as SentinelRun;

async function sentinelDigest(root: Promise<string>): Promise<Element> {
  return withoutDisclosureBodies(await renderRoute("/sentinel", await root));
}

describe("the sentinel digest", () => {
  it("leads with the health grade and the coherence grade, without the report text", async () => {
    const digest = await sentinelDigest(fullProject());
    const text = textOf(digest);

    expect(hasToken(text, "C")).toBe(true);
    expect(text).toMatch(/coherence\W*A\b/i);
    expect(text).not.toContain(sentinelBodySentence(NEWEST));
  });

  it("shows the critical, important and suggested finding counts as tiles", async () => {
    const digest = await sentinelDigest(fullProject());

    expect(labelledNumber(digest, /critical/i)).toBe(1);
    expect(labelledNumber(digest, /important/i)).toBe(2);
    expect(labelledNumber(digest, /suggested/i)).toBe(3);
  });

  it("marks a partial report", async () => {
    const digest = await sentinelDigest(fullProject());

    expect(textOf(digest)).toMatch(/partial/i);
  });

  it("does not mark a complete report as partial", async () => {
    // CLEAN's newest report: grade A, complete
    const digest = await sentinelDigest(cleanProject());

    expect(textOf(digest)).not.toMatch(/partial/i);
  });

  it("counts the checks the report marks as not reached", async () => {
    const digest = await sentinelDigest(fullProject());

    expect(labelledNumber(digest, /not reached/i)).toBe(3);
  });

  it("reports no unreached checks when every check ran", async () => {
    const digest = await sentinelDigest(cleanProject());

    expect(labelledNumber(digest, /not reached/i) ?? 0).toBe(0);
  });

  it("charts the health grade over the recent runs with their dates", async () => {
    const digest = await sentinelDigest(fullProject());

    const trend = regionLabelled(digest, /trend/i);
    expect(trend, "no region labelled as a trend").not.toBeNull();
    for (const day of ["2026-09-20", "2026-09-26", "2026-10-01"]) {
      expect(mentionsDate(accessibleTextOf(trend as Element), day), `trend lacks the run of ${day}`).toBe(true);
    }
  });
});

describe("the sentinel report selector and stamp", () => {
  it("keeps a keyboard-reachable selector over every report, the newest selected", async () => {
    const page = await renderRoute("/sentinel", await fullProject());

    const selector = page.querySelector("select");
    expect(selector, "no report selector").not.toBeNull();
    const options = Array.from(selector?.options ?? []);
    expect(options).toHaveLength(3);
    const selected = options.find((o) => o.selected) ?? options[0];
    expect(mentionsDate(`${selected?.text} ${selected?.value}`, "2026-10-01")).toBe(true);
    expect(isKeyboardReachable(selector as Element)).toBe(true);
  });

  it("stamps the page with the selected report's timestamp", async () => {
    const page = await renderRoute("/sentinel", await fullProject());

    expect(dataAsOf(page)?.at.toISOString()).toBe(NEWEST.at.toISOString());
  });
});

describe("the sentinel report sections", () => {
  it("opens the critical findings and closes the important, suggested and full-report sections when there is a critical finding", async () => {
    const page = await renderRoute("/sentinel", await fullProject());

    expect(disclosureLabelled(page, /critical/i)?.open).toBe(true);
    expect(disclosureLabelled(page, /important/i)?.open).toBe(false);
    expect(disclosureLabelled(page, /suggested/i)?.open).toBe(false);
    expect(disclosureLabelled(page, /full report/i)?.open).toBe(false);
  });

  it("opens the important findings when there is no critical finding", async () => {
    const root = buildProjectRoot(
      sentinelFamily([
        { at: at("2026-10-01T09:30:00Z"), grade: "B", coherence: "A", critical: 0, important: 2, suggested: 1 }
      ])
    );
    const page = await renderRoute("/sentinel", await root);

    expect(disclosureLabelled(page, /important/i)?.open).toBe(true);
    expect(disclosureLabelled(page, /suggested/i)?.open).toBe(false);
    expect(disclosureLabelled(page, /full report/i)?.open).toBe(false);
  });

  it("keeps the report body inside the closed full-report disclosure", async () => {
    const page = await renderRoute("/sentinel", await fullProject());

    expect(textOf(disclosureLabelled(page, /full report/i)?.content)).toContain(sentinelBodySentence(NEWEST));
  });
});
