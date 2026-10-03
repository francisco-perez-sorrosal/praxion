/**
 * Fixture project roots for the dashboard acceptance suite.
 *
 * A fixture is a temp directory shaped like a Praxion-onboarded project: the
 * `.ai-state/` and `.ai-work/` artifact families the dashboard reads, written
 * in the producers' on-disk formats, each file stamped with an explicit
 * modification time. Recency, "data as of" and age all hinge on those times,
 * so they are set relative to FIXED_NOW, the instant the suite freezes the
 * clock at (see `dashboard.tsx`).
 *
 * Built programmatically rather than committed: `.ai-work/` is gitignored at
 * any depth, and mtimes do not survive a checkout.
 */

import { mkdir, mkdtemp, rm, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

// ─── Clock ────────────────────────────────────────────────────────────────────

/** The instant the suite treats as "now" (UTC; the suite runs with TZ=UTC). */
export const FIXED_NOW = new Date("2026-10-02T15:00:00Z");

export function hoursAgo(hours: number): Date {
  return new Date(FIXED_NOW.getTime() - hours * 3_600_000);
}

export function daysAgo(days: number): Date {
  return hoursAgo(days * 24);
}

export function at(iso: string): Date {
  return new Date(iso);
}

// ─── Files ────────────────────────────────────────────────────────────────────

export type FixtureFile = { path: string; content: string; mtime: Date };

type FixtureEntry = FixtureFile | { dir: string };

const builtRoots: string[] = [];

/** Writes the files into a fresh temp project root and returns its path. */
export async function buildProjectRoot(entries: FixtureEntry[], prefix = "acceptance-"): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), prefix));
  builtRoots.push(root);
  await mkdir(path.join(root, ".ai-state"), { recursive: true });
  for (const entry of entries) {
    if ("dir" in entry) {
      await mkdir(path.join(root, entry.dir), { recursive: true });
      continue;
    }
    const target = path.join(root, entry.path);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, entry.content);
    await utimes(target, entry.mtime, entry.mtime);
  }
  return root;
}

