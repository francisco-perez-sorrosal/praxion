import type { ReactNode } from "react";

import type { Tone } from "@/lib/tone";

export type TonePillProps = {
  children: ReactNode;
  /** Monospace face for counts and ratios ("3/7", "×2"). */
  mono?: boolean;
  title?: string;
  tone: Tone;
};

/**
 * An inline word or count with a tone. The text carries the meaning; the colour
 * only reinforces it, and `data-tone` lets tests and assistive tooling read the
 * tone without parsing class names.
 */
export function TonePill({ children, mono = false, title, tone }: TonePillProps) {
  const className = `tone-pill tone-pill--${tone}${mono ? " tone-pill--mono" : ""}`;
  return (
    <span className={className} data-tone={tone} title={title}>
      {children}
    </span>
  );
}
