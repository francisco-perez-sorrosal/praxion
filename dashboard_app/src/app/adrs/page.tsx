import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getAdrData } from "@/server/view-models/adrs";

import { AdrFilterClient } from "./adr-filter-client";
import { AdrGraphClient } from "./adr-graph-client";

export default async function AdrsPage() {
  const cfg = getConfig();
  const { records: adrs, graph } = await getAdrData(cfg.projectRoot);

  const sources = (
    <>
      <p>
        Reads <code>.ai-state/decisions/</code> (finalized) and{" "}
        <code>.ai-state/decisions/drafts/</code> (in-pipeline fragments).
      </p>
    </>
  );

  return (
    <PageShell
      title="ADRs"
      sourcesContent={sources}
    >
      <p className="page-intro__lede muted">
        Finalized and draft architecture decisions rendered directly from the canonical
        Markdown files.{" "}
        <EducationalPopover
          title="Architecture Decision Records"
          body="ADRs capture significant decisions: context, the decision, options considered, consequences. The graph shows supersedes (solid) and re-affirms (dashed) relationships."
          href="rules/swe/adr-conventions.md"
        />
      </p>

      {adrs.length === 0 ? (
        <EmptyState
          title="No ADRs found"
          body="Run a pipeline that produces architecture decisions or inspect a project that already has `.ai-state/decisions/` populated."
          producerPath=".ai-state/decisions/"
        />
      ) : (
        <div className="adrs-body">
          {/* ── Relationship graph ──────────────────────────────────────────── */}
          {graph.length > 0 ? (
            <details className="adr-graph-details">
              <summary>ADR relationship graph ({graph.length} nodes)</summary>
              <AdrGraphClient nodes={graph} />
            </details>
          ) : null}

          {/* ── Filtered list ───────────────────────────────────────────────── */}
          <AdrFilterClient records={adrs} />
        </div>
      )}
    </PageShell>
  );
}
