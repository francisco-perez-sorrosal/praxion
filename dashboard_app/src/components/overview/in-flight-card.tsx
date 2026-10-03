import Link from "next/link";

import { SectionCard } from "@/components/chrome/section-card";
import { TonePill } from "@/components/chrome/tone-pill";
import { ACTIVE_WINDOW_DAYS } from "@/lib/workshops";
import { relativeAge } from "@/lib/tone";
import type { OverviewData, WorkshopDigest } from "@/server/view-models/overview";

import { CardTitle } from "./card-title";
import { LabelledCount } from "./labelled-count";

type InFlightCardProps = { now: Date; workshops: OverviewData["workshops"] };

/** The workshops active in the window, with their step and progress, and how many are stale or finished. */
export function InFlightCard({ now, workshops }: InFlightCardProps) {
  const active = workshops?.active ?? [];
  return (
    <SectionCard
      subtitle={`active in the last ${ACTIVE_WINDOW_DAYS} days`}
      title={<CardTitle href="/workshops">In flight</CardTitle>}
    >
      {active.length === 0 ? (
        <p className="digest-placeholder">
          Nothing in flight. Pipelines appear here while their <code>.ai-work/&lt;task-slug&gt;/</code> directory is
          being worked.
        </p>
      ) : (
        <ul className="digest-list">
          {active.map((workshop) => (
            <WorkshopRow key={workshop.slug} now={now} workshop={workshop} />
          ))}
        </ul>
      )}
      {workshops === null ? null : (
        <p className="overview-counts overview-foot">
          <LabelledCount count={workshops.staleCount} label="stale" />
          <LabelledCount count={workshops.doneCount} label="done" />
        </p>
      )}
    </SectionCard>
  );
}

function WorkshopRow({ now, workshop }: { now: Date; workshop: WorkshopDigest }) {
  const age = relativeAge(workshop.updatedAt, now);
  return (
    <li className="digest-list__row overview-row">
      <Link className="overview-row__link" href="/workshops">
        <span className="overview-row__primary">{workshop.slug}</span>
        {workshop.currentStep === null ? null : <span className="overview-row__detail">{workshop.currentStep}</span>}
        {workshop.progress === null ? null : (
          <TonePill mono tone="neutral">
            {workshop.progress.done}/{workshop.progress.total}
          </TonePill>
        )}
        {age === null ? null : <span className="digest-list__secondary">{age}</span>}
      </Link>
    </li>
  );
}
