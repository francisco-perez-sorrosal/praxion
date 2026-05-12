import path from "node:path";

import { DecisionGraph } from "@/components/viz/decision-graph";
import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { LiveRefresh } from "@/components/live-refresh";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import type { AdrGraphNode } from "@/server/view-models/adr-graph";
import { getWorkshopsData } from "@/server/view-models/workshops";
import type { WorkshopProgressItem } from "@/server/types";

const MIN_STEPS_FOR_DAG = 3;

function stepsToNodes(items: WorkshopProgressItem[]): AdrGraphNode[] {
  return items.map((item, index) => {
    const status = item.checked ? "accepted" : item.current ? "proposed" : "superseded";
    const prevItem = index > 0 ? items[index - 1] : undefined;
    const nextItem = index < items.length - 1 ? items[index + 1] : undefined;
    return {
      id: item.stepId,
      status,
      title: item.label,
      supersedes: prevItem?.stepId,
      superseded_by: nextItem?.stepId
    };
  });
}

export default async function WorkshopsPage() {
  const cfg = getConfig();
  const workshops = await getWorkshopsData(cfg.projectRoot);

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
    <PageShell title="Workshops" sourcesContent={sources}>
      <LiveRefresh seconds={cfg.pollIntervalSeconds} />

      <p className="page-intro__lede muted">
        In-flight pipeline state from <code>.ai-work/&lt;task-slug&gt;/</code>, refreshed on a
        fixed cadence.{" "}
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
        <div className="grid-two">
          {workshops.map((workshop) => (
            <article className="artifact-card" key={workshop.path}>
              <h3>{path.basename(workshop.path)}</h3>
              <div className="artifact-meta">
                {workshop.currentStep ? <span className="chip">{workshop.currentStep}</span> : null}
                {workshop.status ? <span className="chip">{workshop.status}</span> : null}
              </div>

              <section className="section-card">
                <h3>Progress</h3>
                {workshop.progress.length === 0 ? (
                  <p className="muted">No parsed WIP checklist yet.</p>
                ) : (
                  <>
                    {workshop.progress.length >= MIN_STEPS_FOR_DAG && (
                      <DecisionGraph nodes={stepsToNodes(workshop.progress)} />
                    )}
                    <ul className="status-list">
                      {workshop.progress.map((item) => (
                        <li className="status-row" key={`${workshop.path}:${item.stepId}`}>
                          <strong>
                            {item.checked ? "Completed" : item.current ? "Current" : "Pending"} · Step {item.stepId}
                          </strong>
                          <span className="muted">{item.label}</span>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>

              <section className="section-card">
                <h3>Recent events</h3>
                {workshop.events.length === 0 ? (
                  <p className="muted">No `PROGRESS.md` events yet.</p>
                ) : (
                  <ul className="event-list">
                    {workshop.events.slice(-8).map((event) => (
                      <li className="event-row" key={`${event.timestamp}:${event.agent}:${event.phase}`}>
                        <strong>
                          {event.agent} · Phase {event.phase}
                        </strong>
                        <span className="muted">{event.timestamp}</span>
                        <p>{event.summary}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="section-card">
                <h3>Artifacts</h3>
                <ul className="artifact-list">
                  {workshop.artifacts.map((artifact) => (
                    <li key={`${workshop.path}:${artifact}`}>
                      <span className="pill-note">{artifact}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </article>
          ))}
        </div>
      )}
    </PageShell>
  );
}
