import { DefaultShell } from "@/components/shells";
import { formatMetricValue } from "@/lib/metrics";
import type { MetricKey } from "@/lib/metrics";
import type { ManifestSurface } from "@/server/types";

type RendererProps = {
  readonly body: string;
  readonly surface?: ManifestSurface;
};

type MetricsAggregateJson = Partial<Record<MetricKey, number>>;

type MetricsReportJson = {
  readonly aggregate: MetricsAggregateJson;
  readonly schema_version?: string;
  readonly run_metadata?: { readonly window_days?: number };
};

const SUMMARY_FIELDS: ReadonlyArray<{ metric: MetricKey; label: string }> = [
  { metric: "coverage_line_pct", label: "Coverage" },
  { metric: "ccn_p95", label: "CCN p95" },
  { metric: "cognitive_p95", label: "Cognitive p95" },
  { metric: "file_count", label: "Files" },
  { metric: "cyclic_deps", label: "Cyclic deps" }
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseMetricsReport(body: string): MetricsReportJson | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }
  if (!isRecord(parsed) || !isRecord(parsed.aggregate)) {
    return null;
  }
  return parsed as unknown as MetricsReportJson;
}

/**
 * Thin Pathway-B preview of a METRICS_REPORT_*.json snapshot: a handful of
 * aggregate stats plus a link to the full /metrics dashboard. Never re-reads
 * the ~440 KB of per-file detail (hotspots, lizard, scc, ...) — that stays
 * the /metrics route's job.
 */
export function MetricsViewRenderer({ body }: RendererProps) {
  const report = parseMetricsReport(body);
  if (report === null) {
    return <DefaultShell body={body} />;
  }

  const { aggregate, schema_version: schemaVersion, run_metadata: runMetadata } = report;

  return (
    <div className="renderer-metrics-summary">
      <p className="renderer-metrics-summary-meta">
        Metrics snapshot
        {schemaVersion !== undefined ? ` · schema ${schemaVersion}` : ""}
        {runMetadata?.window_days !== undefined
          ? ` · ${runMetadata.window_days}-day window`
          : ""}
      </p>
      <dl className="renderer-metrics-summary-stats">
        {SUMMARY_FIELDS.map(({ metric, label }) => (
          <div key={metric} className="renderer-metrics-summary-stat">
            <dt>{label}</dt>
            <dd>{formatMetricValue(metric, aggregate[metric])}</dd>
          </div>
        ))}
      </dl>
      <a href="/metrics">Open the full metrics dashboard</a>
    </div>
  );
}
