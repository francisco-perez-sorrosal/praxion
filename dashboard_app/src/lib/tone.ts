/**
 * One tone vocabulary for every status the dashboard shows.
 *
 * Grades, health words and verdicts all collapse to a `Tone`; tiles, chips and
 * badges render the tone with a glyph or word beside the colour, so meaning is
 * never carried by colour alone. Pure module: no React, no filesystem.
 */
import type { HealthLabel } from "@/lib/health-tone";

export type Tone = "good" | "info" | "warn" | "bad" | "neutral";

export type Grade = "A" | "B" | "C" | "D" | "F";

export type GradeVariant = "grade-a" | "grade-b" | "grade-c" | "grade-d" | "grade-f" | "neutral";

const GRADES: readonly Grade[] = ["A", "B", "C", "D", "F"];

const GRADE_TONES: Record<Grade, Tone> = {
  A: "good",
  B: "info",
  C: "warn",
  D: "bad",
  F: "bad"
};

const GRADE_VARIANTS: Record<Grade, GradeVariant> = {
  A: "grade-a",
  B: "grade-b",
  C: "grade-c",
  D: "grade-d",
  F: "grade-f"
};

const HEALTH_TONES: Record<HealthLabel, Tone> = {
  IMPROVING: "good",
  STABLE: "neutral",
  WORSENING: "bad",
  "BASELINE CAPTURED": "info"
};

const VERDICT_TONES: Record<string, Tone> = {
  PASS: "good",
  WARN: "warn",
  FAIL: "bad",
  SKIP: "neutral"
};

/** Glyph rendered beside a tone so colour-blind readers see the same meaning. */
export const TONE_GLYPHS: Record<Tone, string> = {
  good: "✓",
  info: "i",
  warn: "!",
  bad: "✕",
  neutral: "·"
};

/** Trend arrows for the metrics health words (word + arrow, never arrow alone). */
export const HEALTH_ARROWS: Record<HealthLabel, string> = {
  IMPROVING: "↗",
  STABLE: "→",
  WORSENING: "↘",
  "BASELINE CAPTURED": "·"
};

/** Upper-cases and validates a grade letter; anything else is `null`. */
export function normalizeGrade(raw: string | null | undefined): Grade | null {
  if (typeof raw !== "string") {
    return null;
  }
  const letter = raw.trim().toUpperCase();
  return (GRADES as readonly string[]).includes(letter) ? (letter as Grade) : null;
}

export function gradeTone(raw: string | null | undefined): Tone {
  const grade = normalizeGrade(raw);
  return grade === null ? "neutral" : GRADE_TONES[grade];
}

export function gradeChipVariant(raw: string | null | undefined): GradeVariant {
  const grade = normalizeGrade(raw);
  return grade === null ? "neutral" : GRADE_VARIANTS[grade];
}

export function healthLabelTone(label: HealthLabel | null | undefined): Tone {
  return label ? HEALTH_TONES[label] : "neutral";
}

export function verdictTone(verdict: string | null | undefined): Tone {
  if (typeof verdict !== "string") {
    return "neutral";
  }
  return VERDICT_TONES[verdict.trim().toUpperCase()] ?? "neutral";
}

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const MONTH_MS = 30 * DAY_MS;

function toDate(value: string | Date | null | undefined): Date | null {
  if (value == null) {
    return null;
  }
  const date = typeof value === "string" ? new Date(value) : value;
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Human relative age ("just now", "5 min ago", "3 h ago", "12 d ago", "4 mo ago").
 * `now` is injected so renders and tests are deterministic. Future stamps read
 * "just now" rather than a negative age.
 */
export function relativeAge(value: string | Date | null | undefined, now: Date): string | null {
  const date = toDate(value);
  if (date === null) {
    return null;
  }
  const elapsed = Math.max(0, now.getTime() - date.getTime());
  if (elapsed < MINUTE_MS) {
    return "just now";
  }
  if (elapsed < HOUR_MS) {
    return `${Math.floor(elapsed / MINUTE_MS)} min ago`;
  }
  if (elapsed < DAY_MS) {
    return `${Math.floor(elapsed / HOUR_MS)} h ago`;
  }
  if (elapsed < MONTH_MS) {
    return `${Math.floor(elapsed / DAY_MS)} d ago`;
  }
  return `${Math.floor(elapsed / MONTH_MS)} mo ago`;
}

/** The newest of a set of timestamps, as ISO; `null` when none parses. */
export function newestOf(values: ReadonlyArray<string | Date | null | undefined>): string | null {
  let newest: Date | null = null;
  for (const value of values) {
    const date = toDate(value);
    if (date !== null && (newest === null || date.getTime() > newest.getTime())) {
      newest = date;
    }
  }
  return newest === null ? null : newest.toISOString();
}
