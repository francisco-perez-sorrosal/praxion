import "server-only";

import path from "node:path";

import type {
  DashboardMetricsData,
  MetricDelta,
  MetricKey,
  MetricsAggregate,
  MetricsHotspot,
  MetricsSnapshot,
  SentruxSnapshot,
  ToolAvailability
} from "@/lib/metrics";
import { METRIC_KEYS } from "@/lib/metrics";
import { isMetricsReportJson, listDirectory } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readJson, readMarkdown } from "@/server/parsers/content";

const SENTRUX_REPORT_JSON =
  /^SENTRUX_REPORT_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.json$/;

type RawMetricsReport = {
  aggregate?: Record<string, unknown>;
  coverage?: {
    data?: {
      artifact_path?: unknown;
    };
    status?: unknown;
  };
  hotspots?: {
    top_n?: unknown;
  };
  run_metadata?: Record<string, unknown>;
  schema_version?: unknown;
  tool_availability?: Record<string, Record<string, unknown>>;
  trends?: {
    deltas?: Record<string, Record<string, unknown>>;
  };
};

type RawSentruxReport = {
  commit_sha?: unknown;
  exit_code?: unknown;
  graph?: Record<string, unknown>;
  quality_signal?: unknown;
  rules?: Record<string, unknown>;
  timestamp?: unknown;
};

function toStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function toFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function isSentruxReportJson(filename: string): boolean {
  return SENTRUX_REPORT_JSON.test(filename);
}

function parseMarkdownTable(body: string): Array<Record<string, string>> {
  const tableLines = body
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|"));
  if (tableLines.length < 2) {
    return [];
  }

  const splitRow = (row: string): string[] => row.split("|").slice(1, -1).map((cell) => cell.trim());
  const headers = splitRow(tableLines[0] ?? "");
  const rows = tableLines
    .slice(1)
    .filter((line) => !/^\|\s*[-:]+\s*(\|\s*[-:]+\s*)+\|?$/.test(line));

  return rows.map((row) => {
    const cells = splitRow(row);
    const paddedCells = cells.length >= headers.length ? cells : cells.concat(Array(headers.length - cells.length).fill(""));
    return headers.reduce<Record<string, string>>((record, header, index) => {
      record[header] = paddedCells[index] ?? "";
      return record;
    }, {});
  });
}

function buildAggregate(raw: Record<string, unknown> | undefined): MetricsAggregate {
  const aggregate = raw ?? {};
  return {
    ccn_p95: toFiniteNumber(aggregate.ccn_p95),
    change_entropy_90d: toFiniteNumber(aggregate.change_entropy_90d),
    churn_total_90d: toFiniteNumber(aggregate.churn_total_90d),
    cognitive_p95: toFiniteNumber(aggregate.cognitive_p95),
    commitSha: toStringValue(aggregate.commit_sha),
    coverage_line_pct: toFiniteNumber(aggregate.coverage_line_pct),
    cyclic_deps: toFiniteNumber(aggregate.cyclic_deps),
    file_count: toFiniteNumber(aggregate.file_count),
    hotspot_gini: toFiniteNumber(aggregate.hotspot_gini),
    hotspot_top_score: toFiniteNumber(aggregate.hotspot_top_score),
    language_count: toFiniteNumber(aggregate.language_count),
    schemaVersion: toStringValue(aggregate.schema_version),
    sloc_total: toFiniteNumber(aggregate.sloc_total),
    timestamp: toStringValue(aggregate.timestamp),
    truck_factor: toFiniteNumber(aggregate.truck_factor),
    windowDays: toFiniteNumber(aggregate.window_days)
  };
}

function buildMetricDeltas(raw: Record<string, Record<string, unknown>> | undefined) {
  return METRIC_KEYS.reduce<Partial<Record<MetricKey, MetricDelta>>>((deltas, metricKey) => {
    const entry = raw?.[metricKey];
    if (!entry) {
      return deltas;
    }

    deltas[metricKey] = {
      current: toFiniteNumber(entry.current),
      delta: toFiniteNumber(entry.delta),
      deltaPct: toFiniteNumber(entry.delta_pct),
      prior: toFiniteNumber(entry.prior)
    };
    return deltas;
  }, {});
}

