"use client";

import { DocInfo } from "@/components/readiness-shared";
import type { ReadinessCriterion, ReadinessPillar } from "@/lib/metrics";
import {
  criterionTitle,
  formatPct,
  groupCriteriaByPillar,
  levelLabel,
  topFailingCriteria,
  type CriteriaStats
} from "@/lib/readiness-section-data";

export function CriteriaSummaryBar({ stats }: { stats: CriteriaStats }) {
  const denom = stats.total || 1;
  const passW = `${(stats.passed / denom) * 100}%`;
  const failW = `${(stats.failed / denom) * 100}%`;
  const naW = `${(stats.notApplicable / denom) * 100}%`;
  return (
    <div className="readiness-criteria-summary">
      <span className="readiness-criteria-summary__bar" aria-hidden="true">
        <span className="readiness-criteria-summary__seg" data-state="pass" style={{ width: passW }} />
        <span className="readiness-criteria-summary__seg" data-state="fail" style={{ width: failW }} />
        <span className="readiness-criteria-summary__seg" data-state="na" style={{ width: naW }} />
      </span>
      <span className="readiness-criteria-summary__legend muted">
        <strong className="readiness-criteria-summary__count" data-state="pass">
          {stats.passed} pass
        </strong>
        <strong className="readiness-criteria-summary__count" data-state="fail">
          {stats.failed} fail
        </strong>
        {stats.notApplicable > 0 && (
          <strong className="readiness-criteria-summary__count" data-state="na">
            {stats.notApplicable} n/a
          </strong>
        )}
        <span>· {stats.llmJudged} LLM-judged</span>
      </span>
    </div>
  );
}

export function CriteriaMatrix({
  pillars,
  criteria
}: {
  pillars: ReadinessPillar[];
  criteria: ReadinessCriterion[];
}) {
  const groups = groupCriteriaByPillar(pillars, criteria);
  if (groups.length === 0) {
    return <p className="muted">No criteria recorded for this snapshot.</p>;
  }
  return (
    <div className="readiness-criteria-matrix" aria-label="All criteria by pillar">
      {groups.map(({ pillar, items }) => (
        <div key={pillar.id} className="readiness-criteria-matrix__group">
          <span
            className="readiness-criteria-matrix__pillar"
            title={pillar.explanation ? `${pillar.name}\n\n${pillar.explanation}` : pillar.name}
          >
            {pillar.name}
          </span>
          <span className="readiness-criteria-matrix__pips">
            {items.map((c) => {
              const state = !c.applicable
                ? "na"
                : c.passed === true
                  ? "pass"
                  : c.passed === false
                    ? "fail"
                    : "na";
              const glyph = state === "pass" ? "✓" : state === "fail" ? "✗" : "–";
              return (
                <span
                  key={c.id}
                  className="readiness-criteria-matrix__pip"
                  data-state={state}
                  data-llm={c.llm ? "true" : undefined}
                  title={criterionTitle(c)}
                  aria-label={`${c.id} ${levelLabel(c.level)}: ${
                    state === "pass" ? "pass" : state === "fail" ? "fail" : "not applicable"
                  }`}
                >
                  {glyph}
                </span>
              );
            })}
          </span>
        </div>
      ))}
    </div>
  );
}

export function FailingCriteriaList({ criteria }: { criteria: ReadinessCriterion[] }) {
  const failing = topFailingCriteria(criteria);
  if (failing.length === 0) {
    return <p className="muted">No failing criteria in this snapshot.</p>;
  }
  return (
    <ul className="readiness-failing-criteria">
      {failing.map((c) => (
        <li key={c.id} className="readiness-failing-criteria__item">
          <span className="readiness-failing-criteria__head">
            <span className="readiness-failing-criteria__level muted">L{c.level}</span>
            <span className="readiness-failing-criteria__id">{c.id}</span>
            {c.llm && (
              <span className="readiness-failing-criteria__llm" title="LLM-judged criterion">
                LLM
              </span>
            )}
          </span>
          {c.rationale && (
            <span className="readiness-failing-criteria__rationale muted">{c.rationale}</span>
          )}
          {c.remediation && (
            <span className="readiness-failing-criteria__remediation">
              <span className="readiness-failing-criteria__fix-label">Fix</span>
              {c.remediationSource === "llm" && (
                <span
                  className="readiness-failing-criteria__badge"
                  title="Project-specific recommendation from the LLM judge"
                >
                  AI-tailored
                </span>
              )}
              <span className="readiness-failing-criteria__fix-text">{c.remediation}</span>
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ManageabilityChip({
  pass_pct,
  numerator,
  denominator,
  note
}: {
  pass_pct: number;
  numerator: number;
  denominator: number;
  note: string | null;
}) {
  return (
    <div className="readiness-manageability-chip" aria-label="Pillar 9 manageability sub-score">
      <span className="readiness-manageability-chip__label">
        Pillar 9 — Manageability <DocInfo docKey="manageability" />
      </span>
      <span className="readiness-manageability-chip__score">{formatPct(pass_pct)}</span>
      <span className="readiness-manageability-chip__frac muted">
        {numerator}/{denominator}
      </span>
      {note && <span className="readiness-manageability-chip__note muted">{note}</span>}
    </div>
  );
}
