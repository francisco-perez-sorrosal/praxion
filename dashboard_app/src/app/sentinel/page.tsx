import path from "node:path";

import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { getConfig } from "@/lib/config";
import { getSentinelData } from "@/server/view-models/sentinel";

export default async function SentinelPage() {
  const cfg = getConfig();
  const sentinel = await getSentinelData(cfg.projectRoot);

  return (
    <section className="page-card">
      <header className="page-intro">
        <div>
          <p className="eyebrow">Ecosystem quality</p>
          <h2>Sentinel</h2>
          <p>
            Health history and the latest audit rendered from `.ai-state/sentinel_reports/`.
          </p>
        </div>
        <aside>
          <span>Latest report</span>
          <strong>
            {sentinel.reports.length > 0 ? path.basename(sentinel.reports[0]) : "None"}
          </strong>
        </aside>
      </header>

      {!sentinel.latest ? (
        <EmptyState
          title="No sentinel reports found"
          body="Run `/sentinel` in the target project to generate the first ecosystem audit."
        />
      ) : (
        <div className="grid-two">
          <article className="artifact-card">
            <h3>Latest report</h3>
            <div className="artifact-meta">
              <span className="chip">{path.relative(cfg.projectRoot, sentinel.latest.path)}</span>
            </div>
            <MarkdownSurface body={sentinel.latest.body} />
          </article>

          <article className="artifact-card">
            <h3>History</h3>
            {sentinel.log ? (
              <MarkdownSurface body={sentinel.log.body} />
            ) : (
              <p className="muted">No `SENTINEL_LOG.md` found alongside the reports.</p>
            )}
          </article>
        </div>
      )}
    </section>
  );
}
