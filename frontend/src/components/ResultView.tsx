"use client";

import { useMemo, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { type ChartConfig, type ChartType, MAX_PIE_SLICES, chartData, defaultChart, numericColumns } from "@/lib/chartModel";
import type { QueryResult } from "@/lib/types";

const COLORS = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];
const EXPORT_FORMATS = ["csv", "json"] as const;

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
          <>
            <button className={view === "table" ? "" : "secondary"} onClick={() => setView("table")}>Table</button>
            <button className={view === "chart" ? "" : "secondary"} onClick={() => setView("chart")}>Chart</button>
          </>
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
          <ResponsiveContainer width="100%" height={280}>
            {config.type === "pie" ? (
              <PieChart>
                <Pie data={data} dataKey="value" nameKey="label" outerRadius={100} label>
                  {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            ) : config.type === "line" ? (
              <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="value" name={result.columns[config.y]} stroke={COLORS[0]} />
              </LineChart>
            ) : (
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" name={result.columns[config.y]} fill={COLORS[0]} />
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
