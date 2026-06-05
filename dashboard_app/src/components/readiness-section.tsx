"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer
} from "recharts";

import { EducationalPopover } from "@/components/educational-popover";
import { LEVEL_MEANINGS, READINESS_DOCS, type ReadinessDocKey } from "@/lib/readiness-docs";
import type {
  ReadinessCriterion,
  ReadinessLlm,
  ReadinessPillar,
  ReadinessSnapshot
} from "@/lib/metrics";

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_LEVEL = 5;

const LEVEL_LABELS: Record<number, string> = {
  1: "L1",
  2: "L2",
  3: "L3",
  4: "L4",
  5: "L5"
};

const LEVEL_COLORS: Record<number, string> = {
  1: "var(--color-danger-text, #b91c1c)",
  2: "var(--color-warn-text, #b45309)",
  3: "var(--color-info-text, #0369a1)",
  4: "var(--color-success-text, #047857)",
  5: "var(--color-success-text, #047857)"
};

const FALLBACK_LEVEL_COLOR = "var(--color-info-text, #0369a1)";

/** Maps an LLM scoring status to a human label, a color tone, and a detail hint. */
const LLM_STATUS_COPY: Record<
  ReadinessLlm["status"],
  { label: string; tone: ScoreTone; fallbackDetail: string }
