"use client";

import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Sparkline } from "@/components/viz/sparkline";
import { formatEvalCost, formatEvalTimestamp } from "@/lib/evals";
import type { PraxionEvalRun } from "@/lib/praxion-evals";

const EVALS_ROUTE = "/evals";
const MISSING_COUNT = "—";

const runHref = (stamp: string): Route => `${EVALS_ROUTE}?run=${encodeURIComponent(stamp)}` as Route;

const formatCount = (value: number | null): string => (value === null ? MISSING_COUNT : String(value));

type RunSelectorProps = {
  /** Stamps of the reports on disk, newest first. */
  reportStamps: readonly string[];
  selectedStamp: string | null;
};

/** Native select that shows another run's digest by navigating to `?run=<stamp>`. */
export function RunSelector({ reportStamps, selectedStamp }: RunSelectorProps) {
  const router = useRouter();
  return (
    <label className="eval-run-select">
      <span className="eval-run-select__label">Run</span>
      <select
        aria-label="Select quality-eval run by date"
        onChange={(event) => router.push(runHref(event.target.value))}
        value={selectedStamp ?? ""}
      >
        {reportStamps.map((stamp) => (
          <option key={stamp} value={stamp}>
            {formatEvalTimestamp(stamp)}
          </option>
        ))}
      </select>
    </label>
  );
}

type RunHistoryProps = {
  runs: readonly PraxionEvalRun[];
  /** Runs whose report file exists; only these link to a digest. */
  reportStamps: readonly string[];
  selectedStamp: string | null;
};

/**
 * The run log: a failure-count trend over the runs, then one table row per run,
 * newest first. Returns a fragment so the table is a direct child of the card
 * body that also holds the digest: a wrapper around the table alone would be
 * the innermost element holding the "Pass / Warn / Fail" header words and the
 * run counts, and would read as the digest's own count.
 */
export function RunHistory({ runs, reportStamps, selectedStamp }: RunHistoryProps) {
  const withReport = new Set(reportStamps);
  return (
    <>
      <FailTrend runs={runs} />
      <table className="eval-history-table">
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Target</th>
            <th scope="col">Families</th>
            <th scope="col">Pass</th>
            <th scope="col">Warn</th>
            <th scope="col">Fail</th>
            <th scope="col">Cost</th>
          </tr>
        </thead>
        <tbody>
          {[...runs].reverse().map((run) => (
            <tr aria-current={run.timestamp === selectedStamp ? "true" : undefined} key={run.timestamp}>
              <th scope="row">
                {withReport.has(run.timestamp) ? (
                  <Link href={runHref(run.timestamp)}>{formatEvalTimestamp(run.timestamp)}</Link>
                ) : (
                  formatEvalTimestamp(run.timestamp)
                )}
              </th>
              <td className="eval-history-table__target" title={run.target}>
                <code>{run.target}</code>
              </td>
              <td>{run.families}</td>
              <td>{formatCount(run.pass)}</td>
              <td>{formatCount(run.warn)}</td>
              <td>{formatCount(run.fail)}</td>
              <td>{formatEvalCost(run.costUsd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function FailTrend({ runs }: { runs: readonly PraxionEvalRun[] }) {
  if (runs.length < 2) {
    return null;
  }
  const points = runs.map((run) => ({ x: run.timestamp, y: run.fail }));
  const spoken = runs.map((run) => `${formatEvalTimestamp(run.timestamp)}: ${formatCount(run.fail)}`).join("; ");
  return (
    <div aria-label={`FAIL count per run, oldest to newest. ${spoken}`} className="eval-trend" role="img">
      <span aria-hidden="true" className="eval-trend__label">
        FAIL per run
      </span>
      <Sparkline series={[{ label: "FAIL", color: "var(--color-danger-text)", points }]} />
    </div>
  );
}
