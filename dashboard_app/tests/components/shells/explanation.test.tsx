// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ExplanationShell } from "@/components/shells/explanation";

afterEach(() => {
  cleanup();
});

describe("ExplanationShell — labelled aside", () => {
  it("renders an aside labelled 'Why this matters'", () => {
    render(<ExplanationShell body={"Some explanatory prose."} />);

    expect(screen.getByLabelText("Why this matters")).toBeTruthy();
  });
});
