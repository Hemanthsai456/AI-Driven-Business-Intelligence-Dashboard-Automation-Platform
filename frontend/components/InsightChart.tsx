'use client';

import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  PieChart,
  Pie,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts';
import {
  BarChart3,
  LineChart as LineIcon,
  PieChart as PieIcon,
  Table as TableIcon,
  Hash,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';

export interface InsightChartProps {
  visualization: string; // 'bar' | 'horizontal_bar' | 'line' | 'area' | 'donut' | 'stacked_bar' | 'scatter' | 'histogram' | 'table' | 'kpi'
  metric?: string;
  dimensions?: string[];
  executionData?: any;
  className?: string;
  isLoading?: boolean;
  isInsufficientData?: boolean;
  errorMessage?: string;
  delta?: {
    value?: number | string;
    percentage?: number;
    direction?: 'up' | 'down' | 'neutral';
    label?: string;
  };
  onItemClick?: (dimension: string, value: any) => void;
  selectedFilterValue?: any;
}

const CHART_SERIES_VARS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

/**
 * Bulletproof resolver for dimension and metric keys.
 * Ensures data marks (rect/path) are always drawn by matching columns case-insensitively
 * and guaranteeing numeric values for metric series.
 */
export function resolveChartKeys(
  rows: Record<string, any>[],
  preferredDims: string[] = [],
  preferredMetrics: string[] = []
): { dimKey: string; metricKey: string } {
  if (!rows || rows.length === 0) {
    return { dimKey: 'dimension', metricKey: 'value' };
  }
  const sample = rows[0] || {};
  const keys = Object.keys(sample);
  if (keys.length === 0) {
    return { dimKey: 'dimension', metricKey: 'value' };
  }

  // Find candidate numeric columns (can be parsed to a finite number)
  const numericKeys = keys.filter((k) =>
    rows.some((r) => {
      const v = r[k];
      if (typeof v === 'number') return true;
      if (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v))) return true;
      return false;
    })
  );

  // Non-numeric candidate columns
  const nonNumericKeys = keys.filter((k) => !numericKeys.includes(k));

  // 1. Resolve dimKey
  let dimKey = '';
  for (const pd of preferredDims) {
    if (!pd) continue;
    const cleanPd = pd.replace(/^[a-z_]+\((.+)\)$/i, '$1');
    const found = keys.find(
      (k) =>
        k.toLowerCase() === pd.toLowerCase() ||
        k.toLowerCase() === cleanPd.toLowerCase() ||
        k.toLowerCase().endsWith(`_${cleanPd.toLowerCase()}`)
    );
    if (found) {
      dimKey = found;
      break;
    }
  }
  if (!dimKey && nonNumericKeys.length > 0) {
    dimKey = nonNumericKeys[0];
  }
  if (!dimKey) {
    dimKey = keys[0];
  }

  // 2. Resolve metricKey
  let metricKey = '';
  for (const pm of preferredMetrics) {
    if (!pm) continue;
    const cleanPm = pm.replace(/^[a-z_]+\((.+)\)$/i, '$1');
    const found = numericKeys.find(
      (k) =>
        k.toLowerCase() === pm.toLowerCase() ||
        k.toLowerCase() === cleanPm.toLowerCase() ||
        k.toLowerCase().endsWith(`_${cleanPm.toLowerCase()}`)
    );
    if (found && found !== dimKey) {
      metricKey = found;
      break;
    }
  }
  if (!metricKey) {
    metricKey = numericKeys.find((k) => k !== dimKey) || '';
  }
  if (!metricKey) {
    metricKey = keys.find((k) => k !== dimKey) || keys[1] || keys[0];
  }

  return { dimKey, metricKey };
}

