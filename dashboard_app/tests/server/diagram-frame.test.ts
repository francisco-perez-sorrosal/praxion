/**
 * Behavioral tests for DiagramFrame, DiagramModal (static markup), and
 * the re-homed usePanZoom pure-math functions.
 *
 * Test environment: vitest node (no DOM). Components are rendered to a static
 * HTML string via renderToStaticMarkup so we can assert on server-rendered
 * markup without a browser. React hooks execute in their initial state.
 *
 * Interactive behaviors that require a live DOM (focus-trap, Escape key,
 * wheel zoom, pointer drag) cannot be verified here — they need a manual or
 * e2e check in the verifier's review pass.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

// ─── Fixture helpers ─────────────────────────────────────────────────────────

/**
 * A minimal normalized SVG string that mimics what normalizeSvg produces:
 * - no width/height attrs on the root <svg>
 * - has viewBox, preserveAspectRatio
 * - has data-aspect / data-vb-w / data-vb-h
 */
const NORMALIZED_SVG = `<svg id="my-svg" viewBox="-50 -10 1645.5 597" preserveAspectRatio="xMidYMid meet" data-aspect="2.7563" data-vb-w="1645.5" data-vb-h="597"><rect x="0" y="0" width="100" height="100" /></svg>`;

/**
 * A normalized SVG whose aspect ratio is unmeasurable (no viewBox, no
 * data-aspect). Represents the degraded path described in the systems plan.
 */
const UNMEASURABLE_SVG = `<svg><rect x="0" y="0" width="50" height="50" /></svg>`;

/**
 * An SVG that retains width="100%" as it would appear if normalization had NOT
 * been applied. Used to guard the regression described in the systems plan.
 */
const UNNORMALIZED_SVG = `<svg width="100%" style="max-width: 1645.5px; background-color: white;" viewBox="-50 -10 1645.5 597"><rect /></svg>`;

// ─── DiagramFrame ─────────────────────────────────────────────────────────────

describe("DiagramFrame — renders the SVG inline in the server markup", () => {
  it("includes the svg element with its viewBox in the rendered markup", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    expect(html).toContain("<svg");
    expect(html).toContain('viewBox="-50 -10 1645.5 597"');
  });

  it("preserves data-aspect in the rendered SVG markup", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    expect(html).toContain('data-aspect="2.7563"');
  });
});

describe("DiagramFrame — sets an aspect-ratio box when the SVG is measurable", () => {
  it("renders a box element whose style contains the aspect-ratio value", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    // The aspect-ratio CSS property is set from data-aspect="2.7563"
    // React serializes the style object as style="aspect-ratio:2.7563"
    expect(html).toMatch(/aspect-ratio/);
    expect(html).toContain("2.7563");
  });

  it("applies the aspect ratio from the SVG data-aspect attribute", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    // Use a different aspect ratio to confirm it reads from the SVG, not a hardcoded value
    const svgWithOtherAspect = NORMALIZED_SVG.replace(
      'data-aspect="2.7563"',
      'data-aspect="1.5000"'
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: svgWithOtherAspect, label: "Flow" })
    );

    expect(html).toMatch(/aspect-ratio/);
    expect(html).toContain("1.5");
  });
});

describe("DiagramFrame — degrades gracefully when the SVG is unmeasurable", () => {
  it("does not throw when no data-aspect is present", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    expect(() =>
      renderToStaticMarkup(
        createElement(DiagramFrame, { svg: UNMEASURABLE_SVG, label: "Unknown" })
      )
    ).not.toThrow();
  });

  it("still emits the figure and the SVG markup when unmeasurable", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: UNMEASURABLE_SVG, label: "Unknown" })
    );

    expect(html).toContain("<figure");
    expect(html).toContain("<svg");
  });

  it("does not emit an aspect-ratio style when there is no data-aspect", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: UNMEASURABLE_SVG, label: "Unknown" })
    );

    expect(html).not.toMatch(/aspect-ratio/);
  });
});

