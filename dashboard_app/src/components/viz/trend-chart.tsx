"use client";

import { useState } from "react";
import {
  CartesianGrid,
  type DotItemDotProps,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis
} from "recharts";

export type AxisSide = "left" | "right";

export type TrendPoint = { x: string | number; y: number | null };

export type TrendSeries = {
  label: string;
  color: string;
  points: TrendPoint[];
  /**
   * Which y-axis this series binds to. When omitted, axis assignment is
   * computed from series magnitudes (see `assignSeriesAxes`): same-scale
   * series share one axis; a small-magnitude series is split onto the right
   * axis so it is never flattened against the bottom of a large-magnitude one.
   */
  axis?: AxisSide;
  /** Per-series value formatter, in the metric's own unit. */
  yFormatter?: (n: number) => string;
};

export type TrendChartProps = {
  series: TrendSeries[];
  xLabel?: string;
  /** Fallback formatter for series that carry no `yFormatter` of their own. */
  yFormatter?: (n: number) => string;
  height?: number;
  /**
   * When provided, the x-value for the currently selected snapshot is marked
   * with a larger filled dot and the x-axis shows only [first, last, selected].
   */
  selectedX?: string | null;
};

/** A single recharts data row: keys are the x-axis value key plus one key per series. */
export type ChartRow = Record<string, string | number | null>;

/**
 * Merges multiple TrendSeries into a flat recharts-compatible data array.
 * The x-tick union is the set of all x values across all series, in original
 * order (stable: first-appearance ordering, ties broken by series index).
 * Where a series has no data point for a given x, the value is null — recharts
 * renders null as a gap when `connectNulls={false}`.
 */
export function shapeChartData(series: TrendSeries[]): ChartRow[] {
  if (series.length === 0) {
    return [];
  }

  // Build ordered x-tick union preserving first-appearance order.
  const seen = new Set<string | number>();
  const xOrder: Array<string | number> = [];

  for (const s of series) {
    for (const pt of s.points) {
      if (!seen.has(pt.x)) {
        seen.add(pt.x);
        xOrder.push(pt.x);
      }
    }
  }

  // Build a lookup per series label: Map<xValue, y|null>
  const lookups = new Map<string, Map<string | number, number | null>>();
  for (const s of series) {
    const m = new Map<string | number, number | null>();
    for (const pt of s.points) {
      m.set(pt.x, pt.y);
    }
    lookups.set(s.label, m);
  }

  // Merge into row objects.
  return xOrder.map((x) => {
    const row: ChartRow = { x };
    for (const s of series) {
      const y = lookups.get(s.label)?.get(x);
      row[s.label] = y !== undefined ? y : null;
    }
    return row;
  });
}

// ---------------------------------------------------------------------------
// Axis assignment — keep mismatched-unit series legible on separate axes
// ---------------------------------------------------------------------------

/** Series whose magnitudes differ by more than this factor get split onto two axes. */
const AXIS_SPLIT_RATIO = 8;

/** Representative magnitude of a series: the largest absolute non-null value. */
function seriesMagnitude(s: TrendSeries): number {
  let max = 0;
  for (const pt of s.points) {
    if (pt.y != null) {
      const a = Math.abs(pt.y);
      if (a > max) max = a;
    }
  }
  return max;
}

/**
 * Decides which y-axis each series binds to. An explicit `series.axis` always
 * wins. Otherwise: series with no data and same-scale clusters stay on the left
 * axis; when the largest and smallest magnitudes differ by more than
 * AXIS_SPLIT_RATIO, the series are split at their widest magnitude gap — larger
 * cluster on the left, smaller on the right. Pure and deterministic.
 */
