'use client';

import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { THEME_TOKENS } from '../lib/theme';
import { BarChart3, LineChart as LineIcon, Table as TableIcon, Hash } from 'lucide-react';

interface InsightChartProps {
  visualization: string; // 'bar' | 'line' | 'table' | 'kpi' | 'scatter'
  metric: string;
  dimensions: string[];
  executionData?: any;
  className?: string;
}

export const InsightChart: React.FC<InsightChartProps> = ({
  visualization,
  metric,
  dimensions,
  executionData,
  className = '',
}) => {
  // Extract rows and columns dynamically from DuckDB execution results
  const rawRows: any[] = React.useMemo(() => {
    if (!executionData) return [];
    if (Array.isArray(executionData.data)) return executionData.data;
    if (Array.isArray(executionData.rows)) return executionData.rows;
    if (Array.isArray(executionData)) return executionData;
    return [];
  }, [executionData]);

  const columns: string[] = React.useMemo(() => {
    if (!rawRows || rawRows.length === 0) return [];
    return Object.keys(rawRows[0]);
  }, [rawRows]);

  // Dimension is typically the first non-numeric or grouping key
  const dimKey = dimensions[0] || columns[0] || 'dimension';
  // Metric key is typically the numeric aggregate column
  const metricKey = columns.find((c) => c !== dimKey) || columns[1] || 'value';

  if (!rawRows || rawRows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 bg-surface-muted/30 border border-dashed border-border rounded-card text-muted-foreground min-h-[260px]">
        <TableIcon className="w-8 h-8 mb-2 stroke-1 text-muted-foreground/60" />
        <p className="text-xs font-medium">No execution data returned for this specification.</p>
      </div>
    );
  }

  const vizType = (visualization || 'bar').toLowerCase();

  // 1. KPI Single-Value Card
  if (vizType === 'kpi' || rawRows.length === 1) {
    const primaryVal = rawRows[0][metricKey] ?? rawRows[0][columns[0]] ?? '—';
    const formattedVal = typeof primaryVal === 'number' ? primaryVal.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(primaryVal);
    const label = dimKey && rawRows[0][dimKey] ? `${rawRows[0][dimKey]} • ${metric}` : metric;

    return (
      <div className={`p-6 bg-surface border border-border rounded-card flex flex-col justify-center min-h-[220px] ${className}`}>
        <div className="flex items-center gap-2 text-2xs font-semibold text-muted-foreground uppercase font-mono tracking-wider mb-2">
          <Hash className="w-3.5 h-3.5 text-primary" />
          <span>Key Performance Metric</span>
        </div>
        <div className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground font-mono">
          {formattedVal}
        </div>
        <div className="text-xs text-muted-foreground mt-2 font-medium">
          {label}
        </div>
      </div>
    );
  }

  // 2. Line Chart
  if (vizType === 'line') {
    return (
      <div className={`p-4 bg-surface border border-border rounded-card min-h-[300px] flex flex-col ${className}`}>
        <div className="flex items-center justify-between pb-3 mb-2 border-b border-border">
          <div className="flex items-center gap-2">
            <LineIcon className="w-4 h-4 text-primary" />
            <span className="text-xs font-semibold text-foreground">{metric} by {dimKey}</span>
          </div>
          <span className="text-2xs font-mono text-muted-foreground">{rawRows.length} points</span>
        </div>
        <div className="flex-1 w-full h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rawRows} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={THEME_TOKENS.border} vertical={false} />
              <XAxis
                dataKey={dimKey}
                tick={{ fontSize: 11, fill: THEME_TOKENS.mutedText }}
                stroke={THEME_TOKENS.border}
                tickLine={false}
                angle={-20}
                textAnchor="end"
              />
              <YAxis
                tick={{ fontSize: 11, fill: THEME_TOKENS.mutedText }}
                stroke={THEME_TOKENS.border}
                tickLine={false}
                tickFormatter={(v) => typeof v === 'number' ? v.toLocaleString() : v}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: THEME_TOKENS.surface,
                  borderColor: THEME_TOKENS.border,
                  borderRadius: '8px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  fontSize: '12px',
                }}
              />
              <Line
                type="monotone"
                dataKey={metricKey}
                stroke={THEME_TOKENS.chartSeries[0]}
                strokeWidth={2.5}
                dot={{ r: 3, fill: THEME_TOKENS.chartSeries[0] }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 3. Table Visualization
  if (vizType === 'table') {
    return (
      <div className={`bg-surface border border-border rounded-card overflow-hidden ${className}`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-muted/30">
          <div className="flex items-center gap-2">
            <TableIcon className="w-4 h-4 text-primary" />
            <span className="text-xs font-semibold text-foreground">{metric} by {dimKey}</span>
          </div>
          <span className="text-2xs font-mono text-muted-foreground">{rawRows.length} rows</span>
        </div>
        <div className="overflow-x-auto max-h-[320px]">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-surface-muted/50 text-muted-foreground font-mono uppercase text-2xs">
                {columns.map((c) => (
                  <th key={c} className="py-2 px-3 font-semibold">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rawRows.slice(0, 50).map((row, idx) => (
                <tr key={idx} className="hover:bg-primary-soft/30 transition-colors">
                  {columns.map((c) => {
                    const val = row[c];
                    const isNum = typeof val === 'number';
                    return (
                      <td key={c} className={`py-2 px-3 ${isNum ? 'font-mono' : ''}`}>
                        {isNum ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(val ?? '—')}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 4. Default: Bar Chart
  return (
    <div className={`p-4 bg-surface border border-border rounded-card min-h-[300px] flex flex-col ${className}`}>
      <div className="flex items-center justify-between pb-3 mb-2 border-b border-border">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-primary" />
          <span className="text-xs font-semibold text-foreground">{metric} by {dimKey}</span>
        </div>
        <span className="text-2xs font-mono text-muted-foreground">{rawRows.length} groups</span>
      </div>
      <div className="flex-1 w-full h-[260px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rawRows} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={THEME_TOKENS.border} vertical={false} />
            <XAxis
              dataKey={dimKey}
              tick={{ fontSize: 11, fill: THEME_TOKENS.mutedText }}
              stroke={THEME_TOKENS.border}
              tickLine={false}
              angle={-20}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: THEME_TOKENS.mutedText }}
              stroke={THEME_TOKENS.border}
              tickLine={false}
              tickFormatter={(v) => typeof v === 'number' ? v.toLocaleString() : v}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: THEME_TOKENS.surface,
                borderColor: THEME_TOKENS.border,
                borderRadius: '8px',
                boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                fontSize: '12px',
              }}
            />
            <Bar dataKey={metricKey} radius={[4, 4, 0, 0]}>
              {rawRows.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={THEME_TOKENS.chartSeries[index % THEME_TOKENS.chartSeries.length]}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
