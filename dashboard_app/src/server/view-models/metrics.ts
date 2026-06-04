import "server-only";

import path from "node:path";

import type {
  DashboardMetricsData,
  MetricDelta,
  MetricKey,
  MetricsAggregate,
  MetricsHotspot,
  MetricsLogPoint,
  MetricsSnapshot,
  ReadinessCriterion,
  ReadinessLlm,
  ReadinessManageability,
  ReadinessPillar,
  ReadinessSnapshot,
  ToolAvailability
} from "@/lib/metrics";
import { METRIC_KEYS } from "@/lib/metrics";
import { isMetricsReportJson, listDirectory } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import { readJson, readMarkdown } from "@/server/parsers/content";
import { parseMarkdownTable } from "@/server/parsers/markdown-table";

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
  readiness?: Record<string, unknown>;
  run_metadata?: Record<string, unknown>;
  schema_version?: unknown;
  tool_availability?: Record<string, Record<string, unknown>>;
  trends?: {
    deltas?: Record<string, Record<string, unknown>>;
  };
};

function toStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function toFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Parses the METRICS_LOG.md append-only table into a typed array of log points.
 * Numeric columns that are blank or non-numeric coerce to null.
 * A markdown link in the report_file cell is reduced to its label text.
 */
export function parseMetricsLog(body: string): MetricsLogPoint[] {
  const rows = parseMarkdownTable(body);
  return rows.map((row) => ({
    timestamp: toStringCell(row["timestamp"]),
    commit_sha: toStringCell(row["commit_sha"]),
    window_days: toNumberCell(row["window_days"]),
    sloc_total: toNumberCell(row["sloc_total"]),
    file_count: toNumberCell(row["file_count"]),
    language_count: toNumberCell(row["language_count"]),
    ccn_p95: toNumberCell(row["ccn_p95"]),
    cognitive_p95: toNumberCell(row["cognitive_p95"]),
    cyclic_deps: toNumberCell(row["cyclic_deps"]),
    churn_total_90d: toNumberCell(row["churn_total_90d"]),
    change_entropy_90d: toNumberCell(row["change_entropy_90d"]),
    truck_factor: toNumberCell(row["truck_factor"]),
    hotspot_top_score: toNumberCell(row["hotspot_top_score"]),
    hotspot_gini: toNumberCell(row["hotspot_gini"]),
    coverage_line_pct: toNumberCell(row["coverage_line_pct"]),
    report_file: stripMarkdownLink(row["report_file"])
  }));
}

function toStringCell(cell: string | undefined): string | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  return cell.trim();
}

function toNumberCell(cell: string | undefined): number | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  const parsed = Number(cell.trim());
  return Number.isFinite(parsed) ? parsed : null;
}

/** Converts `[label](url)` to `label`; returns the raw string if not a link. */
function stripMarkdownLink(cell: string | undefined): string | null {
  if (cell === undefined || cell.trim() === "") {
    return null;
  }
  const match = /^\[([^\]]+)\]\([^)]*\)$/.exec(cell.trim());
  return match?.[1] ?? cell.trim();
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

function toBoolean(value: unknown): boolean | null {
  if (value === true || value === false) return value;
  return null;
}

function buildReadinessCriteria(raw: unknown): ReadinessCriterion[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const c = item as Record<string, unknown>;
      const id = toStringValue(c.id);
      const pillar = toStringValue(c.pillar);
      const scope = toStringValue(c.scope);
      if (!id || !pillar || !scope) return null;
      return {
        applicable: c.applicable === true,
        id,
        level: typeof c.level === "number" ? c.level : 1,
        llm: c.llm === true,
        passed: toBoolean(c.passed),
        pillar,
        rationale: toStringValue(c.rationale),
        scope
      } satisfies ReadinessCriterion;
    })
    .filter((item): item is ReadinessCriterion => item !== null);
}

