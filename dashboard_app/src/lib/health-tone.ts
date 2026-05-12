/**
 * Pure health-tone aggregation utilities for the Metrics page.
 *
 * No I/O, no React, no server-only imports — this module is used from the
 * "use client" MetricsDashboard component so it must stay browser-safe.
 */

import type { MetricTone } from "@/lib/metrics";

// ─── Types ────────────────────────────────────────────────────────────────────

export type HealthLabel =
  | "IMPROVING"
  | "STABLE"
  | "WORSENING"
  | "BASELINE CAPTURED";

export type HealthSummary = {
  /** Primary one-word health label. */
  label: HealthLabel;
  /** True when at least one collector is degraded (unavailable/error/timeout). */
  degraded: boolean;
  /**
   * Optional note appended to the label when a collector is degraded.
   * e.g. "· data confidence reduced (ruff unavailable)"
   */
  degradedNote: string | null;
};

// ─── metricTone ──────────────────────────────────────────────────────────────

export type ToneResult = {
  /** Semantic tone from the existing MetricTone type. */
  tone: MetricTone;
  /** Direction arrow glyph. */
  arrow: "↗" | "↘" | "→";
  /** Human-readable word. */
  word: string;
};

/**
 * Derives a tone + arrow + word from a metric's current and previous values.
 *
 * - `previous === null` → baseline (no comparison available)
 * - values equal within epsilon → steady
 * - `betterDirection === "lower"` → lower current is good → arrow ↘ for good
 * - `betterDirection === "higher"` → higher current is good → arrow ↗ for good
 */
export function metricTone(
  current: number | null,
  previous: number | null,
  betterDirection: "lower" | "higher"
): ToneResult {
  if (previous === null || current === null) {
    return { tone: "neutral", arrow: "→", word: "baseline" };
  }

  const EPSILON = 1e-9;
  const diff = current - previous;

  if (Math.abs(diff) < EPSILON) {
    return { tone: "steady", arrow: "→", word: "stable" };
  }

  // For "lower is better": diff < 0 means improved.
  // For "higher is better": diff > 0 means improved.
  const improved = betterDirection === "lower" ? diff < 0 : diff > 0;

  if (improved) {
    return { tone: "good", arrow: "↘", word: "improving" };
  }

  return { tone: "bad", arrow: "↗", word: "worsening" };
}

// ─── healthSummary ────────────────────────────────────────────────────────────

/**
 * Aggregates the 4 KPI tones into a single health label.
 *
 * Aggregation rule (simple majority):
 * - If tones is empty → "STABLE" (no crash)
 * - Any tone is "neutral" and all tones are "neutral" → "BASELINE CAPTURED"
 *   (handled by the caller passing opts.isBaseline when only 1 snapshot)
 * - Majority "good" (>= half) with no "bad" → "IMPROVING"
 * - Any "bad" present → "WORSENING"
 * - Otherwise → "STABLE"
 *
 * The "BASELINE CAPTURED" case is driven by opts.isBaseline because the caller
 * (MetricsDashboard) knows whether exactly one snapshot is selected.
 */
export function healthSummary(
  tones: MetricTone[],
  opts?: {
    degradedCollectors?: string[];
    isBaseline?: boolean;
  }
): HealthSummary {
  const degradedCollectors = opts?.degradedCollectors ?? [];
  const degraded = degradedCollectors.length > 0;
  const degradedNote = degraded
    ? `· data confidence reduced (${degradedCollectors.join(", ")} unavailable)`
    : null;

  if (opts?.isBaseline === true) {
    return { label: "BASELINE CAPTURED", degraded, degradedNote };
  }

  if (tones.length === 0) {
    return { label: "STABLE", degraded, degradedNote };
  }

  const badCount = tones.filter((t) => t === "bad").length;
  const goodCount = tones.filter((t) => t === "good").length;

  if (badCount > 0) {
    return { label: "WORSENING", degraded, degradedNote };
  }

  if (goodCount >= Math.ceil(tones.length / 2)) {
    return { label: "IMPROVING", degraded, degradedNote };
  }

  return { label: "STABLE", degraded, degradedNote };
}
