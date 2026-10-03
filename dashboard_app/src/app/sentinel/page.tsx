import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getSentinelData } from "@/server/view-models/sentinel";

import { SentinelClient } from "./sentinel-client";

export default async function SentinelPage() {
  const cfg = getConfig();
  const sentinel = await getSentinelData(cfg.projectRoot);

  const sources = (
    <>
      <p>
        Reads <code>.ai-state/sentinel_reports/</code> — timestamped audit reports and
        the <code>SENTINEL_LOG.md</code> run summary.
      </p>
      <p>
        Reports found: <strong>{sentinel.reports.length}</strong>
      </p>
    </>
  );

  return (
    <PageShell
      title="Sentinel"
      dataAsOf={sentinel.reports[0]?.reportTimestamp ?? null}
      sourcesContent={sources}
    >
      <p className="page-intro__lede muted">
        The latest audit at a glance, with the full report one click away.{" "}
        <EducationalPopover
          title="Sentinel audits"
          body="The sentinel agent audits the project's context artifacts across ten dimensions and grades overall health. Findings are tiered Critical / Important / Suggested."
          href="agents/sentinel.md"
        />
      </p>

      {sentinel.reports.length === 0 ? (
        <EmptyState
          title="No sentinel reports found"
          body="Run `/sentinel` in the target project to generate the first ecosystem audit."
          producerPath=".ai-state/sentinel_reports/"
        />
      ) : (
        <div className="sentinel-body">
          <SentinelClient reports={sentinel.reports} logSeries={sentinel.logSeries} />
        </div>
      )}
    </PageShell>
  );
}
