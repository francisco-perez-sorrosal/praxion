export const SUMMARY_METRICS = [
  "sloc_total",
  "file_count",
  "ccn_p95",
  "cognitive_p95",
  "cyclic_deps",
  "churn_total_90d",
  "truck_factor",
  "hotspot_top_score",
  "hotspot_gini",
  "coverage_line_pct"
] as const;

export const METRIC_KEYS = [
  "sloc_total",
  "file_count",
  "language_count",
  "ccn_p95",
  "cognitive_p95",
  "cyclic_deps",
  "churn_total_90d",
  "change_entropy_90d",
  "truck_factor",
  "hotspot_top_score",
  "hotspot_gini",
  "coverage_line_pct"
] as const;

export type MetricKey = (typeof METRIC_KEYS)[number];
export type SummaryMetricKey = (typeof SUMMARY_METRICS)[number];

export type MetricFormat = "int" | "float2" | "pct" | "score";
export type MetricDirection = "higher" | "lower" | "neutral";
export type MetricTone = "good" | "bad" | "steady" | "neutral";

export type MetricDefinition = {
  accent: string;
  chartColor: string;
  direction: MetricDirection;
  format: MetricFormat;
  label: string;
  shortLabel: string;
  summary: string;
};

export type MetricDelta = {
  current: number | null;
  delta: number | null;
  deltaPct: number | null;
  prior: number | null;
};

export type MetricsAggregate = Record<MetricKey, number | null> & {
  commitSha: string | null;
  schemaVersion: string | null;
  timestamp: string | null;
  windowDays: number | null;
};

export type ToolAvailability = {
  details: Record<string, unknown>;
  hint: string | null;
  reason: string | null;
  status: string;
  version: string | null;
};

export type MetricsHotspot = {
  churn90d: number | null;
  complexity: number | null;
  path: string;
  rank: number | null;
  score: number | null;
};

export type MetricsSnapshot = {
  aggregate: MetricsAggregate;
  coverageArtifactPath: string | null;
  coverageStatus: string | null;
  deltas: Partial<Record<MetricKey, MetricDelta>>;
  fileName: string;
  id: string;
  path: string;
  hotspots: MetricsHotspot[];
  schemaVersion: string | null;
  toolAvailability: Record<string, ToolAvailability>;
  wallClockSeconds: number | null;
};

export type SentruxSnapshot = {
  callEdges: number | null;
  commitSha: string | null;
  exitCode: number | null;
  fileName: string | null;
  filesKept: number | null;
  id: string;
  importEdges: number | null;
  inheritEdges: number | null;
  qualitySignal: number | null;
  rulesChecked: number | null;
  rulesPass: boolean | null;
  timestamp: string | null;
};

export type DashboardMetricsData = {
  latest: MetricsSnapshot | null;
  latestPath: string | null;
  log: {
    body: string;
    path: string;
  } | null;
  sentrux: {
    history: SentruxSnapshot[];
    latest: SentruxSnapshot | null;
    latestPath: string | null;
    log: {
      body: string;
      path: string;
    } | null;
  };
  snapshots: MetricsSnapshot[];
};

export type MetricChartSection = {
  metrics: MetricKey[];
  note: string;
  title: string;
};

export const METRIC_DEFINITIONS: Record<MetricKey, MetricDefinition> = {
  sloc_total: {
    accent: "size",
    chartColor: "#2c7da0",
    direction: "neutral",
    format: "int",
    label: "SLOC",
    shortLabel: "SLOC",
    summary: "Source lines of code, excluding blanks and comments. Informational: more code means a larger surface area to reason about."
  },
  file_count: {
    accent: "size",
    chartColor: "#5f7a61",
    direction: "neutral",
    format: "int",
    label: "Files",
    shortLabel: "Files",
    summary: "Tracked source files after project-metrics path filtering. Informational: rising counts usually mean a broader maintenance surface."
  },
  language_count: {
    accent: "size",
    chartColor: "#a97732",
    direction: "neutral",
    format: "int",
    label: "Languages",
    shortLabel: "Languages",
    summary: "Distinct languages identified in scope. Informational: a larger count usually means more tooling and architectural variety."
  },
  ccn_p95: {
    accent: "risk",
    chartColor: "#c06138",
    direction: "lower",
    format: "float2",
    label: "CCN p95",
    shortLabel: "CCN p95",
    summary: "95th percentile cyclomatic complexity per function. Lower is better because fewer branches are easier to test and change safely."
  },
  cognitive_p95: {
    accent: "risk",
    chartColor: "#b14545",
    direction: "lower",
    format: "float2",
    label: "Cognitive p95",
    shortLabel: "Cognitive p95",
    summary: "95th percentile cognitive complexity per function. Lower is better because heavy nesting and branching increase comprehension cost."
  },
  cyclic_deps: {
    accent: "risk",
    chartColor: "#8f3d65",
    direction: "lower",
    format: "int",
    label: "Cyclic deps",
    shortLabel: "Cyclic SCCs",
    summary: "Non-trivial strongly connected components in the Python import graph. Lower is better; zero is the healthy target."
  },
  churn_total_90d: {
    accent: "activity",
    chartColor: "#b0721a",
    direction: "lower",
    format: "int",
    label: "Churn 90d",
    shortLabel: "Churn total",
    summary: "Insertions plus deletions across the recent analysis window. Lower is usually calmer; sharp spikes deserve investigation."
  },
  change_entropy_90d: {
    accent: "activity",
    chartColor: "#4f8f88",
    direction: "higher",
    format: "float2",
    label: "Change entropy",
    shortLabel: "Change entropy",
    summary: "How spread recent changes are across contributors. Higher is usually better for resilience, though sudden jumps can indicate scattered ownership."
  },
  truck_factor: {
    accent: "quality",
    chartColor: "#2f7d4c",
    direction: "higher",
    format: "int",
    label: "Truck factor",
    shortLabel: "Truck factor",
    summary: "Minimum number of authors whose loss would endanger the project. Higher is better because knowledge is less concentrated."
  },
  hotspot_top_score: {
    accent: "risk",
    chartColor: "#8f3b2e",
    direction: "lower",
    format: "score",
    label: "Hotspot top",
    shortLabel: "Top score",
    summary: "Worst file score from churn multiplied by complexity. Lower is better because it means the riskiest file is cooling down."
  },
  hotspot_gini: {
    accent: "risk",
    chartColor: "#7a4f9a",
    direction: "lower",
    format: "float2",
    label: "Hotspot gini",
    shortLabel: "Gini (0–1)",
    summary: "Concentration of hotspot risk. Lower is better because risk is spread rather than dominated by a few pathological files."
  },
  coverage_line_pct: {
    accent: "quality",
    chartColor: "#0f766e",
    direction: "higher",
    format: "pct",
    label: "Coverage",
    shortLabel: "Line coverage",
    summary: "Line coverage from the latest coverage artifact. Higher is better because more executable lines are exercised by tests."
  }
};