/** Removes every root built so far; call from afterEach. */
export async function removeProjectRoots(): Promise<void> {
  await Promise.all(builtRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
}

/** A directory standing where a file is expected: reading it fails (EISDIR). */
export function unreadable(relativePath: string): FixtureEntry {
  return { dir: relativePath };
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** `2026-10-01_09-30-00` — the sentinel and metrics filename stamp. */
function underscoreStamp(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}_${pad(d.getUTCHours())}-${pad(d.getUTCMinutes())}-${pad(d.getUTCSeconds())}`;
}

/** `2026-09-30T08-00-00Z` — the quality-eval run stamp. */
function evalStamp(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}-${pad(d.getUTCMinutes())}-${pad(d.getUTCSeconds())}Z`;
}

function isoSeconds(d: Date): string {
  return d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function newest(dates: Date[]): Date {
  return new Date(Math.max(...dates.map((d) => d.getTime())));
}

// ─── Sentinel (producer: the `sentinel` agent) ────────────────────────────────

export type SentinelRun = {
  at: Date;
  grade: string;
  coherence: string;
  critical: number;
  important: number;
  suggested: number;
  partial?: boolean;
  /** Check ids the report marks `[not reached]`, one marker per check. */
  notReached?: string[];
};

export function sentinelReportFileName(run: SentinelRun): string {
  return `SENTINEL_REPORT_${underscoreStamp(run.at)}.md`;
}

/** A sentence that appears only in the body of this run's report. */
export function sentinelBodySentence(run: SentinelRun): string {
  return `Report body for the sweep of ${isoSeconds(run.at)}.`;
}

function findingsTable(kind: string, count: number): string {
  const header =
    "| # | Check | Dimension | Location | Finding | Recommended Action | Owner |\n|---|-------|-----------|----------|---------|---------------------|-------|";
  if (count === 0) {
    return `${header}\n| — | — | — | — | None found this run | — | — |`;
  }
  const rows = Array.from(
    { length: count },
    (_, i) =>
      `| ${i + 1} | ${kind.slice(0, 2).toUpperCase()}0${i + 1} | Freshness | \`skills/${kind}-${i + 1}/SKILL.md\` | The ${kind} finding number ${i + 1} | Fix it | context-engineer |`
  );
  return `${header}\n${rows.join("\n")}`;
}

function sentinelReportBody(run: SentinelRun): string {
  const notReached = (run.notReached ?? [])
    .map((id) => `- **${id}** — not performed this run (time budget) — **[not reached]**.`)
    .join("\n");
  return [
    `# Sentinel Report${run.partial ? " [PARTIAL]" : ""}`,
    "",
    "Scope: Full ecosystem sweep — all artifacts, all dimensions.",
    "",
    `## Ecosystem Health: ${run.grade}`,
    "",
    "### Summary",
    "",
    sentinelBodySentence(run),
    "",
    `### Ecosystem Coherence: ${run.coherence}`,
    "",
    "### Depth Disclosure",
    "",
    notReached || "Every catalog check reached a verdict.",
    "",
    "### Findings",
    "",
    "#### Critical (blocks correct behavior)",
    findingsTable("critical", run.critical),
    "",
    "#### Important (degrades quality or efficiency)",
    findingsTable("important", run.important),
    "",
    "#### Suggested (improves but not urgent)",
    findingsTable("suggested", run.suggested),
    "",
    "### Recommended Actions (prioritized)",
    "",
    "1. Keep going.",
    ""
  ].join("\n");
}

/** Reports plus `SENTINEL_LOG.md`, in the sentinel agent's formats. */
export function sentinelFamily(runs: SentinelRun[]): FixtureFile[] {
  const dir = ".ai-state/sentinel_reports";
  const reports = runs.map((run) => ({
    path: `${dir}/${sentinelReportFileName(run)}`,
    content: sentinelReportBody(run),
    mtime: run.at
  }));
  const rows = runs.map(
    (run) =>
      `| ${isoSeconds(run.at)} | ${run.grade}${run.partial ? " [PARTIAL]" : ""} | 40 | ${run.critical}/${run.important}/${run.suggested} | ${run.coherence} | ${sentinelReportFileName(run)} |`
  );
  const log = {
    path: `${dir}/SENTINEL_LOG.md`,
    content: [
      "# Sentinel Log",
      "",
      "| Timestamp | Health Grade | Artifacts | Findings (C/I/S) | Ecosystem Coherence | Report File |",
      "|-----------|--------------|-----------|-------------------|---------------------|-------------|",
      ...rows,
      ""
    ].join("\n"),
    mtime: newest(runs.map((run) => run.at))
  };
  return [...reports, log];
}

// ─── Metrics (producer: `/project-metrics`) ───────────────────────────────────

export type MetricsSnapshotSpec = {
  at: Date;
  coverage: number;
  ccnP95: number;
  cognitiveP95: number;
  cyclicDeps: number;
  truckFactor: number;
  hotspotGini: number;
  readinessLevel: number;
  readinessPassPct: number;
};

export const HEALTHY_METRICS: Omit<MetricsSnapshotSpec, "at"> = {
  coverage: 0.85,
  ccnP95: 6,
  cognitiveP95: 8,
  cyclicDeps: 0,
  truckFactor: 3,
  hotspotGini: 0.4,
  readinessLevel: 3,
  readinessPassPct: 0.82
};

/** Every indicator markedly worse than HEALTHY_METRICS. */
export const DEGRADED_METRICS: Omit<MetricsSnapshotSpec, "at"> = {
  coverage: 0.4,
  ccnP95: 14,
  cognitiveP95: 22,
  cyclicDeps: 6,
  truckFactor: 1,
  hotspotGini: 0.8,
  readinessLevel: 3,
  readinessPassPct: 0.82
};

function aggregateOf(s: MetricsSnapshotSpec) {
  return {
    ccn_p95: s.ccnP95,
    change_entropy_90d: 300.5,
    churn_total_90d: 9000,
    cognitive_p95: s.cognitiveP95,
    commit_sha: "0123456789abcdef0123456789abcdef01234567",
    coverage_line_pct: s.coverage,
    cyclic_deps: s.cyclicDeps,
    file_count: 400,
    hotspot_gini: s.hotspotGini,
    hotspot_top_score: 5000,
    language_count: 4,
    schema_version: "1.2.1",
    sloc_total: 40000,
    timestamp: s.at.toISOString(),
    truck_factor: s.truckFactor,
    window_days: 90
  };
}

const TREND_KEYS = [
  "ccn_p95",
  "cognitive_p95",
  "coverage_line_pct",
  "cyclic_deps",
  "truck_factor",
  "hotspot_gini"
] as const;

function metricsReportJson(s: MetricsSnapshotSpec, prior: MetricsSnapshotSpec | null): string {
  const current = aggregateOf(s);
  const before = prior ? aggregateOf(prior) : null;
  const deltas = Object.fromEntries(
    TREND_KEYS.map((key) => {
      const c = current[key] as number;
      const p = before ? (before[key] as number) : null;
      return [
        key,
        p === null
          ? { current: c, delta: null, delta_pct: null, prior: null }
          : { current: c, delta: c - p, delta_pct: p === 0 ? null : (c - p) / p, prior: p }
      ];
    })
  );
  return JSON.stringify(
    {
      aggregate: current,
      hotspots: { top_n: [] },
      readiness: {
        status: "ok",
        duration_seconds: 0.5,
        issues: [],
        data: {
          level: s.readinessLevel,
          pass_pct: s.readinessPassPct,
          adjusted_level: s.readinessLevel,
          adjusted_pass_pct: s.readinessPassPct,
          weighting_active: false,
          pillar_weights: {},
          note: "mechanical-only",
          llm: { status: "llm_skipped", model: null, grounded_on: null, reason: "mechanical_only" },
          manageability: { pass_pct: 0.75, numerator: 3, denominator: 4, note: "Praxion-native" },
          pillars: [
            {
              id: "testing",
              name: "Testing",
              pass_pct: s.readinessPassPct,
              numerator: 4,
              denominator: 5,
              level_pass: [true, true, true, false, false]
            }
          ],
          criteria: [
            {
              id: "c.testing.unit_tests",
              pillar: "testing",
              level: 1,
              scope: "repo",
              applicable: true,
              passed: true,
              llm: false,
              rationale: "unit tests present"
            }
          ]
        }
      },
      run_metadata: {
        command_version: "1.0.0",
        commit: current.commit_sha,
        dirty: false,
        generated_at: s.at.toISOString(),
        python_version: "3.13.0",
        top_n: 10,
        wall_clock_seconds: 12.5,
        window_days: 90
      },
      schema_version: "1.2.1",
      tool_availability: {},
      trends: before
        ? { current_schema: "1.2.1", prior_schema: "1.2.1", deltas }
        : { current_schema: "1.2.1", prior_schema: null, deltas: {} }
    },
    null,
    2
  );
}

/** Per-run JSON reports plus `METRICS_LOG.md`, oldest snapshot first. */
export function metricsFamily(snapshots: MetricsSnapshotSpec[]): FixtureFile[] {
  const dir = ".ai-state/metrics_reports";
  const reports = snapshots.map((s, i) => ({
    path: `${dir}/METRICS_REPORT_${underscoreStamp(s.at)}.json`,
    content: metricsReportJson(s, i === 0 ? null : (snapshots[i - 1] ?? null)),
    mtime: s.at
  }));
  const columns =
    "| schema_version | timestamp | commit_sha | window_days | sloc_total | file_count | language_count | ccn_p95 | cognitive_p95 | cyclic_deps | churn_total_90d | change_entropy_90d | truck_factor | hotspot_top_score | hotspot_gini | coverage_line_pct | report_file |";
  const rows = snapshots.map((s) => {
    const a = aggregateOf(s);
    const md = `METRICS_REPORT_${underscoreStamp(s.at)}.md`;
    return `| 1.2.1 | ${a.timestamp} | ${a.commit_sha} | 90 | ${a.sloc_total} | ${a.file_count} | ${a.language_count} | ${a.ccn_p95} | ${a.cognitive_p95} | ${a.cyclic_deps} | ${a.churn_total_90d} | ${a.change_entropy_90d} | ${a.truck_factor} | ${a.hotspot_top_score} | ${a.hotspot_gini} | ${a.coverage_line_pct} | [${md}](${md}) |`;
  });
  const log = {
    path: `${dir}/METRICS_LOG.md`,
    content: [columns, `| ${columns.split("|").slice(1, -1).map(() => "---").join(" | ")} |`, ...rows, ""].join("\n"),
    mtime: newest(snapshots.map((s) => s.at))
  };
  return [...reports, log];
}

// ─── Quality evals (producer: `/eval-praxion`) ────────────────────────────────

export type EvalCheckRow = {
  check: string;
  verdict: "PASS" | "WARN" | "FAIL" | "SKIP";
  artifact: string;
  finding: string;
};

export type QualityEvalRun = {
  at: Date;
  target: string;
  pass: number;
  warn: number;
  fail: number;
  skip: number;
  costUsd: number;
  judged?: { calls: number; cacheHits: number; tokensIn: number; tokensOut: number };
  rows: EvalCheckRow[];
  calibrationNote?: string;
};

export function evalReportFileName(run: QualityEvalRun): string {
  return `PRAXION_EVAL_REPORT_${evalStamp(run.at)}.md`;
}

export function evalRunStamp(run: QualityEvalRun): string {
  return evalStamp(run.at);
}

function thousands(n: number): string {
  return n.toLocaleString("en-US");
}

function evalReportBody(run: QualityEvalRun): string {
  const header = [
    `# Praxion Eval Report — ${evalStamp(run.at)}`,
    "",
    `**Target**: \`${run.target}\` (kind: path)`,
    `**Summary**: ${run.pass} PASS / ${run.warn} WARN / ${run.fail} FAIL / ${run.skip} SKIP`
  ];
  if (run.judged) {
    header.push(
      `**Judged**: ${run.judged.calls} calls, ${run.judged.cacheHits} cache hits, 8 workers`,
      `**Tokens**: ${thousands(run.judged.tokensIn)} in / ${thousands(run.judged.tokensOut)} out / 0 cache-read / 0 cache-write`
    );
  }
  header.push(`**Estimated cost**: $${run.costUsd.toFixed(4)} USD`, "");
  const table = [
    "## Check Results",
    "",
    "| Check | Kind | Verdict | Artifact | Score | Findings |",
    "|-------|------|---------|----------|-------|----------|",
    ...run.rows.map((r) => `| ${r.check} | mechanical | ${r.verdict} | ${r.artifact} | N/A | ${r.finding} |`),
    ""
  ];
  const calibration = run.calibrationNote ? ["## Calibration Notes", "", run.calibrationNote, ""] : [];
  return [...header, ...table, ...calibration].join("\n");
}

/** Reports plus `PRAXION_EVAL_LOG.md`, oldest run first (append order). */
export function qualityEvalFamily(runs: QualityEvalRun[]): FixtureFile[] {
  const dir = ".ai-state/praxion_eval_reports";
  const reports = runs.map((run) => ({
    path: `${dir}/${evalReportFileName(run)}`,
    content: evalReportBody(run),
    mtime: run.at
  }));
  const log = {
    path: `${dir}/PRAXION_EVAL_LOG.md`,
    content: [
      "| Timestamp | Target | Auth route | Families | Pass | Warn | Fail | Cost (USD) | Report |",
      "|-----------|--------|------------|----------|------|------|------|------------|--------|",
      ...runs.map(
        (run) =>
          `| ${evalStamp(run.at)} | ${run.target} | messages-api | family1+family2 | ${run.pass} | ${run.warn} | ${run.fail} | $${run.costUsd.toFixed(4)} | ${evalReportFileName(run)} |`
      ),
      ""
    ].join("\n"),
    mtime: newest(runs.map((run) => run.at))
  };
  return [...reports, log];
}

// ─── Eval ledger ──────────────────────────────────────────────────────────────

/** A ledger whose header carries `run_id`: the experiment-leaderboard shape. */
export function leaderboardLedger(mtime: Date): FixtureFile {
  return {
    path: ".ai-state/eval_ledger/EVAL_LOG.md",
    content: [
      "# EVAL_LOG",
      "",
      "| run_id | task | generation | primary_metric | held_out_delta | model_id | prompt_hash | dataset_sha | cost_usd | git_sha | store_uri |",
      "|---|---|---|---|---|---|---|---|---|---|---|",
      "| eval-lowscore-g1 | swebench_verified | 1 | 0.512 | 0.003 | claude-opus-4 | aa11bb22 | cc33dd44 | 12.50 | b2c3d4e | ~/runs/eval-lowscore-g1/ |",
      "| eval-topscore-g3 | swebench_verified | 3 | 0.641 | -0.012 | claude-sonnet-4-5 | f3a9d2b7 | 9e3c2a1b | 7.23 | a1b2c3d | ~/runs/eval-topscore-g3/ |",
      ""
    ].join("\n"),
    mtime
  };
}

/** A ledger of another shape (no `run_id` column), like a baselines log. */
export function baselineLedger(mtime: Date): FixtureFile {
  return {
    path: ".ai-state/eval_ledger/EVAL_LOG.md",
    content: [
      "# EVAL_LOG — context-layer quality baselines",
      "",
      "One row per recorded baseline of the context layer.",
      "",
      "| date | commit | purpose | mechanical (PASS/WARN/FAIL) | notes |",
      "| --- | --- | --- | --- | --- |",
      "| 2026-09-07 | d483b2ec | Phase zero baseline | 758/389/1 | first measurement |",
      "| 2026-09-20 | 3242a76b | Post-slice remeasure | 798/522/0 | after the prune |",
      ""
    ].join("\n"),
    mtime
  };
}

// ─── Workshops (`.ai-work/<slug>/`, written by pipeline agents) ───────────────

export type WorkshopSpec = {
  slug: string;
  finished: boolean;
  currentStep: string;
  done: number;
  total: number;
  /** Modification time of each artifact in the workshop directory. */
  files: { "WIP.md": Date; "PROGRESS.md"?: Date; "LEARNINGS.md"?: Date };
};

function wipBody(w: WorkshopSpec): string {
  const steps = Array.from({ length: w.total }, (_, i) => {
    const label = i === w.done ? w.currentStep : `${w.slug} step ${i + 1}`;
    return `- [${i < w.done ? "x" : " "}] Step ${i + 1}: ${label}`;
  });
  return [
    "# WIP",
    "",
    "## Current Step",
    "",
    w.finished ? "All steps complete" : w.currentStep,
    "",
    "## Status",
    "",
    w.finished ? "[COMPLETE]" : "[IN-PROGRESS] - work underway",
    "",
    "## Progress",
    "",
    ...steps,
    ""
  ].join("\n");
}

export function workshop(w: WorkshopSpec): FixtureFile[] {
  const dir = `.ai-work/${w.slug}`;
  const files: FixtureFile[] = [{ path: `${dir}/WIP.md`, content: wipBody(w), mtime: w.files["WIP.md"] }];
  if (w.files["PROGRESS.md"]) {
    files.push({
      path: `${dir}/PROGRESS.md`,
      content: `[${w.files["PROGRESS.md"].toISOString()}] [implementer] Phase 2/4: [build] -- worked on ${w.slug}\n`,
      mtime: w.files["PROGRESS.md"]
    });
  }
  if (w.files["LEARNINGS.md"]) {
    files.push({
      path: `${dir}/LEARNINGS.md`,
      content: `# Learnings\n\n- **[implementer]** something learned in ${w.slug}\n`,
      mtime: w.files["LEARNINGS.md"]
    });
  }
  return files;
}

// ─── Decisions (`.ai-state/decisions/`) ──────────────────────────────────────

export type DecisionSpec = {
  number?: number;
  draftHash?: string;
  title: string;
  category: string;
  mtime: Date;
};

export function decision(d: DecisionSpec): FixtureFile {
  const slug = d.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  const id = d.number !== undefined ? `dec-${String(d.number).padStart(3, "0")}` : `dec-draft-${d.draftHash}`;
  const file =
    d.number !== undefined
      ? `.ai-state/decisions/${String(d.number).padStart(3, "0")}-${slug}.md`
      : `.ai-state/decisions/drafts/20260920-1200-dev-main-${slug}.md`;
  return {
    path: file,
    content: [
      "---",
      `id: ${id}`,
      `title: ${d.title}`,
      `status: ${d.number !== undefined ? "accepted" : "proposed"}`,
      `category: ${d.category}`,
      `date: ${d.mtime.toISOString().slice(0, 10)}`,
      `summary: ${d.title}`,
      "tags: [dashboard]",
      "made_by: agent",
      "---",
      "",
      "## Context",
      "",
      `Context of ${d.title}.`,
      "",
      "## Decision",
      "",
      `We decided ${d.title}.`,
      ""
    ].join("\n"),
    mtime: d.mtime
  };
}

// ─── Tech debt (`.ai-state/TECH_DEBT_LEDGER.md`) ─────────────────────────────

export type DebtRow = { id: string; severity: string; status: string; note: string };

export function techDebtLedger(rows: DebtRow[], mtime: Date): FixtureFile {
  return {
    path: ".ai-state/TECH_DEBT_LEDGER.md",
    content: [
      "# Tech Debt Ledger",
      "",
      "| id | severity | class | direction | location | goal-ref-type | goal-ref-value | source | first-seen | last-seen | owner-role | status | resolved-by | notes | dedup_key |",
      "|----|----------|-------|-----------|----------|---------------|----------------|--------|------------|-----------|-----------|--------|-------------|-------|-----------|",
      ...rows.map(
        (r) =>
          `| ${r.id} | ${r.severity} | complexity | code-to-goals | scripts/x.py | code-quality |  | verifier | 2026-09-01 | 2026-09-01 | implementer | ${r.status} |  | ${r.note} | ${r.id}-key |`
      ),
      ""
    ].join("\n"),
    mtime
  };
}

// ─── Knowledge documents ──────────────────────────────────────────────────────

export function roadmap(mtime: Date): FixtureFile {
  return { path: "ROADMAP.md", content: "# Roadmap\n\n## Now\n\n- Ship the overview\n", mtime };
}

export function designDocs(designMtime: Date, guideMtime: Date): FixtureFile[] {
  return [
    { path: ".ai-state/DESIGN.md", content: "# Design\n\n## System Overview\n\nThe system.\n", mtime: designMtime },
    { path: "docs/architecture.md", content: "# Architecture\n\n## Navigating\n\nThe guide.\n", mtime: guideMtime }
  ];
}

export function documentationManifest(mtime: Date): FixtureFile[] {
  return [
    { path: "docs/guide.md", content: "# Guide\n\nHow to use it.\n", mtime },
    {
      path: ".ai-state/doc_manifest.yaml",
      content: [
        "groups:",
        "  - id: docs",
        "    label: Docs",
        "    surface_ids: [guide]",
        "surfaces:",
        "  - id: guide",
        "    title: Guide",
        "    path: docs/guide.md",
        "    type: markdown",
        ""
      ].join("\n"),
      mtime
    }
  ];
}
