// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { DefaultShell } from "@/components/shells/default";

afterEach(() => {
  cleanup();
});

describe("DefaultShell — plain wrapper", () => {
  it("renders the .shell-default wrapper", () => {
    const { container } = render(<DefaultShell body={"Plain body text."} />);

    expect(container.querySelector(".shell-default")).toBeTruthy();
  });
});
