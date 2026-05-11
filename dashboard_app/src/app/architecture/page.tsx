import path from "node:path";

import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { getConfig } from "@/lib/config";
import { getArchitectureData } from "@/server/view-models/architecture";

export default async function ArchitecturePage() {
  const cfg = getConfig();
  const data = await getArchitectureData(cfg.projectRoot);

  return (
    <section className="page-card">
      <header className="page-intro">
        <div>
          <p className="eyebrow">Status surface</p>
          <h2>Architecture</h2>
          <p>
            Design-target architecture, developer guide, and rendered diagrams from
            the live project filesystem.
          </p>
        </div>
        <aside>
          <span>Source contract</span>
          <strong>Read `.ai-state/DESIGN.md`, `docs/architecture.md`, and SVGs directly.</strong>
        </aside>
      </header>

      {!data.design && !data.guide && data.diagrams.length === 0 ? (
        <EmptyState
          title="No architecture artifacts found"
          body="Run a systems-architect pass for the target project to generate the architecture surfaces."
        />
      ) : (
        <>
          {data.diagrams.length > 0 ? (
            <section className="section-card">
              <h3>Diagrams</h3>
              <div className="grid-two">
                {data.diagrams.map((diagram) => (
                  <article className="artifact-card" key={diagram.path}>
                    <div className="artifact-meta">
                      <span className="chip">
                        {path.relative(cfg.projectRoot, diagram.path)}
                      </span>
                    </div>
                    <div
                      className="svg-frame"
                      dangerouslySetInnerHTML={{ __html: diagram.markup ?? "" }}
                    />
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <div className="grid-two">
            {data.design ? (
              <article className="artifact-card">
                <h3>Design target</h3>
                <div className="artifact-meta">
                  <span className="chip">.ai-state/DESIGN.md</span>
                </div>
                <MarkdownSurface body={data.design.body} />
              </article>
            ) : null}

            {data.guide ? (
              <article className="artifact-card">
                <h3>Developer guide</h3>
                <div className="artifact-meta">
                  <span className="chip">docs/architecture.md</span>
                </div>
                <MarkdownSurface body={data.guide.body} />
              </article>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
