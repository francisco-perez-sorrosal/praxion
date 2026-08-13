"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer
} from "recharts";

import { PillarWeightMarker } from "@/components/readiness-shared";
import type { ReadinessPillar } from "@/lib/metrics";
import { buildRadarData, formatPct, scoreTone } from "@/lib/readiness-section-data";

export function PillarRadar({ pillars }: { pillars: ReadinessPillar[] }) {
  if (pillars.length === 0) {
    return <p className="muted">No pillar data available.</p>;
  }
  const data = buildRadarData(pillars);
  return (
    <div className="readiness-radar" aria-label="8-pillar readiness radar chart">
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 8, right: 32, bottom: 8, left: 32 }}>
          <PolarGrid />
          <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            name="Pass %"
            dataKey="score"
            stroke="var(--color-info-text, #0369a1)"
            fill="var(--color-info-text, #0369a1)"
            fillOpacity={0.25}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PillarBars({ pillars }: { pillars: ReadinessPillar[] }) {
  if (pillars.length === 0) {
    return <p className="muted">No pillar data available.</p>;
  }
  const sorted = [...pillars].sort((a, b) => a.pass_pct - b.pass_pct);
  return (
    <ul className="readiness-pillar-bars" aria-label="Per-pillar pass ratios">
      {sorted.map((p) => {
        const tone = scoreTone(p.pass_pct);
        const width = `${Math.round(p.pass_pct * 100)}%`;
        return (
          <li
            key={p.id}
            className="readiness-pillar-bars__row"
            data-excluded={p.excluded ? "true" : undefined}
          >
            <span
              className="readiness-pillar-bars__name"
              title={p.explanation ? `${p.name}\n\n${p.explanation}` : p.name}
            >
              {p.name}
              <PillarWeightMarker pillar={p} />
            </span>
            <span className="readiness-pillar-bars__track">
              <span
                className="readiness-pillar-bars__fill"
                data-tone={tone}
                style={{ width }}
                aria-hidden="true"
              />
            </span>
            <span className="readiness-pillar-bars__value">
              <span className="readiness-pillar-bars__frac">
                {p.numerator}/{p.denominator}
              </span>
              <span className="readiness-pillar-bars__pct muted">{formatPct(p.pass_pct)}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
