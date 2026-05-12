import path from "node:path";

import { ArtifactCard } from "@/components/artifact-card";
import { Chip } from "@/components/chrome/chip";
import { ErrorState } from "@/components/chrome/error-state";
import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { MarkdownToc } from "@/components/markdown-toc";
import { PageShell } from "@/components/page-shell";
import { DiagramFrame } from "@/components/viz/diagram-frame";
import { getConfig } from "@/lib/config";
import { getArchitectureData } from "@/server/view-models/architecture";
import type { AacRegion } from "@/server/aac/parse-fences";

// ─── Diagram ordering ─────────────────────────────────────────────────────────

// Priority-first ordering by filename stem. Diagrams matching these stems
// appear first (in this order); remaining diagrams sort alphabetically.
const DIAGRAM_PRIORITY_ORDER = [
  "deployment-system-context",
  "agent-pipeline-execution"
];

function sortDiagrams(diagrams: Array<{ markup: string | null; path: string }>): typeof diagrams {
  return [...diagrams].sort((a, b) => {
    const stemA = path.basename(a.path, ".svg");
    const stemB = path.basename(b.path, ".svg");
    const idxA = DIAGRAM_PRIORITY_ORDER.indexOf(stemA);
    const idxB = DIAGRAM_PRIORITY_ORDER.indexOf(stemB);
    const rankA = idxA >= 0 ? idxA : DIAGRAM_PRIORITY_ORDER.length;
    const rankB = idxB >= 0 ? idxB : DIAGRAM_PRIORITY_ORDER.length;
    if (rankA !== rankB) return rankA - rankB;
    return stemA.localeCompare(stemB);
  });
}

function friendlyDiagramLabel(diagramPath: string, projectRoot: string): string {
  const rel = path.relative(projectRoot, diagramPath);
  const base = path.basename(diagramPath, ".svg");
  return `${base} (${rel})`;
}

// ─── AaC inline chip ─────────────────────────────────────────────────────────

