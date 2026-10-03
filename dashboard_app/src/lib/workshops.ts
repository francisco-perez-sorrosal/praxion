/**
 * Workshop recency: which pipelines are running, which were abandoned and
 * which finished. Pure module — `now` is injected so renders and tests agree.
 */
import type { WorkshopProgressItem, WorkshopState } from "@/server/types";

/** A workshop untouched for longer than this many days is stale, not active. */
export const ACTIVE_WINDOW_DAYS = 7;

const DAY_MS = 24 * 60 * 60 * 1000;

export type WorkshopRecency = Pick<WorkshopState, "isDone" | "updatedAt">;

export type WorkshopGroups<T extends WorkshopRecency> = {
  active: T[];
  stale: T[];
  done: T[];
};

export type ProgressSummary = { done: number; total: number };

function activityTime(workshop: WorkshopRecency): number | null {
  if (workshop.updatedAt === null) {
    return null;
  }
  const time = new Date(workshop.updatedAt).getTime();
  return Number.isNaN(time) ? null : time;
}

/** Newest first; a workshop with no readable stamp sorts last. */
function byNewestFirst(left: WorkshopRecency, right: WorkshopRecency): number {
  return (activityTime(right) ?? -Infinity) - (activityTime(left) ?? -Infinity);
}

/**
 * Finished beats everything; otherwise a workshop is active when its newest
 * artifact is no older than the window, and stale when older or unreadable.
 */
export function groupWorkshops<T extends WorkshopRecency>(
  workshops: readonly T[],
  now: Date,
  windowDays: number = ACTIVE_WINDOW_DAYS
): WorkshopGroups<T> {
  const cutoff = now.getTime() - windowDays * DAY_MS;
  const groups: WorkshopGroups<T> = { active: [], stale: [], done: [] };

  for (const workshop of workshops) {
    const touched = activityTime(workshop);
    if (workshop.isDone) {
      groups.done.push(workshop);
    } else if (touched !== null && touched >= cutoff) {
      groups.active.push(workshop);
    } else {
      groups.stale.push(workshop);
    }
  }

  groups.active.sort(byNewestFirst);
  groups.stale.sort(byNewestFirst);
  groups.done.sort(byNewestFirst);
  return groups;
}

/** Done over total checklist steps; `null` when no checklist was parsed. */
export function progressSummary(
  progress: readonly Pick<WorkshopProgressItem, "checked">[]
): ProgressSummary | null {
  if (progress.length === 0) {
    return null;
  }
  return { done: progress.filter((item) => item.checked).length, total: progress.length };
}