describe("DiagramFrame — has the Expand affordance", () => {
  it("renders a button element", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    expect(html).toContain("<button");
  });

  it("button accessible name includes 'Expand'", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    // Either the button text or the aria-label contains "Expand"
    const hasExpand =
      html.includes("Expand") ||
      html.includes("expand");
    expect(hasExpand).toBe(true);
  });

  it("button accessible name references the diagram label", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "ADR Finalize Flow" })
    );

    expect(html).toContain("ADR Finalize Flow");
  });
});

describe("DiagramFrame — guards the width='100%' regression", () => {
  it("does not emit width=\"100%\" on the root svg when svg is normalized", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    // The normalized SVG has no width attr; the rendered markup must not re-introduce it
    expect(html).not.toContain('width="100%"');
  });

  it("does not emit max-width on the root svg style when svg is normalized", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    const html = renderToStaticMarkup(
      createElement(DiagramFrame, { svg: NORMALIZED_SVG, label: "Agent Pipeline" })
    );

    expect(html).not.toMatch(/max-width/);
  });

  it("unnormalized SVG still renders without crashing (regression guard does not throw)", async () => {
    const { DiagramFrame } = await import(
      "@/components/viz/diagram-frame"
    );

    // Guard: if a caller passes an unnormalized SVG, DiagramFrame must not throw
    expect(() =>
      renderToStaticMarkup(
        createElement(DiagramFrame, { svg: UNNORMALIZED_SVG, label: "Broken" })
      )
    ).not.toThrow();
  });
});

// ─── DiagramModal ─────────────────────────────────────────────────────────────
//
// NOTE: DiagramModal is a "use client" component that only renders its content
// when `isOpen` is true (or when conditionally mounted by the parent). The
// contract below covers the open-state static markup.
//
// Runtime behaviors that CANNOT be tested in node-env (manual/e2e required):
//   - focus trap: Tab stays inside the modal
//   - Escape key closes the modal and returns focus to the trigger
//   - Wheel zoom, pointer drag, keyboard +/-/0/arrows
//   - Focus return to the Expand trigger on close
//
// The verifier must validate these via keyboard walk + screen-reader check.

describe("DiagramModal — open-state static markup has the required a11y attributes", () => {
  it("renders role='dialog' when open", async () => {
    // Deferred import: DiagramModal may not exist when tests first run (concurrent BDD/TDD).
    // If the module is absent, this test is expected to fail with ImportError — RED state.
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    expect(html).toContain('role="dialog"');
  });

  it("renders aria-modal='true' when open", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    expect(html).toContain('aria-modal="true"');
  });

  it("renders aria-labelledby pointing to a caption element", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    expect(html).toContain("aria-labelledby=");
  });

  it("includes the SVG markup inline in the modal", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    expect(html).toContain("<svg");
    expect(html).toContain('data-aspect="2.7563"');
  });

  it("includes a zoom-in control button", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    // Accessible name must convey "zoom in" — accept aria-label or visible text
    const hasZoomIn =
      /zoom.?in/i.test(html) ||
      /aria-label="[^"]*\+[^"]*"/i.test(html) ||
      html.includes("zoom-in") ||
      html.includes("zoomIn");
    expect(hasZoomIn, "zoom-in control not found in modal markup").toBe(true);
  });

  it("includes a zoom-out control button", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    const hasZoomOut =
      /zoom.?out/i.test(html) ||
      /aria-label="[^"]*−[^"]*"/i.test(html) ||
      html.includes("zoom-out") ||
      html.includes("zoomOut");
    expect(hasZoomOut, "zoom-out control not found in modal markup").toBe(true);
  });

  it("includes a fit/reset control button", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    const hasFitOrReset =
      /\bfit\b/i.test(html) ||
      /\breset\b/i.test(html);
    expect(hasFitOrReset, "fit/reset control not found in modal markup").toBe(true);
  });

  it("includes a close control button", async () => {
    const { DiagramModal } = await import(
      "@/components/viz/diagram-modal"
    );

    const triggerRef = { current: null } as React.RefObject<HTMLElement | null>;

    const html = renderToStaticMarkup(
      createElement(DiagramModal, {
        svg: NORMALIZED_SVG,
        label: "Agent Pipeline",
        onClose: () => undefined,
        triggerRef
      })
    );

    const hasClose =
      /\bclose\b/i.test(html) ||
      /aria-label="[^"]*close[^"]*"/i.test(html) ||
      html.includes("×") ||
      html.includes("✕");
    expect(hasClose, "close control not found in modal markup").toBe(true);
  });
});

