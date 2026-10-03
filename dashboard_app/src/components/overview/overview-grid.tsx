import type { OverviewData } from "@/server/view-models/overview";

import { ActivityList } from "./activity-list";
import { AttentionCard } from "./attention-card";
import { DecisionsCard } from "./decisions-card";
import { ExploreGrid } from "./explore-grid";
import { InFlightCard } from "./in-flight-card";
import { PulseRow } from "./pulse-row";

/**
 * The Overview's reading order: is anything on fire (pulse, attention), what
 * is in flight, what changed (activity), and where to go next (explore).
 */
export function OverviewGrid({ data, now }: { data: OverviewData; now: Date }) {
  return (
    <div className="overview">
      <PulseRow evals={data.evals} metrics={data.metrics} sentinel={data.sentinel} />
      <div className="overview__split">
        <InFlightCard now={now} workshops={data.workshops} />
        <DecisionsCard decisions={data.decisions} />
      </div>
      <AttentionCard attention={data.attention} />
      <div className="overview__split overview__split--wide-end">
        <ActivityList activity={data.activity} now={now} />
        <ExploreGrid />
      </div>
    </div>
  );
}
