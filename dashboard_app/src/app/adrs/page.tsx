import path from "node:path";

import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { getConfig } from "@/lib/config";
import { getAdrData } from "@/server/view-models/adrs";

export default async function AdrsPage() {
  const cfg = getConfig();
  const adrs = await getAdrData(cfg.projectRoot);

  return (
    <section className="page-card">
      <header className="page-intro">
        <div>
          <p className="eyebrow">Decision record</p>
          <h2>ADRs</h2>
          <p>
            Finalized and draft architecture decisions rendered directly from the
            canonical Markdown files.
          </p>
        </div>
        <aside>
          <span>Current count</span>
          <strong>{adrs.length} decision surfaces</strong>
        </aside>
      </header>

      {adrs.length === 0 ? (
        <EmptyState
          title="No ADRs found"
          body="Run a pipeline that produces architecture decisions or inspect a project that already has `.ai-state/decisions/` populated."
        />
      ) : (
        <div className="grid-two">
          {adrs.map((adr) => {
            const title = typeof adr.data.title === "string" ? adr.data.title : path.basename(adr.path);
            const status = typeof adr.data.status === "string" ? adr.data.status : "unknown";
            return (
              <article className="artifact-card" key={adr.path}>
                <h3>{title}</h3>
                <div className="artifact-meta">
                  <span className="chip">{adr.isDraft ? "draft" : "finalized"}</span>
                  <span className="chip">{status}</span>
                  <span className="chip">{path.relative(cfg.projectRoot, adr.path)}</span>
                </div>
                <details>
                  <summary>Open decision body</summary>
                  <MarkdownSurface body={adr.body} />
                </details>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
