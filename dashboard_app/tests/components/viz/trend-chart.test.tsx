// @vitest-environment jsdom
/**
 * TrendChart wraps recharts. jsdom has no ResizeObserver, so recharts'
 * <ResponsiveContainer> measures a 0x0 box and never renders its children —
 * confirmed empirically before writing these tests. The polyfill below (a
 * no-op ResizeObserver plus a fixed getBoundingClientRect) gives it a real
 * size so the <svg> and series lines render.
 *
 * Degradation taken (per the plan's pre-mortem #5): recharts' internal
 * hover/tooltip mouse tracking does not respond to synthetic pointer events
 * under jsdom even with the polyfill above (verified empirically — a
 * fireEvent mouseMove/mouseOver over the chart surface never flips the
 * tooltip wrapper's visibility). Hover-tooltip interaction is out of scope
 * here; these tests cover render-only "SVG renders with expected series"
 * plus the legend chip, which is a plain React click handler with no
 * recharts/SVG-measurement dependency and remains reliably testable as a
 * real interaction. See LEARNINGS.md for the full note.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TrendChart, type TrendSeries } from "@/components/viz/trend-chart";

class FakeResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  global.ResizeObserver = FakeResizeObserver;
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 600,
    height: 200,
    top: 0,
    left: 0,
    bottom: 200,
    right: 600,
    x: 0,
    y: 0,
    toJSON: () => undefined
  } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // @ts-expect-error -- undo the polyfill so it does not leak into other files
  delete global.ResizeObserver;
});

function twoSeries(): TrendSeries[] {
  return [
    {
      label: "Coverage",
      color: "#5b4fca",
      points: [
        { x: "2026-01-01", y: 80 },
        { x: "2026-01-02", y: 82 }
      ]
    },
    {
      label: "CCN p95",
      color: "#e08a2c",
      points: [
        { x: "2026-01-01", y: 9 },
        { x: "2026-01-02", y: 8 }
      ]
    }
  ];
}

describe("TrendChart — renders the SVG chart with one line per series", () => {
  it("draws a line path for each series, in each series' own color", () => {
    const { container } = render(<TrendChart series={twoSeries()} height={200} />);

    const lines = container.querySelectorAll(".recharts-line-curve");
    expect(lines).toHaveLength(2);
    const strokes = Array.from(lines).map((el) => el.getAttribute("stroke"));
    expect(strokes).toEqual(["#5b4fca", "#e08a2c"]);
  });
});

describe("TrendChart — legend chip toggles a series' visibility", () => {
  it("removes the series line when its chip is clicked and restores it on a second click", async () => {
    const user = userEvent.setup();
    const { container } = render(<TrendChart series={twoSeries()} height={200} />);
    const chip = screen.getByRole("button", { name: /Coverage/i });

    await user.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(1);

    await user.click(chip);
    expect(chip.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(2);
  });
});
