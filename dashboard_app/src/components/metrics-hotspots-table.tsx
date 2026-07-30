"use client";

import { useState } from "react";

export type Hotspot = {
  churn90d: number | null;
  complexity: number | null;
  path: string;
  rank: number | null;
  score: number | null;
};

const HOTSPOT_PREVIEW_ROWS = 10;

export function HotSpotsTable({ hotspots }: { hotspots: Hotspot[] }) {
  const [showAll, setShowAll] = useState(false);

  if (hotspots.length === 0) {
    return <p className="muted">No hot-spot rows exist in this snapshot.</p>;
  }

  const maxScore = hotspots.reduce((max, h) => Math.max(max, h.score ?? 0), 0);
  const visibleRows = showAll ? hotspots : hotspots.slice(0, HOTSPOT_PREVIEW_ROWS);
  const hiddenCount = hotspots.length - HOTSPOT_PREVIEW_ROWS;

  return (
    <>
      <table className="table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Path</th>
            <th>Score</th>
            <th>Churn 90d</th>
            <th>Complexity</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((row) => {
            const scorePct =
              row.score !== null && maxScore > 0
                ? Math.round((row.score / maxScore) * 100)
                : 0;

            return (
              <tr key={`${row.path}-${row.rank ?? "na"}`}>
                <td>{row.rank ?? "—"}</td>
                <td>{row.path}</td>
                <td>
                  <span
                    className="hotspot-score-bar"
                    style={{ "--hotspot-score-pct": `${scorePct}%` } as React.CSSProperties}
                  >
                    {row.score === null
                      ? "—"
                      : new Intl.NumberFormat("en-US", {
                          maximumFractionDigits: 0
                        }).format(row.score)}
                  </span>
                </td>
                <td>
                  {row.churn90d === null
                    ? "—"
                    : new Intl.NumberFormat("en-US", {
                        maximumFractionDigits: 0
                      }).format(row.churn90d)}
                </td>
                <td>{row.complexity === null ? "—" : row.complexity.toFixed(0)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {!showAll && hiddenCount > 0 && (
        <button
          className="hotspot-show-all-btn"
          type="button"
          onClick={() => setShowAll(true)}
        >
          Show all {hotspots.length} ▸
        </button>
      )}
    </>
  );
}
