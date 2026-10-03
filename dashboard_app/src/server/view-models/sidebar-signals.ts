/**
 * The live signals at the right edge of the sidebar rows.
 *
 * Each signal follows the rule of the digest the Overview shows, so the two never
 * disagree; the sentinel grade takes the light read, because this runs on every
 * navigation. Every family is read on its own: one that cannot be read leaves
 * only its own signal absent and the rest of the sidebar intact.
 */
import "server-only";

import type { HealthLabel } from "@/lib/health-tone";
import { groupWorkshops } from "@/lib/workshops";
import { digestMetrics, readOrNull } from "@/server/view-models/overview";
import { getMetricsData } from "@/server/view-models/metrics";
import { getPraxionEvalRuns } from "@/server/view-models/praxion-evals";
import { getSentinelSignal } from "@/server/view-models/sentinel";
import { getWorkshopsData } from "@/server/view-models/workshops";

export type SidebarSignals = {
  /** Workshops not finished and touched within the Active window — the Workshops page's Active group. */
  activeWorkshops: number;
  /** Failures of the latest quality-eval run; `null` when no run is logged. */
  evalFails: number | null;
  metricsHealth: HealthLabel | null;
  sentinelGrade: string | null;
};

export async function getSidebarSignals(projectRoot: string, now: Date = new Date()): Promise<SidebarSignals> {
  const [workshops, sentinel, metrics, evalRuns] = await Promise.all([
    readOrNull("sidebar workshops", () => getWorkshopsData(projectRoot)),
    readOrNull("sidebar sentinel", () => getSentinelSignal(projectRoot)),
    readOrNull("sidebar metrics", () => getMetricsData(projectRoot)),
    readOrNull("sidebar quality evals", () => getPraxionEvalRuns(projectRoot))
  ]);

  return {
    activeWorkshops: workshops === null ? 0 : groupWorkshops(workshops, now).active.length,
    evalFails: evalRuns?.at(-1)?.fail ?? null,
    metricsHealth: (metrics === null ? null : digestMetrics(metrics)?.healthLabel) ?? null,
    sentinelGrade: sentinel?.grade ?? null
  };
}