export function assignSeriesAxes(series: TrendSeries[]): Map<string, AxisSide> {
  const result = new Map<string, AxisSide>();

  const explicit = series.filter((s) => s.axis);
  for (const s of explicit) {
    result.set(s.label, s.axis as AxisSide);
  }
  const auto = series.filter((s) => !s.axis);

  // Series with measurable magnitude, sorted descending.
  const ranked = auto
    .map((s) => ({ label: s.label, mag: seriesMagnitude(s) }))
    .filter((r) => r.mag > 0)
    .sort((a, b) => b.mag - a.mag);

  if (ranked.length <= 1) {
    for (const s of auto) result.set(s.label, "left");
    return result;
  }

  const mags = ranked.map((r) => r.mag);
  const maxMag = mags[0] ?? 0;
  const minMag = mags[mags.length - 1] ?? 0;

  if (minMag <= 0 || maxMag / minMag <= AXIS_SPLIT_RATIO) {
    for (const s of auto) result.set(s.label, "left");
    return result;
  }

  // Split at the widest consecutive magnitude gap (in ratio terms).
  let splitIndex = 1;
  let widestRatio = 0;
  for (let i = 1; i < ranked.length; i += 1) {
    const prev = ranked[i - 1];
    const curr = ranked[i];
    if (!prev || !curr) continue;
    const ratio = prev.mag / Math.max(curr.mag, Number.EPSILON);
    if (ratio > widestRatio) {
      widestRatio = ratio;
      splitIndex = i;
    }
  }

  ranked.forEach((r, i) => result.set(r.label, i < splitIndex ? "left" : "right"));
  // Auto series with no measurable magnitude default to the left axis.
  for (const s of auto) {
    if (!result.has(s.label)) result.set(s.label, "left");
  }
  return result;
}

