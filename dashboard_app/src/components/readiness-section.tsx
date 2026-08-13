"use client";

import { PillarLevelHeatmap } from "@/components/readiness-heatmap";
import { ReadinessHero } from "@/components/readiness-hero";
import { LevelTrack } from "@/components/readiness-level-track";
import {
  CriteriaMatrix,
  CriteriaSummaryBar,
  FailingCriteriaList,
  ManageabilityChip
} from "@/components/readiness-criteria";
import { PillarBars, PillarRadar } from "@/components/readiness-pillar-views";
import { Subhead } from "@/components/readiness-shared";
import type { ReadinessSnapshot } from "@/lib/metrics";
import { criteriaStats } from "@/lib/readiness-section-data";

export function AgentReadinessSection({
  readiness
}: {
  readiness: ReadinessSnapshot | null;
}) {
  if (!readiness) {
    return (
      <p className="muted">
        No readiness data — run <code>/project-metrics</code> to generate a readiness snapshot.
      </p>
    );
  }

  const stats = criteriaStats(readiness.criteria);

  return (
    <div className="readiness-section">
      <ReadinessHero readiness={readiness} stats={stats} />

      <LevelTrack level={readiness.level} pillars={readiness.pillars} />

      <div className="readiness-pillar-grid">
        <div className="readiness-pillar-grid__panel">
          <Subhead text="Pillar shape" docKey="pillarRadar" />
          <PillarRadar pillars={readiness.pillars} />
        </div>
        <div className="readiness-pillar-grid__panel">
          <Subhead text="Pillar scores" docKey="pillarBars" />
          <PillarBars pillars={readiness.pillars} />
        </div>
      </div>

      <div className="readiness-heatmap-block">
        <Subhead text="Pillar × level matrix" docKey="heatmap" />
        <PillarLevelHeatmap pillars={readiness.pillars} criteria={readiness.criteria} />
      </div>

      <div className="readiness-criteria-block">
        <Subhead text="Criteria" docKey="criteria" />
        <CriteriaSummaryBar stats={stats} />
        <div className="readiness-criteria-cols">
          <div className="readiness-criteria-cols__panel">
            <Subhead text="All criteria by pillar" docKey="criteria" minor />
            <CriteriaMatrix pillars={readiness.pillars} criteria={readiness.criteria} />
          </div>
          <div className="readiness-criteria-cols__panel">
            <Subhead text="Recommendations" docKey="recommendations" minor />
            <FailingCriteriaList criteria={readiness.criteria} />
          </div>
        </div>
      </div>

      <ManageabilityChip
        pass_pct={readiness.manageability.pass_pct}
        numerator={readiness.manageability.numerator}
        denominator={readiness.manageability.denominator}
        note={readiness.manageability.note}
      />
    </div>
  );
}
