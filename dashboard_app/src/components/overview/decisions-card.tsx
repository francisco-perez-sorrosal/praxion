import Link from "next/link";

import { SectionCard } from "@/components/chrome/section-card";
import type { DecisionsDigest } from "@/server/view-models/overview";

import { CardTitle } from "./card-title";
import { LabelledCount } from "./labelled-count";

/** Finalized and draft counts, the newest decisions by number, and the split by category. */
export function DecisionsCard({ decisions }: { decisions: DecisionsDigest | null }) {
  return (
    <SectionCard title={<CardTitle href="/adrs">Decisions</CardTitle>}>
      {decisions === null ? (
        <p className="digest-placeholder">
          No decisions recorded yet. Architecture decision records appear here from{" "}
          <code>.ai-state/decisions/</code>.
        </p>
      ) : (
        <>
          <p className="overview-counts">
            <LabelledCount count={decisions.finalized} label="finalized" />
            <LabelledCount count={decisions.drafts} label={decisions.drafts === 1 ? "draft" : "drafts"} />
          </p>
          <ul className="digest-list">
            {decisions.latest.map((decision) => (
              <li className="digest-list__row overview-row" key={decision.id}>
                <Link className="overview-row__link" href="/adrs">
                  <code className="overview-row__primary">{decision.id}</code>
                  <span className="overview-row__detail">{decision.title}</span>
                  {decision.status === null ? null : <span className="digest-list__secondary">{decision.status}</span>}
                </Link>
              </li>
            ))}
          </ul>
          <ul aria-label="Decisions by category" className="overview-chips">
            {Object.entries(decisions.byCategory)
              .sort(([leftName, left], [rightName, right]) => right - left || leftName.localeCompare(rightName))
              .map(([category, count]) => (
                <li className="tone-pill tone-pill--neutral" key={category}>
                  {category} · {count}
                </li>
              ))}
          </ul>
        </>
      )}
    </SectionCard>
  );
}
