"use client";

import { Sparkline } from "@/components/viz/sparkline";
import { gradeTone, normalizeGrade } from "@/lib/tone";
import type { Grade, Tone } from "@/lib/tone";

// ─── Grade ↔ plotted height ───────────────────────────────────────────────────

/** Worst to best, so a grade's index is its height on the sparkline. */
const GRADES_WORST_FIRST: readonly Grade[] = ["F", "D", "C", "B", "A"];

const TONE_COLORS: Record<Tone, string> = {
  good: "var(--color-success-text)",
  info: "var(--color-info-text)",
  warn: "var(--color-warn-text)",
  bad: "var(--color-danger-text)",
  neutral: "var(--color-text-muted)"
};

function gradeHeight(raw: string | null): number | null {
  const grade = normalizeGrade(raw);
  return grade === null ? null : GRADES_WORST_FIRST.indexOf(grade);
}

function colorForHeight(height: number): string {
  return TONE_COLORS[gradeTone(GRADES_WORST_FIRST[Math.round(height)])];
}

// ─── Component ───────────────────────────────────────────────────────────────

export type SentinelTrendRun = {
  readonly grade: string | null;
  readonly timestamp: string | null;
};

/**
 * Client wrapper that owns the grade→height and tone→colour closures so the
 * server component never passes a function across the server→client boundary.
 */
export function SentinelSparklineClient({ runs }: { readonly runs: readonly SentinelTrendRun[] }) {
  const points = runs.map((run, index) => ({
    x: run.timestamp ?? String(index + 1),
    y: gradeHeight(run.grade)
  }));

  return (
    <Sparkline
      series={[{ label: "Health", color: "var(--color-accent)", points }]}
      colorForValue={colorForHeight}
    />
  );
}
