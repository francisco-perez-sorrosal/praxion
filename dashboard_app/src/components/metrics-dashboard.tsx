"use client";

import { useState, useTransition } from "react";

import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { MetricsSummaryCards } from "@/components/metrics-summary-cards";
import type { SparklineSeriesMap } from "@/components/metrics-summary-cards";
import { MetricsTrends } from "@/components/metrics-trends";
import type { TrendSeries } from "@/components/viz/trend-chart";
import { healthSummary } from "@/lib/health-tone";
import type { DashboardMetricsData, MetricTone, SummaryMetricKey } from "@/lib/metrics";
import {
  formatSnapshotLong,
  getMetricTone,
  METRIC_DEFINITIONS,
  sliceLogSeriesUpTo,
  sliceSnapshotsUpTo,
  SUMMARY_METRICS
} from "@/lib/metrics";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toJsonPreview(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function summarizeCollectorDegraded(
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
function buildSparklineForMetric(
  metricKey: SummaryMetricKey,
  snapshots: import("@/lib/metrics").MetricsSnapshot[]
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

function buildSparklineSeriesMap(
  snapshots: import("@/lib/metrics").MetricsSnapshot[]
): SparklineSeriesMap {
  return Object.fromEntries(
    SUMMARY_METRICS.map((key) => [key, buildSparklineForMetric(key, snapshots)])
  ) as SparklineSeriesMap;
}

// ─── PerMetricArrows ──────────────────────────────────────────────────────────

function PerMetricArrows({
  tones
}: {
  tones: Array<{ label: string; tone: MetricTone; arrow: string }>;
}) {
  if (tones.length === 0) return null;

  return (
    <ul className="health-strip__arrows">
      {tones.map(({ label, tone, arrow }) => (
        <li key={label} className={`health-strip__arrow health-strip__arrow--${tone}`}>
          {label} {arrow}
        </li>
      ))}
    </ul>
  );
}

// ─── HealthStrip ──────────────────────────────────────────────────────────────

type HealthStripProps = {
  activeSnapshotId: string;
  degradedCollectors: string[];
  hasMultipleSnapshots: boolean;
  isPending: boolean;
  onSnapshotChange: (id: string) => void;
  snapshotOptions: Array<{ id: string; label: string }>;
  tones: Array<{ label: string; tone: MetricTone; arrow: string }>;
};

function HealthStrip({
  activeSnapshotId,
  degradedCollectors,
  hasMultipleSnapshots,
  isPending,
  onSnapshotChange,
  snapshotOptions,
  tones
}: HealthStripProps) {
  const tonesToAggregate: MetricTone[] = tones.map((t) => t.tone);
  const summary = healthSummary(tonesToAggregate, {
    degradedCollectors,
    isBaseline: !hasMultipleSnapshots
  });

  return (
    <section className="metrics-health-strip" aria-label="Health summary">
      <div className="health-strip__headline">
        <strong className="health-strip__label">
          Health: {summary.label}
        </strong>
        {summary.degradedNote && (
          <span className="health-strip__degraded-note">{summary.degradedNote}</span>
        )}
      </div>

      {hasMultipleSnapshots && (
        <PerMetricArrows tones={tones} />
      )}

      <div className="health-strip__controls">
        <label className="health-strip__selector">
          <span className="health-strip__selector-label">Viewing through</span>
          <select
            aria-label="View metrics through snapshot"
            value={activeSnapshotId}
            onChange={(event) => onSnapshotChange(event.target.value)}
          >
            {snapshotOptions.map(({ id, label }) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>

        {/* Compare toggle — disabled stub; snapshot comparison is a planned follow-up. Kept for layout completeness. */}
        <button
          className="health-strip__compare-btn"
          type="button"
          disabled
          title="Snapshot comparison — coming soon"
          aria-disabled="true"
        >
          ⇄ compare
        </button>

        {isPending && (
          <span className="health-strip__pending" aria-live="polite">
            Updating…
          </span>
        )}
      </div>
    </section>
  );
}

// ─── HotSpotsTable ────────────────────────────────────────────────────────────

type Hotspot = {
  churn90d: number | null;
  complexity: number | null;
  path: string;
  rank: number | null;
  score: number | null;
};

function HotSpotsTable({ hotspots }: { hotspots: Hotspot[] }) {
  const [showAll, setShowAll] = useState(false);

  if (hotspots.length === 0) {
    return <p className="muted">No hot-spot rows exist in this snapshot.</p>;
  }

  const maxScore = hotspots.reduce((max, h) => Math.max(max, h.score ?? 0), 0);
  const visibleRows = showAll ? hotspots : hotspots.slice(0, 10);
  const hiddenCount = hotspots.length - 10;

  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Path</th>
            <th>Score</th>
            <th>Churn 90d</th>
            <th>Complexity</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row) => {
            const scorePct =
              row.score !== null && maxScore > 0
                ? Math.round((row.score / maxScore) * 100)
                : 0;

            return (
              <tr key={`${row.path}-${row.rank ?? "na"}`}>
                <td>{row.rank ?? "—"}</td>
                <td>{row.path}</td>
                <td>
                  <span
                    className="hotspot-score-bar"
                    style={{ "--hotspot-score-pct": `${scorePct}%` } as React.CSSProperties}
                  >
                    {row.score === null
                      ? "—"
                      : new Intl.NumberFormat("en-US", {
                          maximumFractionDigits: 0
                        }).format(row.score)}
                  </span>
                </td>
                <td>
                  {row.churn90d === null
                    ? "—"
                    : new Intl.NumberFormat("en-US", {
                        maximumFractionDigits: 0
                      }).format(row.churn90d)}
                </td>
                <td>{row.complexity === null ? "—" : row.complexity.toFixed(0)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {!showAll && hiddenCount > 0 && (
        <button
          className="hotspot-show-all-btn"
          type="button"
          onClick={() => setShowAll(true)}
        >
          Show all {hotspots.length} ▸
        </button>
      )}
    </>
  );
}

// ─── CollectorChips ───────────────────────────────────────────────────────────

type CollectorEntry = {
  tool: string;
  status: string;
  version: string | null;
  reason: string | null;
  hint: string | null;
};

function collectorIcon(status: string): string {
  if (status === "available") return "✓";
  if (status === "unavailable" || status === "error" || status === "timeout") return "✕";
  return "⚠";
}

function CollectorChips({ collectors }: { collectors: CollectorEntry[] }) {
  if (collectors.length === 0) {
    return <p className="muted">No collector metadata exists in this snapshot.</p>;
  }

  return (
    <ul className="collector-chips">
      {collectors.map(({ tool, status, version, reason, hint }) => {
        const isDegraded =
          status === "unavailable" || status === "error" || status === "timeout";
        const detail = version ?? reason ?? hint ?? status;
        return (
          <li
            key={tool}
            className={`collector-chip${isDegraded ? " collector-chip--degraded" : ""}`}
          >
            <span className="collector-chip__icon" aria-hidden="true">
              {collectorIcon(status)}
            </span>
            <span className="collector-chip__name">{tool}</span>
            <span className="collector-chip__detail">{detail}</span>
          </li>
        );
      })}
    </ul>
  );
}

// ─── MetricsDashboard ─────────────────────────────────────────────────────────

export function MetricsDashboard({ data }: { data: DashboardMetricsData }) {
  const defaultSnapshotId = data.latest?.id ?? data.snapshots.at(-1)?.id ?? null;
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(defaultSnapshotId);
  const [isPending, startTransition] = useTransition();

  const activeSnapshot =
    data.snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    data.latest ??
    data.snapshots.at(-1) ??
    null;

  const visibleSnapshots = sliceSnapshotsUpTo(data.snapshots, activeSnapshot?.id ?? null);
  const visibleLogSeries = sliceLogSeriesUpTo(
    data.logSeries,
    activeSnapshot?.aggregate.timestamp ?? null
  );
  const hasMultipleSnapshots = data.snapshots.length >= 2;

  // ─── Empty state ────────────────────────────────────────────────────────────
  if (data.snapshots.length === 0) {
    return (
      <section className="page-card metrics-page">
        <EmptyState
          title="No metrics reports found"
          body="Run `/project-metrics` in the target project to generate the first metrics bundle."
          producerPath=".ai-state/metrics_reports/"
        />
      </section>
    );
  }

  if (!activeSnapshot) {
    return (
      <section className="page-card metrics-page">
        <section className="artifact-card">
          <h3>Metrics snapshots unavailable</h3>
          <p className="muted">No canonical metrics snapshots were readable.</p>
        </section>
      </section>
    );
  }

  // ─── KPI tones ──────────────────────────────────────────────────────────────
  const kpiTones: Array<{ label: string; tone: MetricTone; arrow: string }> = SUMMARY_METRICS.map(
    (metricKey) => {
      const delta = activeSnapshot.deltas[metricKey]?.delta ?? null;
      const tone = getMetricTone(metricKey, delta);
      const arrow = tone === "good" ? "↘" : tone === "bad" ? "↗" : "→";
      return { label: METRIC_DEFINITIONS[metricKey].shortLabel, tone, arrow };
    }
  );

  const degradedCollectors = summarizeCollectorDegraded(activeSnapshot.toolAvailability);

  // ─── Sparkline series ───────────────────────────────────────────────────────
  const sparklineSeriesMap = buildSparklineSeriesMap(visibleSnapshots);

  // ─── Snapshot selector options ──────────────────────────────────────────────
  const snapshotOptions = [...data.snapshots].reverse().map((snapshot) => ({
    id: snapshot.id,
    label: `${formatSnapshotLong(snapshot.aggregate.timestamp)} · ${snapshot.fileName}`
  }));

  // ─── Collector entries ──────────────────────────────────────────────────────
  const collectorEntries: CollectorEntry[] = Object.entries(
    activeSnapshot.toolAvailability
  ).map(([tool, details]) => ({
    tool,
    status: details.status,
    version: details.version,
    reason: details.reason,
    hint: details.hint
  }));

  // ─── Render ─────────────────────────────────────────────────────────────────
  return (
    <section className="page-card metrics-page">
      {/* Health strip — above the fold */}
      <HealthStrip
        activeSnapshotId={activeSnapshot.id}
        degradedCollectors={degradedCollectors}
        hasMultipleSnapshots={hasMultipleSnapshots}
        isPending={isPending}
        onSnapshotChange={(id) => startTransition(() => setSelectedSnapshotId(id))}
        snapshotOptions={snapshotOptions}
        tones={kpiTones}
      />

      {/* KPI tiles */}
      <MetricsSummaryCards
        snapshot={activeSnapshot}
        sparklineSeriesMap={sparklineSeriesMap}
        hasMultipleSnapshots={hasMultipleSnapshots}
      />

      {/* Trend charts (suppressed when only 1 snapshot) */}
      <MetricsTrends
        activeSnapshot={activeSnapshot}
        logSeries={visibleLogSeries}
        snapshots={visibleSnapshots}
      />

      {/* Hot spots */}
      {activeSnapshot.hotspots.length > 0 && (
        <section className="artifact-card">
          <h3>Hot spots</h3>
          <p className="muted">
            Highest-risk files in the selected snapshot. Lower top scores and lower
            concentration are healthier.
          </p>
          <HotSpotsTable hotspots={activeSnapshot.hotspots} />
        </section>
      )}

      {/* Collectors */}
      {collectorEntries.length > 0 && (
        <section className="artifact-card metrics-collectors">
          <h3>Collectors</h3>
          <p className="muted">
            Per-tool status for the selected snapshot. Missing collectors degrade
            gracefully but weaken confidence in the affected metrics.
          </p>
          <CollectorChips collectors={collectorEntries} />
        </section>
      )}

      {/* Consolidated raw data — ONE disclosure */}
      <details className="metrics-raw">
        <summary>Raw data ▸</summary>
        <div className="metrics-raw__body">
          <h4 className="metrics-raw__section-heading">Selected snapshot JSON</h4>
          <pre className="code-block">{toJsonPreview(activeSnapshot)}</pre>

          <h4 className="metrics-raw__section-heading">Metrics history log</h4>
          {data.log ? (
            <MarkdownSurface body={data.log.body} />
          ) : (
            <p className="muted">History log not available.</p>
          )}

          {activeSnapshot.hotspots.length === 0 && (
            <p className="muted metrics-raw__note">No hot-spot rows in this snapshot.</p>
          )}
          {collectorEntries.length === 0 && (
            <p className="muted metrics-raw__note">No collector metadata in this snapshot.</p>
          )}
        </div>
      </details>
    </section>
  );
}
