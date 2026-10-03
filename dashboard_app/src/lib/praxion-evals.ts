/**
 * Types and parsers for the quality-eval artifacts `/eval-praxion` writes:
 * `PRAXION_EVAL_LOG.md` (one row per run) and `PRAXION_EVAL_REPORT_<stamp>.md`
 * (one report per run). Parsing is tolerant: a missing header line is `null`
 * for that fact, a malformed table row is skipped, an absent `## Check Results`
 * heading is no checks. Type-only imports from client components are safe;
 * the parsers themselves run on the server.
 */
import { toNumberCell, toStringCell } from "@/lib/evals";
import { parseMarkdownTable } from "@/server/parsers/markdown-table";

export type PraxionEvalRun = {
  /** The `<date>T<hh>-<mm>-<ss>Z` stamp; also the `?run=` selector value. */
  timestamp: string;
  target: string;
  authRoute: string;
  families: string;
  pass: number | null;
  warn: number | null;
  fail: number | null;
  costUsd: number | null;
  reportFile: string | null;
};

export type PraxionEvalCheck = {
  check: string;
  kind: string;
  verdict: "PASS" | "WARN" | "FAIL" | "SKIP" | string;
  artifact: string;
  score: string;
  findings: string;
};

export type PraxionEvalCheckGroup = { check: string; count: number; artifacts: string[] };

export type PraxionEvalReport = {
  fileName: string;
  path: string;
  timestamp: string;
  target: string | null;
  summary: { pass: number; warn: number; fail: number; skip: number } | null;
  judgedCalls: number | null;
  cacheHits: number | null;
  tokensIn: number | null;
  tokensOut: number | null;
  costUsd: number | null;
  checks: PraxionEvalCheck[];
  failGroups: PraxionEvalCheckGroup[];
  warnGroups: PraxionEvalCheckGroup[];
  calibrationNotes: string | null;
  body: string;
};

/** A report file on disk, listed without being read. */
export type PraxionEvalReportRef = { fileName: string; path: string; timestamp: string };

const REPORT_FILE_PATTERN = /^PRAXION_EVAL_REPORT_(.+)\.md$/;
const MARKDOWN_LINK = /^\[[^\]]*\]\(([^)]+)\)$/;
const CHECK_RESULTS_HEADING = "## Check Results";
const CALIBRATION_HEADING = "## Calibration Notes";

/** The stamp inside a `PRAXION_EVAL_REPORT_<stamp>.md` filename; `null` for any other name. */
export function evalReportStamp(fileName: string): string | null {
  return REPORT_FILE_PATTERN.exec(fileName)?.[1] ?? null;
}

function toCostCell(cell: string | undefined): number | null {
  return toNumberCell(cell?.replace(/^\$/, ""));
}

function toReportFileCell(cell: string | undefined): string | null {
  const text = toStringCell(cell);
  return text === null ? null : (MARKDOWN_LINK.exec(text)?.[1] ?? text);
}

/** Runs from the nine-column log table, oldest first (the log is append-order, not strictly time-order). */
export function parsePraxionEvalLog(body: string): PraxionEvalRun[] {
  return parseMarkdownTable(body)
    .flatMap((row): PraxionEvalRun[] => {
      const timestamp = toStringCell(row["Timestamp"]);
      if (timestamp === null) {
        return [];
      }
      return [
        {
          timestamp,
          target: row["Target"] ?? "",
          authRoute: row["Auth route"] ?? "",
          families: row["Families"] ?? "",
          pass: toNumberCell(row["Pass"]),
          warn: toNumberCell(row["Warn"]),
          fail: toNumberCell(row["Fail"]),
          costUsd: toCostCell(row["Cost (USD)"]),
          reportFile: toReportFileCell(row["Report"])
        }
      ];
    })
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp));
}

/** The text of a `**Label**: value` header line; `null` when the line is absent. */
function headerLine(body: string, label: string): string | null {
  const match = new RegExp(`^\\*\\*${label}\\*\\*:\\s*(.+)$`, "m").exec(body);
  return match?.[1]?.trim() ?? null;
}

