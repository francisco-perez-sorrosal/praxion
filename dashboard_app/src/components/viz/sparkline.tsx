"use client";

import { shapeChartData, type TrendChartProps, type TrendSeries } from "./trend-chart";
import { Line, LineChart, ResponsiveContainer } from "recharts";

export type SparklineProps = Omit<TrendChartProps, "xLabel"> & {
  compact?: true;
  /** Override stroke color for all series. Takes precedence over `colorForValue`. */
  color?: string;
  colorForValue?: (y: number) => string;
};

const SPARKLINE_HEIGHT = 56;
const DOT_RADIUS = 2;
const DEFAULT_COLOR = "var(--color-text-muted)";

/**
 * Compact line preview — no axes, no grid, no tooltip.
 * Suitable for inline health-grade trends next to the latest sentinel report.
 * `color` overrides the stroke color for all series uniformly.
 * `colorForValue` overrides per-render based on the most recent y value (ignored when `color` is set).
 */
export function Sparkline({ series, height = SPARKLINE_HEIGHT, color, colorForValue }: SparklineProps) {
  if (series.length === 0) {
    return null;
  }

  const data = shapeChartData(series);
  if (data.length === 0) {
    return null;
  }

  // Resolve stroke: static `color` prop wins; then `colorForValue` from last non-null y; then series color.
  const resolveColor = (s: TrendSeries): string => {
    if (color !== undefined) {
      return color;
    }
    if (colorForValue) {
      const lastPoint = [...s.points].reverse().find((pt) => pt.y !== null);
      return lastPoint?.y !== undefined && lastPoint.y !== null
        ? colorForValue(lastPoint.y)
        : s.color ?? DEFAULT_COLOR;
    }
    return s.color ?? DEFAULT_COLOR;
  };

  return (
    <div className="sparkline-wrapper">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          {series.map((s) => (
            <Line
              key={s.label}
              type="monotone"
              dataKey={s.label}
              stroke={resolveColor(s)}
              strokeWidth={1.5}
              dot={{ r: DOT_RADIUS, fill: resolveColor(s), strokeWidth: 0 }}
              activeDot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
