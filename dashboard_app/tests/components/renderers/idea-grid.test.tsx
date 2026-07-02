// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { IdeaGridRenderer } from "@/components/renderers/idea-grid";

afterEach(() => {
  cleanup();
});

// IDEA_LEDGER.md-shaped markdown — headings match the real ledger file
// (.ai-state/idea_ledgers/IDEA_LEDGER.md): Implemented / Pending / Discarded.
const LEDGER_BODY = `# Idea Ledger

## Implemented

- Shipped the export button.

## Pending

- Under review: dark mode toggle.
- Queued: keyboard shortcuts.

## Discarded

- Rejected for duplicate scope.
`;

// Only one of the three recognized sections present — still expected to render
// (the fallback trigger is "none of the three present", not "all three required").
const PARTIAL_LEDGER_BODY = `# Idea Ledger

## Pending

- Queued: keyboard shortcuts.
`;

const NO_LEDGER_SECTIONS_BODY = "# Random doc\n\nJust prose, no ledger structure.";

describe("IdeaGridRenderer — status-column grid", () => {
  it("renders the Implemented, Pending, and Discarded sections as labelled status columns", () => {
    const { container } = render(<IdeaGridRenderer body={LEDGER_BODY} />);

    const grid = container.querySelector(".renderer-idea-grid");
    expect(grid).toBeTruthy();
    expect(grid?.textContent).toMatch(/Implemented/);
    expect(grid?.textContent).toMatch(/Pending/);
    expect(grid?.textContent).toMatch(/Discarded/);
  });

  it("still renders the grid when only a subset of the three sections is present", () => {
    const { container } = render(<IdeaGridRenderer body={PARTIAL_LEDGER_BODY} />);

    expect(container.querySelector(".renderer-idea-grid")).toBeTruthy();
  });

  it("falls back to the default shell when none of the three ledger sections are present", () => {
    const { container } = render(
      <IdeaGridRenderer body={NO_LEDGER_SECTIONS_BODY} />
    );

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-idea-grid")).toBeFalsy();
  });
});
