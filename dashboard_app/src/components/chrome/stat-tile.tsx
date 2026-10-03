import type { Route } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

import type { Tone } from "@/lib/tone";
import { TONE_GLYPHS } from "@/lib/tone";

export type StatTileProps = {
  /** Small count or status pill in the head row (e.g. "PARTIAL", "3 crit"). */
  badge?: ReactNode;
  /** One short line under the value: a delta, a date, "not run yet". */
  caption?: ReactNode;
  /** Render the label as a heading of this level, so the tile names itself in the outline. */
  headingLevel?: 2 | 3 | 4;
  /** Links the whole tile to the surface holding the detail. */
  href?: Route;
  label: ReactNode;
  tone?: Tone;
  /** Sparkline or arrow row between value and caption. */
  trend?: ReactNode;
  value: ReactNode;
};

/**
 * One glance tile: label, dominant value, optional trend and caption.
 *
 * The tone is rendered as a left accent plus a glyph next to the label so the
 * meaning survives without colour, and exposed as `data-tone` on the value so
 * tests and assistive tooling can read it. A tile with `href` is a link; the whole
 * surface is the target (Fitts).
 */
export function StatTile({ badge, caption, headingLevel, href, label, tone = "neutral", trend, value }: StatTileProps) {
  const className = `stat-tile stat-tile--${tone}`;
  const Label = headingLevel === undefined ? "span" : (`h${headingLevel}` as const);
  const body = (
    <>
      <div className="stat-tile__head">
        <Label className="stat-tile__label">
          <span className="stat-tile__glyph" aria-hidden="true">{TONE_GLYPHS[tone]}</span>
          {label}
        </Label>
        {badge != null ? <span className="stat-tile__badge">{badge}</span> : null}
      </div>
      <span className="stat-tile__value" data-tone={tone}>{value}</span>
      {trend != null ? <span className="stat-tile__trend">{trend}</span> : null}
      {caption != null ? <span className="stat-tile__caption">{caption}</span> : null}
    </>
  );

  if (href !== undefined) {
    return (
      <Link className={`${className} stat-tile--link`} href={href}>
        {body}
      </Link>
    );
  }
  return <div className={className}>{body}</div>;
}
