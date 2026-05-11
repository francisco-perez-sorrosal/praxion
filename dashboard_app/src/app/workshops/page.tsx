import path from "node:path";

import { EmptyState } from "@/components/empty-state";
import { LiveRefresh } from "@/components/live-refresh";
import { getConfig } from "@/lib/config";
import { getWorkshopsData } from "@/server/view-models/workshops";

export default async function WorkshopsPage() {
  const cfg = getConfig();
  const workshops = await getWorkshopsData(cfg.projectRoot);

  return (
    <section className="page-card">
      <LiveRefresh seconds={cfg.pollIntervalSeconds} />

      <header className="page-intro">
        <div>
          <p className="eyebrow">Live supervision</p>
          <h2>Workshops</h2>
          <p>
            In-flight pipeline state from `.ai-work/&lt;task-slug&gt;/`, refreshed on a
            fixed cadence without introducing a secondary data store.
          </p>
        </div>
        <aside>
          <span>Refresh cadence</span>
          <strong>{cfg.pollIntervalSeconds}s server refresh on this page only.</strong>
        </aside>
      </header>

      {workshops.length === 0 ? (
        <EmptyState
          title="No active workshops"
          body="`.ai-work/` is empty right now. Pipelines surface here while they are in flight and disappear after cleanup."
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
    </section>
  );
}
