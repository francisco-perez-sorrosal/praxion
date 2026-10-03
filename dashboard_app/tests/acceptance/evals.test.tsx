// @vitest-environment jsdom
/**
 * Acceptance: the Evals surface presents the quality-eval run history and a
 * digest of the selected run, keeps the full report one click away, and
 * renders the experiment leaderboard only for a leaderboard-shaped ledger.
 */

import { describe, expect, it, vi } from "vitest";

import {
  dashOnlyRows,
  disclosureLabelled,
  innermostHolding,
  isKeyboardReachable,
  labelledNumber,
  mentionsDate,
  renderRoute,
  textOf,
  useDashboardHarness,
  withoutDisclosure
} from "./drivers/dashboard";
import {
  fullProject,
  fullProjectWithBaselineLedger,
  fullProjectWithoutLedger
} from "./drivers/project-presets";

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...(await import("./drivers/navigation-stub")).navigationOverrides
}));
vi.setConfig({ testTimeout: 60_000 });

useDashboardHarness();

const FULL_REPORT = /full report/i;

/** The page as read before opening the full report. */
async function evalsDigest(): Promise<Element> {
  return withoutDisclosure(await renderRoute("/evals", await fullProject()), FULL_REPORT);
}

describe("the quality-eval run history", () => {
  it.each([
    { target: "git:1111111", day: "2026-09-10", counts: ["1100", "70", "9"], cost: /\$\s?0\.00/ },
    { target: "git:2222222", day: "2026-09-18", counts: ["1150", "66", "5"], cost: /\$\s?0\.00/ },
    { target: "/work/praxion", day: "2026-09-30", counts: ["1187", "64", "3"], cost: /\$\s?0\.43/ }
  ])("lists the run of $day with target, families, counts, cost and a link to its report", async (run) => {
    const page = await evalsDigest();

    const row = Array.from(page.querySelectorAll("tr")).find((tr) => textOf(tr).includes(run.target));
    expect(row, `no history row for ${run.target}`).toBeDefined();
    const text = textOf(row);
    expect(mentionsDate(text, run.day)).toBe(true);
    expect(text).toMatch(/family1/);
    for (const count of run.counts) expect(text.split(/[^0-9]+/)).toContain(count);
    expect(text).toMatch(run.cost);
    expect(row?.querySelector("a[href]")).not.toBeNull();
  });

  it("offers a run selector listing every run, the newest selected", async () => {
    const page = await renderRoute("/evals", await fullProject());

    const selector = Array.from(page.querySelectorAll("select")).find((select) =>
      Array.from(select.options).some((option) => mentionsDate(`${option.text} ${option.value}`, "2026-09-18"))
    );
    expect(selector, "no run selector").toBeDefined();
    const options = Array.from(selector?.options ?? []);
    for (const day of ["2026-09-10", "2026-09-18", "2026-09-30"]) {
      expect(options.some((o) => mentionsDate(`${o.text} ${o.value}`, day)), `no option for ${day}`).toBe(true);
    }
    const selected = options.find((o) => o.selected) ?? options[0];
    expect(mentionsDate(`${selected?.text} ${selected?.value}`, "2026-09-30")).toBe(true);
    expect(isKeyboardReachable(selector as Element)).toBe(true);
  });
});

describe("the digest of the selected run", () => {
  it("shows the pass, warn, fail and skip counts", async () => {
    const digest = await evalsDigest();

    expect(labelledNumber(digest, /pass/i)).toBe(1187);
    expect(labelledNumber(digest, /warn/i)).toBe(64);
    expect(labelledNumber(digest, /fail/i)).toBe(3);
    expect(labelledNumber(digest, /skip/i)).toBe(9);
  });

  it("shows the judged calls, cache hits, token totals and estimated cost", async () => {
    const digest = await evalsDigest();
    const text = textOf(digest);

    expect(labelledNumber(digest, /judged|calls/i)).toBe(271);
    expect(labelledNumber(digest, /cache/i)).toBe(17);
    expect(text).toMatch(/812[,.\s]?3/);
    expect(text).toMatch(/23[,.\s]?[45]/);
    expect(text).toMatch(/\$\s?0\.43/);
  });

  it("groups the failures by check with each group's count and the artifacts it names", async () => {
    const digest = await evalsDigest();

    const bodySections = innermostHolding(digest, ["adr_body_sections", "missing-context.md", "missing-decision.md"]);
    expect(bodySections, "no failure group naming both adr_body_sections artifacts").not.toBeNull();
    expect(textOf(bodySections)).not.toContain("task_artifact_manifest");
    expect(labelledNumber(digest, /adr_body_sections/)).toBe(2);

    const manifest = innermostHolding(digest, ["task_artifact_manifest", "VERIFICATION_REPORT.md"]);
    expect(manifest, "no failure group naming the task_artifact_manifest artifact").not.toBeNull();
    expect(labelledNumber(digest, /task_artifact_manifest/)).toBe(1);
  });

  it("groups the warnings by check with counts only", async () => {
    const digest = await evalsDigest();

    expect(labelledNumber(digest, /affected_reqs_resolvability/)).toBe(4);
    expect(labelledNumber(digest, /adr_staleness/)).toBe(2);
    expect(textOf(digest)).not.toContain("warned-alpha.md");
    expect(textOf(digest)).not.toContain("stale-epsilon.md");
  });

  it("shows the calibration notes", async () => {
    const digest = await evalsDigest();

    expect(textOf(digest)).toContain("unresolvable affected_reqs entries emit WARN by design");
  });

  it("keeps the full report in a disclosure that is closed by default", async () => {
    const page = await renderRoute("/evals", await fullProject());

    const report = disclosureLabelled(page, FULL_REPORT);
    expect(report, "no full-report disclosure").not.toBeNull();
    expect(report?.open).toBe(false);
    expect(textOf(report?.content)).toContain("pass-record-a.md");
    expect(textOf(await evalsDigest())).not.toContain("pass-record-a.md");
  });
});

describe("the experiment leaderboard", () => {
  it("ranks a leaderboard-shaped ledger by its primary metric", async () => {
    const text = textOf(await renderRoute("/evals", await fullProject()));

    expect(text.indexOf("eval-topscore-g3")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("eval-lowscore-g1")).toBeGreaterThan(text.indexOf("eval-topscore-g3"));
  });

  it("renders a ledger of any other shape as a plain table captioned with its file", async () => {
    const page = await renderRoute("/evals", await fullProjectWithBaselineLedger());

    const table = Array.from(page.querySelectorAll("table")).find((t) => textOf(t).includes("Phase zero baseline"));
    expect(table, "the baseline ledger rows are not shown").toBeDefined();
    expect(textOf(table?.querySelector("caption"))).toMatch(/EVAL_LOG\.md/);
  });

  it("names the ledger's file when there is no ledger", async () => {
    const page = await renderRoute("/evals", await fullProjectWithoutLedger());

    expect(textOf(page)).toMatch(/eval_ledger|EVAL_LOG\.md/);
    expect(textOf(page)).toContain("/work/praxion");
  });

  it.each([
    ["a leaderboard-shaped ledger", fullProject],
    ["a ledger of another shape", fullProjectWithBaselineLedger],
    ["no ledger", fullProjectWithoutLedger]
  ])("never renders a row of placeholder dashes with %s", async (_shape, build) => {
    const page = await renderRoute("/evals", await build());

    expect(dashOnlyRows(page).map((row) => row.outerHTML)).toEqual([]);
  });
});
