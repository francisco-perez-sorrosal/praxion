"use client";

import { useState, useTransition } from "react";

import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import type {
  DashboardMetricsData,
  MetricChartSection,
  MetricKey,
  MetricTone,
  MetricsSnapshot,
  SentruxSnapshot,
  SummaryMetricKey,
  ToolAvailability
} from "@/lib/metrics";
import {
  formatChartAxisValue,
  formatMetricDelta,
  formatMetricValue,
  formatSnapshotLabel,
  formatSnapshotLong,
  getMetricDirectionCopy,
  getMetricTone,
  METRIC_CHART_SECTIONS,
  METRIC_DEFINITIONS,
  sliceSnapshotsUpTo,
  SUMMARY_METRICS
} from "@/lib/metrics";

type TrendPoint = {
  index: number;
  isCurrent: boolean;
  label: string;
  longLabel: string;
  snapshotId: string;
  total: number;
  value: number;
};

type TrendSeries = {
  chartColor: string;
  label: string;
  metricKey: MetricKey;
  points: TrendPoint[];
};

const SENTRUX_CHART_SECTIONS = [
  {
    keys: ["qualitySignal"],
    note: "Sentrux's rolled-up structural quality signal on a 0–10000 scale.",
    title: "Quality signal"
  },
  {
    keys: ["filesKept", "importEdges", "callEdges", "inheritEdges"],
    note: "Indexed files and graph edge counts across import, call, and inheritance relations.",
    title: "Graph size"
  }
] as const;

const SENTRUX_SERIES_META = {
  callEdges: { color: "#b14545", label: "Call edges" },
  filesKept: { color: "#2c7da0", label: "Files indexed" },
  importEdges: { color: "#2f7d4c", label: "Import edges" },
  inheritEdges: { color: "#a97732", label: "Inherit edges" },
  qualitySignal: { color: "#0f766e", label: "Quality (0–10000)" }
} as const;

type SentruxKey = keyof typeof SENTRUX_SERIES_META;

function InfoHint({
  body,
  direction,
  title
}: {
  body: string;
  direction: string;
  title: string;
}) {
  return (
    <span className="info-hint" tabIndex={0}>
      <span className="info-hint__dot">i</span>
      <span className="info-hint__panel">
        <strong>{title}</strong>
        <span>{body}</span>
        <span className="info-hint__direction">{direction}</span>
      </span>
    </span>
  );
}

function toneLabel(tone: MetricTone): string {
  if (tone === "good") {
    return "Improving";
  }

  if (tone === "bad") {
    return "Worsening";
  }

  if (tone === "steady") {
    return "Stable";
  }

  return "Informational";
}

function summarizeCollector(tool: string, details: ToolAvailability): string {
  if (details.status === "available") {
    return details.version ? `version ${details.version}` : "available";
  }

  return details.reason ?? details.hint ?? `${tool} status unavailable`;
}

