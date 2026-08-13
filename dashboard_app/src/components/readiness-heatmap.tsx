"use client";

import { EducationalPopover } from "@/components/educational-popover";
import { PillarWeightMarker } from "@/components/readiness-shared";
import { LEVEL_MEANINGS } from "@/lib/readiness-docs";
import type { ReadinessCriterion, ReadinessPillar } from "@/lib/metrics";
import { levelLabel, MAX_LEVEL } from "@/lib/readiness-section-data";

export function PillarLevelHeatmap({
  pillars,
  criteria
}: {
  pillars: ReadinessPillar[];
  criteria: ReadinessCriterion[];
}) {
  if (pillars.length === 0) {
    return <p className="muted">No pillar data available.</p>;
  }
  const levels = Array.from({ length: MAX_LEVEL }, (_, i) => i + 1);
  // Count applicable criteria per (pillar, level) so a level with no criteria
  // renders as "–" (not assessed) instead of a misleading vacuous ✓.
  const countAt = (pillarId: string, level: number): number =>
    criteria.filter((c) => c.pillar === pillarId && c.level === level && c.applicable).length;
  return (
    <div className="readiness-heatmap" role="table" aria-label="Pillar by level pass matrix">
      <div className="readiness-heatmap__head" role="row">
        <span className="readiness-heatmap__corner" role="columnheader">
          Pillar
        </span>
        {levels.map((lvl) => {
          const meaning = LEVEL_MEANINGS[lvl];
          return (
            <span key={lvl} className="readiness-heatmap__col" role="columnheader">
              {levelLabel(lvl)}
              {meaning && <EducationalPopover title={meaning.title} body={meaning.body} />}
            </span>
          );
        })}
      </div>
      {pillars.map((p) => (
        <div
          key={p.id}
          className="readiness-heatmap__row"
          role="row"
          data-excluded={p.excluded ? "true" : undefined}
        >
          <span
            className="readiness-heatmap__rowname"
            role="rowheader"
            title={p.explanation ? `${p.name}\n\n${p.explanation}` : p.name}
          >
            {p.name}
            <PillarWeightMarker pillar={p} />
          </span>
          {levels.map((lvl, idx) => {
            const hasCriteria = countAt(p.id, lvl) > 0;
            const pass = hasCriteria ? p.level_pass[idx] === true : null;
            const state = pass === null ? "na" : pass ? "pass" : "fail";
            const glyph = pass === null ? "–" : pass ? "✓" : "✗";
            return (
              <span
                key={lvl}
                className="readiness-heatmap__cell"
                data-state={state}
                role="cell"
                aria-label={`${p.name} ${levelLabel(lvl)}: ${
                  pass === null ? "no criteria at this level" : pass ? "pass" : "fail"
                }`}
              >
                {glyph}
              </span>
            );
          })}
        </div>
      ))}
      <p className="readiness-heatmap__legend muted">
        <span data-state="pass">✓ clears level</span>
        <span data-state="fail">✗ fails level</span>
        <span data-state="na">– no criteria at this level</span>
      </p>
    </div>
  );
}
