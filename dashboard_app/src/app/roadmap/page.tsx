import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { getConfig } from "@/lib/config";
import { getRoadmapData } from "@/server/view-models/roadmap";

export default async function RoadmapPage() {
  const cfg = getConfig();
  const roadmap = await getRoadmapData(cfg.projectRoot);

  return (
    <section className="page-card">
      <header className="page-intro">
        <div>
          <p className="eyebrow">Direction</p>
          <h2>Roadmap</h2>
          <p>Project-level direction and backlog, rendered directly from `ROADMAP.md`.</p>
        </div>
        <aside>
          <span>Source of truth</span>
          <strong>Project root roadmap file</strong>
        </aside>
      </header>

      {!roadmap ? (
        <EmptyState
          title="No roadmap present"
          body="Generate `ROADMAP.md` for the target project to surface long-horizon direction here."
        />
      ) : (
        <article className="artifact-card">
          <MarkdownSurface body={roadmap.body} />
        </article>
      )}
    </section>
  );
}
