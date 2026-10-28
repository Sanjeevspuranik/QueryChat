"use client";

import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type ChartConfig, type ChartType, MAX_PIE_SLICES, chartData, defaultChart, numericColumns } from "@/lib/chartModel";
import type { QueryResult } from "@/lib/types";

const COLORS = ["#6c63ff", "#22b8cf", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#f472b6", "#2dd4bf"];
const EXPORT_FORMATS = ["csv", "json"] as const;
const CHART_MARGIN = { top: 8, right: 12, bottom: 4, left: 0 };
const TOOLTIP = {
  contentStyle: {
    background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", fontSize: 13,
  },
  labelStyle: { color: "var(--text)", fontWeight: 600 },
  itemStyle: { color: "var(--text)" },
};

const shorten = (s: string, max: number) => (s.length > max ? `${s.slice(0, max - 1)}…` : s);

function formatNumber(v: unknown): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return Math.abs(n) >= 10_000
    ? new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n)
    : new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(n);
}

/** Keeps category labels readable: tilt and thin them out as the count grows. */
function xAxisProps(count: number) {
  return {
    tickLine: false,
    tickFormatter: (v: unknown) => shorten(String(v), 14),
    interval: count > 12 ? ("preserveStartEnd" as const) : 0,
    angle: count > 6 ? -35 : 0,
    textAnchor: count > 6 ? ("end" as const) : ("middle" as const),
    height: count > 6 ? 70 : 30,
    minTickGap: 12,
  };
}

interface Props {
  result: QueryResult;
  /** Base URL of the export endpoint for this result; omit to hide the export buttons. */
  exportUrl?: string;
}

export default function ResultView({ result, exportUrl }: Props) {
  const initial = useMemo(() => defaultChart(result), [result]);
  const numeric = useMemo(() => numericColumns(result), [result]);
  const [config, setConfig] = useState<ChartConfig | null>(initial);
  const [view, setView] = useState<"table" | "chart">(initial ? "chart" : "table");

  if (result.row_count === 0) return <p className="muted">No rows returned.</p>;

  const data = view === "chart" && config ? chartData(result, config) : null;
  const update = (patch: Partial<ChartConfig>) => setConfig((c) => (c ? { ...c, ...patch } : c));

  return (
    <div className="result">
      <div className="row toolbar">
        {config && (
          <div className="segmented" role="group" aria-label="View">
            <button className={view === "table" ? "active" : ""} onClick={() => setView("table")}>Table</button>
            <button className={view === "chart" ? "active" : ""} onClick={() => setView("chart")}>Chart</button>
          </div>
        )}
        {exportUrl && (
          <span className="export">
            {EXPORT_FORMATS.map((fmt) => (
              <a key={fmt} className="button-link secondary" href={`${exportUrl}?format=${fmt}`} download>
                {fmt.toUpperCase()}
              </a>
            ))}
          </span>
        )}
      </div>

      {view === "chart" && config && (
        <div className="chart-controls row">
          <label>
            Type
            <select value={config.type} onChange={(e) => update({ type: e.target.value as ChartType })}>
              <option value="bar">Bar</option>
              <option value="line">Line</option>
              <option value="pie">Pie</option>
            </select>
          </label>
          <label>
            Label
            <select value={config.x} onChange={(e) => update({ x: Number(e.target.value) })}>
              {result.columns.map((c, i) => <option key={c + i} value={i}>{c}</option>)}
            </select>
          </label>
          <label>
            Value
            <select value={config.y} onChange={(e) => update({ y: Number(e.target.value) })}>
              {numeric.map((i) => <option key={i} value={i}>{result.columns[i]}</option>)}
            </select>
          </label>
        </div>
      )}

      {data && config ? (
        <div className="chart">
          <ResponsiveContainer width="100%" height={config.type === "pie" ? 300 : 280}>
            {config.type === "pie" ? (
              <PieChart>
                <Pie
                  data={data} dataKey="value" nameKey="label"
                  innerRadius={62} outerRadius={105} paddingAngle={2} stroke="none"
                >
                  {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip {...TOOLTIP} formatter={(v) => formatNumber(v)} />
                <Legend verticalAlign="bottom" iconType="circle" iconSize={8} formatter={(v) => shorten(String(v), 22)} />
              </PieChart>
            ) : config.type === "line" ? (
              <LineChart data={data} margin={CHART_MARGIN}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="label" {...xAxisProps(data.length)} />
                <YAxis width={56} tickLine={false} axisLine={false} tickFormatter={formatNumber} />
                <Tooltip {...TOOLTIP} formatter={(v) => formatNumber(v)} />
                <Line
                  type="monotone" dataKey="value" name={result.columns[config.y]}
                  stroke={COLORS[0]} strokeWidth={2.5} dot={data.length <= 30 ? { r: 3 } : false} activeDot={{ r: 5 }}
                />
              </LineChart>
            ) : (
              <BarChart data={data} margin={CHART_MARGIN}>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="label" {...xAxisProps(data.length)} />
                <YAxis width={56} tickLine={false} axisLine={false} tickFormatter={formatNumber} />
                <Tooltip {...TOOLTIP} formatter={(v) => formatNumber(v)} cursor={{ fillOpacity: 0.4 }} />
                <Bar
                  dataKey="value" name={result.columns[config.y]} fill={COLORS[0]}
                  radius={[4, 4, 0, 0]} maxBarSize={48}
                />
              </BarChart>
            )}
          </ResponsiveContainer>
          {config.type === "pie" && result.row_count > MAX_PIE_SLICES && (
            <p className="muted">Showing the first {MAX_PIE_SLICES} rows.</p>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>{result.columns.map((c, i) => <th key={c + i}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>{row.map((cell, j) => <td key={j}>{cell === null ? "—" : String(cell)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted">
        {result.row_count} row(s){result.truncated && " — truncated, refine your question for the full set"}
      </p>
    </div>
  );
}