function buildReadinessPillars(raw: unknown): ReadinessPillar[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const p = item as Record<string, unknown>;
      const id = toStringValue(p.id);
      const name = toStringValue(p.name);
      if (!id || !name) return null;
      const levelPass = Array.isArray(p.level_pass)
        ? (p.level_pass as unknown[]).map((v) => v === true)
        : [];
      return {
        denominator: typeof p.denominator === "number" ? p.denominator : 0,
        id,
        level_pass: levelPass,
        name,
        numerator: typeof p.numerator === "number" ? p.numerator : 0,
        pass_pct: typeof p.pass_pct === "number" ? p.pass_pct : 0
      } satisfies ReadinessPillar;
    })
    .filter((item): item is ReadinessPillar => item !== null);
}

function buildReadinessManageability(raw: unknown): ReadinessManageability | null {
  if (!raw || typeof raw !== "object") return null;
  const m = raw as Record<string, unknown>;
  return {
    denominator: typeof m.denominator === "number" ? m.denominator : 0,
    note: toStringValue(m.note),
    numerator: typeof m.numerator === "number" ? m.numerator : 0,
    pass_pct: typeof m.pass_pct === "number" ? m.pass_pct : 0
  };
}

function buildReadinessLlm(raw: unknown): ReadinessLlm {
  const VALID_STATUSES = new Set(["scored", "llm_skipped", "llm_error", "pending"]);
  if (!raw || typeof raw !== "object") {
    return { grounded_on: null, model: null, status: "llm_skipped" };
  }
  const l = raw as Record<string, unknown>;
  const status =
    typeof l.status === "string" && VALID_STATUSES.has(l.status)
      ? (l.status as ReadinessLlm["status"])
      : "llm_skipped";
  return {
    grounded_on: toStringValue(l.grounded_on),
    model: toStringValue(l.model),
    status
  };
}

/**
 * Parses the `readiness` block from a raw metrics report into a typed
 * `ReadinessSnapshot`. Returns null when the block is absent or structurally
 * invalid (missing required numeric fields).
 */
export function buildReadiness(raw: Record<string, unknown> | undefined): ReadinessSnapshot | null {
  if (!raw) return null;
  const data = raw.data;
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  const level = typeof d.level === "number" ? d.level : null;
  const pass_pct = typeof d.pass_pct === "number" ? d.pass_pct : null;
  if (level === null || pass_pct === null) return null;
  const manageability = buildReadinessManageability(d.manageability);
  if (!manageability) return null;
  return {
    criteria: buildReadinessCriteria(d.criteria),
    level,
    llm: buildReadinessLlm(d.llm),
    manageability,
    note: toStringValue(d.note),
    pass_pct,
    pillars: buildReadinessPillars(d.pillars)
  };
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
    readiness: buildReadiness(report.readiness),
    schemaVersion: toStringValue(report.schema_version) ?? aggregate.schemaVersion,
    toolAvailability: buildToolAvailability(report.tool_availability),
    wallClockSeconds: toFiniteNumber(report.run_metadata?.wall_clock_seconds)
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

export async function getMetricsData(projectRoot: string): Promise<DashboardMetricsData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  const reportsRoot = path.join(validatedRoot, ".ai-state", "metrics_reports");
  const entries = await listDirectory(reportsRoot);

  const metricReportPaths = entries
    .filter((entry) => isMetricsReportJson(entry))
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

  const metricsLog = await readMarkdown(metricsLogPath);

  const sortedMetrics = sortMetricSnapshots(metricSnapshots);
  const latestMetrics = sortedMetrics.at(-1) ?? null;
  const logSeries = metricsLog ? parseMetricsLog(metricsLog.body) : [];

  return {
    latest: latestMetrics,
    latestPath: latestMetrics?.path ?? null,
    log: metricsLog ? { body: metricsLog.body, path: metricsLog.path } : null,
    logSeries,
    snapshots: sortedMetrics
  };
}
