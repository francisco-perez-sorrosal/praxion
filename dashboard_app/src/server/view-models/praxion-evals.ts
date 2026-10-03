import "server-only";

import path from "node:path";

import type { PraxionEvalReport, PraxionEvalReportRef, PraxionEvalRun } from "@/lib/praxion-evals";
import { evalReportStamp, parsePraxionEvalLog, parsePraxionEvalReport } from "@/lib/praxion-evals";
import { listDirectory, newestMtime, readText } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";

export type PraxionEvalsData = {
  /** The newest of the log's and the selected report's modification times; `null` when neither was read. */
  dataAsOf: string | null;
  /** Report files on disk, newest first, listed without being read. */
  reports: PraxionEvalReportRef[];
  /** Log rows, oldest first. */
  runs: PraxionEvalRun[];
  /** The one report that was read and parsed: the requested run, else the newest. */
  selected: PraxionEvalReport | null;
};

const REPORTS_DIRECTORY = [".ai-state", "praxion_eval_reports"] as const;
const LOG_FILE_NAME = "PRAXION_EVAL_LOG.md";

function toReportRefs(reportsRoot: string, fileNames: string[]): PraxionEvalReportRef[] {
  return fileNames
    .flatMap((fileName): PraxionEvalReportRef[] => {
      const timestamp = evalReportStamp(fileName);
      return timestamp === null ? [] : [{ fileName, path: path.join(reportsRoot, fileName), timestamp }];
    })
    .sort((left, right) => right.timestamp.localeCompare(left.timestamp));
}

/**
 * Reads the quality-eval log and lists the reports; only the selected report
 * (`selectedStamp` when it names a report, else the newest) is read and parsed.
 * An absent or unreadable log or report yields empty data, never an error.
 */
export async function getPraxionEvalsData(
  projectRoot: string,
  selectedStamp?: string | null
): Promise<PraxionEvalsData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = path.join(validatedRoot, ...REPORTS_DIRECTORY);

  const logPath = await assertAllowedArtifactPath(validatedRoot, path.join(reportsRoot, LOG_FILE_NAME));
  const logText = await readText(logPath);
  const runs = logText === null ? [] : parsePraxionEvalLog(logText);

  const reports = toReportRefs(reportsRoot, await listDirectory(reportsRoot));
  const chosen = reports.find((report) => report.timestamp === selectedStamp) ?? reports[0] ?? null;
  const reportText = chosen === null ? null : await readText(await assertAllowedArtifactPath(validatedRoot, chosen.path));
  const selected =
    chosen === null || reportText === null
      ? null
      : parsePraxionEvalReport(reportText, chosen.fileName, chosen.path);

  const dataAsOf = await newestMtime([
    ...(logText === null ? [] : [logPath]),
    ...(selected === null ? [] : [selected.path])
  ]);

  return { dataAsOf, reports, runs, selected };
}
