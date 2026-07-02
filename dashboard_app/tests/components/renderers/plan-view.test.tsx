// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { PlanViewRenderer } from "@/components/renderers/plan-view";

afterEach(() => {
  cleanup();
});

// IMPLEMENTATION_PLAN.md-shaped markdown with GFM task-list items — mirrors the
// real plan/progress documents this renderer previews.
const PLAN_BODY = `# Plan: Example feature

## Environment setup

- [x] install dependencies
- [x] configure the test runner

## Build the feature

- [ ] implement the handler
- [ ] wire the registry
`;

const NO_STRUCTURE_BODY =
  "Just a plain paragraph of prose with no headings and no task items.";

describe("PlanViewRenderer — step-progress overview", () => {
  it("renders one list item per plan step with a checked/unchecked marker", () => {
    const { container } = render(<PlanViewRenderer body={PLAN_BODY} />);

    expect(container.querySelector(".renderer-plan")).toBeTruthy();

    const steps = container.querySelectorAll(".renderer-plan-steps li");
    expect(steps.length).toBe(4);

    const checkboxes = container.querySelectorAll<HTMLInputElement>(
      ".renderer-plan-steps input[type='checkbox']"
    );
    expect(checkboxes.length).toBe(4);
    const checkedCount = Array.from(checkboxes).filter(
      (checkbox) => checkbox.checked
    ).length;
    expect(checkedCount).toBe(2);
  });

  it("falls back to the default shell when the body has no headings or task items", () => {
    const { container } = render(<PlanViewRenderer body={NO_STRUCTURE_BODY} />);

    expect(container.querySelector(".shell-default")).toBeTruthy();
    expect(container.querySelector(".renderer-plan")).toBeFalsy();
  });
});
