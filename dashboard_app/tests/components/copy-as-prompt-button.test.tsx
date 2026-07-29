// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CopyAsPromptButton } from "@/components/copy-as-prompt-button";

function stubClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText }
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CopyAsPromptButton", () => {
  it("renders nothing when there is no prompt to copy", () => {
    const { container } = render(<CopyAsPromptButton prompt={null} />);

    expect(container.innerHTML).toBe("");
  });

  it("writes the prompt to the clipboard and shows a brief confirmation", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);

    render(<CopyAsPromptButton prompt="Resume Example Feature — do the thing." />);

    fireEvent.click(screen.getByRole("button", { name: "Copy as prompt" }));

    expect(writeText).toHaveBeenCalledWith("Resume Example Feature — do the thing.");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();
    });
  });

  it("shows a failure state when the clipboard write is rejected", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    stubClipboard(writeText);

    render(<CopyAsPromptButton prompt="Resume Example Feature." />);

    fireEvent.click(screen.getByRole("button", { name: "Copy as prompt" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Copy failed" })).toBeTruthy();
    });
  });
});
