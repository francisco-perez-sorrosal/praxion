/**
 * The Overview: one composition over the readers the other surfaces already
 * use. Nothing is stored; each artifact family is read independently, reduced
 * to a digest, and a family that cannot be read is `null` — never a blank page
 * and never a zero standing in for "unknown".
 *
 * Reading goes gather → compose → render: `readInputs` does the I/O, the pure
 * `composeOverview` derives every digest, attention line and activity entry
 * from what was read, and the components only present the result.
 */
import "server-only";

import path from "node:path";

import type { Route } from "next";

import type { HealthLabel } from "@/lib/health-tone";
import { healthSummary } from "@/lib/health-tone";
import type { DashboardMetricsData } from "@/lib/metrics";
import { deriveMetricsView, selectActiveSnapshot } from "@/lib/metrics-dashboard-data";
import type { PraxionEvalCheckGroup, PraxionEvalRun } from "@/lib/praxion-evals";
import type { Tone } from "@/lib/tone";
import { newestOf, normalizeGrade } from "@/lib/tone";
import type { ProgressSummary } from "@/lib/workshops";
import { groupWorkshops, progressSummary } from "@/lib/workshops";
import { fileMtime, newestMtime } from "@/server/artifacts/files";
import { assertAllowedArtifactPath, validateProjectRoot } from "@/server/artifacts/project-root";
import type { SentinelLogPoint } from "@/server/sentinel/extract-sections";
import type { WorkshopState } from "@/server/types";
import { getAdrData } from "@/server/view-models/adrs";
import { getMetricsData } from "@/server/view-models/metrics";
import type { PraxionEvalsData } from "@/server/view-models/praxion-evals";
import { getPraxionEvalsData } from "@/server/view-models/praxion-evals";
import type { SentinelData } from "@/server/view-models/sentinel";
import { getSentinelData } from "@/server/view-models/sentinel";
import type { TechDebtSummary } from "@/server/view-models/tech-debt";
import { getTechDebtSummary } from "@/server/view-models/tech-debt";
import { getWorkshopsData } from "@/server/view-models/workshops";

// ─── The digests the page renders ─────────────────────────────────────────────

export type SentinelDigest = {
  coherence: string | null;
  critical: number | null;
  grade: string | null;
  important: number | null;
  isPartial: boolean;
  notReachedCount: number;
  /** Chronological, the most recent runs only. */
  series: SentinelLogPoint[];
  suggested: number | null;
  timestamp: string | null;
};

export type MetricsDigest = {
  degraded: boolean;
  healthLabel: HealthLabel;
  /** Readiness headline of the newest snapshot; `passPct` is a fraction of 1. */
  readiness: { level: number; passPct: number } | null;
  timestamp: string | null;
  /** Scored indicators only; informational (size) indicators are not counted. */
  tones: { bad: number; good: number; steady: number };
};

export type EvalsDigest = {
  failGroups: PraxionEvalCheckGroup[];
  latest: PraxionEvalRun;
  /** Every run, chronological, for the failure trend. */
  runs: PraxionEvalRun[];
  timestamp: string;
};

export type WorkshopDigest = {
  currentStep: string | null;
  progress: ProgressSummary | null;
  slug: string;
  updatedAt: string | null;
};

export type WorkshopsDigest = {
  /** Newest first. */
  active: WorkshopDigest[];
  doneCount: number;
  staleCount: number;
};

export type DecisionDigest = { date: string | null; id: string; status: string | null; title: string };

export type DecisionsDigest = {
  byCategory: Record<string, number>;
  drafts: number;
  finalized: number;
  /** The highest-numbered finalized decisions, highest first. */
  latest: DecisionDigest[];
};

export type AttentionLine = { href: Route | null; text: string; tone: Tone };

export type ActivityEntry = { family: string; href: Route; label: string; mtime: string };

export type OverviewData = {
  activity: ActivityEntry[];
  attention: AttentionLine[];
  dataAsOf: string | null;
  debt: Pick<TechDebtSummary, "bySeverity" | "inFlight" | "open"> | null;
  decisions: DecisionsDigest | null;
  evals: EvalsDigest | null;
  metrics: MetricsDigest | null;
  sentinel: SentinelDigest | null;
  workshops: WorkshopsDigest | null;
};

// ─── Refresh cadence ──────────────────────────────────────────────────────────

const OVERVIEW_POLL_MULTIPLIER = 4;
const OVERVIEW_MIN_REFRESH_SECONDS = 60;

/** The Overview polls slower than Workshops: four times the interval, never under a minute. */
export function overviewRefreshSeconds(pollSeconds: number): number {
  return Math.max(OVERVIEW_MIN_REFRESH_SECONDS, OVERVIEW_POLL_MULTIPLIER * pollSeconds);
}

// ─── Entry point ──────────────────────────────────────────────────────────────

