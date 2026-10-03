"use client";

import { useState } from "react";

import { Chip } from "@/components/chrome/chip";
import { SectionCard } from "@/components/chrome/section-card";
import { TonePill } from "@/components/chrome/tone-pill";
import { CopyAsPromptButton } from "@/components/copy-as-prompt-button";
import { MarkdownSurface } from "@/components/markdown-surface";
import { DecisionGraph } from "@/components/viz/decision-graph";
import { relativeAge, type Tone } from "@/lib/tone";
import { groupWorkshops, progressSummary } from "@/lib/workshops";
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
      supersedes: prevItem === undefined ? undefined : [prevItem.stepId],
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

// ─── Step graph — mounted only once opened ───────────────────────────────────

/**
 * The graph is the heaviest widget on the page and the checklist beneath it
 * already carries the same facts, so it stays unmounted until the operator
 * asks for it.
 */
function StepGraphDisclosure({ items }: { readonly items: WorkshopProgressItem[] }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <details
      className="workshop-artifact"
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
    >
      <summary className="workshop-artifact__summary">
        <span className="workshop-artifact__chevron" aria-hidden="true" />
        Step graph
      </summary>
      <div className="workshop-artifact__body">
        {isOpen ? <DecisionGraph nodes={stepsToNodes(items)} /> : null}
      </div>
    </details>
  );
}

// ─── Selected-workshop panel ──────────────────────────────────────────────────

function WorkshopPanel({ workshop, now }: { readonly workshop: WorkshopState; readonly now: Date }) {
  const lastActivity = relativeAge(workshop.updatedAt, now);

  return (
    <article className="workshop-panel">
      <header className="workshop-panel__header">
        <div className="workshop-panel__title-row">
          <h3>{basename(workshop.path)}</h3>
          <CopyAsPromptButton prompt={workshop.handoffPrompt} />
        </div>
        <div className="artifact-meta">
          {workshop.currentStep ? <Chip>{workshop.currentStep}</Chip> : null}
          {workshop.status ? <Chip>{workshop.status}</Chip> : null}
        </div>
        <p className="workshop-panel__activity muted" title={workshop.updatedAt ?? undefined}>
          Last activity: {lastActivity ?? "unknown"}
        </p>
      </header>

      <SectionCard title="Progress">
        {workshop.progress.length === 0 ? (
          <p className="muted">No parsed WIP checklist yet.</p>
        ) : (
          <>
            {workshop.progress.length >= MIN_STEPS_FOR_DAG && (
              <StepGraphDisclosure key={workshop.path} items={workshop.progress} />
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
      </SectionCard>

      <SectionCard title="Recent events">
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
      </SectionCard>

      <SectionCard title="Artifacts">
        {workshop.artifacts.length === 0 ? (
          <p className="muted">No canonical artifacts found in this workshop.</p>
        ) : (
          <div className="workshop-artifacts">
            {workshop.artifacts.map((artifact) => (
              <ArtifactDisclosure key={artifact.name} artifact={artifact} />
            ))}
          </div>
        )}
      </SectionCard>
    </article>
  );
}

// ─── Workshop selector ────────────────────────────────────────────────────────

function progressTone(done: number, total: number): Tone {
  return done === total ? "good" : "neutral";
}

function WorkshopButton({
  workshop,
  now,
  isSelected,
  onSelect
}: {
  readonly workshop: WorkshopState;
  readonly now: Date;
  readonly isSelected: boolean;
  readonly onSelect: (path: string) => void;
}) {
  const progress = progressSummary(workshop.progress);
  const age = relativeAge(workshop.updatedAt, now);

  return (
    <button
      type="button"
      className={`workshop-selector__item${isSelected ? " workshop-selector__item--active" : ""}${workshop.isDone ? " workshop-selector__item--done" : ""}`}
      onClick={() => onSelect(workshop.path)}
      aria-current={isSelected ? "true" : undefined}
    >
      <span className="workshop-selector__name">{basename(workshop.path)}</span>
      <span className="workshop-selector__meta">
        {progress !== null ? (
          <TonePill mono title="Steps done of total" tone={progressTone(progress.done, progress.total)}>
            {progress.done}/{progress.total}
          </TonePill>
        ) : null}
        {age !== null ? <span className="workshop-selector__age muted">{age}</span> : null}
        {workshop.isDone ? <Chip variant="status-accepted">Done</Chip> : null}
      </span>
      {!workshop.isDone && workshop.currentStep ? (
        <span className="workshop-selector__step muted">{workshop.currentStep}</span>
      ) : null}
    </button>
  );
}

function WorkshopGroup({
  title,
  workshops,
  now,
  selectedPath,
  onSelect,
  defaultOpen,
  emptyNote
}: {
  readonly title: string;
  readonly workshops: WorkshopState[];
  readonly now: Date;
  readonly selectedPath: string;
  readonly onSelect: (path: string) => void;
  readonly defaultOpen: boolean;
  readonly emptyNote?: string;
}) {
  return (
    <SectionCard title={`${title} (${workshops.length})`} collapsible defaultOpen={defaultOpen}>
      {workshops.length === 0 ? (
        <p className="muted">{emptyNote}</p>
      ) : (
        <div className="workshop-selector">
          {workshops.map((workshop) => (
            <WorkshopButton
              key={workshop.path}
              workshop={workshop}
              now={now}
              isSelected={workshop.path === selectedPath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

// ─── Main client component ────────────────────────────────────────────────────

/** `nowIso` comes from the server render so ages agree between server and client. */
export function WorkshopsClient({
  workshops,
  nowIso
}: {
  readonly workshops: WorkshopState[];
  readonly nowIso: string;
}) {
  const now = new Date(nowIso);
  const { active, stale, done } = groupWorkshops(workshops, now);

  const firstWorkshop = active[0] ?? stale[0] ?? done[0] ?? null;
  const [selectedPath, setSelectedPath] = useState(firstWorkshop?.path ?? "");

  const selected =
    workshops.find((workshop) => workshop.path === selectedPath) ?? firstWorkshop ?? null;

  if (selected === null) {
    return null;
  }

  const groupProps = { now, selectedPath: selected.path, onSelect: setSelectedPath };

  return (
    <div className="workshops-client">
      <nav className="workshop-groups" aria-label="Select a workshop">
        <WorkshopGroup
          title="Active"
          workshops={active}
          defaultOpen
          emptyNote="Nothing touched in the last seven days."
          {...groupProps}
        />
        {stale.length > 0 && (
          <WorkshopGroup title="Stale" workshops={stale} defaultOpen={false} {...groupProps} />
        )}
        {done.length > 0 && (
          <WorkshopGroup title="Done" workshops={done} defaultOpen={false} {...groupProps} />
        )}
      </nav>

      <WorkshopPanel workshop={selected} now={now} />
    </div>
  );
}
