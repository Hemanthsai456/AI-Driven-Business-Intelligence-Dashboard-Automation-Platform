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
import { BarChart3, LineChart as LineIcon, Table as TableIcon, Hash } from 'lucide-react';

interface InsightChartProps {
  visualization: string; // 'bar' | 'line' | 'table' | 'kpi' | 'scatter'
  metric: string;
  dimensions: string[];
  executionData?: any;
  className?: string;
}

const CHART_SERIES_VARS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

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

  // 1. KPI Visualization
  if (vizType === 'kpi') {
    const primaryValue = rawRows[0]?.[metricKey] ?? rawRows[0]?.[columns[0]] ?? '—';
    const formatted = typeof primaryValue === 'number'
      ? primaryValue.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(primaryValue);

    return (
      <div className={`p-6 bg-surface border border-border rounded-card flex flex-col items-center justify-center text-center shadow-xs min-h-[220px] ${className}`}>
        <div className="p-2 rounded-full bg-primary-soft text-primary mb-3">
          <Hash className="w-5 h-5" />
        </div>
        <div className="text-3xl sm:text-4xl font-extrabold font-mono text-foreground tracking-tight">
          {formatted}
        </div>
        <div className="text-xs text-muted-foreground mt-2 font-mono">
          {metric} {dimKey ? `(${dimKey})` : ''}
        </div>
      </div>
    );
  }

  // 2. Line Chart Visualization
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
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey={dimKey}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                angle={-20}
                textAnchor="end"
              />
              <YAxis
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                tickFormatter={(v) => typeof v === 'number' ? v.toLocaleString() : v}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--surface)',
                  borderColor: 'var(--border)',
                  borderRadius: '10px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                  fontSize: '12px',
                  color: 'var(--text)',
                }}
              />
              <Line
                type="monotone"
                dataKey={metricKey}
                stroke="var(--chart-1)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: 'var(--chart-1)' }}
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
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey={dimKey}
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              stroke="var(--border)"
              tickLine={false}
              angle={-20}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              stroke="var(--border)"
              tickLine={false}
              tickFormatter={(v) => typeof v === 'number' ? v.toLocaleString() : v}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--surface)',
                borderColor: 'var(--border)',
                borderRadius: '10px',
                boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
                fontSize: '12px',
                color: 'var(--text)',
              }}
            />
            <Bar dataKey={metricKey} radius={[4, 4, 0, 0]}>
              {rawRows.map((_, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={CHART_SERIES_VARS[index % CHART_SERIES_VARS.length]}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
