// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DiagramFrame } from "@/components/viz/diagram-frame";

// jsdom has no ResizeObserver. DiagramModal mounts usePanZoom, which
// instantiates one unconditionally on mount — opening the modal throws
// without this polyfill (see LEARNINGS.md).
class FakeResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeEach(() => {
  global.ResizeObserver = FakeResizeObserver;
});

afterEach(() => {
  cleanup();
  // @ts-expect-error -- undo the polyfill so it does not leak into other files
  delete global.ResizeObserver;
});

const SVG = `<svg viewBox="0 0 100 100" data-aspect="1"><rect width="10" height="10" /></svg>`;

describe("DiagramFrame — Expand opens the fullscreen pan/zoom modal", () => {
  it("opens the modal only after the Expand button is clicked", async () => {
    const user = userEvent.setup();
    render(<DiagramFrame svg={SVG} label="Agent Pipeline" />);

    expect(screen.queryByRole("dialog", { hidden: true })).toBeNull();

    await user.click(screen.getByRole("button", { name: /expand agent pipeline/i }));

    // The modal backdrop carries aria-hidden="true", which hides the nested
    // dialog from the default accessible-role query; { hidden: true } opts
    // back in for this structural assertion (see LEARNINGS.md).
    expect(screen.getByRole("dialog", { hidden: true })).toBeTruthy();
  });
});

describe("DiagramFrame — Escape closes the modal and restores focus", () => {
  it("closes the modal and returns focus to the Expand trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<DiagramFrame svg={SVG} label="Agent Pipeline" />);
    const trigger = screen.getByRole("button", { name: /expand agent pipeline/i });

    await user.click(trigger);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { hidden: true })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
