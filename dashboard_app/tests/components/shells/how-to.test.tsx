// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { HowToShell } from "@/components/shells/how-to";

afterEach(() => {
  cleanup();
});

describe("HowToShell — labelled goal region", () => {
  it("renders a region labelled 'Goal'", () => {
    render(<HowToShell body={"Some how-to prose."} />);

    expect(screen.getByLabelText("Goal")).toBeTruthy();
  });

  it("renders the goal region without crashing when the body is empty", () => {
    render(<HowToShell body={""} />);

    expect(screen.getByLabelText("Goal")).toBeTruthy();
  });
});