export async function getOverviewData(projectRoot: string, now: Date): Promise<OverviewData> {
  const validatedRoot = await validateProjectRoot(projectRoot);
  return composeOverview(await readInputs(validatedRoot), now);
}

// ─── Gather: one independent read per family ──────────────────────────────────

/** What a family's reader returned, with when its newest artifact last changed. */
export type Read<T> = { touched: string | null; value: T };

export type DecisionRecord = { data: Record<string, unknown>; isDraft: boolean; path: string };

export type KnowledgeStamps = { architecture: string | null; documentation: string | null; roadmap: string | null };

/** When the sentinel and metrics run logs last changed; they feed the page stamp, not the activity list. */
export type LogStamps = { metrics: string | null; sentinel: string | null };

export type OverviewInputs = {
  debt: TechDebtSummary | null;
  decisions: Read<DecisionRecord[]> | null;
  evals: Read<PraxionEvalsData> | null;
  knowledge: KnowledgeStamps;
  logStamps: LogStamps;
  metrics: Read<DashboardMetricsData> | null;
  sentinel: Read<SentinelData> | null;
  workshops: WorkshopState[] | null;
};

/**
 * Runs one family's reader so its failure costs only that family: the failure
 * is reported and the family reads as absent, and every other family (and the
 * sidebar) renders as usual.
 */
export async function readOrNull<T>(family: string, read: () => Promise<T>): Promise<T | null> {
  try {
    return await read();
  } catch (error) {
    console.warn(`[dashboard] ${family} unreadable:`, error instanceof Error ? error.message : String(error));
    return null;
  }
}

async function readInputs(root: string): Promise<OverviewInputs> {
  const [sentinel, metrics, evals, workshops, decisions, debt, knowledge] = await Promise.all([
    readOrNull("sentinel", async () => {
      const value = await getSentinelData(root);
      return { touched: await mtimeOf(value.reports[0]?.path), value };
    }),
    readOrNull("metrics", async () => {
      const value = await getMetricsData(root);
      return { touched: await mtimeOf(value.latestPath ?? value.snapshots.at(-1)?.path), value };
    }),
    readOrNull("quality evals", async () => {
      const value = await getPraxionEvalsData(root);
      return { touched: value.dataAsOf, value };
    }),
    readOrNull("workshops", () => getWorkshopsData(root)),
    readOrNull("decisions", async () => {
      const value = (await getAdrData(root)).records;
      return { touched: await newestMtime(value.map((record) => record.path)), value };
    }),
    readOrNull("tech debt", () => getTechDebtSummary(root)),
    readKnowledgeStamps(root)
  ]);
  const logStamps: LogStamps = {
    metrics: await mtimeOf(metrics?.value.log?.path),
    sentinel: await mtimeOf(sentinel?.value.log?.path)
  };
  return { debt, decisions, evals, knowledge, logStamps, metrics, sentinel, workshops };
}

const mtimeOf = async (target: string | undefined): Promise<string | null> =>
  target === undefined ? null : fileMtime(target);

async function readKnowledgeStamps(root: string): Promise<KnowledgeStamps> {
  const allowed = (...segments: string[]) => assertAllowedArtifactPath(root, path.join(root, ...segments));
  const stamps = await readOrNull("knowledge documents", async () => {
    const [design, guide, manifest, roadmap] = await Promise.all([
      allowed(".ai-state", "DESIGN.md"),
      allowed("docs", "architecture.md"),
      allowed(".ai-state", "doc_manifest.yaml"),
      allowed("ROADMAP.md")
    ]);
    return {
      architecture: await newestMtime([design, guide]),
      documentation: await fileMtime(manifest),
      roadmap: await fileMtime(roadmap)
    };
  });
  return stamps ?? { architecture: null, documentation: null, roadmap: null };
}

// ─── Compose (pure) ───────────────────────────────────────────────────────────

export function composeOverview(inputs: OverviewInputs, now: Date): OverviewData {
  const sentinel = inputs.sentinel === null ? null : digestSentinel(inputs.sentinel.value);
  const metrics = inputs.metrics === null ? null : digestMetrics(inputs.metrics.value);
  const evals = inputs.evals === null ? null : digestEvals(inputs.evals.value);
  const workshops = inputs.workshops === null ? null : digestWorkshops(inputs.workshops, now);
  const decisions = inputs.decisions === null ? null : digestDecisions(inputs.decisions.value);
  const debt =
    inputs.debt === null
      ? null
      : { bySeverity: inputs.debt.bySeverity, inFlight: inputs.debt.inFlight, open: inputs.debt.open };

  const activity = deriveActivity(inputs);
  return {
    activity,
    attention: deriveAttention({ debt, evals, metrics, sentinel }),
    dataAsOf: newestOf([activity[0]?.mtime, inputs.debt?.mtime, inputs.logStamps.metrics, inputs.logStamps.sentinel]),
    debt,
    decisions,
    evals,
    metrics,
    sentinel,
    workshops
  };
}

