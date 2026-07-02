// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { ArchitectureExplorerRenderer } from "@/components/renderers/architecture-explorer";

afterEach(() => {
  cleanup();
});

// docs/architecture.md-shaped markdown with multiple H2 sections for ToC extraction.
const ARCHITECTURE_BODY = `# System Overview

## Components

Description of the major components.

## Data Flow

Description of how data moves through the system.

## Deployment

Description of the deployment topology.
`;

const NO_HEADINGS_BODY = "No headings here, just plain prose describing something.";

describe("ArchitectureExplorerRenderer — section-map preview", () => {
  it("renders a compact section nav and a link to the full architecture explorer", () => {
    const { container } = render(
      <ArchitectureExplorerRenderer body={ARCHITECTURE_BODY} />
    );

    expect(container.querySelector(".renderer-architecture")).toBeTruthy();

    const nav = container.querySelector(".renderer-architecture-nav");
    expect(nav).toBeTruthy();
    expect(nav?.textContent).toMatch(/Components/);
    expect(nav?.textContent).toMatch(/Data Flow/);

    expect(container.querySelector('a[href="/architecture"]')).toBeTruthy();
  });

  it("falls back to the default shell when the body has no headings", () => {
    const { container } = render(
      <ArchitectureExplorerRenderer body={NO_HEADINGS_BODY} />
    );

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-architecture")).toBeFalsy();
  });
});
