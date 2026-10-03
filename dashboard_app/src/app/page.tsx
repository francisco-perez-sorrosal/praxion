import { LiveRefresh } from "@/components/live-refresh";
import { OverviewGrid } from "@/components/overview/overview-grid";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getOverviewData, overviewRefreshSeconds } from "@/server/view-models/overview";

export default async function OverviewPage() {
  const cfg = getConfig();
  const now = new Date();
  const overview = await getOverviewData(cfg.projectRoot, now);

  const sources = (
    <>
      <p>
        Composed from the same readers as the other surfaces: sentinel reports, metrics snapshots, quality-eval
        reports, <code>.ai-work/&lt;task-slug&gt;/</code> workshops, decision records,{" "}
        <code>.ai-state/TECH_DEBT_LEDGER.md</code> and the knowledge documents. Nothing is stored here.
      </p>
      <p>
        Refresh cadence: <strong>{overviewRefreshSeconds(cfg.pollIntervalSeconds)}s server refresh on this page and
        Workshops only.</strong>
      </p>
    </>
  );

  return (
    <PageShell title="Overview" dataAsOf={overview.dataAsOf} sourcesContent={sources}>
      <LiveRefresh seconds={overviewRefreshSeconds(cfg.pollIntervalSeconds)} />

      <p className="page-intro__lede muted">
        Is anything on fire, what is in flight, what changed — with the detail one click away.
      </p>

      <OverviewGrid data={overview} now={now} />
    </PageShell>
  );
}
