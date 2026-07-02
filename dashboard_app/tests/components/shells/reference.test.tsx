// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ReferenceShell } from "@/components/shells/reference";

afterEach(() => {
  cleanup();
});

describe("ReferenceShell — table of contents nav", () => {
  it("renders a navigation region labelled 'Table of contents'", () => {
    render(<ReferenceShell body={"# Heading\n\nSome body text."} />);

    expect(
      screen.getByRole("navigation", { name: /table of contents/i })
    ).toBeTruthy();
  });
});
