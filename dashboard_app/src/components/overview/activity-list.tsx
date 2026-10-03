import Link from "next/link";

import { SectionCard } from "@/components/chrome/section-card";
import { relativeAge } from "@/lib/tone";
import type { ActivityEntry } from "@/server/view-models/overview";

/** The newest artifact of each family with its age, newest first. */
export function ActivityList({ activity, now }: { activity: ActivityEntry[]; now: Date }) {
  return (
    <SectionCard title="Recent activity">
      {activity.length === 0 ? (
        <p className="digest-placeholder">No artifacts yet. Activity appears as the project's agents write state.</p>
      ) : (
        <ul className="digest-list">
          {activity.map((entry) => (
            <li className="digest-list__row overview-row" key={entry.family}>
              <Link className="overview-row__link" href={entry.href}>
                <span className="overview-row__primary">{entry.label}</span>
                <time className="digest-list__secondary" dateTime={entry.mtime}>
                  {relativeAge(entry.mtime, now)}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
