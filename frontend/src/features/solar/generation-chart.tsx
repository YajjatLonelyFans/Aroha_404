"use client";

import { useEffect, useId, useRef, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Schemas } from "@/lib/api";
import { formatKwh, formatKwpNumber, formatNumber } from "@/lib/format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FULL_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

// Chart tokens (docs/DESIGN_SYSTEM.md): amber marks; text, grid and whiskers in neutral ink.
const BAR = "var(--aroha-amber)";
const WHISKER = "var(--muted-foreground)";
const GRID = "var(--border)";
const INK = "var(--muted-foreground)";
// Season bands: two light neutral washes, alternating, so neighbouring seasons read apart.
const SEASON_TINTS = ["#efece4", "#f6f4ee"];

type Row = { month: number; median: number | null; p10: number | null; p90: number | null; whisker: [number, number] };

/** Consecutive runs of months for each season (winter wraps Dec → Feb, so it can be two runs). */
function seasonRuns(seasons: Record<string, number[]>): { name: string; from: number; to: number }[] {
  const runs: { name: string; from: number; to: number }[] = [];
  for (const [name, months] of Object.entries(seasons)) {
    const sorted = [...months].sort((a, b) => a - b);
    let start = sorted[0];
    for (let i = 1; i <= sorted.length; i++) {
      if (sorted[i] !== sorted[i - 1] + 1) {
        runs.push({ name, from: start, to: sorted[i - 1] });
        start = sorted[i];
      }
    }
  }
  return runs.sort((a, b) => a.from - b.from);
}

const seasonLabel = (name: string) => name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const Y_AXIS_PX = 48;
const LABEL_PX_PER_CHAR = 6.5; // 11px text

/** A season's label only if it fits its band: full, then 3 letters, else none (the notes and table still name it). */
function fittedLabel(name: string, bandPx: number): string | undefined {
  const full = seasonLabel(name);
  if (full.length * LABEL_PX_PER_CHAR + 8 <= bandPx) return full;
  const short = `${full.slice(0, 3)}.`;
  return short.length * LABEL_PX_PER_CHAR + 6 <= bandPx ? short : undefined;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/**
 * Monthly generation: median bars with p10–p90 whiskers from 10 years of weather, and the
 * seasons as background bands. One series, so no legend; the title names it. All values come
 * from the backend's estimate. A table view carries every number for readers who can't use the chart.
 */
export function GenerationChart({
  option,
  seasons,
  period,
}: {
  option: Schemas["EstimateOption"];
  seasons: Record<string, number[]> | null;
  period: string | null;
}) {
  const titleId = useId();
  const [plotRef, width] = useWidth<HTMLDivElement>();
  const monthPx = Math.max(0, width - Y_AXIS_PX - 8) / 12;
  const narrow = monthPx < 40; // three-letter months stop fitting
  // Bars at most 20px, always leaving a gap between neighbours.
  const barSize = Math.max(4, Math.min(20, Math.floor(monthPx - 6)));
  const rows: Row[] = option.monthly_kwh.map((m) => ({
    month: m.month,
    median: m.median,
    p10: m.p10,
    p90: m.p90,
    whisker: [
      m.median != null && m.p10 != null ? m.median - m.p10 : 0,
      m.median != null && m.p90 != null ? m.p90 - m.median : 0,
    ],
  }));
  const runs = seasons ? seasonRuns(seasons) : [];
  const tint = new Map(Object.keys(seasons ?? {}).map((name, i) => [name, SEASON_TINTS[i % SEASON_TINTS.length]]));

  return (
    <figure aria-labelledby={titleId} className="flex flex-col gap-3">
      <figcaption id={titleId}>
        <h3 className="text-lg">Monthly generation, {formatKwpNumber(option.capacity_kwp)} kWp system</h3>
        <p className="text-sm text-muted-foreground">
          kWh per month. Bars show a typical month; the thin lines show the range in 8 years out of 10.
        </p>
      </figcaption>

      <div ref={plotRef} className="h-72 w-full" role="img" aria-label={`Bar chart of monthly generation in kWh for a ${option.capacity_kwp} kWp system`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 22, right: 8, bottom: 0, left: 0 }}>
            {runs.map((r) => (
              <ReferenceArea
                key={`${r.name}-${r.from}`}
                x1={r.from - 0.5}
                x2={r.to + 0.5}
                fill={tint.get(r.name)}
                fillOpacity={1}
                stroke="none"
                ifOverflow="hidden"
                label={{ value: fittedLabel(r.name, (r.to - r.from + 1) * monthPx), position: "insideTop", fill: INK, fontSize: 11, offset: -16 }}
              />
            ))}
            <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
            <XAxis
              dataKey="month"
              type="number"
              domain={[0.5, 12.5]}
              ticks={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]}
              tickFormatter={(m: number) => (narrow ? MONTHS[m - 1][0] : MONTHS[m - 1])}
              tick={{ fill: INK, fontSize: 12 }}
              axisLine={{ stroke: GRID }}
              tickLine={false}
              interval={0}
            />
            <YAxis
              tick={{ fill: INK, fontSize: 12 }}
              tickFormatter={(v: number) => formatNumber(v)}
              axisLine={false}
              tickLine={false}
              width={48}
            />
            <Tooltip
              cursor={{ fill: "rgba(7, 63, 50, 0.06)" }}
              content={({ active, payload }) => <MonthTooltip row={active ? (payload?.[0]?.payload as Row) : undefined} />}
            />
            <Bar dataKey="median" fill={BAR} barSize={barSize} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              <ErrorBar dataKey="whisker" width={6} stroke={WHISKER} strokeWidth={1.5} direction="y" />
            </Bar>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <p className="text-sm text-muted-foreground">
        Estimate based on {period ?? "past"} historical weather data, not a guarantee
      </p>

      <details className="text-sm">
        <summary className="cursor-pointer font-medium text-primary">Show as a table</summary>
        <table className="mt-2 w-full tabular-nums">
          <caption className="sr-only">Monthly generation in kWh</caption>
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th scope="col" className="py-1.5 font-medium">Month</th>
              <th scope="col" className="py-1.5 text-right font-medium">Typical</th>
              <th scope="col" className="py-1.5 text-right font-medium">Low (1 in 10)</th>
              <th scope="col" className="py-1.5 text-right font-medium">High (1 in 10)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.month} className="border-b border-border last:border-0">
                <th scope="row" className="py-1.5 text-left font-normal">{FULL_MONTHS[r.month - 1]}</th>
                <td className="py-1.5 text-right">{formatKwh(r.median)}</td>
                <td className="py-1.5 text-right">{formatKwh(r.p10)}</td>
                <td className="py-1.5 text-right">{formatKwh(r.p90)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

function MonthTooltip({ row }: { row: Row | undefined }) {
  if (!row) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-sm shadow-sm">
      <p className="font-semibold tabular-nums text-foreground">{formatKwh(row.median)}</p>
      <p className="text-muted-foreground">{FULL_MONTHS[row.month - 1]}, typical</p>
      <p className="mt-1 tabular-nums text-muted-foreground">
        Range {formatKwh(row.p10)} to {formatKwh(row.p90)}
      </p>
    </div>
  );
}
