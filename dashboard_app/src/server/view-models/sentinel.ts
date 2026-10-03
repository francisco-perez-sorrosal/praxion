import "server-only";

import path from "node:path";

import { normalizeGrade } from "@/lib/tone";
import { isSentinelReport, listDirectory } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readMarkdown } from "@/server/parsers/content";
import { extractSections, parseSentinelLog } from "@/server/sentinel/extract-sections";
import type { SentinelLogPoint, SentinelSections } from "@/server/sentinel/extract-sections";

export type { SentinelLogPoint, SentinelSections };

/**
 * One fully-loaded sentinel report: its body, parsed finding sections, and the
 * matching `SENTINEL_LOG.md` row (grade + finding counts) when one exists.
 */
export type SentinelReport = {
  body: string;
  data: Record<string, unknown>;
  fileName: string;
  highlight: SentinelLogPoint | null;
  /** The title carries `[PARTIAL]`: the run was cut short and the grade is provisional. */
  isPartial: boolean;
  /** Distinct checks the report marks `[not reached]`. */
  notReachedCount: number;
  path: string;
  /** ISO instant recovered from the `SENTINEL_REPORT_<date>_<time>.md` filename (UTC). */
  reportTimestamp: string | null;
  sections: SentinelSections;
};

export type SentinelData = {
  log: { body: string } | null;
  logSeries: SentinelLogPoint[];
  reports: SentinelReport[];
};

const FILE_TIMESTAMP_PATTERN =
  /SENTINEL_REPORT_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/;
const PARTIAL_MARKER = "[PARTIAL]";
const NOT_REACHED_MARKER = /\[not reached\]/i;
const INLINE_CODE_SPAN = /`[^`]*`/g;
const CHECK_ID = /\b[A-Z]{1,3}\d{2}\b/g;

/** ISO instant from a report filename; `null` when the name carries no valid stamp. */
export function reportTimestampFromFileName(fileName: string): string | null {
  const match = FILE_TIMESTAMP_PATTERN.exec(fileName);
  if (!match) {
    return null;
  }
  const [, year, month, day, hour, minute, second] = match;
  const date = new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Whether the report's title line (first `# ` heading) carries the partial mark. */
export function isPartialReport(body: string): boolean {
  const title = body.split("\n").find((line) => /^#\s/.test(line));
  return title?.includes(PARTIAL_MARKER) ?? false;
}

function checkIdsIn(text: string): string[] {
  return text.match(CHECK_ID) ?? [];
}

/**
 * Counts the distinct checks a report marks `[not reached]`.
 *
 * A marker quoted in backticks is prose about the marker, not a marker. On a
 * marker line the checks are the identifiers written before the marker (list
 * items and table rows both lead with their ids; text after the marker is
 * commentary that may cite other checks); ids after it are used only when none
 * precede it, and a marker naming no id counts as one unnamed check.
 */
export function countNotReached(body: string): number {
  const unreached = new Set<string>();
  body.split("\n").forEach((line, index) => {
    const prose = line.replace(INLINE_CODE_SPAN, "");
    const marker = NOT_REACHED_MARKER.exec(prose);
    if (marker === null) {
      return;
    }
    const before = checkIdsIn(prose.slice(0, marker.index));
    const named = before.length > 0 ? before : checkIdsIn(prose);
    if (named.length === 0) {
      unreached.add(`unnamed-line-${index}`);
    }
    named.forEach((id) => unreached.add(id));
  });
  return unreached.size;
}

/**
 * A partial run's log row writes its grade as `C [PARTIAL]`; every consumer
 * wants the letter. Cells that are not a grade pass through unchanged.
 */
function withGradeLetters(point: SentinelLogPoint): SentinelLogPoint {
  const letter = (cell: string | null): string | null =>
    cell === null ? null : (normalizeGrade(cell.split(/\s+/)[0]) ?? cell);
  return { ...point, coherence: letter(point.coherence), grade: letter(point.grade) };
}

export async function getSentinelData(projectRoot: string): Promise<SentinelData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = path.join(validatedRoot, ".ai-state", "sentinel_reports");

  // Newest-first: filenames sort lexically because the timestamp is fixed-width.
  const reportFileNames = (await listDirectory(reportsRoot))
    .filter((entry) => isSentinelReport(entry))
    .sort((left, right) => right.localeCompare(left));

  const log = await readMarkdown(
    await assertAllowedArtifactPath(validatedRoot, path.join(reportsRoot, "SENTINEL_LOG.md"))
  );
  const logSeries = parseSentinelLog(log?.body ?? "").map(withGradeLetters);
  const highlightByFile = new Map<string, SentinelLogPoint>();
  for (const point of logSeries) {
    if (point.reportFile !== null) {
      highlightByFile.set(point.reportFile, point);
    }
  }

  const reports = (
    await Promise.all(
      reportFileNames.map(async (fileName) => {
        const file = await readMarkdown(
          await assertAllowedArtifactPath(validatedRoot, path.join(reportsRoot, fileName))
        );
        if (file === null) {
          return null;
        }
        return {
          body: file.body,
          data: file.data,
          fileName,
          highlight: highlightByFile.get(fileName) ?? null,
          isPartial: isPartialReport(file.body),
          notReachedCount: countNotReached(file.body),
          path: file.path,
          reportTimestamp: reportTimestampFromFileName(fileName),
          sections: extractSections(file.body)
        } satisfies SentinelReport;
      })
    )
  ).filter((report): report is SentinelReport => report !== null);

  return {
    log: log ? { body: log.body } : null,
    logSeries,
    reports
  };
}
