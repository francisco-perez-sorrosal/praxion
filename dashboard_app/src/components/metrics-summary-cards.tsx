"use client";

import { Sparkline } from "@/components/viz/sparkline";
import type {
  MetricTone,
  MetricsSnapshot,
  SummaryMetricKey,
  ToolAvailability
} from "@/lib/metrics";
import {
  formatMetricDelta,
  formatMetricValue,
  getMetricDirectionCopy,
  getMetricTone,
  METRIC_DEFINITIONS,
  SUMMARY_METRICS
} from "@/lib/metrics";
import type { TrendSeries } from "@/components/viz/trend-chart";

// ─── Helpers ──────────────────────────────────────────────────────────────────

export function toneLabel(tone: MetricTone): string {
  if (tone === "good") return "Improving";
  if (tone === "bad") return "Worsening";
  if (tone === "steady") return "Stable";
  return "Informational";
}

function toneArrow(tone: MetricTone): string {
  if (tone === "good") return "↘";
  if (tone === "bad") return "↗";
  return "→";
}

function toneCssVar(tone: MetricTone): string {
  if (tone === "good") return "var(--color-success-text)";
  if (tone === "bad") return "var(--color-danger-text)";
  if (tone === "steady") return "var(--color-warn-text)";
  return "var(--color-info-text)";
}

export function summarizeCollector(tool: string, details: ToolAvailability): string {
  if (details.status === "available") {
    return details.version ? `version ${details.version}` : "available";
  }
  return details.reason ?? details.hint ?? `${tool} status unavailable`;
}

// ─── SummaryCard ─────────────────────────────────────────────────────────────

function SummaryCard({
  metricKey,
  snapshot,
  sparklineSeries,
  hasMultipleSnapshots
}: {
  metricKey: SummaryMetricKey;
  snapshot: MetricsSnapshot;
  sparklineSeries: TrendSeries | null;
  hasMultipleSnapshots: boolean;
}) {
  const definition = METRIC_DEFINITIONS[metricKey];
  const delta = snapshot.deltas[metricKey]?.delta ?? null;
  const tone = getMetricTone(metricKey, delta);
  const deltaLabel = hasMultipleSnapshots ? formatMetricDelta(metricKey, delta) : null;
  const accentColor = toneCssVar(tone);

  return (
    <article
      className={`kpi-tile tone-${tone} accent-${definition.accent}`}
      style={{ "--kpi-accent-color": accentColor } as React.CSSProperties}
    >
      <div className="kpi-tile__header">
        <p className="kpi-tile__label">{definition.label}</p>
        <span className={`kpi-tile__tone kpi-tile__tone--${tone}`}>
          {toneArrow(tone)} {toneLabel(tone)}
        </span>
      </div>

      <p className="kpi-tile__value">
        {formatMetricValue(metricKey, snapshot.aggregate[metricKey])}
      </p>

      {hasMultipleSnapshots && sparklineSeries && sparklineSeries.points.length >= 2 ? (
        <div className="kpi-tile__sparkline">
          <Sparkline
            series={[sparklineSeries]}
            height={28}
            color={accentColor}
          />
        </div>
      ) : null}

      <p className="kpi-tile__footer">
        {deltaLabel
          ? `${deltaLabel} vs previous`
          : hasMultipleSnapshots
            ? getMetricDirectionCopy(metricKey)
            : "Baseline — no prior run to compare"}
      </p>
    </article>
  );
}

// ─── MetricsSummaryCards ──────────────────────────────────────────────────────

export type SparklineSeriesMap = Partial<Record<SummaryMetricKey, TrendSeries>>;

export function MetricsSummaryCards({
  snapshot,
  sparklineSeriesMap,
  hasMultipleSnapshots
}: {
  snapshot: MetricsSnapshot;
  sparklineSeriesMap: SparklineSeriesMap;
  hasMultipleSnapshots: boolean;
}) {
  return (
    <div className="metrics-summary-grid">
      {SUMMARY_METRICS.map((metricKey) => (
        <SummaryCard
          key={metricKey}
          metricKey={metricKey}
          snapshot={snapshot}
          sparklineSeries={sparklineSeriesMap[metricKey] ?? null}
          hasMultipleSnapshots={hasMultipleSnapshots}
        />
      ))}
    </div>
  );
}
