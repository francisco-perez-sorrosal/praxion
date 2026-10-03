// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TonePill } from "@/components/chrome/tone-pill";
import type { Tone } from "@/lib/tone";

afterEach(cleanup);

const TONES: readonly Tone[] = ["good", "info", "warn", "bad", "neutral"];

describe("TonePill", () => {
  it.each(TONES)("carries the %s tone as a class and as data-tone", (tone) => {
    render(<TonePill tone={tone}>word</TonePill>);
    const pill = screen.getByText("word");
    expect(pill.className).toBe(`tone-pill tone-pill--${tone}`);
    expect(pill.getAttribute("data-tone")).toBe(tone);
  });

  it("renders only its children, with no glyph of its own", () => {
    render(<TonePill tone="bad">3 FAIL</TonePill>);
    expect(screen.getByText("3 FAIL").textContent).toBe("3 FAIL");
  });

  it("adds the monospace modifier and the title only when asked", () => {
    const { rerender } = render(<TonePill tone="good">plain</TonePill>);
    const plain = screen.getByText("plain");
    expect(plain.className).not.toContain("tone-pill--mono");
    expect(plain.hasAttribute("title")).toBe(false);

    rerender(
      <TonePill mono title="Steps done of total" tone="good">
        3/7
      </TonePill>
    );
    const mono = screen.getByText("3/7");
    expect(mono.className).toBe("tone-pill tone-pill--good tone-pill--mono");
    expect(mono.getAttribute("title")).toBe("Steps done of total");
  });
});
