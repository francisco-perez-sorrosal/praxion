"use client";

import { useMemo, useState } from "react";

import { ArtifactCard } from "@/components/artifact-card";
import { SectionCard } from "@/components/chrome/section-card";
import { StatTile } from "@/components/chrome/stat-tile";
import { MarkdownSurface } from "@/components/markdown-surface";
import { gradeTone } from "@/lib/tone";
import type { Tone } from "@/lib/tone";
import type { SentinelLogPoint, SentinelReport } from "@/server/view-models/sentinel";

import { SentinelSparklineClient } from "./sentinel-sparkline-client";

/** Runs shown in the trend: enough to see a direction, few enough to read the dates. */
const TREND_RUN_LIMIT = 12;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

// ─── Formatting helpers ───────────────────────────────────────────────────────

function formatReportLabel(report: SentinelReport): string {
  if (report.reportTimestamp === null) {
    return report.fileName;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(new Date(report.reportTimestamp));
}

/** The calendar day of a log timestamp, or the raw text when it is not date-shaped. */
function runDay(timestamp: string | null, index: number): string {
  return timestamp?.match(ISO_DAY)?.[0] ?? timestamp ?? `run ${index + 1}`;
}

type CountTile = {
  readonly caption: string;
  readonly label: string;
  readonly tone: (count: number) => Tone;
  readonly value: (point: SentinelLogPoint) => number | null;
};

const COUNT_TILES: readonly CountTile[] = [
  {
    caption: "blocks correct behavior",
    label: "Critical",
    tone: (count) => (count > 0 ? "bad" : "good"),
    value: (point) => point.critical
  },
  {
    caption: "degrades quality or efficiency",
    label: "Important",
    tone: (count) => (count > 0 ? "warn" : "good"),
    value: (point) => point.important
  },
  {
    caption: "improves, not urgent",
    label: "Suggested",
    tone: (count) => (count > 0 ? "info" : "neutral"),
    value: (point) => point.suggested
  }
];

// ─── Digest ───────────────────────────────────────────────────────────────────

function ToneText({ children, className, tone }: {
  readonly children: React.ReactNode;
  readonly className?: string;
  readonly tone: Tone;
}) {
  return (
    <span className={className} data-tone={tone}>
      {children}
    </span>
  );
}

function notReachedCaption(count: number): string | null {
  if (count === 0) {
    return null;
  }
  return `${count} ${count === 1 ? "check" : "checks"} not reached`;
}

function GradeTile({ report }: { readonly report: SentinelReport }) {
  const grade = report.highlight?.grade ?? null;
  const coherence = report.highlight?.coherence ?? null;
  const tone = gradeTone(grade);
  const coherenceTone = gradeTone(coherence);

  return (
    <StatTile
      label="Health"
      tone={tone}
      badge={report.isPartial ? "PARTIAL" : undefined}
      value={
        grade === null ? (
          <ToneText className="stat-tile__value--word" tone="neutral">Not graded</ToneText>
        ) : (
          <ToneText className="stat-tile__value--grade" tone={tone}>{grade}</ToneText>
        )
      }
      trend={
        coherence === null ? undefined : (
          <ToneText className={`tone-pill tone-pill--${coherenceTone}`} tone={coherenceTone}>
            Coherence {coherence}
          </ToneText>
        )
      }
      caption={notReachedCaption(report.notReachedCount)}
    />
  );
}

function CountTiles({ report }: { readonly report: SentinelReport }) {
  return (
    <>
      {COUNT_TILES.map((tile) => {
        const count = report.highlight === null ? null : tile.value(report.highlight);
        const tone = count === null ? "neutral" : tile.tone(count);
        return (
          <StatTile
            key={tile.label}
            label={tile.label}
            tone={tone}
            value={<ToneText tone={tone}>{count ?? "n/a"}</ToneText>}
            caption={tile.caption}
          />
        );
      })}
    </>
  );
}

// ─── Trend ────────────────────────────────────────────────────────────────────

function ReportSelector({ reports, selected, onSelect }: {
  readonly onSelect: (fileName: string) => void;
  readonly reports: readonly SentinelReport[];
  readonly selected: SentinelReport;
}) {
  return (
    <label className="sentinel-selector">
      <span className="sentinel-selector__label">Report</span>
      <select
        aria-label="Select sentinel report by date"
        value={selected.fileName}
        onChange={(event) => onSelect(event.target.value)}
      >
        {reports.map((candidate) => (
          <option key={candidate.fileName} value={candidate.fileName}>
            {formatReportLabel(candidate)}
          </option>
        ))}
      </select>
    </label>
  );
}

function GradeTrend({ logSeries }: { readonly logSeries: readonly SentinelLogPoint[] }) {
  const recent = logSeries.slice(-TREND_RUN_LIMIT);
  if (recent.length === 0) {
    return <p className="muted">No runs in SENTINEL_LOG.md yet.</p>;
  }

  return (
    <figure className="sentinel-trend" aria-label="Health grade trend by run">
      <SentinelSparklineClient runs={recent} />
      <figcaption>
        <ol className="sentinel-trend__runs">
          {recent.map((run, index) => {
            const tone = gradeTone(run.grade);
            return (
              <li key={`${run.timestamp ?? "run"}-${index}`}>
                <time>{runDay(run.timestamp, index)}</time>
                <ToneText className={`tone-pill tone-pill--${tone}`} tone={tone}>
                  {run.grade ?? "?"}
                </ToneText>
              </li>
            );
          })}
        </ol>
      </figcaption>
    </figure>
  );
}

// ─── Findings ─────────────────────────────────────────────────────────────────

/** Whether the report has critical findings: the log count when known, else any section text. */
function hasCriticalFindings(report: SentinelReport): boolean {
  return (report.highlight?.critical ?? (report.sections.critical.trim() === "" ? 0 : 1)) > 0;
}

function Findings({ report }: { readonly report: SentinelReport }) {
  const { sections } = report;
  const critical = hasCriticalFindings(report);

  return (
    <div className="sentinel-sections">
      {sections.critical.trim() !== "" ? (
        <ArtifactCard title="Critical" defaultOpen={critical}>
          <MarkdownSurface body={sections.critical} />
        </ArtifactCard>
      ) : null}
      {sections.important.trim() !== "" ? (
        <ArtifactCard title="Important" defaultOpen={!critical}>
          <MarkdownSurface body={sections.important} />
        </ArtifactCard>
      ) : null}
      {sections.suggested.trim() !== "" ? (
        <ArtifactCard title="Suggested">
          <MarkdownSurface body={sections.suggested} />
        </ArtifactCard>
      ) : null}
      {sections.rest.trim() !== "" ? (
        <ArtifactCard title="Full report">
          <MarkdownSurface body={sections.rest} />
        </ArtifactCard>
      ) : null}
    </div>
  );
}

// ─── Main client component ────────────────────────────────────────────────────

export function SentinelClient({ reports, logSeries }: {
  readonly logSeries: readonly SentinelLogPoint[];
  readonly reports: readonly SentinelReport[];
}) {
  const [selectedFileName, setSelectedFileName] = useState(reports[0]?.fileName ?? "");

  const selected = useMemo(
    () => reports.find((report) => report.fileName === selectedFileName) ?? reports[0] ?? null,
    [reports, selectedFileName]
  );

  if (selected === null) {
    return null;
  }

  return (
    <div className="sentinel-client">
      <section className="digest-row" aria-label="Sentinel report summary">
        <GradeTile report={selected} />
        <CountTiles report={selected} />
      </section>

      <SectionCard
        title="Health grade trend"
        actions={<ReportSelector reports={reports} selected={selected} onSelect={setSelectedFileName} />}
      >
        <GradeTrend logSeries={logSeries} />
      </SectionCard>

      <Findings report={selected} />
    </div>
  );
}
