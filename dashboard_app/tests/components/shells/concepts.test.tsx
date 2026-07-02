// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ConceptsShell } from "@/components/shells/concepts";

afterEach(() => {
  cleanup();
});

describe("ConceptsShell — key-takeaway callout", () => {
  it("renders a note region for the key takeaway", () => {
    render(<ConceptsShell body={"Some conceptual prose."} />);

    expect(screen.getByRole("note")).toBeTruthy();
  });

  it("renders the takeaway region without crashing when the body is empty", () => {
    render(<ConceptsShell body={""} />);

    expect(screen.getByRole("note")).toBeTruthy();
  });
});
