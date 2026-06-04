"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer
} from "recharts";

import type { ReadinessCriterion, ReadinessPillar, ReadinessSnapshot } from "@/lib/metrics";

// ─── Constants ────────────────────────────────────────────────────────────────

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

// ─── Helpers ──────────────────────────────────────────────────────────────────

const FALLBACK_LEVEL_COLOR = "var(--color-info-text, #0369a1)";

function levelColor(level: number): string {
  return LEVEL_COLORS[level] ?? FALLBACK_LEVEL_COLOR;
}

function levelLabel(level: number): string {
  return LEVEL_LABELS[level] ?? `L${level}`;
}

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
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

// ─── Sub-components ──────────────────────────────────────────────────────────

function LevelBadge({ level, pass_pct }: { level: number; pass_pct: number }) {
  const color = levelColor(level);
  const label = levelLabel(level);
  return (
    <div className="readiness-level-badge" aria-label={`Readiness level ${label}`}>
      <span
        className="readiness-level-badge__score"
        style={{ color }}
      >
        {label}
      </span>
      <span className="readiness-level-badge__pct muted">{formatPct(pass_pct)} criteria passed</span>
    </div>
  );
}

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

function ManageabilityChip({
  pass_pct,
  note
}: {
  pass_pct: number;
  note: string | null;
}) {
  return (
    <div className="readiness-manageability-chip" aria-label="Pillar 9 manageability sub-score">
      <span className="readiness-manageability-chip__label">Pillar 9 — Manageability</span>
      <span className="readiness-manageability-chip__score">{formatPct(pass_pct)}</span>
      {note && <span className="readiness-manageability-chip__note muted">{note}</span>}
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
          <span className="readiness-failing-criteria__level muted">L{c.level}</span>
          <span className="readiness-failing-criteria__id">{c.id}</span>
          {c.rationale && (
            <span className="readiness-failing-criteria__rationale muted">{c.rationale}</span>
          )}
        </li>
      ))}
    </ul>
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

  return (
    <div className="readiness-section">
      <LevelBadge level={readiness.level} pass_pct={readiness.pass_pct} />
      <PillarRadar pillars={readiness.pillars} />
      <ManageabilityChip
        pass_pct={readiness.manageability.pass_pct}
        note={readiness.manageability.note}
      />
      <div className="readiness-failing-criteria-block">
        <h4>Top failing criteria</h4>
        <FailingCriteriaList criteria={readiness.criteria} />
      </div>
    </div>
  );
}
