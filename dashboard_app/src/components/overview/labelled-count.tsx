import type { Tone } from "@/lib/tone";

/**
 * A number with its label in one element ("3 FAIL"), so the count is never
 * read without what it counts. With a tone it also carries `data-tone`; the
 * label word, not the colour, says what the tone means.
 */
export function LabelledCount({ count, label, tone }: { count: number; label: string; tone?: Tone }) {
  return (
    <span className="overview-count" data-tone={tone}>
      <strong>{count}</strong> {label}
    </span>
  );
}
