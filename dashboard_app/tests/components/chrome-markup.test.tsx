// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SectionCard } from "@/components/chrome/section-card";
import { StatTile } from "@/components/chrome/stat-tile";

afterEach(cleanup);

/** Elements whose content model is phrasing-only: a heading inside one is invalid HTML. */
const PHRASING_ONLY = "span, a > span, p";

function headingsInsidePhrasing(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll("h1, h2, h3, h4, h5, h6")).filter(
    (heading) => heading.closest(PHRASING_ONLY) !== null
  );
}

describe("shared card primitives emit valid heading markup", () => {
  it("keeps the stat tile heading out of any span", () => {
    const { container } = render(<StatTile badge="PARTIAL" headingLevel={2} label="Health" value="A" />);

    expect(headingsInsidePhrasing(container)).toEqual([]);
    expect(container.querySelector(".stat-tile__head")?.tagName).toBe("DIV");
  });

  it("keeps the plain section card heading out of any span", () => {
    const { container } = render(
      <SectionCard actions={<span>act</span>} subtitle="sub" title="Findings">
        body
      </SectionCard>
    );

    expect(headingsInsidePhrasing(container)).toEqual([]);
    expect(container.querySelector(".section-card__heading")?.tagName).toBe("DIV");
  });

  it("puts the collapsible card heading directly inside its summary beside the chevron", () => {
    const { container } = render(
      <SectionCard actions={<span>act</span>} collapsible subtitle="sub" title="Full report">
        body
      </SectionCard>
    );
    const summary = container.querySelector("details > summary") as HTMLElement;

    expect(headingsInsidePhrasing(container)).toEqual([]);
    expect(Array.from(summary.children).map((child) => child.className)).toEqual([
      "section-card__chevron",
      "section-card__title",
      "section-card__subtitle",
      "section-card__actions"
    ]);
    expect(summary.querySelector(":scope > h2")?.textContent).toBe("Full report");
  });
});
