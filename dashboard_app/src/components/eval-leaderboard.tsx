import type { EvalLeaderboardData, EvalLogRow } from "@/lib/evals";
import { formatEvalCost, formatEvalMetric } from "@/lib/evals";
import { EmptyState } from "@/components/empty-state";

type EvalLeaderboardProps = {
  data: EvalLeaderboardData;
};

function EvalTableRow({ rank, row }: { rank: number; row: EvalLogRow }) {
  const deltaValue = row.held_out_delta;
  const deltaDisplay = deltaValue === null ? "—" : deltaValue.toFixed(3);
  const deltaTone = deltaValue === null ? "" : deltaValue <= 0 ? " tone--good" : " tone--warn";

  return (
    <tr>
      <td className="eval-table__rank">{rank}</td>
      <td className="eval-table__run-id" title={row.run_id ?? undefined}>
        <code>{row.run_id ?? "—"}</code>
      </td>
      <td>{row.task ?? "—"}</td>
      <td className="eval-table__num">{row.generation ?? "—"}</td>
      <td className="eval-table__num eval-table__primary-metric">
        {formatEvalMetric(row.primary_metric)}
      </td>
      <td className={`eval-table__num${deltaTone}`}>{deltaDisplay}</td>
      <td>{row.model_id ?? "—"}</td>
      <td className="eval-table__hash" title={row.prompt_hash ?? undefined}>
        <code>{row.prompt_hash ?? "—"}</code>
      </td>
      <td className="eval-table__hash" title={row.dataset_sha ?? undefined}>
        <code>{row.dataset_sha ?? "—"}</code>
      </td>
      <td className="eval-table__num">{formatEvalCost(row.cost_usd)}</td>
      <td className="eval-table__hash" title={row.git_sha ?? undefined}>
        <code>{row.git_sha ?? "—"}</code>
      </td>
      <td className="eval-table__store-uri" title={row.store_uri ?? undefined}>
        <code>{row.store_uri ?? "—"}</code>
      </td>
    </tr>
  );
}

/**
 * Stateless leaderboard component rendering EVAL_LOG.md rows as a ranked table.
 * Rows arrive pre-sorted (descending primary_metric) from the view-model.
 * Uses design tokens from tokens.css; no inline styles.
 */
export function EvalLeaderboard({ data }: EvalLeaderboardProps) {
  if (data.rows.length === 0) {
    return (
      <EmptyState
        title="No eval runs recorded"
        body="Run the eval loop on a managed project to populate .ai-state/eval_ledger/EVAL_LOG.md."
        producerPath=".ai-state/eval_ledger/EVAL_LOG.md"
      />
    );
  }

  return (
    <div className="eval-leaderboard">
      <div className="eval-leaderboard__table-wrap">
        <table className="eval-table">
          <thead>
            <tr>
              <th scope="col" className="eval-table__rank">#</th>
              <th scope="col">Run ID</th>
              <th scope="col">Task</th>
              <th scope="col" className="eval-table__num">Gen</th>
              <th scope="col" className="eval-table__num">Metric</th>
              <th scope="col" className="eval-table__num">Delta</th>
              <th scope="col">Model</th>
              <th scope="col" className="eval-table__hash">Prompt</th>
              <th scope="col" className="eval-table__hash">Dataset</th>
              <th scope="col" className="eval-table__num">Cost</th>
              <th scope="col" className="eval-table__hash">Git SHA</th>
              <th scope="col" className="eval-table__store-uri">Store</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, index) => (
              <EvalTableRow
                key={row.run_id ?? String(index)}
                rank={index + 1}
                row={row}
              />
            ))}
          </tbody>
        </table>
      </div>
      <p className="eval-leaderboard__note">
        Sorted by primary metric descending. Delta: held-out minus public score;
        negative values indicate no contamination.
      </p>
    </div>
  );
}