function buildHotspots(raw: unknown): MetricsHotspot[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .map((row) => {
      if (!row || typeof row !== "object") {
        return null;
      }

      const hotspot = row as Record<string, unknown>;
      return {
        churn90d: toFiniteNumber(hotspot.churn_90d),
        complexity: toFiniteNumber(hotspot.complexity),
        path: toStringValue(hotspot.path) ?? "Unknown",
        rank: toFiniteNumber(hotspot.rank),
        score: toFiniteNumber(hotspot.hotspot_score)
      } satisfies MetricsHotspot;
    })
    .filter((row): row is MetricsHotspot => row !== null);
}

function buildToolAvailability(raw: Record<string, Record<string, unknown>> | undefined) {
  return Object.entries(raw ?? {}).reduce<Record<string, ToolAvailability>>((tools, [tool, details]) => {
    tools[tool] = {
      details:
        details.details && typeof details.details === "object"
          ? (details.details as Record<string, unknown>)
          : {},
      hint: toStringValue(details.hint),
      reason: toStringValue(details.reason),
      status: toStringValue(details.status) ?? "unknown",
      version: toStringValue(details.version)
    };
    return tools;
  }, {});
}

function buildMetricsSnapshot(reportPath: string, report: RawMetricsReport): MetricsSnapshot | null {
  const aggregate = buildAggregate(report.aggregate);
  if (aggregate.timestamp === null && aggregate.sloc_total === null && aggregate.file_count === null) {
    return null;
  }

  return {
    aggregate,
    coverageArtifactPath: toStringValue(report.coverage?.data?.artifact_path),
    coverageStatus: toStringValue(report.coverage?.status),
    deltas: buildMetricDeltas(report.trends?.deltas),
    fileName: path.basename(reportPath),
    hotspots: buildHotspots(report.hotspots?.top_n),
    id: path.basename(reportPath),
    path: reportPath,
    schemaVersion: toStringValue(report.schema_version) ?? aggregate.schemaVersion,
    toolAvailability: buildToolAvailability(report.tool_availability),
    wallClockSeconds: toFiniteNumber(report.run_metadata?.wall_clock_seconds)
  };
}

function buildSentruxSnapshotFromRow(
  row: Record<string, string>,
  fileName: string | null
): SentruxSnapshot {
  return {
    callEdges: toFiniteNumber(Number(row.call_edges)),
    commitSha: row.commit_sha || null,
    exitCode: toFiniteNumber(Number(row.exit_code)),
    fileName,
    filesKept: toFiniteNumber(Number(row.files_kept)),
    id: row.timestamp || fileName || row.commit_sha || "sentrux-history-row",
    importEdges: toFiniteNumber(Number(row.import_edges)),
    inheritEdges: toFiniteNumber(Number(row.inherit_edges)),
    qualitySignal: toFiniteNumber(Number(row.quality_signal)),
    rulesChecked: toFiniteNumber(Number(row.rules_checked)),
    rulesPass:
      row.rules_pass === "true" ? true : row.rules_pass === "false" ? false : null,
    timestamp: row.timestamp || null
  };
}

function buildSentruxSnapshotFromReport(
  reportPath: string,
  report: RawSentruxReport
): SentruxSnapshot | null {
  if (!report || typeof report !== "object") {
    return null;
  }

  return {
    callEdges: toFiniteNumber(report.graph?.call_edges),
    commitSha: toStringValue(report.commit_sha),
    exitCode: toFiniteNumber(report.exit_code),
    fileName: path.basename(reportPath),
    filesKept: toFiniteNumber(report.graph?.files_kept),
    id: path.basename(reportPath),
    importEdges: toFiniteNumber(report.graph?.import_edges),
    inheritEdges: toFiniteNumber(report.graph?.inherit_edges),
    qualitySignal: toFiniteNumber(report.quality_signal),
    rulesChecked: toFiniteNumber(report.rules?.checked),
    rulesPass: toBoolean(report.rules?.passed),
    timestamp: toStringValue(report.timestamp)
  };
}

