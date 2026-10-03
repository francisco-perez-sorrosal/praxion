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
 * meaning survives without colour. A tile with `href` is a link; the whole
 * surface is the target (Fitts).
 */
export function StatTile({ badge, caption, href, label, tone = "neutral", trend, value }: StatTileProps) {
  const className = `stat-tile stat-tile--${tone}`;
  const body = (
    <>
      <span className="stat-tile__head">
        <span className="stat-tile__label">
          <span className="stat-tile__glyph" aria-hidden="true">{TONE_GLYPHS[tone]}</span>
          {label}
        </span>
        {badge != null ? <span className="stat-tile__badge">{badge}</span> : null}
      </span>
      <span className="stat-tile__value">{value}</span>
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
