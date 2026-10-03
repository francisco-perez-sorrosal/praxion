import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { LiveRefresh } from "@/components/live-refresh";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { newestOf } from "@/lib/tone";
import { getWorkshopsData } from "@/server/view-models/workshops";

import { WorkshopsClient } from "./workshops-client";

export default async function WorkshopsPage() {
  const cfg = getConfig();
  const workshops = await getWorkshopsData(cfg.projectRoot);
  const now = new Date();

  const sources = (
    <>
      <p>
        Reads <code>.ai-work/&lt;task-slug&gt;/</code> — in-flight pipeline state refreshed on a
        fixed cadence without a secondary data store.
      </p>
      <p>
        Refresh cadence: <strong>{cfg.pollIntervalSeconds}s server refresh on this page only.</strong>
      </p>
    </>
  );

  return (
    <PageShell
      title="Workshops"
      dataAsOf={newestOf(workshops.map((workshop) => workshop.updatedAt))}
      sourcesContent={sources}
    >
      <LiveRefresh seconds={cfg.pollIntervalSeconds} />

      <p className="page-intro__lede muted">
        In-flight pipeline state from <code>.ai-work/&lt;task-slug&gt;/</code>, refreshed on a
        fixed cadence.{" "}
        <span className="workshops-live">live · {cfg.pollIntervalSeconds}s</span>{" "}
        <EducationalPopover
          title="Pipeline workshops"
          body="In-flight agent pipelines surface here: the current WIP step, the step plan, the PROGRESS.md transition log, and which intermediate artifacts exist. Workshop directories disappear after the pipeline completes and is cleaned."
          href="rules/swe/agent-intermediate-documents.md"
        />
      </p>

      {workshops.length === 0 ? (
        <EmptyState
          title="No active workshops"
          body="`.ai-work/` is empty right now. Pipelines surface here while they are in flight and disappear after cleanup."
          producerPath=".ai-work/<task-slug>/"
        />
      ) : (
        <WorkshopsClient workshops={workshops} nowIso={now.toISOString()} />
      )}
    </PageShell>
  );
}