> = {
  scored: { label: "LLM-scored", tone: "good", fallbackDetail: "4 criteria judged by an LLM" },
  llm_skipped: { label: "Mechanical-only", tone: "warn", fallbackDetail: "LLM tier not run" },
  llm_error: { label: "LLM error", tone: "bad", fallbackDetail: "judge call failed" },
  pending: { label: "LLM pending", tone: "info", fallbackDetail: "scoring in progress" }
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

type ScoreTone = "good" | "warn" | "bad" | "info";

function levelColor(level: number): string {
  return LEVEL_COLORS[level] ?? FALLBACK_LEVEL_COLOR;
}

function levelLabel(level: number): string {
  return LEVEL_LABELS[level] ?? `L${level}`;
}

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Threshold tone for a 0–1 pass ratio. Always paired with a number in the UI (never color-alone). */
function scoreTone(pct: number): ScoreTone {
  if (pct >= 0.8) return "good";
  if (pct >= 0.4) return "warn";
  return "bad";
}

function topFailingCriteria(criteria: ReadinessCriterion[]): ReadinessCriterion[] {
  return [...criteria]
    .filter((c) => c.passed === false)
    .sort((a, b) => a.level - b.level);
}

function buildRadarData(pillars: ReadinessPillar[]): Array<{ subject: string; score: number }> {
  return pillars.map((p) => ({
    subject: p.name,
    score: Math.round(p.pass_pct * 100)
  }));
}

type CriteriaStats = {
  total: number;
  passed: number;
  failed: number;
  notApplicable: number;
  llmJudged: number;
};

function criteriaStats(criteria: ReadinessCriterion[]): CriteriaStats {
  return criteria.reduce<CriteriaStats>(
    (acc, c) => ({
      total: acc.total + 1,
      passed: acc.passed + (c.passed === true ? 1 : 0),
      failed: acc.failed + (c.passed === false ? 1 : 0),
      notApplicable: acc.notApplicable + (c.applicable ? 0 : 1),
      llmJudged: acc.llmJudged + (c.llm ? 1 : 0)
    }),
    { total: 0, passed: 0, failed: 0, notApplicable: 0, llmJudged: 0 }
  );
}

/** Groups criteria by pillar id, preserving pillar order from the pillars array. */
function groupCriteriaByPillar(
  pillars: ReadinessPillar[],
  criteria: ReadinessCriterion[]
): Array<{ pillar: ReadinessPillar; items: ReadinessCriterion[] }> {
  const groups = pillars.map((pillar) => ({
    pillar,
    items: criteria.filter((c) => c.pillar === pillar.id)
  }));
  const known = new Set(pillars.map((p) => p.id));
  const orphans = criteria.filter((c) => !known.has(c.pillar));
  if (orphans.length > 0) {
    const orphanPillars = [...new Set(orphans.map((c) => c.pillar))];
    for (const id of orphanPillars) {
      groups.push({
        pillar: { id, name: id, pass_pct: 0, numerator: 0, denominator: 0, level_pass: [] },
        items: orphans.filter((c) => c.pillar === id)
      });
    }
  }
  return groups.filter((g) => g.items.length > 0);
}

/** Native-tooltip text for a criterion pip: id, level, LLM flag, explanation, fix. */
function criterionTitle(c: ReadinessCriterion): string {
  const lines = [`${c.id} · ${levelLabel(c.level)}${c.llm ? " · LLM-judged" : ""}`];
  if (c.explanation) lines.push("", c.explanation);
  if (c.passed === false && c.remediation) lines.push("", `Fix: ${c.remediation}`);
  return lines.join("\n");
}

// ─── Educational hover affordances ─────────────────────────────────────────────

/** A `?` popover carrying instrument-level documentation for a concept. */
function DocInfo({ docKey }: { docKey: ReadinessDocKey }) {
  const doc = READINESS_DOCS[docKey];
  return <EducationalPopover title={doc.title} body={doc.body} />;
}

/** A section subheading paired with its educational popover. */
function Subhead({
  text,
  docKey,
  minor = false
}: {
  text: string;
  docKey: ReadinessDocKey;
  minor?: boolean;
}) {
  const Tag = minor ? "h5" : "h4";
  return (
    <Tag className={`readiness-subhead${minor ? " readiness-subhead--minor" : ""}`}>
      <span className="readiness-subhead__text">{text}</span>
      <DocInfo docKey={docKey} />
    </Tag>
  );
}

/** A small marker showing a pillar's weight when it differs from the default 1. */
function PillarWeightMarker({ pillar }: { pillar: ReadinessPillar }) {
  if (pillar.excluded) {
    return (
      <span className="readiness-pillar-weight" data-excluded="true" title="Excluded from the adjusted score (weight 0)">
        excluded
      </span>
    );
  }
  if (typeof pillar.weight === "number" && pillar.weight !== 1) {
    return (
      <span className="readiness-pillar-weight" title={`Counts ×${pillar.weight} in the adjusted score`}>
        ×{pillar.weight}
      </span>
    );
  }
  return null;
}

// ─── Hero ─────────────────────────────────────────────────────────────────────

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

function ReadinessHero({
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

// ─── Level track ──────────────────────────────────────────────────────────────

function LevelTrack({ level, pillars }: { level: number; pillars: ReadinessPillar[] }) {
  const nextIndex = level;
  const blockers =
    level < MAX_LEVEL
      ? pillars.filter((p) => p.level_pass[nextIndex] !== true).map((p) => p.name)
      : [];
  return (
    <div className="readiness-level-track-block">
      <ol className="readiness-level-track" aria-label="Factory readiness level progression">
        {Array.from({ length: MAX_LEVEL }, (_, i) => i + 1).map((lvl) => {
          const state = lvl < level ? "cleared" : lvl === level ? "current" : "pending";
          return (
            <li key={lvl} className="readiness-level-track__step" data-state={state}>
              <span className="readiness-level-track__marker" aria-hidden="true">
                {lvl <= level ? "●" : "○"}
              </span>
              <span className="readiness-level-track__label">{levelLabel(lvl)}</span>
            </li>
          );
        })}
      </ol>
      <p className="readiness-level-track__caption muted">
        {level >= MAX_LEVEL ? (
          <>Top level reached — all pillars clear L{MAX_LEVEL}.</>
        ) : blockers.length > 0 ? (
          <>
            Blocking L{level + 1}: <strong>{blockers.join(", ")}</strong>
          </>
        ) : (
          <>Highest fully-cleared level: {levelLabel(level)}.</>
        )}
      </p>
    </div>
  );
}

// ─── Pillar views (radar + bars) ───────────────────────────────────────────────

function PillarRadar({ pillars }: { pillars: ReadinessPillar[] }) {
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

function PillarBars({ pillars }: { pillars: ReadinessPillar[] }) {
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

// ─── Pillar × Level heatmap ────────────────────────────────────────────────────

function PillarLevelHeatmap({
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

// ─── Criteria ──────────────────────────────────────────────────────────────────

function CriteriaSummaryBar({ stats }: { stats: CriteriaStats }) {
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

function CriteriaMatrix({
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

function FailingCriteriaList({ criteria }: { criteria: ReadinessCriterion[] }) {
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

function ManageabilityChip({
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

// ─── AgentReadinessSection ───────────────────────────────────────────────────

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
