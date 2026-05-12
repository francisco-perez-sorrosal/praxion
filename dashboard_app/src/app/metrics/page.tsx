import { MetricsDashboard } from "@/components/metrics-dashboard";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getMetricsData } from "@/server/view-models/metrics";

export default async function MetricsPage() {
  const cfg = getConfig();
  const metrics = await getMetricsData(cfg.projectRoot);

  // Use the latest snapshot's timestamp as "data as of".
  const dataAsOf = metrics.latest?.aggregate.timestamp ?? null;

  const sourcesContent = (
    <dl className="sources-list">
      <dt>Reports</dt>
      <dd><code>.ai-state/metrics_reports/METRICS_REPORT_*.json</code></dd>
      <dt>History log</dt>
      <dd><code>.ai-state/metrics_reports/METRICS_LOG.md</code></dd>
      <dt>Snapshots found</dt>
      <dd>{metrics.snapshots.length}</dd>
    </dl>
  );

  return (
    <PageShell
      title="Metrics"
      dataAsOf={dataAsOf}
      sourcesContent={sourcesContent}
    >
      <MetricsDashboard data={metrics} />
    </PageShell>
  );
}
