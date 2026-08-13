"use client";

import { DocInfo } from "@/components/readiness-shared";
import type { ReadinessLlm, ReadinessSnapshot } from "@/lib/metrics";
import {
  formatPct,
  levelColor,
  levelLabel,
  LLM_STATUS_COPY,
  scoreTone,
  type CriteriaStats
} from "@/lib/readiness-section-data";

function ScoreRing({ pass_pct }: { pass_pct: number }) {
  const tone = scoreTone(pass_pct);
  const style = { ["--ring-pct" as string]: pass_pct } as React.CSSProperties;
  return (
    <div
      className="readiness-score-ring"
      data-tone={tone}
      style={style}
      role="img"
      aria-label={`${formatPct(pass_pct)} of criteria passed`}
    >
      <span className="readiness-score-ring__value">{formatPct(pass_pct)}</span>
      <span className="readiness-score-ring__label muted">passed</span>
    </div>
  );
}

function LevelBadge({ level }: { level: number }) {
  const color = levelColor(level);
  const label = levelLabel(level);
  return (
    <div className="readiness-level-badge" aria-label={`Readiness level ${label}`}>
      <span className="readiness-level-badge__score" style={{ color }}>
        {label}
      </span>
      <span className="readiness-level-badge__caption muted">
        readiness level <DocInfo docKey="level" />
      </span>
    </div>
  );
}

function LlmProvenanceChip({ llm }: { llm: ReadinessLlm }) {
  const copy = LLM_STATUS_COPY[llm.status];
  const detail = llm.model ?? copy.fallbackDetail;
  return (
    <div className="readiness-llm-chip" data-tone={copy.tone}>
      <span className="readiness-llm-chip__dot" aria-hidden="true" />
      <span className="readiness-llm-chip__label">{copy.label}</span>
      <span className="readiness-llm-chip__detail muted">{detail}</span>
      {llm.grounded_on && (
        <span className="readiness-llm-chip__grounded muted" title={`Grounded on ${llm.grounded_on}`}>
          grounded on {llm.grounded_on}
        </span>
      )}
      <DocInfo docKey="llmScoring" />
    </div>
  );
}

export function ReadinessHero({
  readiness,
  stats
}: {
  readiness: ReadinessSnapshot;
  stats: CriteriaStats;
}) {
  const weighted = readiness.weightingActive === true;
  // Under weighting the adjusted view is the project headline; the canonical
  // (unweighted) Factory score is kept visible for cross-tool comparison.
  const headlinePct = weighted ? readiness.adjustedPassPct ?? readiness.pass_pct : readiness.pass_pct;
  const headlineLevel = weighted ? readiness.adjustedLevel ?? readiness.level : readiness.level;
  return (
    <div className="readiness-hero">
      {weighted && (
        <span className="readiness-hero__tag">
          Adjusted · your weights <DocInfo docKey="weighting" />
        </span>
      )}
      <ScoreRing pass_pct={headlinePct} />
      <LevelBadge level={headlineLevel} />
      <div className="readiness-hero__stats">
        <p className="readiness-hero__stat-line">
          <strong>
            {stats.passed}/{stats.total}
          </strong>{" "}
          criteria passed <DocInfo docKey="passPct" />
        </p>
        <p className="readiness-hero__stat-line muted">
          {stats.llmJudged} LLM-judged
          {stats.notApplicable > 0 && ` · ${stats.notApplicable} n/a`}
        </p>
        {weighted && (
          <p className="readiness-hero__canonical muted">
            Factory (unweighted): {formatPct(readiness.pass_pct)} · {levelLabel(readiness.level)}{" "}
            <DocInfo docKey="adjustedScore" />
          </p>
        )}
        <LlmProvenanceChip llm={readiness.llm} />
      </div>
    </div>
  );
}