// ─── Digests ──────────────────────────────────────────────────────────────────

const SENTINEL_TREND_RUNS = 8;

/**
 * The newest report's own log row. A report no row names (a run cut short
 * before the log append) is reported as not graded, never as the previous
 * run's grade; the log's last row stands in only when no report exists.
 */
export function digestSentinel(data: SentinelData): SentinelDigest | null {
  const newest = data.reports[0] ?? null;
  const latest = newest === null ? (data.logSeries.at(-1) ?? null) : newest.highlight;
  if (newest === null && latest === null) {
    return null;
  }
  return {
    coherence: latest?.coherence ?? null,
    critical: latest?.critical ?? null,
    grade: normalizeGrade(latest?.grade) ?? null,
    important: latest?.important ?? null,
    isPartial: newest?.isPartial ?? false,
    notReachedCount: newest?.notReachedCount ?? 0,
    series: data.logSeries.slice(-SENTINEL_TREND_RUNS),
    suggested: latest?.suggested ?? null,
    timestamp: newest?.fileTimestamp ?? latest?.timestamp ?? null
  };
}

export function digestMetrics(data: DashboardMetricsData): MetricsDigest | null {
  const snapshot = selectActiveSnapshot(data, null);
  if (snapshot === null) {
    return null;
  }
  const view = deriveMetricsView(data, snapshot, []);
  const tones = view.kpiTones.map((entry) => entry.tone);
  const readiness = snapshot.readiness;
  const weighted = readiness?.weightingActive === true;
  return {
    degraded: view.degradedCollectors.length > 0,
    healthLabel: healthSummary(tones, {
      degradedCollectors: view.degradedCollectors,
      isBaseline: data.snapshots.length < 2
    }).label,
    readiness:
      readiness === null
        ? null
        : {
            level: weighted ? (readiness.adjustedLevel ?? readiness.level) : readiness.level,
            passPct: weighted ? (readiness.adjustedPassPct ?? readiness.pass_pct) : readiness.pass_pct
          },
    timestamp: snapshot.aggregate.timestamp,
    tones: {
      bad: tones.filter((tone) => tone === "bad").length,
      good: tones.filter((tone) => tone === "good").length,
      steady: tones.filter((tone) => tone === "steady").length
    }
  };
}

export function digestEvals(data: PraxionEvalsData): EvalsDigest | null {
  const latest = data.runs.at(-1);
  if (latest === undefined) {
    return null;
  }
  return {
    failGroups: data.selected?.timestamp === latest.timestamp ? data.selected.failGroups : [],
    latest,
    runs: data.runs,
    timestamp: latest.timestamp
  };
}

export function digestWorkshops(workshops: readonly WorkshopState[], now: Date): WorkshopsDigest {
  const groups = groupWorkshops(workshops, now);
  return {
    active: groups.active.map(toWorkshopDigest),
    doneCount: groups.done.length,
    staleCount: groups.stale.length
  };
}

function toWorkshopDigest(workshop: WorkshopState): WorkshopDigest {
  return {
    currentStep: workshop.currentStep,
    progress: progressSummary(workshop.progress),
    slug: path.basename(workshop.path),
    updatedAt: workshop.updatedAt
  };
}

const LATEST_DECISIONS = 3;
const UNCATEGORIZED = "uncategorized";
const FINALIZED_NUMBER = /^(?:dec-)?(\d+)/;

export function digestDecisions(records: readonly DecisionRecord[]): DecisionsDigest | null {
  if (records.length === 0) {
    return null;
  }
  const finalized = records.filter((record) => !record.isDraft);
  const byCategory: Record<string, number> = {};
  for (const record of records) {
    const category = textField(record.data["category"]) ?? UNCATEGORIZED;
    byCategory[category] = (byCategory[category] ?? 0) + 1;
  }
  return {
    byCategory,
    drafts: records.length - finalized.length,
    finalized: finalized.length,
    latest: finalized
      .map((record) => ({ number: decisionNumber(record), record }))
      .sort((left, right) => right.number - left.number)
      .slice(0, LATEST_DECISIONS)
      .map(({ record }) => toDecisionDigest(record))
  };
}

function decisionNumber(record: DecisionRecord): number {
  const id = textField(record.data["id"]) ?? path.basename(record.path);
  const match = FINALIZED_NUMBER.exec(id) ?? FINALIZED_NUMBER.exec(path.basename(record.path));
  return match?.[1] === undefined ? -1 : Number(match[1]);
}

function toDecisionDigest(record: DecisionRecord): DecisionDigest {
  return {
    date: dayOf(record.data["date"]),
    id: textField(record.data["id"]) ?? path.basename(record.path, ".md"),
    status: textField(record.data["status"]),
    title: textField(record.data["title"]) ?? path.basename(record.path, ".md")
  };
}

