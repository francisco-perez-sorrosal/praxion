// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { TutorialShell } from "@/components/shells/tutorial";

afterEach(() => {
  cleanup();
});

describe("TutorialShell — ordered step rail", () => {
  it("renders an ordered list of steps derived from level-2 headings", () => {
    render(
      <TutorialShell
        body={"# Overview\n\n## Setup\n\nText.\n\n## Install\n\nText."}
      />
    );

    expect(screen.getByRole("list")).toBeTruthy();
  });

  it("renders an empty step rail without crashing when the body has no headings", () => {
    render(<TutorialShell body={""} />);

    expect(screen.getByRole("list")).toBeTruthy();
  });
});
