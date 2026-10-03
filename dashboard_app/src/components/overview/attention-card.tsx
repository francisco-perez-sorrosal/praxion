import Link from "next/link";

import { SectionCard } from "@/components/chrome/section-card";
import { TONE_GLYPHS } from "@/lib/tone";
import type { AttentionLine } from "@/server/view-models/overview";

/** One line per condition that needs an operator; a calm card when there is none. */
export function AttentionCard({ attention }: { attention: AttentionLine[] }) {
  const calm = attention.length === 0;
  return (
    <SectionCard title="Attention" tone={calm ? "good" : "warn"}>
      {calm ? (
        <p className="digest-placeholder">Nothing needs attention.</p>
      ) : (
        <ul className="digest-list">
          {attention.map((line) => (
            <li className="digest-list__row overview-attention" data-tone={line.tone} key={line.text}>
              <span aria-hidden="true" className="overview-attention__glyph">
                {TONE_GLYPHS[line.tone]}
              </span>
              {line.href === null ? <span>{line.text}</span> : <Link href={line.href}>{line.text}</Link>}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
