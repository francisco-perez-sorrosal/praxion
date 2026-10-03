// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvalLedgerSection } from "@/components/eval-leaderboard";
import { CheckGroups } from "@/components/praxion-evals/check-groups";
import { ReportDigest } from "@/components/praxion-evals/report-digest";
import { RunHistory, RunSelector } from "@/components/praxion-evals/run-history";
import type { EvalLedger } from "@/lib/evals";
import { parsePraxionEvalLog, parsePraxionEvalReport } from "@/lib/praxion-evals";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const FIXTURES = path.join(__dirname, "..", "fixtures", "praxion-evals");
const REPORT_FILE = "PRAXION_EVAL_REPORT_2026-10-03T01-22-07Z.md";

const fixture = (name: string): string => readFileSync(path.join(FIXTURES, name), "utf8");
const report = parsePraxionEvalReport(fixture(REPORT_FILE), REPORT_FILE);
const runs = parsePraxionEvalLog(fixture("PRAXION_EVAL_LOG.md"));

afterEach(() => {
  cleanup();
  push.mockClear();
});

/** Table rows whose data cells are all empty or dashes. */
function placeholderRows(scope: HTMLElement): Element[] {
  return Array.from(scope.querySelectorAll("tr")).filter((row) => {
    const cells = Array.from(row.querySelectorAll("td"));
    return cells.length > 0 && cells.every((cell) => /^[\s—–-]*$/.test(cell.textContent ?? ""));
  });
}

describe("ReportDigest", () => {
  it("shows each verdict count as a tile whose label carries its tone", () => {
    const { container } = render(<ReportDigest report={report} />);

    const tones = Array.from(container.querySelectorAll(".stat-tile__label [data-tone]")).map((el) => [
      el.textContent,
      el.getAttribute("data-tone")
    ]);
    expect(tones).toEqual([
      ["PASS", "good"],
      ["WARN", "warn"],
      ["FAIL", "bad"],
      ["SKIP", "neutral"]
    ]);
    expect(container.textContent).toContain("1,316");
  });

  it("lists the failing checks with their counts and the artifacts they name", () => {
    render(<ReportDigest report={report} />);

    const failures = screen.getByText("Failures by check").closest("section") as HTMLElement;
    const surgical = within(failures).getByText("bc_stay_surgical").closest("li") as HTMLElement;
    expect(within(surgical).getByText("×2")).toBeTruthy();
    expect(surgical.querySelectorAll("li")).toHaveLength(2);
    expect(within(failures).getByText("scenario_lightweight_fix_llm")).toBeTruthy();
  });

  it("collapses warnings, calibration notes and the full report, naming only counts for warnings", () => {
    const { container } = render(<ReportDigest report={report} />);

    const closed = Array.from(container.querySelectorAll("details")).map((el) => [
      el.querySelector("summary")?.textContent,
      el.open
    ]);
    expect(closed.map(([title]) => title)).toEqual([
      expect.stringContaining("Warnings by check"),
      expect.stringContaining("Calibration notes"),
      expect.stringContaining("Full report")
    ]);
    expect(closed.every(([, open]) => open === false)).toBe(true);
    const warnings = container.querySelector("details") as HTMLElement;
    expect(warnings.querySelectorAll("code")).toHaveLength(3);
  });

  it("renders no placeholder row anywhere, including the full report table", () => {
    const { container } = render(<ReportDigest report={report} />);

    expect(placeholderRows(container)).toEqual([]);
    expect(container.querySelectorAll(".eval-report-table tbody tr")).toHaveLength(report.checks.length);
  });

  it("leaves out a fact the report does not state instead of showing a dash", () => {
    const older = parsePraxionEvalReport(fixture("PRAXION_EVAL_REPORT_2026-09-07T21-32-00Z.md"), "PRAXION_EVAL_REPORT_2026-09-07T21-32-00Z.md");

    const { container } = render(<ReportDigest report={older} />);

    const labels = Array.from(container.querySelectorAll(".eval-facts dt")).map((el) => el.textContent);
    expect(labels).toEqual(["Target", "Estimated cost"]);
    expect(container.textContent).not.toContain("Calibration notes");
  });

  it("falls back to the report text when it carries no check table", () => {
    const bare = parsePraxionEvalReport("# Report\n\nNothing ran this time.\n", REPORT_FILE);

    const { container } = render(<ReportDigest report={bare} />);

    expect(container.textContent).toContain("Nothing ran this time.");
    expect(container.textContent).toContain("states no summary line");
  });

  it("says so when no check failed", () => {
    const clean = { ...report, failGroups: [] };

    render(<ReportDigest report={clean} />);

    expect(screen.getByText("No check failed in this run.")).toBeTruthy();
  });
});