function AacChip({ region }: { readonly region: AacRegion }) {
  if (region.kind === "plain") {
    return null;
  }

  const source = typeof region.attrs["source"] === "string" ? region.attrs["source"] : undefined;
  const view = typeof region.attrs["view"] === "string" ? region.attrs["view"] : undefined;
  const owner = typeof region.attrs["owner"] === "string" ? region.attrs["owner"] : undefined;

  if (region.kind === "generated") {
    const label = ["Generated", source !== undefined ? `source=${source}` : null, view !== undefined ? `view=${view}` : null]
      .filter(Boolean)
      .join(" · ");
    return (
      <span className="aac-chip aac-chip--generated">
        <Chip variant="neutral">{label}</Chip>
      </span>
    );
  }

  // authored
  const label = ["Authored", owner !== undefined ? `owner=${owner}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <span className="aac-chip aac-chip--authored">
      <Chip variant="neutral">{label}</Chip>
    </span>
  );
}

// ─── AaC region list — inline chip at region top ─────────────────────────────

function AacRegionList({ regions }: { readonly regions: AacRegion[] }) {
  return (
    <div className="aac-regions">
      {regions.map((region, idx) => (
        // eslint-disable-next-line react/no-array-index-key
        <div key={idx} className={`aac-region aac-region--${region.kind}`}>
          <AacChip region={region} />
          <MarkdownSurface body={region.content} />
        </div>
      ))}
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default async function ArchitecturePage() {
  const cfg = getConfig();
  const data = await getArchitectureData(cfg.projectRoot);

  const hasContent = data.design !== null || data.guide !== null || data.diagrams.length > 0;

  if (!hasContent) {
    return (
      <PageShell
        title="Architecture"
        sourcesContent={<SourceContract />}
      >
        <EmptyState
          title="No architecture artifacts found"
          body="Run a systems-architect pass for the target project to generate the architecture surfaces."
          producerPath=".ai-state/DESIGN.md"
        />
      </PageShell>
    );
  }

  const sortedDiagrams = sortDiagrams(data.diagrams);
  const diagramCount = sortedDiagrams.length;
  const hasDesign = data.design !== null;
  const hasGuide = data.guide !== null;
  const hasDiagrams = diagramCount > 0;
  const hasAacRegions = data.regions.length > 0;

  // The view-model does not currently expose mtime; pass null and let the
  // AppHeader omit the stamp. A follow-up can wire mtime into MarkdownFile.
  const dataAsOf = null;

  return (
    <PageShell
      title="Architecture"
      dataAsOf={dataAsOf}
      sourcesContent={<SourceContract hasDiagrams={hasDiagrams} />}
    >
      <p className="page-intro__lede">
        Design-target architecture, developer guide, and rendered diagrams from
        the live project filesystem.{" "}
        <EducationalPopover
          title="What is this?"
          body="The architecture surface shows the design-target (DESIGN.md) and code-verified (architecture.md) views, plus the rendered diagrams."
          href="docs/architecture.md"
        />
      </p>

      {/* ── Row 1: Diagrams (full width) ────────────────────────────────── */}
      {hasDiagrams && (
        <section className="section-card">
          <h3>
            Diagrams
            <span className="section-card__meta">
              {" "}· {diagramCount} {diagramCount === 1 ? "diagram" : "diagrams"}
            </span>
          </h3>
          <div className="architecture-diagrams">
            {sortedDiagrams.map((diagram, index) => {
              if (diagram.markup === null) {
                return null;
              }
              const label = friendlyDiagramLabel(diagram.path, cfg.projectRoot);
              return (
                <ArtifactCard
                  key={diagram.path}
                  title={label}
                  defaultOpen={index === 0}
                >
                  <DiagramFrame svg={diagram.markup} label={label} />
                </ArtifactCard>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Row 2: Two-column (Component index + docs) ──────────────────── */}
      <div className={`architecture-layout${hasDesign ? " architecture-layout--two-col" : ""}`}>
        {/* LEFT: Component index (sticky ToC from DESIGN.md) */}
        {hasDesign && data.design !== null && (
          <aside className="component-index">
            <p className="component-index__label">Component index</p>
            <MarkdownToc body={data.design.body} ariaLabel="Component index" />
          </aside>
        )}

        {/* RIGHT: Doc cards */}
        <div className="architecture-docs">
          {/* Design target card */}
          {hasDesign && data.design !== null ? (
            <ArtifactCard
              title="Design target"
              meta={<Chip variant="neutral">.ai-state/DESIGN.md</Chip>}
              defaultOpen
            >
              {hasAacRegions ? (
                <AacRegionList regions={data.regions} />
              ) : (
                <MarkdownSurface body={data.design.body} />
              )}
            </ArtifactCard>
          ) : null}

          {/* Developer guide card */}
          {hasGuide && data.guide !== null ? (
            <ArtifactCard
              title="Developer guide"
              meta={<Chip variant="neutral">docs/architecture.md</Chip>}
              defaultOpen
            >
              <MarkdownSurface body={data.guide.body} />
            </ArtifactCard>
          ) : (
            /* Show inline error only when guide was expected but failed —
               absence (null from view-model) is normal sparse state, not an error */
            null
          )}

          {/* Neither doc present but we have diagrams — inline note */}
          {!hasDesign && !hasGuide && hasDiagrams && (
            <ErrorState
              variant="inline"
              title="No documentation artifacts"
              message="Neither .ai-state/DESIGN.md nor docs/architecture.md was found. Only diagrams are available."
            />
          )}
        </div>
      </div>
    </PageShell>
  );
}

// ─── Sources disclosure content ───────────────────────────────────────────────

function SourceContract({ hasDiagrams = true }: { hasDiagrams?: boolean }) {
  return (
    <>
      <strong>
        Reads <code>.ai-state/DESIGN.md</code>, <code>docs/architecture.md</code>
        {hasDiagrams ? (
          <>, and SVGs from <code>.ai-state/diagrams/*/rendered/</code>.</>
        ) : (
          <>. No rendered diagrams found in <code>.ai-state/diagrams/*/rendered/</code>.</>
        )}
      </strong>
    </>
  );
}
