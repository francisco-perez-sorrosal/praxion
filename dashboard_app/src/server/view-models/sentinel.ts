import "server-only";

import path from "node:path";

import { cache } from "react";

import { normalizeGrade } from "@/lib/tone";
import { fileMtime, isSentinelReport, listDirectory } from "@/server/artifacts/files";
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
  /**
   * ISO instant the file was last written: its modification time, which is
   * absolute. It dates the page's data-as-of stamp and the report's age. Git
   * rewrites it on checkout, so it never says when the run happened. Only when
   * the file cannot be stat'ed is it recovered from the filename.
   */
  fileTimestamp: string | null;
  /**
   * When the producer ran, as the plain wall-clock text `YYYY-MM-DD HH:MM` taken
   * from the filename; `null` when the name carries no valid stamp. A string, not
   * an instant: the stamp has no zone, so the text is the same on server and client.
   */
  runStamp: string | null;
  sections: SentinelSections;
};

export type SentinelData = {
  log: { body: string; path: string } | null;
  logSeries: SentinelLogPoint[];
  reports: SentinelReport[];
};

const FILE_TIMESTAMP_PATTERN =
  /SENTINEL_REPORT_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})/;
const PARTIAL_MARKER = "[PARTIAL]";
const NOT_REACHED_MARKER = /\[not reached\]/i;
const INLINE_CODE_SPAN = /`[^`]*`/g;
const CHECK_ID = /\b[A-Z]{1,3}\d{2}\b/g;

/**
 * The run's wall-clock `YYYY-MM-DD HH:MM` from a report filename; `null` when
 * the name carries no valid stamp. No `Date` in the output and none in the
 * validity check (UTC arithmetic), so no zone can change the text.
 */
export function runStampFromFileName(fileName: string): string | null {
  const match = FILE_TIMESTAMP_PATTERN.exec(fileName);
  if (!match) {
    return null;
  }
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number) as [
    number, number, number, number, number, number
  ];
  const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  const roundTrips =
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day &&
    date.getUTCHours() === hour &&
    date.getUTCMinutes() === minute &&
    date.getUTCSeconds() === second;
  if (!roundTrips) {
    return null;
  }
  const two = (value: number) => String(value).padStart(2, "0");
  return `${String(year).padStart(4, "0")}-${two(month)}-${two(day)} ${two(hour)}:${two(minute)}`;
}

/**
 * ISO instant from a report filename; `null` when the name carries no valid
 * stamp. The sentinel writes local wall-clock stamps (no zone), so the stamp is
 * read as local time, never UTC.
 */
export function reportTimestampFromFileName(fileName: string): string | null {
  const match = FILE_TIMESTAMP_PATTERN.exec(fileName);
  if (!match) {
    return null;
  }
  // The pattern captures exactly six digit groups.
  const [year, month, day, hour, minute, second] = match.slice(1).map(Number) as [
    number, number, number, number, number, number
  ];
  const date = new Date(year, month - 1, day, hour, minute, second);
  // `Date` rolls an impossible stamp over (month 13 -> next year); a real one round-trips.
  const roundTrips =
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day &&
    date.getHours() === hour &&
    date.getMinutes() === minute &&
    date.getSeconds() === second;
  return roundTrips ? date.toISOString() : null;
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

const SENTINEL_LOG_FILE = "SENTINEL_LOG.md";

function reportsRootOf(validatedRoot: string): string {
  return path.join(validatedRoot, ".ai-state", "sentinel_reports");
}

/** Newest-first: filenames sort lexically because the timestamp is fixed-width. */
async function listReportFileNames(reportsRoot: string): Promise<string[]> {
  return (await listDirectory(reportsRoot))
    .filter((entry) => isSentinelReport(entry))
    .sort((left, right) => right.localeCompare(left));
}

async function readLog(validatedRoot: string, reportsRoot: string) {
  return readMarkdown(
    await assertAllowedArtifactPath(validatedRoot, path.join(reportsRoot, SENTINEL_LOG_FILE))
  );
}

async function readSentinelData(projectRoot: string): Promise<SentinelData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = reportsRootOf(validatedRoot);

  const reportFileNames = await listReportFileNames(reportsRoot);
  const log = await readLog(validatedRoot, reportsRoot);
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
          fileTimestamp: (await fileMtime(file.path)) ?? reportTimestampFromFileName(fileName),
          highlight: highlightByFile.get(fileName) ?? null,
          isPartial: isPartialReport(file.body),
          notReachedCount: countNotReached(file.body),
          path: file.path,
          runStamp: runStampFromFileName(fileName),
          sections: extractSections(file.body)
        } satisfies SentinelReport;
      })
    )
  ).filter((report): report is SentinelReport => report !== null);

  return {
    log: log ? { body: log.body, path: log.path } : null,
    logSeries,
    reports
  };
}

export const getSentinelData = cache(readSentinelData);

/** What the sidebar chip needs from the audits: the latest grade letter, or `null` when it has none. */
export type SentinelSignal = { grade: string | null };

/**
 * The latest grade without opening any report: the log row that names the
 * newest report file. A newest report no row names (a run cut short before the
 * log append) is not graded, never the previous run's grade; the log's last row
 * stands in only when no report exists. Same rule as the Overview's digest, at
 * the cost of one directory listing and one log read however many reports exist.
 */
async function readSentinelSignal(projectRoot: string): Promise<SentinelSignal> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = reportsRootOf(validatedRoot);

  const newest = (await listReportFileNames(reportsRoot))[0] ?? null;
  const log = await readLog(validatedRoot, reportsRoot);
  const series = parseSentinelLog(log?.body ?? "").map(withGradeLetters);
  const row =
    newest === null ? series.at(-1) : series.filter((point) => point.reportFile === newest).at(-1);
  return { grade: normalizeGrade(row?.grade) ?? null };
}

export const getSentinelSignal = cache(readSentinelSignal);