// ─── usePanZoom pure math — re-homed from diagram-viewer.test.ts ──────────────
//
// These tests guard the pure math functions exported from use-pan-zoom.ts.
// They were previously in diagram-viewer.test.ts, which was removed when
// DiagramViewer was split into DiagramFrame + DiagramModal. Re-homing them here
// keeps that coverage. The math itself is unchanged.

describe("clampScale — enforces [minZoom, maxZoom] bounds", () => {
  it("returns the value unchanged when within bounds", async () => {
    const { clampScale } = await import("@/components/viz/use-pan-zoom");
    expect(clampScale(1.5, 0.25, 8)).toBe(1.5);
  });

  it("clamps to minZoom when value is below lower bound", async () => {
    const { clampScale } = await import("@/components/viz/use-pan-zoom");
    expect(clampScale(0.1, 0.25, 8)).toBe(0.25);
  });

  it("clamps to maxZoom when value exceeds upper bound", async () => {
    const { clampScale } = await import("@/components/viz/use-pan-zoom");
    expect(clampScale(10, 0.25, 8)).toBe(8);
  });

  it("returns exact boundary when value equals minZoom", async () => {
    const { clampScale } = await import("@/components/viz/use-pan-zoom");
    expect(clampScale(0.25, 0.25, 8)).toBe(0.25);
  });

  it("returns exact boundary when value equals maxZoom", async () => {
    const { clampScale } = await import("@/components/viz/use-pan-zoom");
    expect(clampScale(8, 0.25, 8)).toBe(8);
  });
});

describe("zoomAtCursor — cursor world position stays fixed under zoom", () => {
  it("zooms in at the cursor: world coordinate under cursor is invariant", async () => {
    const { zoomAtCursor } = await import("@/components/viz/use-pan-zoom");
    const current = { x: 0, y: 0, scale: 1 };
    const result = zoomAtCursor(current, 50, 50, -100, 0.25, 8);
    expect(result.scale).toBeGreaterThan(1);
    const worldXBefore = (50 - current.x) / current.scale;
    const worldXAfter = (50 - result.x) / result.scale;
    expect(worldXAfter).toBeCloseTo(worldXBefore, 5);
  });

  it("zooms out (positive delta) producing a smaller scale", async () => {
    const { zoomAtCursor } = await import("@/components/viz/use-pan-zoom");
    const current = { x: 0, y: 0, scale: 2 };
    const result = zoomAtCursor(current, 100, 100, 200, 0.25, 8);
    expect(result.scale).toBeLessThan(2);
  });

  it("clamps scale at maxZoom when zooming beyond the upper bound", async () => {
    const { zoomAtCursor } = await import("@/components/viz/use-pan-zoom");
    const current = { x: 0, y: 0, scale: 7.9 };
    const result = zoomAtCursor(current, 50, 50, -5000, 0.25, 8);
    expect(result.scale).toBe(8);
  });

  it("clamps scale at minZoom when zooming beyond the lower bound", async () => {
    const { zoomAtCursor } = await import("@/components/viz/use-pan-zoom");
    const current = { x: 0, y: 0, scale: 0.3 };
    const result = zoomAtCursor(current, 50, 50, 5000, 0.25, 8);
    expect(result.scale).toBe(0.25);
  });

  it("preserves cursor world position when zooming in at an offset cursor", async () => {
    const { zoomAtCursor } = await import("@/components/viz/use-pan-zoom");
    const current = { x: 20, y: 30, scale: 1 };
    const cursorX = 80;
    const cursorY = 60;
    const result = zoomAtCursor(current, cursorX, cursorY, -100, 0.25, 8);
    const worldXBefore = (cursorX - current.x) / current.scale;
    const worldYBefore = (cursorY - current.y) / current.scale;
    const worldXAfter = (cursorX - result.x) / result.scale;
    const worldYAfter = (cursorY - result.y) / result.scale;
    expect(worldXAfter).toBeCloseTo(worldXBefore, 5);
    expect(worldYAfter).toBeCloseTo(worldYBefore, 5);
  });
});

