import type { Route } from "next";
import type { ReactNode } from "react";

import { SentinelSparklineClient } from "@/app/sentinel/sentinel-sparkline-client";
import { StatTile } from "@/components/chrome/stat-tile";
import { Sparkline } from "@/components/viz/sparkline";
import { formatEvalCost } from "@/lib/evals";
import { gradeTone, healthLabelTone, verdictTone } from "@/lib/tone";
import type { Tone } from "@/lib/tone";
import type { EvalsDigest, MetricsDigest, OverviewData, SentinelDigest } from "@/server/view-models/overview";

import { healthWord } from "./health-word";
import { LabelledCount } from "./labelled-count";

const PERCENT = 100;

/**
 * The four glance tiles: sentinel grade, metrics health, quality evals and
 * agent readiness. A family that was not read shows what produces it instead.
 */
export function PulseRow({ evals, metrics, sentinel }: Pick<OverviewData, "evals" | "metrics" | "sentinel">) {
  return (
    <div className="digest-row overview-pulse">
      <SentinelTile sentinel={sentinel} />
      <MetricsTile metrics={metrics} />
      <EvalsTile evals={evals} />
      <ReadinessTile readiness={metrics?.readiness ?? null} />
    </div>
  );
}

// ─── Tiles ────────────────────────────────────────────────────────────────────

function SentinelTile({ sentinel }: { sentinel: SentinelDigest | null }) {
  if (sentinel === null) {
    return <MissingTile href="/sentinel" producer={<>the <code>sentinel</code> agent</>} title="Sentinel" />;
  }
  const counts = [
    { count: sentinel.critical, label: "critical" },
    { count: sentinel.important, label: "important" },
    { count: sentinel.suggested, label: "suggested" }
  ];
  return (
    <PulseTile title="Sentinel">
      <StatTile
        badge={sentinel.isPartial ? "PARTIAL" : undefined}
        caption={
          <span className="overview-caption">
            <span className="overview-counts">
              {counts.map(({ count, label }) =>
                count === null ? null : <LabelledCount count={count} key={label} label={label} />
              )}
            </span>
            {sentinel.coherence === null ? null : <span>coherence {sentinel.coherence}</span>}
          </span>
        }
        href="/sentinel"
        label="Sentinel"
        tone={gradeTone(sentinel.grade)}
        trend={
          sentinel.series.length > 1 ? (
            <SentinelSparklineClient runs={sentinel.series.map(({ grade, timestamp }) => ({ grade, timestamp }))} />
          ) : undefined
        }
        value={
          sentinel.grade === null ? (
            <span className="stat-tile__value--word">Not graded</span>
          ) : (
            <span className="stat-tile__value--grade">{sentinel.grade}</span>
          )
        }
      />
    </PulseTile>
  );
}

function MetricsTile({ metrics }: { metrics: MetricsDigest | null }) {
  if (metrics === null) {
    return <MissingTile href="/metrics" producer={<code>/project-metrics</code>} title="Metrics" />;
  }
  const { bad, good, steady } = metrics.tones;
  const isBaseline = metrics.healthLabel === "BASELINE CAPTURED";
  return (
    <PulseTile title="Metrics">
      <StatTile
        badge={metrics.degraded ? "degraded" : undefined}
        caption={
          isBaseline ? (
            "First snapshot; trends appear after the next run"
          ) : (
            <span className="overview-counts">
              <LabelledCount count={good} label="improving" tone={good > 0 ? "good" : "neutral"} />
              <LabelledCount count={steady} label="steady" tone="neutral" />
              <LabelledCount count={bad} label="worsening" tone={bad > 0 ? "bad" : "neutral"} />
            </span>
          )
        }
        href="/metrics"
        label="Metrics"
        tone={healthLabelTone(metrics.healthLabel)}
        value={<span className="stat-tile__value--word">{healthWord(metrics.healthLabel)}</span>}
      />
    </PulseTile>
  );
}

function EvalsTile({ evals }: { evals: EvalsDigest | null }) {
  if (evals === null) {
    return <MissingTile href="/evals" producer={<code>/eval-praxion</code>} title="Quality evals" />;
  }
  const { fail, pass, warn, costUsd } = evals.latest;
  const headline = fail !== null && fail > 0 ? "FAIL" : warn !== null && warn > 0 ? "WARN" : "PASS";
  return (
    <PulseTile title="Quality evals">
      <StatTile
        caption={
          <span className="overview-caption">
            <span className="overview-counts">
              {pass === null ? null : <LabelledCount count={pass} label="PASS" tone={verdictTone("PASS")} />}
              {warn === null ? null : <LabelledCount count={warn} label="WARN" tone={verdictTone("WARN")} />}
            </span>
            {costUsd === null ? null : <span>{formatEvalCost(costUsd)}</span>}
          </span>
        }
        href="/evals"
        label="Quality evals"
        tone={verdictTone(headline)}
        trend={evals.runs.length > 1 ? <FailTrend runs={evals.runs} /> : undefined}
        value={fail === null ? <span className="stat-tile__value--word">No counts</span> : `${fail} FAIL`}
      />
    </PulseTile>
  );
}

function ReadinessTile({ readiness }: { readiness: MetricsDigest["readiness"] }) {
  if (readiness === null) {
    return <MissingTile href="/metrics" producer={<code>/project-metrics</code>} title="Agent readiness" />;
  }
  return (
    <PulseTile title="Agent readiness">
      <StatTile
        caption={`${formatPercent(readiness.passPct)} of criteria pass`}
        href="/metrics"
        label="Agent readiness"
        value={`Level ${readiness.level}`}
      />
    </PulseTile>
  );
}

// ─── Pieces ───────────────────────────────────────────────────────────────────

/** A tile is an article headed by its name; the heading is for the outline and assistive tools, the tile's own label is the visible one. */
function PulseTile({ children, title }: { children: ReactNode; title: string }) {
  return (
    <article className="pulse-tile">
      <h2 className="overview-sr-only">{title}</h2>
      {children}
    </article>
  );
}

function MissingTile({ href, producer, title }: { href: Route; producer: ReactNode; title: string }) {
  const tone: Tone = "neutral";
  return (
    <PulseTile title={title}>
      <StatTile
        caption={<>Produced by {producer}</>}
        href={href}
        label={title}
        tone={tone}
        value={<span className="stat-tile__value--word">Not run yet</span>}
      />
    </PulseTile>
  );
}

function FailTrend({ runs }: { runs: EvalsDigest["runs"] }) {
  const points = runs.map((run) => ({ x: run.timestamp, y: run.fail }));
  return (
    <span aria-label="FAIL count per run, oldest to newest" className="overview-trend" role="img">
      <Sparkline series={[{ label: "FAIL", color: "var(--color-danger-text)", points }]} />
    </span>
  );
}

/** A fraction of 1 as a percentage with at most one decimal: 0.946 → "94.6 %", 0.82 → "82 %". */
function formatPercent(fraction: number): string {
  return `${Math.round(fraction * PERCENT * 10) / 10} %`;
}