/** The integer written before `word` in a header line (`362 cache hits` → 362). */
function countBefore(line: string | null, word: string): number | null {
  const match = line === null ? null : new RegExp(`([\\d,]+)\\s*${word}`, "i").exec(line);
  return match?.[1] === undefined ? null : Number(match[1].replace(/,/g, ""));
}

function parseSummary(line: string | null): PraxionEvalReport["summary"] {
  const pass = countBefore(line, "PASS");
  const warn = countBefore(line, "WARN");
  const fail = countBefore(line, "FAIL");
  if (pass === null || warn === null || fail === null) {
    return null;
  }
  return { pass, warn, fail, skip: countBefore(line, "SKIP") ?? 0 };
}

function parseTarget(line: string | null): string | null {
  if (line === null) {
    return null;
  }
  return /`([^`]+)`/.exec(line)?.[1] ?? line;
}

/** The lines under `heading` up to the next `## ` heading (or the end); `null` when the heading is absent. */
function sectionUnder(body: string, heading: string): string | null {
  const lines = body.split("\n");
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start === -1) {
    return null;
  }
  const rest = lines.slice(start + 1);
  const end = rest.findIndex((line) => line.startsWith("## "));
  return (end === -1 ? rest : rest.slice(0, end)).join("\n");
}

function parseChecks(body: string): PraxionEvalCheck[] {
  const section = sectionUnder(body, CHECK_RESULTS_HEADING);
  if (section === null) {
    return [];
  }
  return parseMarkdownTable(section).flatMap((row): PraxionEvalCheck[] => {
    const check = toStringCell(row["Check"]);
    const verdict = toStringCell(row["Verdict"]);
    if (check === null || verdict === null) {
      return [];
    }
    return [
      {
        check,
        kind: row["Kind"] ?? "",
        verdict: verdict.toUpperCase(),
        artifact: row["Artifact"] ?? "",
        score: row["Score"] ?? "",
        findings: row["Findings"] ?? ""
      }
    ];
  });
}

/**
 * Groups the checks with the given verdict by check name: count per group and
 * the distinct artifacts they name, largest group first, ties by name.
 */
export function groupByCheck(checks: readonly PraxionEvalCheck[], verdict: string): PraxionEvalCheckGroup[] {
  const groups = new Map<string, { count: number; artifacts: Set<string> }>();
  for (const entry of checks) {
    if (entry.verdict !== verdict.toUpperCase()) {
      continue;
    }
    const group = groups.get(entry.check) ?? { count: 0, artifacts: new Set<string>() };
    group.count += 1;
    if (entry.artifact !== "") {
      group.artifacts.add(entry.artifact);
    }
    groups.set(entry.check, group);
  }
  return Array.from(groups, ([check, group]) => ({
    check,
    count: group.count,
    artifacts: Array.from(group.artifacts)
  })).sort((left, right) => right.count - left.count || left.check.localeCompare(right.check));
}

export function parsePraxionEvalReport(body: string, fileName: string, path = fileName): PraxionEvalReport {
  const checks = parseChecks(body);
  const tokens = headerLine(body, "Tokens");
  const judged = headerLine(body, "Judged");
  const calibration = sectionUnder(body, CALIBRATION_HEADING)?.trim() ?? "";
  return {
    fileName,
    path,
    timestamp: evalReportStamp(fileName) ?? "",
    target: parseTarget(headerLine(body, "Target")),
    summary: parseSummary(headerLine(body, "Summary")),
    judgedCalls: countBefore(judged, "calls"),
    cacheHits: countBefore(judged, "cache hits"),
    tokensIn: countBefore(tokens, "in"),
    tokensOut: countBefore(tokens, "out"),
    costUsd: toCostCell(headerLine(body, "Estimated cost")?.replace(/\s*USD$/i, "")),
    checks,
    failGroups: groupByCheck(checks, "FAIL"),
    warnGroups: groupByCheck(checks, "WARN"),
    calibrationNotes: calibration === "" ? null : calibration,
    body
  };
}