function textField(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : null;
}

/** Frontmatter dates arrive as `Date` (YAML timestamps) or as text; both reduce to `YYYY-MM-DD`. */
function dayOf(value: unknown): string | null {
  const iso = value instanceof Date && !Number.isNaN(value.getTime()) ? value.toISOString() : textField(value);
  return iso === null ? null : iso.slice(0, "YYYY-MM-DD".length);
}

// ─── Attention ────────────────────────────────────────────────────────────────

type AttentionSources = Pick<OverviewData, "debt" | "evals" | "metrics" | "sentinel">;

const ATTENTION_DEBT_SEVERITIES = ["critical", "important"] as const;

/** One line per condition an operator should look at, most urgent first. */
function deriveAttention({ debt, evals, metrics, sentinel }: AttentionSources): AttentionLine[] {
  const lines: AttentionLine[] = [];
  const critical = sentinel?.critical ?? 0;
  const important = sentinel?.important ?? 0;
  if (critical > 0) {
    lines.push({ href: "/sentinel", text: `${critical} critical sentinel ${plural(critical, "finding")}`, tone: "bad" });
  }
  if (important > 0) {
    lines.push({ href: "/sentinel", text: `${important} important sentinel ${plural(important, "finding")}`, tone: "warn" });
  }
  if (sentinel?.isPartial === true) {
    const reached = sentinel.notReachedCount > 0 ? ` — ${sentinel.notReachedCount} checks not reached` : "";
    lines.push({ href: "/sentinel", text: `Sentinel report is partial${reached}`, tone: "warn" });
  }
  if (metrics?.healthLabel === "WORSENING") {
    lines.push({ href: "/metrics", text: "Metrics health is worsening", tone: "bad" });
  }
  const failures = evals?.latest.fail ?? 0;
  if (evals !== null && failures > 0) {
    const checks = evals.failGroups.length;
    const across = checks > 0 ? ` across ${checks} ${plural(checks, "check")}` : "";
    lines.push({ href: "/evals", text: `${failures} quality-eval ${plural(failures, "failure")}${across}`, tone: "bad" });
  }
  const urgentDebt = ATTENTION_DEBT_SEVERITIES.reduce((sum, severity) => sum + (debt?.bySeverity[severity] ?? 0), 0);
  if (urgentDebt > 0) {
    lines.push({ href: null, text: `${urgentDebt} critical or important tech-debt ${plural(urgentDebt, "row")} open or in flight`, tone: "warn" });
  }
  return lines;
}

function plural(count: number, noun: string): string {
  if (count === 1) {
    return noun;
  }
  return noun.endsWith("y") ? `${noun.slice(0, -1)}ies` : `${noun}s`;
}

// ─── Recent activity ──────────────────────────────────────────────────────────

/** One entry per artifact family, newest first; a family with nothing read has no entry. */
function deriveActivity(inputs: OverviewInputs): ActivityEntry[] {
  const newestWorkshop = newestWorkshopOf(inputs.workshops ?? []);
  const candidates: Array<Omit<ActivityEntry, "mtime"> & { mtime: string | null }> = [
    {
      family: "workshops",
      href: "/workshops",
      label: newestWorkshop === null ? "Workshops" : `Workshop ${path.basename(newestWorkshop.path)}`,
      mtime: newestWorkshop?.updatedAt ?? null
    },
    { family: "sentinel", href: "/sentinel", label: "Sentinel report", mtime: inputs.sentinel?.touched ?? null },
    { family: "evals", href: "/evals", label: "Quality-eval run", mtime: inputs.evals?.touched ?? null },
    { family: "metrics", href: "/metrics", label: "Metrics snapshot", mtime: inputs.metrics?.touched ?? null },
    { family: "decisions", href: "/adrs", label: "Decisions", mtime: inputs.decisions?.touched ?? null },
    { family: "architecture", href: "/architecture", label: "Architecture", mtime: inputs.knowledge.architecture },
    { family: "documentation", href: "/documentation", label: "Documentation", mtime: inputs.knowledge.documentation },
    { family: "roadmap", href: "/roadmap", label: "Roadmap", mtime: inputs.knowledge.roadmap }
  ];
  return candidates
    .filter((entry): entry is ActivityEntry => entry.mtime !== null)
    .sort((left, right) => right.mtime.localeCompare(left.mtime));
}

function newestWorkshopOf(workshops: readonly WorkshopState[]): WorkshopState | null {
  let newest: WorkshopState | null = null;
  for (const workshop of workshops) {
    if (workshop.updatedAt !== null && (newest === null || workshop.updatedAt > (newest.updatedAt ?? ""))) {
      newest = workshop;
    }
  }
  return newest;
}