export const InsightChart: React.FC<InsightChartProps> = ({
  visualization = 'bar',
  metric = '',
  dimensions = [],
  executionData,
  className = '',
  isLoading = false,
  isInsufficientData = false,
  errorMessage,
  delta,
  onItemClick,
  selectedFilterValue,
}) => {
  // Extract and normalize raw rows
  const rawRows: any[] = React.useMemo(() => {
    if (!executionData) return [];
    if (Array.isArray(executionData.data)) return executionData.data;
    if (Array.isArray(executionData.rows)) return executionData.rows;
    if (Array.isArray(executionData)) return executionData;
    return [];
  }, [executionData]);

  // Resolve valid keys
  const { dimKey, metricKey } = React.useMemo(() => {
    return resolveChartKeys(rawRows, dimensions, metric ? [metric] : []);
  }, [rawRows, dimensions, metric]);

  // Ensure numeric values are real JS numbers for Recharts SVG marks
  const normalizedRows = React.useMemo(() => {
    return rawRows.map((r) => {
      const copy = { ...r };
      for (const k of Object.keys(copy)) {
        const val = copy[k];
        if (typeof val === 'string' && val.trim() !== '' && !isNaN(Number(val))) {
          copy[k] = Number(val);
        }
      }
      if ((!dimensions || dimensions.length === 0 || !dimensions[0]) && Object.keys(r).length === 1 && !copy.dimension) {
        copy.dimension = 'Total';
      }
      return copy;
    });
  }, [rawRows, dimensions]);

  // Detect long labels -> force horizontal layout for readability (unconditionally declared hook)
  const maxLabelLen = React.useMemo(() => {
    if (!normalizedRows || normalizedRows.length === 0) return 0;
    return Math.max(...normalizedRows.map((r) => String(r[dimKey] ?? '').length), 0);
  }, [normalizedRows, dimKey]);

  let vizType = (visualization || 'bar').toLowerCase();

  // Filter usable scatter points where both X and Y are finite numbers
  const usableScatterData = React.useMemo(() => {
    if (vizType !== 'scatter') return [];
    return normalizedRows.filter((r) => {
      const x = r[dimKey];
      const y = r[metricKey];
      return (
        typeof x === 'number' &&
        !isNaN(x) &&
        isFinite(x) &&
        typeof y === 'number' &&
        !isNaN(y) &&
        isFinite(y)
      );
    });
  }, [vizType, normalizedRows, dimKey, metricKey]);

  // Verify plottable data usability
  const hasUsableData = React.useMemo(() => {
    if (!normalizedRows || normalizedRows.length === 0) return false;
    if (vizType === 'kpi' || vizType === 'table') return true;
    if (vizType === 'scatter') return usableScatterData.length > 0;
    return normalizedRows.some((r) => {
      const y = r[metricKey];
      return typeof y === 'number' && !isNaN(y) && isFinite(y);
    });
  }, [vizType, normalizedRows, metricKey, usableScatterData]);

  // Loading State
  if (isLoading) {
    return (
      <div className={`w-full flex flex-col items-center justify-center p-8 bg-surface border border-border rounded-card min-h-[260px] animate-pulse ${className}`}>
        <div className="w-8 h-8 rounded-full border-2 border-primary border-t-transparent animate-spin mb-3" />
        <span className="text-xs text-muted-foreground font-mono">Querying analytical engine...</span>
      </div>
    );
  }

  // Error State
  if (errorMessage) {
    return (
      <div className={`w-full flex flex-col items-center justify-center p-6 bg-error-soft/30 border border-error/30 rounded-card min-h-[220px] text-center ${className}`}>
        <AlertCircle className="w-6 h-6 text-error mb-2" />
        <span className="text-xs font-semibold text-error">Unable to render chart</span>
        <span className="text-2xs text-muted-foreground mt-1 max-w-sm">{errorMessage}</span>
      </div>
    );
  }

  // Insufficient Data State (Filter resulted in fewer than required rows)
  if (isInsufficientData || executionData?.status === 'INSUFFICIENT_DATA') {
    return (
      <div className={`w-full flex flex-col items-center justify-center p-6 bg-attention-soft/30 border border-attention/30 rounded-card min-h-[220px] text-center ${className}`}>
        <AlertCircle className="w-6 h-6 text-attention mb-2" />
        <span className="text-xs font-semibold text-foreground">Insufficient data after filtering</span>
        <span className="text-2xs text-muted-foreground mt-1 max-w-xs">
          Filter selections reduced the data points below statistical confidence. Adjust or reset slicers.
        </span>
      </div>
    );
  }

  // Empty State / No Usable Data State
  if (!normalizedRows || normalizedRows.length === 0 || !hasUsableData) {
    return (
      <div className={`w-full flex flex-col items-center justify-center p-8 bg-surface-muted/30 border border-dashed border-border rounded-card text-muted-foreground min-h-[240px] text-center ${className}`}>
        <TableIcon className="w-7 h-7 mb-2 stroke-1 text-muted-foreground/60" />
        <p className="text-xs font-medium text-foreground">No plottable data points</p>
        <p className="text-2xs text-muted-foreground mt-0.5 max-w-sm">
          {vizType === 'scatter'
            ? 'This scatter plot requires numeric values for both axes, but no valid data points were found.'
            : 'The query executed with zero plottable records matching criteria.'}
        </p>
      </div>
    );
  }



  // Tooltip custom style
  const tooltipStyle = {
    backgroundColor: 'var(--surface)',
    borderColor: 'var(--border)',
    borderRadius: '8px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
    fontSize: '12px',
    color: 'var(--text)',
  };

  // 1. KPI Visual
  if (vizType === 'kpi') {
    const rawVal = normalizedRows[0]?.[metricKey] ?? normalizedRows[0]?.[Object.keys(normalizedRows[0])[0]] ?? 0;
    const formatted = typeof rawVal === 'number'
      ? rawVal.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(rawVal);

    return (
      <div className={`w-full p-6 bg-surface border border-border rounded-card flex flex-col items-center justify-center text-center shadow-xs min-h-[220px] ${className}`}>
        <div className="p-2 rounded-full bg-primary-soft text-primary mb-3">
          <Hash className="w-5 h-5" />
        </div>
        <div className="text-3xl sm:text-4xl font-extrabold font-mono text-foreground tracking-tight">
          {formatted}
        </div>
        <div className="text-xs text-muted-foreground mt-2 font-mono">
          {metric || 'Metric'} {dimKey && dimKey !== 'dimension' ? `(${dimKey})` : ''}
        </div>
        {delta && (
          <div className="flex items-center gap-1.5 mt-3 text-2xs font-mono">
            {delta.direction === 'up' && <TrendingUp className="w-3.5 h-3.5 text-success" />}
            {delta.direction === 'down' && <TrendingDown className="w-3.5 h-3.5 text-error" />}
            {delta.direction === 'neutral' && <Minus className="w-3.5 h-3.5 text-muted-foreground" />}
            <span className={delta.direction === 'up' ? 'text-success font-semibold' : delta.direction === 'down' ? 'text-error font-semibold' : 'text-muted-foreground'}>
              {delta.percentage !== undefined ? `${delta.percentage > 0 ? '+' : ''}${delta.percentage.toFixed(1)}%` : delta.value}
            </span>
            {delta.label && <span className="text-muted-foreground">{delta.label}</span>}
          </div>
        )}
      </div>
    );
  }

  // 2. Line Chart
  if (vizType === 'line') {
    return (
      <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
        <div className="flex-1 w-full h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={normalizedRows} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey={dimKey}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                angle={maxLabelLen > 6 ? -20 : 0}
                textAnchor={maxLabelLen > 6 ? 'end' : 'middle'}
              />
              <YAxis
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Line
                type="monotone"
                dataKey={metricKey}
                stroke="var(--chart-1)"
                strokeWidth={2.5}
                dot={{ r: 3, fill: 'var(--chart-1)' }}
                activeDot={{ r: 6 }}
                onClick={(entry: any) => {
                  if (onItemClick && entry) {
                    onItemClick(dimKey, entry.payload?.[dimKey]);
                  }
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 3. Area Chart
  if (vizType === 'area') {
    return (
      <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
        <div className="flex-1 w-full h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={normalizedRows} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey={dimKey}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                angle={maxLabelLen > 6 ? -20 : 0}
                textAnchor={maxLabelLen > 6 ? 'end' : 'middle'}
              />
              <YAxis
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Area
                type="monotone"
                dataKey={metricKey}
                stroke="var(--chart-1)"
                fill="var(--primary-soft)"
                fillOpacity={0.6}
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 4. Donut Chart (Composition)
  if (vizType === 'donut' || vizType === 'pie') {
    return (
      <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
        <div className="flex-1 w-full h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: '11px', color: 'var(--text)' }} />
              <Pie
                data={normalizedRows}
                dataKey={metricKey}
                nameKey={dimKey}
                innerRadius={50}
                outerRadius={75}
                paddingAngle={3}
                onClick={(entry: any) => {
                  if (onItemClick && entry) {
                    onItemClick(dimKey, entry[dimKey] || entry.name);
                  }
                }}
              >
                {normalizedRows.map((entry, index) => {
                  const isSelected = selectedFilterValue !== undefined && String(entry[dimKey]) === String(selectedFilterValue);
                  return (
                    <Cell
                      key={`donut-cell-${index}`}
                      fill={CHART_SERIES_VARS[index % CHART_SERIES_VARS.length]}
                      stroke={isSelected ? 'var(--primary)' : 'var(--surface)'}
                      strokeWidth={isSelected ? 3 : 1}
                      cursor="pointer"
                    />
                  );
                })}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 5. Horizontal Bar Chart (for category ranking / long labels)
  if (vizType === 'horizontal_bar') {
    const yAxisWidth = Math.min(Math.max(maxLabelLen * 7, 75), 150);
    return (
      <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
        <div className="flex-1 w-full h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={normalizedRows}
              layout="vertical"
              margin={{ top: 10, right: 30, left: Math.max(yAxisWidth - 55, 15), bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
              />
              <YAxis
                type="category"
                dataKey={dimKey}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickLine={false}
                width={yAxisWidth}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey={metricKey} radius={[0, 4, 4, 0]}>
                {normalizedRows.map((entry, index) => {
                  const isSelected = selectedFilterValue !== undefined && String(entry[dimKey]) === String(selectedFilterValue);
                  return (
                    <Cell
                      key={`hbar-cell-${index}`}
                      fill={CHART_SERIES_VARS[index % CHART_SERIES_VARS.length]}
                      stroke={isSelected ? 'var(--primary)' : 'none'}
                      strokeWidth={isSelected ? 2 : 0}
                      cursor="pointer"
                      onClick={() => onItemClick && onItemClick(dimKey, entry[dimKey])}
                    />
                  );
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 6. Scatter Chart (Correlation)
  if (vizType === 'scatter') {
    return (
      <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
        <div className="flex-1 w-full h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey={dimKey}
                name={dimKey}
                type="number"
                domain={['auto', 'auto']}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickFormatter={(v) => (typeof v === 'number' ? Number(v.toFixed(2)).toString() : v)}
              />
              <YAxis
                dataKey={metricKey}
                name={metricKey}
                type="number"
                domain={['auto', 'auto']}
                tick={{ fontSize: 11, fill: 'var(--muted)' }}
                stroke="var(--border)"
                tickFormatter={(v) => (typeof v === 'number' ? Number(v.toFixed(2)).toString() : v)}
              />
              <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter
                name={metricKey}
                data={usableScatterData}
                fill="var(--chart-1)"
                onClick={(entry: any) => {
                  if (onItemClick && entry) {
                    onItemClick(dimKey, entry.payload?.[dimKey]);
                  }
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // 7. Table Visualization
  if (vizType === 'table') {
    const cols = Object.keys(normalizedRows[0] || {});
    return (
      <div className={`w-full bg-surface border border-border rounded-card overflow-hidden ${className}`}>
        <div className="overflow-x-auto max-h-[280px]">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border bg-surface-muted/50 text-muted-foreground font-mono uppercase text-2xs sticky top-0 bg-surface">
                {cols.map((c) => (
                  <th key={c} className="py-2 px-3 font-semibold">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {normalizedRows.slice(0, 50).map((row, idx) => (
                <tr key={idx} className="hover:bg-primary-soft/30 transition-colors">
                  {cols.map((c) => {
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

  // 8. Default: Vertical Bar Chart / Histogram
  return (
    <div className={`w-full p-4 bg-surface border border-border rounded-card min-h-[280px] flex flex-col ${className}`}>
      <div className="flex-1 w-full h-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={normalizedRows} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey={dimKey}
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              stroke="var(--border)"
              tickLine={false}
              angle={maxLabelLen > 5 ? -25 : 0}
              textAnchor={maxLabelLen > 5 ? 'end' : 'middle'}
            />
            <YAxis
              tick={{ fontSize: 11, fill: 'var(--muted)' }}
              stroke="var(--border)"
              tickLine={false}
              tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
            />
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey={metricKey} radius={[4, 4, 0, 0]}>
              {normalizedRows.map((entry, index) => {
                const isSelected = selectedFilterValue !== undefined && String(entry[dimKey]) === String(selectedFilterValue);
                return (
                  <Cell
                    key={`bar-cell-${index}`}
                    fill={CHART_SERIES_VARS[index % CHART_SERIES_VARS.length]}
                    stroke={isSelected ? 'var(--primary)' : 'none'}
                    strokeWidth={isSelected ? 2 : 0}
                    cursor="pointer"
                    onClick={() => onItemClick && onItemClick(dimKey, entry[dimKey])}
                  />
                );
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
