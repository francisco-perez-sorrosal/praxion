import type { ReadinessCriterion, ReadinessLlm, ReadinessPillar } from "@/lib/metrics";

export const MAX_LEVEL = 5;

export const LEVEL_LABELS: Record<number, string> = {
  1: "L1",
  2: "L2",
  3: "L3",
  4: "L4",
  5: "L5"
};

export const LEVEL_COLORS: Record<number, string> = {
  1: "var(--color-danger-text, #b91c1c)",
  2: "var(--color-warn-text, #b45309)",
  3: "var(--color-info-text, #0369a1)",
  4: "var(--color-success-text, #047857)",
  5: "var(--color-success-text, #047857)"
};

export const FALLBACK_LEVEL_COLOR = "var(--color-info-text, #0369a1)";

export type ScoreTone = "good" | "warn" | "bad" | "info";

/** Maps an LLM scoring status to a human label, a color tone, and a detail hint. */
export const LLM_STATUS_COPY: Record<
  ReadinessLlm["status"],
  { label: string; tone: ScoreTone; fallbackDetail: string }
> = {
  scored: { label: "LLM-scored", tone: "good", fallbackDetail: "4 criteria judged by an LLM" },
  llm_skipped: { label: "Mechanical-only", tone: "warn", fallbackDetail: "LLM tier not run" },
  llm_error: { label: "LLM error", tone: "bad", fallbackDetail: "judge call failed" },
  pending: { label: "LLM pending", tone: "info", fallbackDetail: "scoring in progress" }
};

export function levelColor(level: number): string {
  return LEVEL_COLORS[level] ?? FALLBACK_LEVEL_COLOR;
}

export function levelLabel(level: number): string {
  return LEVEL_LABELS[level] ?? `L${level}`;
}

export function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Threshold tone for a 0–1 pass ratio. Always paired with a number in the UI (never color-alone). */
export function scoreTone(pct: number): ScoreTone {
  if (pct >= 0.8) return "good";
  if (pct >= 0.4) return "warn";
  return "bad";
}

export function topFailingCriteria(criteria: ReadinessCriterion[]): ReadinessCriterion[] {
  return [...criteria]
    .filter((c) => c.passed === false)
    .sort((a, b) => a.level - b.level);
}

export function buildRadarData(pillars: ReadinessPillar[]): Array<{ subject: string; score: number }> {
  return pillars.map((p) => ({
    subject: p.name,
    score: Math.round(p.pass_pct * 100)
  }));
}

export type CriteriaStats = {
  total: number;
  passed: number;
  failed: number;
  notApplicable: number;
  llmJudged: number;
};

export function criteriaStats(criteria: ReadinessCriterion[]): CriteriaStats {
  return criteria.reduce<CriteriaStats>(
    (acc, c) => ({
      total: acc.total + 1,
      passed: acc.passed + (c.passed === true ? 1 : 0),
      failed: acc.failed + (c.passed === false ? 1 : 0),
      notApplicable: acc.notApplicable + (c.applicable ? 0 : 1),
      llmJudged: acc.llmJudged + (c.llm ? 1 : 0)
    }),
    { total: 0, passed: 0, failed: 0, notApplicable: 0, llmJudged: 0 }
  );
}

/** Groups criteria by pillar id, preserving pillar order from the pillars array. */
export function groupCriteriaByPillar(
  pillars: ReadinessPillar[],
  criteria: ReadinessCriterion[]
): Array<{ pillar: ReadinessPillar; items: ReadinessCriterion[] }> {
  const groups = pillars.map((pillar) => ({
    pillar,
    items: criteria.filter((c) => c.pillar === pillar.id)
  }));
  const known = new Set(pillars.map((p) => p.id));
  const orphans = criteria.filter((c) => !known.has(c.pillar));
  if (orphans.length > 0) {
    const orphanPillars = [...new Set(orphans.map((c) => c.pillar))];
    for (const id of orphanPillars) {
      groups.push({
        pillar: { id, name: id, pass_pct: 0, numerator: 0, denominator: 0, level_pass: [] },
        items: orphans.filter((c) => c.pillar === id)
      });
    }
  }
  return groups.filter((g) => g.items.length > 0);
}

/** Native-tooltip text for a criterion pip: id, level, LLM flag, explanation, fix. */
export function criterionTitle(c: ReadinessCriterion): string {
  const lines = [`${c.id} · ${levelLabel(c.level)}${c.llm ? " · LLM-judged" : ""}`];
  if (c.explanation) lines.push("", c.explanation);
  if (c.passed === false && c.remediation) lines.push("", `Fix: ${c.remediation}`);
  return lines.join("\n");
}
