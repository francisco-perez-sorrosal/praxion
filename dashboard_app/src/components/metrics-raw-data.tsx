"use client";

import { MarkdownSurface } from "@/components/markdown-surface";
import type { MetricsSnapshot } from "@/lib/metrics";
import { toJsonPreview } from "@/lib/metrics-dashboard-data";

type MetricsRawDataProps = {
  activeSnapshot: MetricsSnapshot;
  hasCollectors: boolean;
  log: { body: string } | null;
};

/**
 * The single raw-data disclosure. Deliberately one `<details>` for the whole
 * dashboard — per-section disclosures were consolidated so the page has exactly
 * one place to look for unformatted state.
 */
export function MetricsRawData({ activeSnapshot, hasCollectors, log }: MetricsRawDataProps) {
  return (
    <details className="metrics-raw">
      <summary>Raw data ▸</summary>
      <div className="metrics-raw__body">
        <h4 className="metrics-raw__section-heading">Selected snapshot JSON</h4>
        <pre className="code-block">{toJsonPreview(activeSnapshot)}</pre>

        <h4 className="metrics-raw__section-heading">Metrics history log</h4>
        {log ? (
          <MarkdownSurface body={log.body} />
        ) : (
          <p className="muted">History log not available.</p>
        )}

        {activeSnapshot.hotspots.length === 0 && (
          <p className="muted metrics-raw__note">No hot-spot rows in this snapshot.</p>
        )}
        {!hasCollectors && (
          <p className="muted metrics-raw__note">No collector metadata in this snapshot.</p>
        )}
      </div>
    </details>
  );
}