function sortMetricSnapshots(snapshots: MetricsSnapshot[]): MetricsSnapshot[] {
  return [...snapshots].sort((left, right) => {
    if (left.aggregate.timestamp && right.aggregate.timestamp) {
      return left.aggregate.timestamp.localeCompare(right.aggregate.timestamp);
    }

    return left.fileName.localeCompare(right.fileName);
  });
}

function sortSentruxSnapshots(snapshots: SentruxSnapshot[]): SentruxSnapshot[] {
  return [...snapshots].sort((left, right) => {
    if (left.timestamp && right.timestamp) {
      return left.timestamp.localeCompare(right.timestamp);
    }

    return (left.fileName ?? "").localeCompare(right.fileName ?? "");
  });
}

export async function getMetricsData(projectRoot: string): Promise<DashboardMetricsData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = path.join(validatedRoot, ".ai-state", "metrics_reports");
  const entries = await listDirectory(reportsRoot);

  const metricReportPaths = entries
    .filter((entry) => isMetricsReportJson(entry))
    .sort((left, right) => left.localeCompare(right))
    .map((entry) => path.join(reportsRoot, entry));

  const sentruxReportPaths = entries
    .filter((entry) => isSentruxReportJson(entry))
    .sort((left, right) => left.localeCompare(right))
    .map((entry) => path.join(reportsRoot, entry));

  const metricSnapshots = (
    await Promise.all(
      metricReportPaths.map(async (reportPath) => {
        const allowedPath = await assertAllowedArtifactPath(validatedRoot, reportPath);
        const report = await readJson<RawMetricsReport>(allowedPath);
        return report ? buildMetricsSnapshot(allowedPath, report) : null;
      })
    )
  ).filter((snapshot): snapshot is MetricsSnapshot => snapshot !== null);

  const metricsLogPath = await assertAllowedArtifactPath(
    validatedRoot,
    path.join(reportsRoot, "METRICS_LOG.md")
  );
  const sentruxLogPath = await assertAllowedArtifactPath(
    validatedRoot,
    path.join(reportsRoot, "SENTRUX_HISTORY.md")
  );

  const [metricsLog, sentruxLog] = await Promise.all([
    readMarkdown(metricsLogPath),
    readMarkdown(sentruxLogPath)
  ]);

  const sentruxHistoryFromLog =
    sentruxLog?.body === undefined
      ? []
      : parseMarkdownTable(sentruxLog.body).map((row) => buildSentruxSnapshotFromRow(row, null));

  const sentruxHistoryFromReports = (
    await Promise.all(
      sentruxReportPaths.map(async (reportPath) => {
        const allowedPath = await assertAllowedArtifactPath(validatedRoot, reportPath);
        const report = await readJson<RawSentruxReport>(allowedPath);
        return report ? buildSentruxSnapshotFromReport(allowedPath, report) : null;
      })
    )
  ).filter((snapshot): snapshot is SentruxSnapshot => snapshot !== null);

  const sentruxHistory =
    sentruxHistoryFromLog.length > 0 ? sentruxHistoryFromLog : sentruxHistoryFromReports;
  const sortedMetrics = sortMetricSnapshots(metricSnapshots);
  const sortedSentrux = sortSentruxSnapshots(sentruxHistory);
  const latestMetrics = sortedMetrics.at(-1) ?? null;
  const latestSentrux = sortedSentrux.at(-1) ?? null;

  return {
    latest: latestMetrics,
    latestPath: latestMetrics?.path ?? null,
    log: metricsLog ? { body: metricsLog.body, path: metricsLog.path } : null,
    sentrux: {
      history: sortedSentrux,
      latest: latestSentrux,
      latestPath:
        sentruxReportPaths.length > 0
          ? await assertAllowedArtifactPath(validatedRoot, sentruxReportPaths.at(-1) as string)
          : null,
      log: sentruxLog ? { body: sentruxLog.body, path: sentruxLog.path } : null
    },
    snapshots: sortedMetrics
  };
}
