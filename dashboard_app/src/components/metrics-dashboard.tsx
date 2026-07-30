"use client";

import { useState, useTransition } from "react";

import { EmptyState } from "@/components/empty-state";
import { CollectorChips } from "@/components/metrics-collector-chips";
import { HealthStrip } from "@/components/metrics-health-strip";
import { HotSpotsTable } from "@/components/metrics-hotspots-table";
import { MetricsRawData } from "@/components/metrics-raw-data";
import { MetricsSummaryCards } from "@/components/metrics-summary-cards";
import { MetricsTrends } from "@/components/metrics-trends";
import { AgentReadinessSection } from "@/components/readiness-section";
import type { DashboardMetricsData } from "@/lib/metrics";
import { sliceLogSeriesUpTo, sliceSnapshotsUpTo } from "@/lib/metrics";
import { deriveMetricsView, selectActiveSnapshot } from "@/lib/metrics-dashboard-data";

export function MetricsDashboard({ data }: { data: DashboardMetricsData }) {
  const defaultSnapshotId = data.latest?.id ?? data.snapshots.at(-1)?.id ?? null;
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(defaultSnapshotId);
  const [isPending, startTransition] = useTransition();

  const activeSnapshot = selectActiveSnapshot(data, selectedSnapshotId);

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

  const {
    collectorEntries,
    degradedCollectors,
    kpiTones,
    snapshotOptions,
    sparklineSeriesMap
  } = deriveMetricsView(data, activeSnapshot, visibleSnapshots);

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

      {/* Agent Readiness */}
      <section className="artifact-card">
        <h3>Agent Readiness</h3>
        <p className="muted">
          Factory-pillar readiness score for this snapshot. Run{" "}
          <code>/project-metrics</code> to update.
        </p>
        <AgentReadinessSection readiness={activeSnapshot.readiness} />
      </section>

      {/* Consolidated raw data — ONE disclosure */}
      <MetricsRawData
        activeSnapshot={activeSnapshot}
        hasCollectors={collectorEntries.length > 0}
        log={data.log}
      />
    </section>
  );
}
