import path from "node:path";

import { ArtifactCard } from "@/components/artifact-card";
import { EducationalPopover } from "@/components/educational-popover";
import { EmptyState } from "@/components/empty-state";
import { MarkdownSurface } from "@/components/markdown-surface";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getSentinelData } from "@/server/view-models/sentinel";
import type { SentinelLogPoint } from "@/server/view-models/sentinel";

import { SentinelSparklineClient } from "./sentinel-sparkline-client";

// ─── Grade helpers ────────────────────────────────────────────────────────────

const GRADE_NUMBERS: Record<string, number> = {
  a: 4,
  b: 3,
  c: 2,
  d: 1
};

function gradeToNumber(grade: string | null): number | null {
  if (grade === null) {
    return null;
  }
  return GRADE_NUMBERS[grade.toLowerCase()] ?? null;
}

function logSeriesToSparklinePoints(
  logSeries: SentinelLogPoint[]
): Array<{ x: string; y: number | null }> {
  return logSeries.map((point, idx) => ({
    x: point.timestamp ?? String(idx + 1),
    y: gradeToNumber(point.grade)
  }));
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default async function SentinelPage() {
  const cfg = getConfig();
  const sentinel = await getSentinelData(cfg.projectRoot);

  const latestReport =
    sentinel.reports.length > 0
      ? path.basename(sentinel.reports[0] ?? "")
      : "None";

  const sources = (
    <>
      <p>
        Reads <code>.ai-state/sentinel_reports/</code> — timestamped audit reports and
        the <code>SENTINEL_LOG.md</code> run summary.
      </p>
      <p>
        Latest report: <code>{latestReport}</code>
      </p>
    </>
  );

  return (
    <PageShell
      title="Sentinel"
      sourcesContent={sources}
    >
      <p className="page-intro__lede muted">
        Health history and the latest audit rendered from{" "}
        <code>.ai-state/sentinel_reports/</code>.{" "}
        <EducationalPopover
          title="Sentinel audits"
          body="The sentinel agent audits the project's context artifacts across ten dimensions and grades overall health. Findings are tiered Critical / Important / Suggested."
          href="agents/sentinel.md"
        />
      </p>

      {sentinel.latest === null ? (
        <EmptyState
          title="No sentinel reports found"
          body="Run `/sentinel` in the target project to generate the first ecosystem audit."
          producerPath=".ai-state/sentinel_reports/"
        />
      ) : (
        <div className="sentinel-body">
          {/* ── Health grade sparkline ──────────────────────────────────────── */}
          {sentinel.logSeries.length > 0 ? (
            <div className="sentinel-sparkline-row">
              <span className="sentinel-sparkline-label muted">Health grade trend</span>
              <SentinelSparklineClient
                points={logSeriesToSparklinePoints(sentinel.logSeries)}
              />
            </div>
          ) : null}

          {/* ── Collapsible finding sections ────────────────────────────────── */}
          <div className="sentinel-sections">
            {sentinel.latest.sections !== null ? (
              <>
                {sentinel.latest.sections.critical.length > 0 ? (
                  <ArtifactCard title="Critical" defaultOpen={true}>
                    <MarkdownSurface body={sentinel.latest.sections.critical} />
                  </ArtifactCard>
                ) : null}

                {sentinel.latest.sections.important.length > 0 ? (
                  <ArtifactCard title="Important">
                    <MarkdownSurface body={sentinel.latest.sections.important} />
                  </ArtifactCard>
                ) : null}

                {sentinel.latest.sections.suggested.length > 0 ? (
                  <ArtifactCard title="Suggested">
                    <MarkdownSurface body={sentinel.latest.sections.suggested} />
                  </ArtifactCard>
                ) : null}

                {sentinel.latest.sections.rest.trim().length > 0 ? (
                  <ArtifactCard title="Full report">
                    <MarkdownSurface body={sentinel.latest.sections.rest} />
                  </ArtifactCard>
                ) : null}
              </>
            ) : (
              /* sections parse failed — render full body */
              <ArtifactCard
                title={path.basename(sentinel.latest.path)}
                defaultOpen={true}
              >
                <MarkdownSurface body={sentinel.latest.body} />
              </ArtifactCard>
            )}
          </div>

          {/* ── Report history list ─────────────────────────────────────────── */}
          <ArtifactCard title="Report history">
            <ul className="surface-list">
              {sentinel.reports.map((reportPath) => (
                <li key={reportPath} className="surface-row">
                  <code>{path.basename(reportPath)}</code>
                </li>
              ))}
            </ul>
          </ArtifactCard>
        </div>
      )}
    </PageShell>
  );
}
