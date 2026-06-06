import { EvalLeaderboard } from "@/components/eval-leaderboard";
import { PageShell } from "@/components/page-shell";
import { getConfig } from "@/lib/config";
import { getEvalsData } from "@/server/view-models/evals";

export default async function EvalsPage() {
  const cfg = getConfig();
  const evals = await getEvalsData(cfg.projectRoot);

  const sourcesContent = (
    <dl className="sources-list">
      <dt>Eval log</dt>
      <dd><code>.ai-state/eval_ledger/EVAL_LOG.md</code></dd>
      <dt>Runs found</dt>
      <dd>{evals.rows.length}</dd>
    </dl>
  );

  return (
    <PageShell
      title="Evals"
      sourcesContent={sourcesContent}
    >
      <EvalLeaderboard data={evals} />
    </PageShell>
  );
}