describe("fitTransform — centers and fits content within container", () => {
  it("scales down content that exceeds container dimensions", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 800, 600);
    expect(result.scale).toBeLessThanOrEqual(1);
    expect(result.scale * 800).toBeLessThanOrEqual(400 + 0.001);
    expect(result.scale * 600).toBeLessThanOrEqual(300 + 0.001);
  });

  it("does not scale up content smaller than the container", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 100, 80);
    expect(result.scale).toBe(1);
  });

  it("centers content horizontally when constrained by height", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 100, 400);
    const scaledW = 100 * result.scale;
    const expectedX = (400 - scaledW) / 2;
    expect(result.x).toBeCloseTo(expectedX, 5);
  });

  it("centers content vertically when constrained by width", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 800, 100);
    const scaledH = 100 * result.scale;
    const expectedY = (300 - scaledH) / 2;
    expect(result.y).toBeCloseTo(expectedY, 5);
  });

  it("returns identity transform for zero-dimension content", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 0, 0);
    expect(result).toEqual({ x: 0, y: 0, scale: 1 });
  });

  it("produces an exact fit when content matches container", async () => {
    const { fitTransform } = await import("@/components/viz/use-pan-zoom");
    const result = fitTransform(400, 300, 400, 300);
    expect(result.scale).toBeCloseTo(1, 5);
    expect(result.x).toBeCloseTo(0, 5);
    expect(result.y).toBeCloseTo(0, 5);
  });
});

describe("panByKey — arrow-key pan moves translate by 20px", () => {
  it("ArrowLeft moves content right (x increases by 20px)", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    const base = { x: 0, y: 0, scale: 1 };
    const result = panByKey(base, "ArrowLeft");
    expect(result.x).toBe(20);
    expect(result.y).toBe(0);
    expect(result.scale).toBe(1);
  });

  it("ArrowRight moves content left (x decreases by 20px)", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    const base = { x: 0, y: 0, scale: 1 };
    const result = panByKey(base, "ArrowRight");
    expect(result.x).toBe(-20);
    expect(result.y).toBe(0);
  });

  it("ArrowUp moves content down (y increases by 20px)", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    const base = { x: 0, y: 0, scale: 1 };
    const result = panByKey(base, "ArrowUp");
    expect(result.x).toBe(0);
    expect(result.y).toBe(20);
  });

  it("ArrowDown moves content up (y decreases by 20px)", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    const base = { x: 0, y: 0, scale: 1 };
    const result = panByKey(base, "ArrowDown");
    expect(result.x).toBe(0);
    expect(result.y).toBe(-20);
  });

  it("preserves the existing scale across a pan operation", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    const t = { x: 10, y: 5, scale: 2.5 };
    const result = panByKey(t, "ArrowLeft");
    expect(result.scale).toBe(2.5);
  });

  it("accumulates correctly across multiple pans", async () => {
    const { panByKey } = await import("@/components/viz/use-pan-zoom");
    let t = { x: 0, y: 0, scale: 1 };
    t = panByKey(t, "ArrowLeft");
    t = panByKey(t, "ArrowLeft");
    t = panByKey(t, "ArrowDown");
    expect(t.x).toBe(40);
    expect(t.y).toBe(-20);
  });
});
