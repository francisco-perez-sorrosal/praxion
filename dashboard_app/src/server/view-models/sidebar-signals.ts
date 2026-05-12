/**
 * Thin composition layer for sidebar live-signal data.
 *
 * Reads active-workshop count and latest sentinel grade from the existing
 * view-models and returns the minimal shape needed by SidebarNav. This is
 * the first-cut piece that the future /overview route will reuse when it
 * aggregates project health into a landing surface.
 *
 * Degrades gracefully: if either underlying read fails or returns empty,
 * the corresponding field returns a safe zero/null sentinel.
 */
import "server-only";

import { getSentinelData } from "@/server/view-models/sentinel";
import { getWorkshopsData } from "@/server/view-models/workshops";

export type SidebarSignals = {
  /** Primary field name — use this in new code. */
  activeWorkshops: number;
  /**
   * Alias for activeWorkshops — both fields always carry the same value.
   * Retained for backward-compatibility with early tests and future
   * /overview consumers that may prefer the more explicit name.
   */
  activeWorkshopCount: number;
  sentinelGrade: string | null;
};

/**
 * A workshop is considered active when WIP.md has been parsed and the status
 * is neither COMPLETE nor absent. Workshops with status===null haven't been
 * started yet or have no WIP.md — not active.
 */
function countActiveWorkshops(
  workshops: Awaited<ReturnType<typeof getWorkshopsData>>
): number {
  return workshops.filter(
    (w) => w.status !== null && w.status.toUpperCase() !== "COMPLETE"
  ).length;
}

function extractLatestGrade(
  sentinelData: Awaited<ReturnType<typeof getSentinelData>>
): string | null {
  if (sentinelData.latest === null) {
    return null;
  }
  // Grade is a single letter (A/B/C/D/F) in the sentinel log series.
  // SENTINEL_LOG.md rows are in document/chronological order — the last row is
  // the most recent run. Use the last entry in logSeries.
  const series = sentinelData.logSeries;
  const latestPoint = series.length > 0 ? series[series.length - 1] : undefined;
  if (latestPoint?.grade) {
    return latestPoint.grade;
  }
  // Fallback: read from latest report frontmatter data field.
  const grade = sentinelData.latest.data["health_grade"] as string | undefined;
  return typeof grade === "string" && grade.length === 1 ? grade : null;
}

export async function getSidebarSignals(projectRoot: string): Promise<SidebarSignals> {
  const [workshopsResult, sentinelResult] = await Promise.allSettled([
    getWorkshopsData(projectRoot),
    getSentinelData(projectRoot)
  ]);

  const activeWorkshops =
    workshopsResult.status === "fulfilled"
      ? countActiveWorkshops(workshopsResult.value)
      : 0;

  const sentinelGrade =
    sentinelResult.status === "fulfilled"
      ? extractLatestGrade(sentinelResult.value)
      : null;

  return { activeWorkshops, activeWorkshopCount: activeWorkshops, sentinelGrade };
}
