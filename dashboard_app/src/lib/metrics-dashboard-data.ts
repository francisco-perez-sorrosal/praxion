import type { CollectorEntry } from "@/components/metrics-collector-chips";
import type { MetricToneEntry } from "@/components/metrics-health-strip";
import type { SparklineSeriesMap } from "@/components/metrics-summary-cards";
import type { TrendSeries } from "@/components/viz/trend-chart";
import type { DashboardMetricsData, MetricsSnapshot, SummaryMetricKey } from "@/lib/metrics";
import {
  formatSnapshotLong,
  getMetricTone,
  METRIC_DEFINITIONS,
  SUMMARY_METRICS
} from "@/lib/metrics";

export function toJsonPreview(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function summarizeCollectorDegraded(
  toolAvailability: Record<string, { status: string }>
): string[] {
  const degradedStatuses = new Set(["unavailable", "error", "timeout"]);
  return Object.entries(toolAvailability)
    .filter(([, details]) => degradedStatuses.has(details.status))
    .map(([tool]) => tool);
}

/**
 * Builds a sparkline TrendSeries for a single KPI metric from visible snapshots.
 * Returns null when there are fewer than 2 data points.
 */
export function buildSparklineForMetric(
  metricKey: SummaryMetricKey,
  snapshots: MetricsSnapshot[]
): TrendSeries | null {
  const definition = METRIC_DEFINITIONS[metricKey];
  const points = snapshots.flatMap((snapshot) => {
    const y = snapshot.aggregate[metricKey];
    if (y === null) return [];
    const x = snapshot.aggregate.timestamp ?? snapshot.id;
    return [{ x, y }];
  });

  if (points.length < 2) return null;

  return {
    color: definition.chartColor,
    label: definition.shortLabel,
    points
  };
}

export function buildSparklineSeriesMap(snapshots: MetricsSnapshot[]): SparklineSeriesMap {
  return Object.fromEntries(
    SUMMARY_METRICS.map((key) => [key, buildSparklineForMetric(key, snapshots)])
  ) as SparklineSeriesMap;
}

/**
 * Resolves which snapshot the dashboard should render, falling back through
 * the explicit selection, the canonical latest, and finally the newest row.
 */
export function selectActiveSnapshot(
  data: DashboardMetricsData,
  selectedSnapshotId: string | null
): MetricsSnapshot | null {
  return (
    data.snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    data.latest ??
    data.snapshots.at(-1) ??
    null
  );
}

export type MetricsView = {
  collectorEntries: CollectorEntry[];
  degradedCollectors: string[];
  kpiTones: MetricToneEntry[];
  snapshotOptions: Array<{ id: string; label: string }>;
  sparklineSeriesMap: SparklineSeriesMap;
};

/**
 * Derives every value the dashboard renders from the active snapshot.
 * Pure — no React, no state — so the presentation container is left holding
 * only state wiring, empty-state guards, and layout.
 */
export function deriveMetricsView(
  data: DashboardMetricsData,
  activeSnapshot: MetricsSnapshot,
  visibleSnapshots: MetricsSnapshot[]
): MetricsView {
  const kpiTones: MetricToneEntry[] = SUMMARY_METRICS.map((metricKey) => {
    const delta = activeSnapshot.deltas[metricKey]?.delta ?? null;
    const tone = getMetricTone(metricKey, delta);
    const arrow = tone === "good" ? "↘" : tone === "bad" ? "↗" : "→";
    return { label: METRIC_DEFINITIONS[metricKey].shortLabel, tone, arrow };
  });

  const snapshotOptions = [...data.snapshots].reverse().map((snapshot) => ({
    id: snapshot.id,
    label: `${formatSnapshotLong(snapshot.aggregate.timestamp)} · ${snapshot.fileName}`
  }));

  const collectorEntries: CollectorEntry[] = Object.entries(
    activeSnapshot.toolAvailability
  ).map(([tool, details]) => ({
    tool,
    status: details.status,
    version: details.version,
    reason: details.reason,
    hint: details.hint
  }));

  return {
    collectorEntries,
    degradedCollectors: summarizeCollectorDegraded(activeSnapshot.toolAvailability),
    kpiTones,
    snapshotOptions,
    sparklineSeriesMap: buildSparklineSeriesMap(visibleSnapshots)
  };
}