function toJsonPreview(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function buildMetricSeries(
  snapshots: MetricsSnapshot[],
  metricKey: MetricKey,
  activeSnapshotId: string | null
): TrendSeries {
  return {
    chartColor: METRIC_DEFINITIONS[metricKey].chartColor,
    label: METRIC_DEFINITIONS[metricKey].shortLabel,
    metricKey,
    points: snapshots.flatMap((snapshot, index) => {
      const value = snapshot.aggregate[metricKey];
      if (value === null) {
        return [];
      }

      return [
        {
          index,
          isCurrent: snapshot.id === activeSnapshotId,
          label: formatSnapshotLabel(snapshot.aggregate.timestamp),
          longLabel: formatSnapshotLong(snapshot.aggregate.timestamp),
          snapshotId: snapshot.id,
          total: snapshots.length,
          value
        }
      ];
    })
  };
}

function buildSentruxSeries(
  snapshots: SentruxSnapshot[],
  key: SentruxKey,
  activeSnapshotId: string | null
) {
  return {
    chartColor: SENTRUX_SERIES_META[key].color,
    label: SENTRUX_SERIES_META[key].label,
    points: snapshots.flatMap((snapshot, index) => {
      const value = snapshot[key];
      if (value === null || typeof value !== "number") {
        return [];
      }

      return [
        {
          index,
          isCurrent: snapshot.id === activeSnapshotId,
          label: formatSnapshotLabel(snapshot.timestamp),
          longLabel: formatSnapshotLong(snapshot.timestamp),
          snapshotId: snapshot.id,
          total: snapshots.length,
          value
        }
      ];
    })
  };
}

function TrendChart({
  emptyMessage,
  formatValue,
  series,
  xAxisLabels
}: {
  emptyMessage: string;
  formatValue: (value: number, seriesKey: string) => string;
  series: Array<{
    chartColor: string;
    label: string;
    metricKey: string;
    points: TrendPoint[];
  }>;
  xAxisLabels: string[];
}) {
  const allPoints = series.flatMap((entry) => entry.points.map((point) => point.value));
  if (allPoints.length === 0) {
    return <p className="muted">{emptyMessage}</p>;
  }

  const minValue = Math.min(...allPoints);
  const maxValue = Math.max(...allPoints);
  const spread = maxValue - minValue;
  const pad = spread === 0 ? (maxValue === 0 ? 1 : Math.abs(maxValue) * 0.12) : spread * 0.12;
  const domainMin = minValue - pad;
  const domainMax = maxValue + pad;

  const width = 720;
  const height = 280;
  const padding = { bottom: 36, left: 54, right: 18, top: 18 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const yRatio = domainMax === domainMin ? 0 : chartHeight / (domainMax - domainMin);
  const gridSteps = 4;
  const totalPoints = Math.max(...series.flatMap((entry) => entry.points.map((point) => point.total)));

  const pointX = (index: number) =>
    padding.left + (totalPoints <= 1 ? chartWidth / 2 : (chartWidth * index) / (totalPoints - 1));
  const pointY = (value: number) => padding.top + (domainMax - value) * yRatio;

  const xLabelIndexes = Array.from(new Set([0, Math.floor((totalPoints - 1) / 2), totalPoints - 1])).filter(
    (index) => index >= 0
  );

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {Array.from({ length: gridSteps + 1 }, (_, step) => {
          const ratio = step / gridSteps;
          const value = domainMax - (domainMax - domainMin) * ratio;
          const y = padding.top + chartHeight * ratio;
          return (
            <g key={`grid-${step}`}>
              <line className="trend-chart__grid" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text className="trend-chart__axis" x={padding.left - 10} y={y + 4}>
                {formatChartAxisValue(value)}
              </text>
            </g>
          );
        })}

        {series.map((entry) => {
          const pathData = entry.points
            .map((point, index) => `${index === 0 ? "M" : "L"} ${pointX(point.index)} ${pointY(point.value)}`)
            .join(" ");

          return (
            <g key={entry.metricKey}>
              <path d={pathData} fill="none" stroke={entry.chartColor} strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
              {entry.points.map((point, index) => {
                const cx = pointX(point.index);
                const cy = pointY(point.value);
                return (
                  <circle
                    key={point.snapshotId}
                    className={point.isCurrent ? "trend-chart__point is-current" : "trend-chart__point"}
                    cx={cx}
                    cy={cy}
                    fill={entry.chartColor}
                    r={point.isCurrent ? 5 : 4}
                  >
                    <title>
                      {`${entry.label} • ${point.longLabel}\n${formatValue(point.value, entry.metricKey)}`}
                    </title>
                  </circle>
                );
              })}
            </g>
          );
        })}

        {xLabelIndexes.map((index) => {
          const label = xAxisLabels[index];
          if (!label) {
            return null;
          }

          return (
            <text
              key={`x-${index}`}
              className="trend-chart__axis"
              textAnchor="middle"
              x={pointX(index)}
              y={height - 8}
            >
              {label}
            </text>
          );
        })}
      </svg>

      <ul className="trend-legend">
        {series.map((entry) => (
          <li className="trend-legend__item" key={entry.metricKey}>
            <span
              className="trend-legend__swatch"
              style={{ backgroundColor: entry.chartColor }}
            />
            <span>{entry.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SummaryCard({
  metricKey,
  snapshot
}: {
  metricKey: SummaryMetricKey;
  snapshot: MetricsSnapshot;
}) {
  const definition = METRIC_DEFINITIONS[metricKey];
  const delta = snapshot.deltas[metricKey]?.delta ?? null;
  const tone = getMetricTone(metricKey, delta);
  const deltaLabel = formatMetricDelta(metricKey, delta);

  return (
    <article className={`metric-summary-card tone-${tone} accent-${definition.accent}`}>
      <div className="metric-summary-card__header">
        <div>
          <p>{definition.label}</p>
          <InfoHint
            body={definition.summary}
            direction={getMetricDirectionCopy(metricKey)}
            title={definition.label}
          />
        </div>
        <span className={`metric-summary-card__tone metric-summary-card__tone--${tone}`}>
          {toneLabel(tone)}
        </span>
      </div>
      <p className="metric-summary-card__value">
        {formatMetricValue(metricKey, snapshot.aggregate[metricKey])}
      </p>
      <p className="metric-summary-card__footer">
        {deltaLabel ? `${deltaLabel} vs previous comparable run` : getMetricDirectionCopy(metricKey)}
      </p>
    </article>
  );
}

function MetricTrendSection({
  activeSnapshotId,
  section,
  snapshots
}: {
  activeSnapshotId: string | null;
  section: MetricChartSection;
  snapshots: MetricsSnapshot[];
}) {
  const series = section.metrics.map((metricKey) =>
    buildMetricSeries(snapshots, metricKey, activeSnapshotId)
  );

  return (
    <section className="artifact-card metric-trend-card">
      <div className="metric-trend-card__header">
        <div>
          <h3>{section.title}</h3>
          <p className="muted">{section.note}</p>
        </div>
        <div className="metric-trend-card__hints">
          {section.metrics.map((metricKey) => (
            <InfoHint
              key={metricKey}
              body={METRIC_DEFINITIONS[metricKey].summary}
              direction={getMetricDirectionCopy(metricKey)}
              title={METRIC_DEFINITIONS[metricKey].label}
            />
          ))}
        </div>
      </div>
      <TrendChart
        emptyMessage="Not enough data points yet for this metric group."
        formatValue={(value, seriesKey) => formatMetricValue(seriesKey as MetricKey, value)}
        series={series.map((entry) => ({ ...entry, metricKey: entry.metricKey }))}
        xAxisLabels={snapshots.map((snapshot) => formatSnapshotLabel(snapshot.aggregate.timestamp))}
      />
    </section>
  );
}

function SentruxSection({ data }: { data: DashboardMetricsData["sentrux"] }) {
  if (data.history.length === 0) {
    return null;
  }

  const latest = data.latest ?? data.history.at(-1) ?? null;
  if (latest === null) {
    return null;
  }

  return (
    <section className="section-card metrics-subsection">
      <div className="metrics-subsection__heading">
        <div>
          <h3>Structural quality (sentrux)</h3>
          <p className="muted">
            Side-car structural analysis history from `.ai-state/metrics_reports/`.
          </p>
        </div>
        <div className="artifact-meta">
          {data.latestPath ? <span className="chip">{data.latestPath.split("/").at(-1)}</span> : null}
          <span className="chip">{data.history.length} runs</span>
        </div>
      </div>

      <div className="metrics-summary-grid metrics-summary-grid--sentrux">
        <article className="metric-summary-card tone-good accent-quality">
          <div className="metric-summary-card__header">
            <div>
              <p>Sentrux quality</p>
              <InfoHint
                body="Sentrux's rolled-up structural quality signal over the scanned project graph."
                direction="Higher is better."
                title="Sentrux quality"
              />
            </div>
            <span className="metric-summary-card__tone metric-summary-card__tone--good">
              Advisory
            </span>
          </div>
          <p className="metric-summary-card__value">
            {latest.qualitySignal === null
              ? "—"
              : new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(
                  latest.qualitySignal
                )}
          </p>
          <p className="metric-summary-card__footer">
            Latest structural quality signal.
          </p>
        </article>

        <article
          className={`metric-summary-card ${latest.rulesPass ? "tone-good" : "tone-bad"} accent-risk`}
        >
          <div className="metric-summary-card__header">
            <div>
              <p>Sentrux rules</p>
              <InfoHint
                body="Whether the full sentrux rule set passed on the latest run."
                direction="Passing is better."
                title="Sentrux rules"
              />
            </div>
            <span
              className={`metric-summary-card__tone metric-summary-card__tone--${
                latest.rulesPass ? "good" : "bad"
              }`}
            >
              {latest.rulesPass ? "Passing" : "Failing"}
            </span>
          </div>
          <p className="metric-summary-card__value">
            {latest.rulesPass === null ? "—" : latest.rulesPass ? "Pass" : "Fail"}
          </p>
          <p className="metric-summary-card__footer">
            {latest.rulesChecked === null
              ? "Latest rule count unavailable."
              : `${latest.rulesChecked.toFixed(0)} rules checked.`}
          </p>
        </article>
      </div>

      <div className="grid-two">
        {SENTRUX_CHART_SECTIONS.map((section) => {
          const series = section.keys.map((key) =>
            buildSentruxSeries(data.history, key, latest.id)
          );
          return (
            <section className="artifact-card metric-trend-card" key={section.title}>
              <div className="metric-trend-card__header">
                <div>
                  <h3>{section.title}</h3>
                  <p className="muted">{section.note}</p>
                </div>
              </div>
              <TrendChart
                emptyMessage="Sentrux history will appear once reports accumulate."
                formatValue={(value, seriesKey) =>
                  `${SENTRUX_SERIES_META[seriesKey as SentruxKey].label}: ${formatChartAxisValue(value)}`
                }
                series={series.map((entry, index) => ({
                  chartColor: entry.chartColor,
                  label: entry.label,
                  metricKey: section.keys[index] as string,
                  points: entry.points
                }))}
                xAxisLabels={data.history.map((snapshot) => formatSnapshotLabel(snapshot.timestamp))}
              />
            </section>
          );
        })}
      </div>

      {data.log ? (
        <details className="metrics-raw">
          <summary>Open sentrux history log</summary>
          <MarkdownSurface body={data.log.body} />
        </details>
      ) : null}
    </section>
  );
}

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

  return (
    <section className="page-card metrics-page">
      <header className="page-intro">
        <div>
          <p className="eyebrow">Complexity and health</p>
          <h2>Metrics</h2>
          <p>
            Historical project signals rendered directly from `.ai-state/metrics_reports/`
            with snapshot filtering, semantic coloring, and structural-quality overlays.
          </p>
        </div>
        <aside>
          <span>Latest JSON</span>
          <strong>{data.latest?.fileName ?? "None"}</strong>
          <span>History</span>
          <strong>{data.snapshots.length} snapshots</strong>
        </aside>
      </header>

      {data.snapshots.length === 0 && data.sentrux.history.length === 0 ? (
        <EmptyState
          title="No metrics reports found"
          body="Run `/project-metrics` in the target project to generate the first metrics bundle."
        />
      ) : (
        <>
          {activeSnapshot ? (
            <>
              <section className="section-card metrics-toolbar">
                <div>
                  <h3>Snapshot focus</h3>
                  <p className="muted">
                    Show every trend up to a specific snapshot so regressions and recoveries are easy to read.
                  </p>
                </div>
                <label className="metrics-toolbar__control">
                  <span>View through snapshot</span>
                  <select
                    aria-label="View metrics through snapshot"
                    value={activeSnapshot.id}
                    onChange={(event) => {
                      const nextSnapshotId = event.target.value;
                      startTransition(() => {
                        setSelectedSnapshotId(nextSnapshotId);
                      });
                    }}
                  >
                    {[...data.snapshots].reverse().map((snapshot) => (
                      <option key={snapshot.id} value={snapshot.id}>
                        {`${formatSnapshotLong(snapshot.aggregate.timestamp)} · ${snapshot.fileName}`}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="artifact-meta">
                  <span className="chip">{activeSnapshot.fileName}</span>
                  <span className="chip">{visibleSnapshots.length} points in view</span>
                  {activeSnapshot.aggregate.windowDays !== null ? (
                    <span className="chip">{activeSnapshot.aggregate.windowDays}d window</span>
                  ) : null}
                  {activeSnapshot.coverageStatus ? (
                    <span className="chip">coverage {activeSnapshot.coverageStatus}</span>
                  ) : null}
                  {isPending ? <span className="pill-note">Updating view…</span> : null}
                </div>
              </section>

              <div className="metrics-summary-grid">
                {SUMMARY_METRICS.map((metricKey) => (
                  <SummaryCard key={metricKey} metricKey={metricKey} snapshot={activeSnapshot} />
                ))}
              </div>

              <div className="grid-two">
                {METRIC_CHART_SECTIONS.map((section) => (
                  <MetricTrendSection
                    key={section.title}
                    activeSnapshotId={activeSnapshot.id}
                    section={section}
                    snapshots={visibleSnapshots}
                  />
                ))}
              </div>

              <div className="grid-two">
                <section className="artifact-card">
                  <h3>Hot spots</h3>
                  <p className="muted">
                    Highest-risk files in the selected snapshot. Lower top scores and lower concentration are healthier.
                  </p>
                  {activeSnapshot.hotspots.length === 0 ? (
                    <p className="muted">No hot-spot rows exist in this snapshot.</p>
                  ) : (
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
                        {activeSnapshot.hotspots.slice(0, 10).map((row) => (
                          <tr key={`${row.path}-${row.rank ?? "na"}`}>
                            <td>{row.rank ?? "—"}</td>
                            <td>{row.path}</td>
                            <td>
                              {row.score === null
                                ? "—"
                                : new Intl.NumberFormat("en-US", {
                                    maximumFractionDigits: 0
                                  }).format(row.score)}
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
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>

                <section className="artifact-card">
                  <h3>Collectors</h3>
                  <p className="muted">
                    Per-tool status for the selected snapshot. Missing collectors degrade gracefully but weaken confidence in the affected metrics.
                  </p>
                  {Object.keys(activeSnapshot.toolAvailability).length === 0 ? (
                    <p className="muted">No collector metadata exists in this snapshot.</p>
                  ) : (
                    <ul className="status-list">
                      {Object.entries(activeSnapshot.toolAvailability).map(([tool, details]) => (
                        <li className="status-row status-row--collector" key={tool}>
                          <div>
                            <strong>{tool}</strong>
                            <span className="muted">{summarizeCollector(tool, details)}</span>
                          </div>
                          <span className={`collector-status collector-status--${details.status}`}>
                            {details.status}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>

              <details className="metrics-raw">
                <summary>Open selected snapshot JSON</summary>
                <pre className="code-block">{toJsonPreview(activeSnapshot)}</pre>
              </details>
            </>
          ) : (
            <section className="artifact-card">
              <h3>Metrics snapshots unavailable</h3>
              <p className="muted">
                No canonical metrics snapshots were readable, but other structural signals may still exist below.
              </p>
            </section>
          )}

          <SentruxSection data={data.sentrux} />

          {data.log ? (
            <details className="metrics-raw">
              <summary>Open metrics history log</summary>
              <MarkdownSurface body={data.log.body} />
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
