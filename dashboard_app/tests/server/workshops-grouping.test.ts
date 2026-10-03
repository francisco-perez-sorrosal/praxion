import { describe, expect, it } from "vitest";

import { ACTIVE_WINDOW_DAYS, groupWorkshops, progressSummary } from "@/lib/workshops";

const NOW = new Date("2026-10-02T15:00:00.000Z");
const DAY_MS = 24 * 60 * 60 * 1000;

type Entry = { name: string; isDone: boolean; updatedAt: string | null };

function entry(name: string, daysAgo: number | null, isDone = false): Entry {
  return {
    name,
    isDone,
    updatedAt: daysAgo === null ? null : new Date(NOW.getTime() - daysAgo * DAY_MS).toISOString()
  };
}

function names(list: Entry[]): string[] {
  return list.map((item) => item.name);
}

describe("groupWorkshops", () => {
  it("keeps the window at seven days", () => {
    expect(ACTIVE_WINDOW_DAYS).toBe(7);
  });

  it("splits unfinished workshops at the window edge", () => {
    const groups = groupWorkshops(
      [entry("inside", 6.9), entry("on-the-edge", 7), entry("outside", 7.1)],
      NOW
    );

    expect(names(groups.active)).toEqual(["inside", "on-the-edge"]);
    expect(names(groups.stale)).toEqual(["outside"]);
    expect(groups.done).toEqual([]);
  });

  it("lets done beat both active and stale", () => {
    const groups = groupWorkshops([entry("fresh-done", 0.1, true), entry("old-done", 90, true)], NOW);

    expect(names(groups.done)).toEqual(["fresh-done", "old-done"]);
    expect(groups.active).toEqual([]);
    expect(groups.stale).toEqual([]);
  });

  it("orders every group newest first", () => {
    const groups = groupWorkshops(
      [
        entry("a-3d", 3),
        entry("a-1h", 0.04),
        entry("s-30d", 30),
        entry("s-9d", 9),
        entry("d-5d", 5, true),
        entry("d-1d", 1, true)
      ],
      NOW
    );

    expect(names(groups.active)).toEqual(["a-1h", "a-3d"]);
    expect(names(groups.stale)).toEqual(["s-9d", "s-30d"]);
    expect(names(groups.done)).toEqual(["d-1d", "d-5d"]);
  });

  it("counts a workshop with no activity stamp as stale, after the stamped ones", () => {
    const groups = groupWorkshops([entry("unstamped", null), entry("old", 20)], NOW);

    expect(names(groups.stale)).toEqual(["old", "unstamped"]);
  });

  it("counts an unparseable stamp as stale", () => {
    const groups = groupWorkshops([{ name: "garbled", isDone: false, updatedAt: "not-a-date" }], NOW);

    expect(names(groups.stale)).toEqual(["garbled"]);
  });

  it("honours an explicit window", () => {
    const groups = groupWorkshops([entry("two-days", 2)], NOW, 1);

    expect(names(groups.stale)).toEqual(["two-days"]);
  });

  it("does not mutate its input", () => {
    const input = [entry("old", 20), entry("new", 1)];
    groupWorkshops(input, NOW);

    expect(names(input)).toEqual(["old", "new"]);
  });
});

describe("progressSummary", () => {
  it("is null when no checklist was parsed", () => {
    expect(progressSummary([])).toBeNull();
  });

  it("counts checked steps over the total", () => {
    expect(progressSummary([{ checked: true }, { checked: false }, { checked: true }, { checked: false }])).toEqual({
      done: 2,
      total: 4
    });
  });

  it("reports a finished checklist as total over total", () => {
    expect(progressSummary([{ checked: true }, { checked: true }])).toEqual({ done: 2, total: 2 });
  });
});
