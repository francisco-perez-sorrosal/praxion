import path from "node:path";

import { SectionCard } from "@/components/chrome/section-card";
import { EmptyState } from "@/components/empty-state";
import { EvalLedgerSection } from "@/components/eval-leaderboard";
import { PageShell } from "@/components/page-shell";
import { ReportDigest } from "@/components/praxion-evals/report-digest";
import { RunHistory, RunSelector } from "@/components/praxion-evals/run-history";
import { getConfig } from "@/lib/config";
import type { EvalLedger } from "@/lib/evals";
import { newestOf } from "@/lib/tone";
import { fileMtime } from "@/server/artifacts/files";
import { getEvalsData } from "@/server/view-models/evals";
import type { PraxionEvalsData } from "@/server/view-models/praxion-evals";
import { getPraxionEvalsData } from "@/server/view-models/praxion-evals";

type EvalsPageProps = {
  searchParams: Promise<{ run?: string | string[] }>;
};

const REPORTS_PATH = ".ai-state/praxion_eval_reports/";

export default async function EvalsPage({ searchParams }: EvalsPageProps) {
  const cfg = getConfig();
  const { run } = await searchParams;
  const [praxion, ledger] = await Promise.all([
    getPraxionEvalsData(cfg.projectRoot, Array.isArray(run) ? run[0] : run),
    getEvalsData(cfg.projectRoot)
  ]);
  const dataAsOf = newestOf([praxion.dataAsOf, await ledgerMtime(cfg.projectRoot, ledger)]);

  const sourcesContent = (
    <dl className="sources-list">
      <dt>Quality-eval log and reports</dt>
      <dd>
        <code>{REPORTS_PATH}</code>
      </dd>
      <dt>Eval ledger</dt>
      <dd>
        <code>.ai-state/eval_ledger/EVAL_LOG.md</code>
      </dd>
      <dt>Runs found</dt>
      <dd>{praxion.runs.length}</dd>
    </dl>
  );

  return (
    <PageShell title="Evals" dataAsOf={dataAsOf} sourcesContent={sourcesContent}>
      <p className="page-intro__lede muted">
        The project&apos;s own quality checks: how each run went, which checks fail and on what, then the
        eval ledger.
      </p>
      <div className="eval-body">
        <QualityEvals data={praxion} />
        <EvalLedgerSection ledger={ledger} />
      </div>
    </PageShell>
  );
}

/** Ledger mtime for the data-as-of stamp; `null` when the ledger is absent. */
async function ledgerMtime(projectRoot: string, ledger: EvalLedger): Promise<string | null> {
  return ledger.shape === "absent" ? null : fileMtime(path.join(projectRoot, ledger.path));
}

function QualityEvals({ data }: { data: PraxionEvalsData }) {
  if (data.runs.length === 0 && data.reports.length === 0) {
    return (
      <EmptyState
        title="No quality-eval runs recorded"
        body="Run `/eval-praxion` in the target project to record the first quality-eval run."
        producerPath={REPORTS_PATH}
      />
    );
  }

  const reportStamps = data.reports.map((report) => report.timestamp);
  const selectedStamp = data.selected?.timestamp ?? null;
  return (
    <SectionCard
      title="Quality evals"
      subtitle={`${data.runs.length} runs`}
      actions={reportStamps.length > 0 ? <RunSelector reportStamps={reportStamps} selectedStamp={selectedStamp} /> : null}
    >
      {data.runs.length > 0 ? (
        <RunHistory runs={data.runs} reportStamps={reportStamps} selectedStamp={selectedStamp} />
      ) : (
        <p className="digest-placeholder">
          The run log is missing; <code>/eval-praxion</code> appends a row to{" "}
          <code>{REPORTS_PATH}PRAXION_EVAL_LOG.md</code> after each run.
        </p>
      )}
      {data.selected === null ? (
        <p className="digest-placeholder">
          No report file was found under <code>{REPORTS_PATH}</code>.
        </p>
      ) : (
        <ReportDigest report={data.selected} />
      )}
    </SectionCard>
  );
}
