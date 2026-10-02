'use client';

import React, { useState } from 'react';
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
import {
  Sparkles,
  BarChart3,
  LineChart as LineIcon,
  Hash,
  ShieldCheck,
  Layers,
  ArrowRight,
  Info,
  Calendar,
  Filter,
  Table as TableIcon,
  Code,
  Brush,
} from 'lucide-react';
import { DashboardPanelUI } from '../lib/types';

export interface DashboardPanelsViewProps {
  spec?: any;
  headline?: string | null;
  panels?: DashboardPanelUI[];
  previewData?: any;
  cleaningReport?: any;
  onSelectCandidate?: (planId: string) => void;
  className?: string;
}

export const DashboardPanelsView: React.FC<DashboardPanelsViewProps> = ({
  spec,
  headline,
  panels: rawPanels,
  previewData,
  cleaningReport,
  onSelectCandidate,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'data' | 'cleaning' | 'trace'>('overview');

  const panels: DashboardPanelUI[] = rawPanels || spec?.panels || [];
  const activeHeadline = headline || spec?.headline;

  if (!panels || panels.length === 0) {
    return null;
  }

  // Find specialized panels
  const insightPanel = panels.find((p) => p.panel_type === 'INSIGHT');
  const mainChartPanel = panels.find((p) => ['BAR', 'LINE', 'KPI'].includes(p.panel_type));
  const robustnessPanel = panels.find((p) => p.panel_type === 'HEATMAP');
  const alternatesPanel = panels.find((p) => p.panel_type === 'ALTERNATES');

  const headlineText = activeHeadline || (insightPanel ? insightPanel.description : null);

  return (
    <div className={`flex flex-col gap-5 ${className}`}>
      {/* Tab Navigation (Demoted Data, Cleaning, and Trace Tabs) */}
      <div className="flex items-center gap-2 border-b border-border text-xs font-medium">
        <button
          onClick={() => setActiveTab('overview')}
          className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${
            activeTab === 'overview'
              ? 'border-primary text-primary font-bold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5" />
          <span>Overview</span>
        </button>

        <button
          onClick={() => setActiveTab('data')}
          className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${
            activeTab === 'data'
              ? 'border-primary text-primary font-bold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <TableIcon className="w-3.5 h-3.5" />
          <span>Data (Raw Preview)</span>
        </button>

        {cleaningReport && (
          <button
            onClick={() => setActiveTab('cleaning')}
            className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${
              activeTab === 'cleaning'
                ? 'border-primary text-primary font-bold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Brush className="w-3.5 h-3.5" />
            <span>Cleaning Report</span>
          </button>
        )}

        {spec?.winner?.execution?.compiled_sql && (
          <button
            onClick={() => setActiveTab('trace')}
            className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${
              activeTab === 'trace'
                ? 'border-primary text-primary font-bold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Code className="w-3.5 h-3.5" />
            <span>Trace & SQL</span>
          </button>
        )}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          {/* 1. Headline Insight Sentence */}
          {headlineText && (
            <div className="bg-primary-soft border border-primary/40 rounded-card p-4 sm:p-5 flex items-start gap-3.5 shadow-xs">
              <div className="p-2 rounded-lg bg-primary text-primary-foreground shrink-0 mt-0.5">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-primary text-2xs font-mono font-bold uppercase tracking-wider">
                    Key Analytical Finding
                  </span>
                </div>
                <p className="text-sm sm:text-base font-semibold text-foreground leading-snug">
                  {headlineText}
                </p>
              </div>
            </div>
          )}

          {/* 2. Winner's Main Chart (KPI, BAR, or LINE) */}
          {mainChartPanel && (
            <div className="bg-surface border border-border rounded-card p-5 flex flex-col shadow-xs">
              {/* Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-4 border-b border-border">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-md bg-primary-soft text-primary">
                    {mainChartPanel.panel_type === 'LINE' ? (
                      <LineIcon className="w-4 h-4" />
                    ) : mainChartPanel.panel_type === 'BAR' ? (
                      <BarChart3 className="w-4 h-4" />
                    ) : (
                      <Hash className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <h3 className="text-sm sm:text-base font-bold text-foreground">
                      {mainChartPanel.title}
                    </h3>
                    <p className="text-2xs text-muted-foreground mt-0.5">
                      {mainChartPanel.description}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-2xs font-mono uppercase px-2 py-0.5 rounded bg-surface-muted border border-border text-foreground font-semibold">
                    {mainChartPanel.panel_type}
                  </span>
                  {mainChartPanel.metadata?.is_compressed && (
                    <span className="text-2xs font-mono px-2 py-0.5 rounded bg-attention-soft text-attention border border-attention/30 font-medium">
                      Top 10 + Other
                    </span>
                  )}
                </div>
              </div>

              {/* Chart Body: KPI */}
              {mainChartPanel.panel_type === 'KPI' && (
                <div className="py-8 flex flex-col items-center justify-center text-center">
                  <span className="text-3xl sm:text-4xl font-extrabold font-mono tracking-tight text-foreground">
                    {typeof mainChartPanel.data?.[0]?.value === 'number'
                      ? mainChartPanel.data[0].value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : mainChartPanel.data?.[0]?.value ?? '—'}
                  </span>
                  <span className="text-xs text-muted-foreground mt-2 font-mono">
                    {mainChartPanel.metadata?.metric_column || 'Single Aggregate Metric'}
                  </span>
                </div>
              )}

              {/* Chart Body: LINE */}
              {mainChartPanel.panel_type === 'LINE' && (
                <div className="h-72 w-full pt-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={mainChartPanel.data} margin={{ top: 10, right: 20, left: 10, bottom: 25 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" opacity={0.7} />
                      <XAxis
                        dataKey={mainChartPanel.x_key || 'date'}
                        tick={{ fontSize: 11, fill: 'var(--muted)', fontFamily: 'monospace' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--border)' }}
                        dy={8}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: 'var(--muted)', fontFamily: 'monospace' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
                        dx={-4}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'var(--surface)',
                          borderColor: 'var(--border)',
                          borderRadius: '10px',
                          fontSize: '12px',
                          color: 'var(--text)',
                        }}
                        formatter={(val: any) => [typeof val === 'number' ? val.toLocaleString() : val, mainChartPanel.y_keys?.[0] || 'Value']}
                      />
                      <Line
                        type="monotone"
                        dataKey={mainChartPanel.y_keys?.[0] || 'value'}
                        stroke="var(--chart-1)"
                        strokeWidth={2.5}
                        dot={{ r: 3, fill: 'var(--chart-1)', strokeWidth: 0 }}
                        activeDot={{ r: 5, fill: 'var(--chart-1)' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Chart Body: BAR */}
              {mainChartPanel.panel_type === 'BAR' && (
                <div className="h-72 w-full pt-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={mainChartPanel.data} margin={{ top: 10, right: 20, left: 10, bottom: 35 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" opacity={0.7} />
                      <XAxis
                        dataKey={mainChartPanel.x_key || 'group'}
                        tick={{ fontSize: 11, fill: 'var(--muted)', fontFamily: 'sans-serif' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--border)' }}
                        interval={0}
                        angle={-20}
                        textAnchor="end"
                        dy={8}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: 'var(--muted)', fontFamily: 'monospace' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => (typeof v === 'number' ? v.toLocaleString() : v)}
                        dx={-4}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'var(--surface)',
                          borderColor: 'var(--border)',
                          borderRadius: '10px',
                          fontSize: '12px',
                          color: 'var(--text)',
                        }}
                        formatter={(val: any, name: any, item: any) => [
                          typeof val === 'number' ? val.toLocaleString() : val,
                          item?.payload?._is_other ? 'Other (Grouped)' : mainChartPanel.y_keys?.[0] || 'Value',
                        ]}
                      />
                      <Bar
                        dataKey={mainChartPanel.y_keys?.[0] || 'value'}
                        radius={[4, 4, 0, 0]}
                      >
                        {mainChartPanel.data.map((entry: any, idx: number) => {
                          const fillColor = entry._is_other ? 'var(--chart-5)' : 'var(--chart-1)';
                          return <Cell key={`cell-${idx}`} fill={fillColor} />;
                        })}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {/* 3. Robustness Panel (Heatmap Data: Group x Interpretation) */}
          {robustnessPanel && (
            <div className="bg-surface border border-border rounded-card p-5 flex flex-col shadow-xs">
              {/* Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-md bg-primary-soft text-primary">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      {robustnessPanel.title}
                    </h3>
                    <p className="text-2xs text-muted-foreground mt-0.5">
                      {robustnessPanel.description}
                    </p>
                  </div>
                </div>

                {robustnessPanel.metadata?.stability_score !== undefined && (
                  <div className="flex items-center gap-2">
                    <span className="text-2xs font-mono text-muted-foreground uppercase">
                      Stability Score:
                    </span>
                    <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-primary-soft text-primary border border-primary/20">
                      {(robustnessPanel.metadata.stability_score * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
              </div>

              {/* Heatmap Matrix Table */}
              {robustnessPanel.data && robustnessPanel.data.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-border bg-surface-muted/50 text-2xs uppercase text-muted-foreground font-mono">
                        <th className="py-2.5 px-3 font-semibold">Group / Category</th>
                        {(robustnessPanel.y_keys || []).map((colKey) => (
                          <th
                            key={colKey}
                            className="py-2.5 px-3 font-semibold text-center whitespace-nowrap"
                            title={colKey}
                          >
                            {colKey === 'Winner (Base)' ? (
                              <span className="text-primary font-bold">★ Winner (Base)</span>
                            ) : (
                              colKey
                            )}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {robustnessPanel.data.map((row: any, rIdx: number) => (
                        <tr key={rIdx} className="hover:bg-surface-muted/30 transition-colors">
                          <td className="py-2 px-3 font-medium text-foreground whitespace-nowrap font-mono text-2xs">
                            {row.group}
                          </td>
                          {(robustnessPanel.y_keys || []).map((colKey) => {
                            const rankVal = row[colKey];
                            let rankClass = 'text-muted-foreground';

                            if (rankVal === 1) {
                              rankClass = 'bg-success-soft text-success border border-success/30';
                            } else if (rankVal === 2) {
                              rankClass = 'bg-primary-soft text-primary border border-primary/30';
                            } else if (typeof rankVal === 'number' && rankVal > 2) {
                              rankClass = 'bg-attention-soft text-attention border border-attention/30';
                            }

                            return (
                              <td key={colKey} className="py-2 px-3 text-center">
                                <span className={`inline-block min-w-[26px] py-0.5 px-1.5 rounded font-mono font-bold text-2xs ${rankClass}`}>
                                  {rankVal !== undefined && rankVal !== null ? rankVal : '—'}
                                </span>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-6 px-4 text-center text-xs text-muted-foreground bg-surface-muted/30 rounded-card border border-dashed border-border mt-2">
                  <p>No dimension ranking perturbations required for this specification.</p>
                </div>
              )}
            </div>
          )}

          {/* 4. Alternate Interpretations Panel */}
          {alternatesPanel && alternatesPanel.data && alternatesPanel.data.length > 0 && (
            <div className="bg-surface border border-border rounded-card p-5 flex flex-col shadow-xs">
              {/* Header */}
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 rounded-md bg-primary-soft text-primary">
                    <Layers className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground">
                      {alternatesPanel.title}
                    </h3>
                    <p className="text-2xs text-muted-foreground mt-0.5">
                      {alternatesPanel.description}
                    </p>
                  </div>
                </div>
                <span className="text-2xs font-mono text-muted-foreground">
                  {alternatesPanel.data.length} alternatives
                </span>
              </div>

              {/* List of Alternates */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                {alternatesPanel.data.map((alt: any) => (
                  <div
                    key={alt.plan_id}
                    className="bg-surface-muted/30 border border-border rounded-card p-3 flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-2xs font-mono font-semibold text-muted-foreground uppercase">
                          {alt.visualization || 'ALT'}
                        </span>
                        <span className="text-2xs font-mono font-bold px-1.5 py-0.5 rounded bg-surface border border-border text-foreground">
                          Score: {typeof alt.score === 'number' ? alt.score.toFixed(3) : alt.score}
                        </span>
                      </div>
                      <h4 className="text-xs font-semibold text-foreground leading-snug">
                        {alt.interpretation}
                      </h4>
                      <div className="flex items-center gap-2 mt-2 text-2xs font-mono text-muted-foreground">
                        <span>Metric: {alt.aggregation}({alt.metric})</span>
                        <span>•</span>
                        <span>Dim: {alt.dimension}</span>
                      </div>
                    </div>
                    <div className="mt-2.5 pt-2 border-t border-border/60 text-2xs text-muted-foreground font-mono flex items-center justify-between">
                      <span className="truncate max-w-[200px]" title={alt.reason_not_winner}>
                        Reason: {alt.reason_not_winner}
                      </span>
                      {onSelectCandidate && (
                        <button
                          onClick={() => onSelectCandidate(alt.plan_id)}
                          className="text-primary hover:underline text-2xs font-semibold flex items-center gap-0.5 shrink-0"
                        >
                          View <ArrowRight className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: DEMOTED DATA TAB */}
      {activeTab === 'data' && (
        <div className="bg-surface border border-border rounded-card p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-foreground">Raw Data Preview</h3>
              <p className="text-2xs text-muted-foreground">Sample rows from the active ingested dataset</p>
            </div>
            {previewData?.rows && (
              <span className="text-2xs font-mono text-muted-foreground">
                Showing {previewData.rows.length} rows
              </span>
            )}
          </div>

          {previewData?.rows && previewData.rows.length > 0 ? (
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-left text-xs font-mono border-collapse">
                <thead>
                  <tr className="border-b border-border bg-surface-muted/50 text-2xs uppercase text-muted-foreground">
                    {previewData.columns.map((col: string) => (
                      <th key={col} className="py-2 px-3 font-semibold whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border text-foreground">
                  {previewData.rows.map((row: any, rIdx: number) => (
                    <tr key={rIdx} className="hover:bg-surface-muted/20">
                      {previewData.columns.map((col: string) => (
                        <td key={col} className="py-1.5 px-3 whitespace-nowrap text-muted-foreground">
                          {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-error italic">null</span>}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No preview data currently loaded.
            </div>
          )}
        </div>
      )}

      {/* TAB 3: CLEANING REPORT */}
      {activeTab === 'cleaning' && cleaningReport && (
        <div className="bg-surface border border-border rounded-card p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-foreground">Data Cleaning Report</h3>
              <p className="text-2xs text-muted-foreground">Deterministic normalization transformations applied to raw data</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-border bg-surface-muted/50 text-2xs uppercase text-muted-foreground">
                  <th className="py-2 px-3 font-semibold">Rule / Operation</th>
                  <th className="py-2 px-3 font-semibold">Column</th>
                  <th className="py-2 px-3 font-semibold text-right">Affected Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground">
                {cleaningReport.transformations && cleaningReport.transformations.length > 0 ? (
                  cleaningReport.transformations.map((t: any, idx: number) => (
                    <tr key={idx} className="hover:bg-surface-muted/20">
                      <td className="py-2 px-3">{t.rule_name || t.type || 'Normalization'}</td>
                      <td className="py-2 px-3 font-semibold">{t.column_name || t.column || 'All'}</td>
                      <td className="py-2 px-3 text-right text-muted-foreground font-mono">
                        {t.affected_count || t.count || 1}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-muted-foreground italic">
                      Zero anomalies detected. Original dataset was already clean.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="text-2xs text-muted-foreground italic font-mono pt-1">
            Original data is preserved unchanged in the ingestion stage.
          </p>
        </div>
      )}

      {/* TAB 4: TRACE & SQL */}
      {activeTab === 'trace' && spec?.winner?.execution?.compiled_sql && (
        <div className="bg-surface border border-border rounded-card p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-foreground">Compiled DuckDB SQL</h3>
              <p className="text-2xs text-muted-foreground">Auditable query executed in sandboxed worker</p>
            </div>
          </div>
          <pre className="p-3 bg-surface-muted/50 rounded-card border border-border font-mono text-xs text-foreground overflow-x-auto">
            <code>{spec.winner.execution.compiled_sql}</code>
          </pre>
        </div>
      )}
    </div>
  );
};
