"use client";

import {
  CartesianGrid,
  type DotItemDotProps,
  Label,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis
} from "recharts";

export type TrendPoint = { x: string | number; y: number | null };

export type TrendSeries = {
  label: string;
  color: string;
  points: TrendPoint[];
};

export type TrendChartProps = {
  series: TrendSeries[];
  xLabel?: string;
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
// Custom tooltip
// ---------------------------------------------------------------------------

type TooltipPayloadEntry = {
  name?: string;
  value?: number | null;
  color?: string;
};

type CustomTooltipProps = TooltipContentProps<number, string> & {
  yFormatter: (n: number) => string;
};

function CustomTooltip({ active, payload, label, yFormatter }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }

  return (
    <div className="trend-chart__tooltip">
      <p className="trend-chart__tooltip-label">{label}</p>
      {payload.map((entry) => {
        const typed = entry as TooltipPayloadEntry;
        if (typed.value == null) return null;
        return (
          <p key={typed.name} className="trend-chart__tooltip-entry" style={{ color: typed.color }}>
            <span className="trend-chart__tooltip-name">{typed.name}: </span>
            <span className="trend-chart__tooltip-value">{yFormatter(typed.value)}</span>
          </p>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrendChart — Tufte pass
// ---------------------------------------------------------------------------

const DEFAULT_HEIGHT = 200;
const DEFAULT_Y_FORMATTER = String;
const DOT_RADIUS = 3;
const ACTIVE_DOT_RADIUS = 5;
const SELECTED_DOT_RADIUS = 5;

/**
 * Generic recharts line chart wrapper — Tufte discipline applied:
 * - No CartesianGrid (gridlines removed; only a single faint baseline at y=0
 *   when relevant)
 * - No Legend box — direct-label the line at its right end via <Label>
 * - X-axis ticks: first / last / selected snapshot only (≤ 3)
 * - Y-axis: ≤ 3 ticks
 * - Thin line (~1.5px), neutral color
 * - Selected snapshot marked with a larger filled dot
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
  if (series.length === 0) {
    return null;
  }

  const data = shapeChartData(series);

  if (data.length === 0) {
    return null;
  }

  // Compute x-axis ticks: first, last, and selected — deduplicated.
  const allXValues = data.map((row) => row["x"]).filter((x): x is string | number => x !== null && x !== undefined);
  const firstX = allXValues[0];
  const lastX = allXValues.at(-1);

  const xTicks = Array.from(
    new Set(
      [firstX, lastX, selectedX].filter((x): x is string | number => x !== null && x !== undefined)
    )
  );

  return (
    <div className="trend-chart-wrapper">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 56, bottom: xLabel ? 24 : 8, left: 8 }}>
          {/* Tufte: no grid — only a faint baseline */}
          <CartesianGrid horizontal={false} vertical={false} />
          <ReferenceLine
            y={0}
            stroke="var(--color-border)"
            strokeWidth={1}
            ifOverflow="hidden"
          />
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
            tickFormatter={(v: number) => yFormatter(v)}
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickCount={3}
            width={48}
          />
          <Tooltip
            content={(props) => (
              <CustomTooltip {...(props as TooltipContentProps<number, string>)} yFormatter={yFormatter} />
            )}
            cursor={{ stroke: "var(--color-border)", strokeWidth: 1 }}
          />
          {series.map((s) => (
            <Line
              key={s.label}
              type="monotone"
              dataKey={s.label}
              stroke="var(--color-text-muted)"
              strokeWidth={1.5}
              dot={(dotProps: DotItemDotProps) => {
                const payloadX = (dotProps.payload as ChartRow)["x"];
                const isSelected = payloadX === selectedX;
                const r = isSelected ? SELECTED_DOT_RADIUS : DOT_RADIUS;
                const fillColor = isSelected ? "var(--color-accent)" : s.color;
                const cx = dotProps.cx ?? 0;
                const cy = dotProps.cy ?? 0;
                return (
                  <circle
                    key={`dot-${String(payloadX)}`}
                    cx={cx}
                    cy={cy}
                    r={r}
                    fill={fillColor}
                    stroke="none"
                  />
                );
              }}
              activeDot={{ r: ACTIVE_DOT_RADIUS, fill: s.color, stroke: "var(--color-surface-1)", strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            >
              {/* Direct-label the line at its right end — Tufte: no legend box */}
              <Label
                value={s.label}
                position="right"
                fill="var(--color-text-muted)"
                fontSize={11}
                offset={4}
              />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
