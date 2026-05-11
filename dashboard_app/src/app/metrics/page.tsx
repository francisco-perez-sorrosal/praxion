import { MetricsDashboard } from "@/components/metrics-dashboard";
import { getConfig } from "@/lib/config";
import { getMetricsData } from "@/server/view-models/metrics";

export default async function MetricsPage() {
  const cfg = getConfig();
  const metrics = await getMetricsData(cfg.projectRoot);

  return <MetricsDashboard data={metrics} />;
}
