"use client";

import { useState } from "react";

import { MarkdownSurface } from "@/components/markdown-surface";
import { DecisionGraph } from "@/components/viz/decision-graph";
import type { AdrGraphNode } from "@/server/view-models/adr-graph";
import type { WorkshopArtifact, WorkshopProgressItem, WorkshopState } from "@/server/types";

const MIN_STEPS_FOR_DAG = 3;

/** Last path segment — `node:path` is unavailable in a client component. */
function basename(fullPath: string): string {
  const segments = fullPath.split("/").filter((segment) => segment.length > 0);
  return segments.at(-1) ?? fullPath;
}

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

// ─── Artifact disclosure — click to expand the file content inline ───────────

function ArtifactDisclosure({ artifact }: { readonly artifact: WorkshopArtifact }) {
  return (
    <details className="workshop-artifact">
      <summary className="workshop-artifact__summary">
        <span className="workshop-artifact__chevron" aria-hidden="true" />
        <code>{artifact.name}</code>
      </summary>
      <div className="workshop-artifact__body">
        {artifact.body === null ? (
          <p className="muted">File could not be read.</p>
        ) : artifact.renderMode === "markdown" ? (
          <MarkdownSurface body={artifact.body} />
        ) : (
          <pre className="code-block">{artifact.body}</pre>
        )}
      </div>
    </details>
  );
}

// ─── Selected-workshop panel ──────────────────────────────────────────────────

function WorkshopPanel({ workshop }: { readonly workshop: WorkshopState }) {
  return (
    <article className="workshop-panel">
      <header className="workshop-panel__header">
        <h3>{basename(workshop.path)}</h3>
        <div className="artifact-meta">
          {workshop.currentStep ? <span className="chip">{workshop.currentStep}</span> : null}
          {workshop.status ? <span className="chip">{workshop.status}</span> : null}
        </div>
      </header>

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
                <li className="status-row" key={item.stepId}>
                  <strong>
                    {item.checked ? "Completed" : item.current ? "Current" : "Pending"} · Step{" "}
                    {item.stepId}
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
        {workshop.artifacts.length === 0 ? (
          <p className="muted">No canonical artifacts found in this workshop.</p>
        ) : (
          <div className="workshop-artifacts">
            {workshop.artifacts.map((artifact) => (
              <ArtifactDisclosure key={artifact.name} artifact={artifact} />
            ))}
          </div>
        )}
      </section>
    </article>
  );
}

// ─── Workshop selector button ─────────────────────────────────────────────────

function WorkshopButton({
  workshop,
  isActive,
  onSelect
}: {
  readonly workshop: WorkshopState;
  readonly isActive: boolean;
  readonly onSelect: (path: string) => void;
}) {
  return (
    <button
      type="button"
      className={`workshop-selector__item${isActive ? " workshop-selector__item--active" : ""}${workshop.isDone ? " workshop-selector__item--done" : ""}`}
      onClick={() => onSelect(workshop.path)}
      aria-pressed={isActive}
    >
      <span className="workshop-selector__name">{basename(workshop.path)}</span>
      {workshop.isDone ? (
        <span className="chip chip--status-accepted workshop-selector__badge">Done</span>
      ) : workshop.currentStep ? (
        <span className="workshop-selector__step muted">{workshop.currentStep}</span>
      ) : null}
    </button>
  );
}

// ─── Main client component ────────────────────────────────────────────────────

export function WorkshopsClient({ workshops }: { readonly workshops: WorkshopState[] }) {
  const activeWorkshops = workshops.filter((workshop) => !workshop.isDone);
  const doneWorkshops = workshops.filter((workshop) => workshop.isDone);

  const firstWorkshop = activeWorkshops[0] ?? doneWorkshops[0] ?? null;
  const [selectedPath, setSelectedPath] = useState(firstWorkshop?.path ?? "");

  const selected =
    workshops.find((workshop) => workshop.path === selectedPath) ?? firstWorkshop ?? null;

  if (selected === null) {
    return null;
  }

  const hasBothGroups = activeWorkshops.length > 0 && doneWorkshops.length > 0;

  return (
    <div className="workshops-client">
      <nav className="workshop-selector" aria-label="Select a workshop">
        {activeWorkshops.length > 0 && (
          <div className="workshop-selector__group">
            {hasBothGroups && (
              <p className="workshop-selector__group-label" aria-hidden="true">
                Active
              </p>
            )}
            {activeWorkshops.map((workshop) => (
              <WorkshopButton
                key={workshop.path}
                workshop={workshop}
                isActive={workshop.path === selected.path}
                onSelect={setSelectedPath}
              />
            ))}
          </div>
        )}

        {doneWorkshops.length > 0 && (
          <div className="workshop-selector__group">
            <p className="workshop-selector__group-label" aria-hidden="true">
              Done
            </p>
            {doneWorkshops.map((workshop) => (
              <WorkshopButton
                key={workshop.path}
                workshop={workshop}
                isActive={workshop.path === selected.path}
                onSelect={setSelectedPath}
              />
            ))}
          </div>
        )}
      </nav>

      <WorkshopPanel workshop={selected} />
    </div>
  );
}