/** Latest (last non-null) value of a series, or null. */
function latestValue(s: TrendSeries): number | null {
  for (let i = s.points.length - 1; i >= 0; i -= 1) {
    const y = s.points[i]?.y;
    if (y != null) return y;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

type TooltipPayloadEntry = {
  name?: string;
  value?: number | null;
  color?: string;
};

type CustomTooltipProps = TooltipContentProps<number, string> & {
  formatters: Map<string, (n: number) => string>;
  fallback: (n: number) => string;
};

function CustomTooltip({ active, payload, label, formatters, fallback }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="trend-chart__tooltip">
      <p className="trend-chart__tooltip-label">{label}</p>
      {payload.map((entry) => {
        const typed = entry as TooltipPayloadEntry;
        if (typed.value == null) return null;
        const fmt = (typed.name && formatters.get(typed.name)) || fallback;
        return (
          <p key={typed.name} className="trend-chart__tooltip-entry">
            <span className="trend-chart__tooltip-swatch" style={{ background: typed.color }} aria-hidden />
            <span className="trend-chart__tooltip-name" style={{ color: typed.color }}>
              {typed.name}
            </span>
            <span className="trend-chart__tooltip-value">{fmt(typed.value)}</span>
          </p>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrendChart — dual-axis, per-series color, interactive legend
// ---------------------------------------------------------------------------

const DEFAULT_HEIGHT = 200;
const DEFAULT_Y_FORMATTER = String;
const DOT_RADIUS = 2.5;
const ACTIVE_DOT_RADIUS = 5;
const SELECTED_DOT_RADIUS = 5;

/**
 * Generic recharts line chart wrapper:
 * - Per-series stroke color (the metric palette), thin lines (~1.6px)
 * - Up to two y-axes (left/right), auto-assigned by magnitude so mismatched
 *   units are never flattened; each axis is tinted to its series group
 * - Interactive legend chips above the plot — swatch + label + latest value;
 *   clicking a chip toggles that series (progressive disclosure / declutter),
 *   and the axes rescale to the remaining visible series
 * - X-axis ticks: first / last / selected snapshot only (≤ 3)
 * - Selected snapshot marked with a larger filled accent dot
 *
 * Accepts arbitrary series — no metric names or grade values hardcoded.
 * null y values produce gaps (`connectNulls={false}`).
 */
export function TrendChart({
  series,
  xLabel,
  yFormatter = DEFAULT_Y_FORMATTER,
  height = DEFAULT_HEIGHT,
  selectedX = null
}: TrendChartProps) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  if (series.length === 0) {
    return null;
  }

  const visible = series.filter((s) => !hidden.has(s.label));
  const axisOf = assignSeriesAxes(visible);
  const hasRight = Array.from(axisOf.values()).includes("right");

  const formatterOf = (s: TrendSeries) => s.yFormatter ?? yFormatter;
  const formatters = new Map(series.map((s) => [s.label, formatterOf(s)]));

  // Per-axis formatter + tint: take the first visible series bound to that side.
  const sideSeries = (side: AxisSide) => visible.find((s) => axisOf.get(s.label) === side);
  const leftSeries = sideSeries("left");
  const rightSeries = sideSeries("right");
  const leftFormatter = leftSeries ? formatterOf(leftSeries) : yFormatter;
  const rightFormatter = rightSeries ? formatterOf(rightSeries) : yFormatter;

  const data = shapeChartData(visible);

  // Compute x-axis ticks: first, last, and selected — deduplicated.
  const allXValues = data
    .map((row) => row["x"])
    .filter((x): x is string | number => x !== null && x !== undefined);
  const firstX = allXValues[0];
  const lastX = allXValues.at(-1);
  const xTicks = Array.from(
    new Set([firstX, lastX, selectedX].filter((x): x is string | number => x !== null && x !== undefined))
  );

  const toggle = (label: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      // Never allow hiding the last visible series.
      if (next.has(label)) {
        next.delete(label);
      } else if (series.length - next.size > 1) {
        next.add(label);
      }
      return next;
    });
  };

  const renderDot = (s: TrendSeries) => (dotProps: DotItemDotProps) => {
    const payloadX = (dotProps.payload as ChartRow)["x"];
    const isSelected = payloadX === selectedX;
    const r = isSelected ? SELECTED_DOT_RADIUS : DOT_RADIUS;
    const fillColor = isSelected ? "var(--color-accent)" : s.color;
    return (
      <circle
        key={`dot-${s.label}-${String(payloadX)}`}
        cx={dotProps.cx ?? 0}
        cy={dotProps.cy ?? 0}
        r={r}
        fill={fillColor}
        stroke="none"
      />
    );
  };

  return (
    <div className="trend-chart-wrapper">
      <div className="trend-chart__legend" role="group" aria-label="Toggle series">
        {series.map((s) => {
          const isHidden = hidden.has(s.label);
          const side = axisOf.get(s.label);
          const latest = latestValue(s);
          return (
            <button
              key={s.label}
              type="button"
              className={`trend-chart__chip${isHidden ? " is-hidden" : ""}`}
              onClick={() => toggle(s.label)}
              aria-pressed={!isHidden}
            >
              <span className="trend-chart__chip-swatch" style={{ background: s.color }} aria-hidden />
              <span className="trend-chart__chip-label">{s.label}</span>
              {latest != null ? (
                <span className="trend-chart__chip-value">{formatterOf(s)(latest)}</span>
              ) : null}
              {hasRight && side ? (
                <span className="trend-chart__chip-axis" aria-hidden>
                  {side === "left" ? "L" : "R"}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: hasRight ? 8 : 16, bottom: xLabel ? 24 : 8, left: 8 }}>
          <CartesianGrid horizontal={false} vertical={false} />
          <ReferenceLine yAxisId="left" y={0} stroke="var(--color-border)" strokeWidth={1} ifOverflow="hidden" />
          <XAxis
            dataKey="x"
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--color-border)" }}
            ticks={xTicks as string[]}
            label={
              xLabel
                ? { value: xLabel, position: "insideBottom", offset: -12, fill: "var(--color-text-muted)", fontSize: 11 }
                : undefined
            }
          />
          <YAxis
            yAxisId="left"
            orientation="left"
            tickFormatter={(v: number) => leftFormatter(v)}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={leftSeries ? { stroke: leftSeries.color, strokeOpacity: 0.5 } : false}
            tickCount={3}
            width={48}
          />
          {hasRight ? (
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={(v: number) => rightFormatter(v)}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
              tickLine={false}
              axisLine={rightSeries ? { stroke: rightSeries.color, strokeOpacity: 0.5 } : false}
              tickCount={3}
              width={48}
            />
          ) : null}
          <Tooltip
            content={(props) => (
              <CustomTooltip
                {...(props as TooltipContentProps<number, string>)}
                formatters={formatters}
                fallback={yFormatter}
              />
            )}
            cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }}
          />
          {visible.map((s) => (
            <Line
              key={s.label}
              yAxisId={axisOf.get(s.label) ?? "left"}
              type="monotone"
              dataKey={s.label}
              stroke={s.color}
              strokeWidth={1.6}
              dot={renderDot(s)}
              activeDot={{ r: ACTIVE_DOT_RADIUS, fill: s.color, stroke: "var(--color-surface-1)", strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