describe("CheckGroups", () => {
  it("shows artifacts only when asked to", () => {
    const groups = [{ check: "adr_x", count: 2, artifacts: ["a.md", "b.md"] }];

    const { container, rerender } = render(<CheckGroups groups={groups} showArtifacts tone="bad" />);
    expect(container.querySelectorAll("li li")).toHaveLength(2);

    rerender(<CheckGroups groups={groups} showArtifacts={false} tone="warn" />);
    expect(container.querySelectorAll("li li")).toHaveLength(0);
    expect(container.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("warn");
  });
});

describe("RunHistory and RunSelector", () => {
  const stamps = runs.map((run) => run.timestamp);

  it("lists runs newest first and links only the runs whose report exists", () => {
    const withReportStamps = [stamps[0] as string, stamps.at(-1) as string];

    const { container } = render(
      <RunHistory runs={runs} reportStamps={withReportStamps} selectedStamp={stamps.at(-1) ?? null} />
    );

    const rows = Array.from(container.querySelectorAll("tbody tr"));
    expect(rows).toHaveLength(runs.length);
    expect(rows[0]?.textContent).toContain("2026-10-03 01:22 UTC");
    expect(rows.filter((row) => row.querySelector("a")).length).toBe(2);
    expect(rows[0]?.getAttribute("aria-current")).toBe("true");
    expect(placeholderRows(container)).toEqual([]);
  });

  it("navigates to the chosen run when the selector changes", () => {
    render(<RunSelector reportStamps={["2026-10-03T01-22-07Z", "2026-09-07T21-32-00Z"]} selectedStamp="2026-10-03T01-22-07Z" />);

    const select = screen.getByLabelText("Select quality-eval run by date") as HTMLSelectElement;
    expect(select.value).toBe("2026-10-03T01-22-07Z");
    fireEvent.change(select, { target: { value: "2026-09-07T21-32-00Z" } });

    expect(push).toHaveBeenCalledWith("/evals?run=2026-09-07T21-32-00Z");
  });
});

describe("EvalLedgerSection", () => {
  const leaderboard: EvalLedger = {
    shape: "leaderboard",
    path: ".ai-state/eval_ledger/EVAL_LOG.md",
    rows: [
      {
        run_id: "eval-top",
        task: "t",
        generation: 3,
        primary_metric: 0.64,
        held_out_delta: -0.01,
        model_id: "m",
        prompt_hash: "p",
        dataset_sha: "d",
        cost_usd: 1,
        git_sha: "g",
        store_uri: "s"
      }
    ]
  };

  it("renders the ranked table for a leaderboard-shaped ledger", () => {
    const { container } = render(<EvalLedgerSection ledger={leaderboard} />);

    expect(screen.getByText("Experiment leaderboard")).toBeTruthy();
    expect(container.querySelector(".eval-table td.eval-table__rank")?.textContent).toBe("1");
    expect(container.textContent).toContain("eval-top");
  });

  it("renders any other shape as a captioned plain table without a leaderboard", () => {
    const ledger: EvalLedger = {
      shape: "table",
      path: ".ai-state/eval_ledger/EVAL_LOG.md",
      table: { headers: ["date", "purpose"], rows: [["2026-09-07", "Phase zero baseline"]] }
    };

    const { container } = render(<EvalLedgerSection ledger={ledger} />);

    expect(container.querySelector("caption")?.textContent).toBe(".ai-state/eval_ledger/EVAL_LOG.md");
    expect(container.textContent).toContain("Phase zero baseline");
    expect(screen.queryByText("Experiment leaderboard")).toBeNull();
  });

  it("names the ledger file in an empty state when there is no ledger", () => {
    const { container } = render(<EvalLedgerSection ledger={{ shape: "absent" }} />);

    expect(container.querySelector(".empty-state__producer-path")?.textContent).toBe(".ai-state/eval_ledger/EVAL_LOG.md");
    expect(container.querySelector("table")).toBeNull();
  });

  it("shows the empty state, not a table of dashes, for a leaderboard with no rows", () => {
    const { container } = render(<EvalLedgerSection ledger={{ ...leaderboard, rows: [] }} />);

    expect(container.querySelector("table")).toBeNull();
    expect(container.textContent).toContain("No eval runs recorded");
  });
});
