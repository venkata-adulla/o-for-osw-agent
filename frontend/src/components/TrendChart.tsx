/**
 * Small multi-series trend chart.
 *
 * The important behaviour is the gap: a NULL day means the day is absent from
 * that extract, which is not the same as zero. `connectNulls={false}` keeps the
 * line broken so the chart cannot imply data it does not hold.
 */
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SERIES_COLORS } from "../lib/api";

export interface TrendSeries {
  /** Key in each data row. */
  key: string;
  /** Legend label. */
  label: string;
  /** Optional explicit colour; defaults to the shared categorical ramp. */
  color?: string;
}

export type TrendRow = Record<string, string | number | null>;

const AXIS_TICK = { fill: "var(--ink-3)", fontSize: 11, fontFamily: "var(--font-mono)" } as const;

export default function TrendChart({
  data,
  series,
  xKey,
  height = 240,
  area = false,
  xTickFormatter,
}: {
  data: TrendRow[];
  series: TrendSeries[];
  xKey: string;
  height?: number;
  area?: boolean;
  xTickFormatter?: (value: string) => string;
}) {
  const colorFor = (s: TrendSeries, i: number) => s.color ?? SERIES_COLORS[i % SERIES_COLORS.length];

  if (data.length === 0) return <div className="empty">Nothing in this extract for the selected window.</div>;

  // An array, not a fragment: recharts inspects its direct children to find the
  // axes, and arrays flatten while fragments are not guaranteed to.
  const axes = [
    <CartesianGrid key="grid" stroke="var(--grid)" vertical={false} />,
    <XAxis
      key="x"
      dataKey={xKey}
      tick={AXIS_TICK}
      tickFormatter={xTickFormatter}
      stroke="var(--rule)"
      tickMargin={8}
    />,
    <YAxis key="y" tick={AXIS_TICK} stroke="var(--rule)" allowDecimals={false} width={38} />,
    <Tooltip
      key="tip"
      isAnimationActive={false}
      formatter={(value: unknown, name: unknown): [string, string] => [
        value === null || value === undefined ? "—" : String(value),
        String(name),
      ]}
    />,
  ];

  return (
    <div className="stack">
      <ResponsiveContainer width="100%" height={height}>
        {area ? (
          <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            {axes}
            {series.map((s, i) => (
              <Area
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={colorFor(s, i)}
                fill={colorFor(s, i)}
                fillOpacity={0.14}
                strokeWidth={2}
                dot={{ r: 2.5 }}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            {axes}
            {series.map((s, i) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={colorFor(s, i)}
                strokeWidth={2}
                dot={{ r: 2.5 }}
                activeDot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        )}
      </ResponsiveContainer>

      <div className="legend">
        {series.map((s, i) => (
          <span className="legend__key" key={s.key}>
            <span className="legend__swatch" style={{ background: colorFor(s, i) }} />
            {s.label}
          </span>
        ))}
        <span className="legend__key">
          <span className="legend__swatch" style={{ background: "var(--rule-strong)" }} />
          gap = day absent from that extract
        </span>
      </div>
    </div>
  );
}
