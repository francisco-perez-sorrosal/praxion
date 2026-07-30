"use client";

import { healthSummary } from "@/lib/health-tone";
import type { MetricTone } from "@/lib/metrics";

export type MetricToneEntry = { label: string; tone: MetricTone; arrow: string };

export type HealthStripProps = {
  activeSnapshotId: string;
  degradedCollectors: string[];
  hasMultipleSnapshots: boolean;
  isPending: boolean;
  onSnapshotChange: (id: string) => void;
  snapshotOptions: Array<{ id: string; label: string }>;
  tones: MetricToneEntry[];
};

function PerMetricArrows({ tones }: { tones: MetricToneEntry[] }) {
  if (tones.length === 0) return null;

  return (
    <ul className="health-strip__arrows">
      {tones.map(({ label, tone, arrow }) => (
        <li key={label} className={`health-strip__arrow health-strip__arrow--${tone}`}>
          {label} {arrow}
        </li>
      ))}
    </ul>
  );
}

export function HealthStrip({
  activeSnapshotId,
  degradedCollectors,
  hasMultipleSnapshots,
  isPending,
  onSnapshotChange,
  snapshotOptions,
  tones
}: HealthStripProps) {
  const tonesToAggregate: MetricTone[] = tones.map((t) => t.tone);
  const summary = healthSummary(tonesToAggregate, {
    degradedCollectors,
    isBaseline: !hasMultipleSnapshots
  });

  return (
    <section className="metrics-health-strip" aria-label="Health summary">
      <div className="health-strip__headline">
        <strong className="health-strip__label">
          Health: {summary.label}
        </strong>
        {summary.degradedNote && (
          <span className="health-strip__degraded-note">{summary.degradedNote}</span>
        )}
      </div>

      {hasMultipleSnapshots && (
        <PerMetricArrows tones={tones} />
      )}

      <div className="health-strip__controls">
        <label className="health-strip__selector">
          <span className="health-strip__selector-label">Viewing through</span>
          <select
            aria-label="View metrics through snapshot"
            value={activeSnapshotId}
            onChange={(event) => onSnapshotChange(event.target.value)}
          >
            {snapshotOptions.map(({ id, label }) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>

        {/* Compare toggle — disabled stub; snapshot comparison is a planned follow-up. Kept for layout completeness. */}
        <button
          className="health-strip__compare-btn"
          type="button"
          disabled
          title="Snapshot comparison — coming soon"
          aria-disabled="true"
        >
          ⇄ compare
        </button>

        {isPending && (
          <span className="health-strip__pending" aria-live="polite">
            Updating…
          </span>
        )}
      </div>
    </section>
  );
}