export const METRIC_CHART_SECTIONS: MetricChartSection[] = [
  {
    metrics: ["sloc_total", "file_count", "language_count"],
    note: "Codebase scale across lines, files, and language count.",
    title: "Size"
  },
  {
    metrics: ["ccn_p95", "cognitive_p95"],
    note: "Per-function complexity at the 95th percentile.",
    title: "Complexity"
  },
  {
    metrics: ["churn_total_90d", "change_entropy_90d", "truck_factor"],
    note: "Recent delivery pressure, contributor spread, and resilience.",
    title: "Evolution"
  },
  {
    metrics: ["hotspot_top_score", "hotspot_gini"],
    note: "How risky the hottest files are, and how concentrated that risk is.",
    title: "Hot-spots"
  },
  {
    metrics: ["cyclic_deps"],
    note: "Cyclic dependency count in the Python import graph.",
    title: "Architecture"
  },
  {
    metrics: ["coverage_line_pct"],
    note: "Line coverage when a coverage artifact is present.",
    title: "Quality"
  }
];

export function formatMetricValue(
  metricKey: MetricKey,
  value: number | null | undefined
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  const format = METRIC_DEFINITIONS[metricKey].format;
  if (format === "int") {
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 0
    }).format(value);
  }

  if (format === "pct") {
    return `${(value * 100).toFixed(1)}%`;
  }

  if (format === "score") {
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 0
    }).format(value);
  }

  return value.toFixed(2);
}

export function formatMetricDelta(
  metricKey: MetricKey,
  delta: number | null | undefined
): string | null {
  if (delta === null || delta === undefined || delta === 0 || Number.isNaN(delta)) {
    return null;
  }

  const format = METRIC_DEFINITIONS[metricKey].format;
  if (format === "int") {
    return `${delta > 0 ? "+" : ""}${new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 0
    }).format(delta)}`;
  }

  if (format === "pct") {
    return `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(1)} pts`;
  }

  if (format === "score") {
    return `${delta > 0 ? "+" : ""}${new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 0
    }).format(delta)}`;
  }

  return `${delta > 0 ? "+" : ""}${delta.toFixed(2)}`;
}

export function formatChartAxisValue(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1000) {
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 1,
      notation: "compact"
    }).format(value);
  }

  if (absolute >= 10) {
    return value.toFixed(0);
  }

  if (absolute >= 1) {
    return value.toFixed(1);
  }

  return value.toFixed(2);
}

export function formatSnapshotLabel(timestamp: string | null): string {
  if (!timestamp) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC"
  }).format(new Date(timestamp));
}

export function formatSnapshotLong(timestamp: string | null): string {
  if (!timestamp) {
    return "Unknown timestamp";
  }

  return `${new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(new Date(timestamp))} UTC`;
}

export function getMetricTone(
  metricKey: MetricKey,
  delta: number | null | undefined
): MetricTone {
  if (delta === null || delta === undefined || delta === 0 || Number.isNaN(delta)) {
    return METRIC_DEFINITIONS[metricKey].direction === "neutral" ? "neutral" : "steady";
  }

  const direction = METRIC_DEFINITIONS[metricKey].direction;
  if (direction === "neutral") {
    return "neutral";
  }

  const improved = direction === "higher" ? delta > 0 : delta < 0;
  return improved ? "good" : "bad";
}

export function getMetricDirectionCopy(metricKey: MetricKey): string {
  const direction = METRIC_DEFINITIONS[metricKey].direction;
  if (direction === "higher") {
    return "Higher is usually better.";
  }

  if (direction === "lower") {
    return "Lower is usually better.";
  }

  return "Read as context, not as a score.";
}

export function sliceSnapshotsUpTo<T extends { id: string }>(
  snapshots: T[],
  selectedSnapshotId: string | null
): T[] {
  if (snapshots.length === 0 || selectedSnapshotId === null) {
    return snapshots;
  }

  const selectedIndex = snapshots.findIndex((snapshot) => snapshot.id === selectedSnapshotId);
  if (selectedIndex < 0) {
    return snapshots;
  }

  return snapshots.slice(0, selectedIndex + 1);
}
