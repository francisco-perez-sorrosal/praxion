import type { ReactNode } from "react";

import { SectionCard } from "@/components/chrome/section-card";
import { StatTile } from "@/components/chrome/stat-tile";
import { CheckGroups } from "@/components/praxion-evals/check-groups";
import { MarkdownSurface } from "@/components/markdown-surface";
import { formatEvalCost, formatEvalTimestamp } from "@/lib/evals";
import type { PraxionEvalCheck, PraxionEvalReport } from "@/lib/praxion-evals";
import { verdictTone } from "@/lib/tone";

type Summary = NonNullable<PraxionEvalReport["summary"]>;

const VERDICT_TILES: ReadonlyArray<{ key: keyof Summary; verdict: string }> = [
  { key: "pass", verdict: "PASS" },
  { key: "warn", verdict: "WARN" },
  { key: "fail", verdict: "FAIL" },
  { key: "skip", verdict: "SKIP" }
];

// A judged run's findings run to paragraphs; a real report holds ~1 MB of them.
// Clipping keeps the collapsed table cheap to send on every load; the report
// file stays the canonical, complete source.
const FINDINGS_PREVIEW_CHARS = 200;

const formatCount = (value: number): string => value.toLocaleString("en-US");

const clipFindings = (text: string): string =>
  text.length > FINDINGS_PREVIEW_CHARS ? `${text.slice(0, FINDINGS_PREVIEW_CHARS).trimEnd()}…` : text;

/**
 * The digest of one quality-eval run: verdict counts, run facts, failures by
 * check, warnings by check, calibration notes and the full report. Everything
 * heavy is collapsed; a fact the report does not state is left out rather than
 * shown as a placeholder.
 */
export function ReportDigest({ report }: { report: PraxionEvalReport }) {
  return (
    <div className="eval-digest">
      <h3 className="eval-digest__title">Digest of {formatEvalTimestamp(report.timestamp)}</h3>
      {report.summary === null ? (
        <p className="digest-placeholder">This report states no summary line; its check table is under Full report.</p>
      ) : (
        <VerdictTiles summary={report.summary} />
      )}
      <ReportFacts report={report} />
      <FailureCard groups={report.failGroups} />
      {report.warnGroups.length > 0 ? (
        <SectionCard collapsible defaultOpen={false} title="Warnings by check" subtitle={`${report.warnGroups.length} checks`}>
          <CheckGroups groups={report.warnGroups} showArtifacts={false} tone="warn" />
        </SectionCard>
      ) : null}
      {report.calibrationNotes !== null ? (
        <SectionCard collapsible defaultOpen={false} title="Calibration notes">
          <MarkdownSurface body={report.calibrationNotes} />
        </SectionCard>
      ) : null}
      <SectionCard collapsible defaultOpen={false} title="Full report" subtitle={`${report.checks.length} check results`}>
        {report.checks.length > 0 ? (
          <CheckTable checks={report.checks} fileName={report.fileName} />
        ) : (
          <MarkdownSurface body={report.body} />
        )}
      </SectionCard>
    </div>
  );
}

function VerdictTiles({ summary }: { summary: Summary }) {
  return (
    <div className="digest-row">
      {VERDICT_TILES.map(({ key, verdict }) => {
        const tone = verdictTone(verdict);
        return (
          <StatTile
            key={key}
            label={<span data-tone={tone}>{verdict}</span>}
            tone={tone}
            value={formatCount(summary[key])}
          />
        );
      })}
    </div>
  );
}

function ReportFacts({ report }: { report: PraxionEvalReport }) {
  const facts: Array<[string, ReactNode | null]> = [
    ["Target", report.target === null ? null : <code>{report.target}</code>],
    ["Judged calls", report.judgedCalls],
    ["Cache hits", report.cacheHits],
    ["Tokens in", report.tokensIn === null ? null : formatCount(report.tokensIn)],
    ["Tokens out", report.tokensOut === null ? null : formatCount(report.tokensOut)],
    ["Estimated cost", report.costUsd === null ? null : formatEvalCost(report.costUsd)]
  ];
  const stated = facts.filter(([, value]) => value !== null);
  if (stated.length === 0) {
    return null;
  }
  return (
    <dl className="kv-list eval-facts">
      {stated.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FailureCard({ groups }: { groups: PraxionEvalReport["failGroups"] }) {
  if (groups.length === 0) {
    return (
      <SectionCard title="Failures by check" tone="good">
        <p className="digest-placeholder">No check failed in this run.</p>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Failures by check" subtitle={`${groups.length} checks`} tone="bad">
      <CheckGroups groups={groups} showArtifacts tone="bad" />
    </SectionCard>
  );
}

function CheckTable({ checks, fileName }: { checks: readonly PraxionEvalCheck[]; fileName: string }) {
  const isClipped = checks.some((entry) => entry.findings.length > FINDINGS_PREVIEW_CHARS);
  return (
    <div className="eval-table-wrap">
      {isClipped ? (
        <p className="eval-clip-note">
          Findings longer than {FINDINGS_PREVIEW_CHARS} characters are clipped here; the complete text is in{" "}
          <code>{fileName}</code>.
        </p>
      ) : null}
      <table className="eval-report-table">
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">Kind</th>
            <th scope="col">Verdict</th>
            <th scope="col">Artifact</th>
            <th scope="col">Score</th>
            <th scope="col">Findings</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((entry, index) => (
            <tr key={index}>
              <td>{entry.check}</td>
              <td>{entry.kind}</td>
              <td data-tone={verdictTone(entry.verdict)}>{entry.verdict}</td>
              <td>
                <code>{entry.artifact}</code>
              </td>
              <td>{entry.score}</td>
              <td>{clipFindings(entry.findings)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
