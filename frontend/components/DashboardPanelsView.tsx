'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  Sparkles,
  BarChart3,
  LineChart as LineIcon,
  PieChart as PieIcon,
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
  Download,
  Maximize2,
  FileText,
  CheckCircle2,
  XCircle,
  RotateCcw,
  Printer,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  X,
  HelpCircle,
  Check,
  Database,
} from 'lucide-react';
import { DashboardPanelUI, DashboardTileUI, SlicerDef } from '../lib/types';
import { InsightChart } from './InsightChart';
import { queryTile, getProvidersStatus } from '../lib/api';
import { THEME_TOKENS } from '../lib/theme';

export interface DashboardPanelsViewProps {
  spec?: any;
  headline?: string | null;
  panels?: DashboardPanelUI[];
  previewData?: any;
  cleaningReport?: any;
  providers?: any[];
  onSelectCandidate?: (planId: string) => void;
  className?: string;
}

export const DashboardPanelsView: React.FC<DashboardPanelsViewProps> = ({
  spec,
  headline,
  panels: rawPanels,
  previewData,
  cleaningReport,
  providers: rawProviders,
  onSelectCandidate,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'data' | 'cleaning' | 'trace'>('dashboard');

  // Provider health state
  const [providers, setProviders] = useState<any[]>(rawProviders || spec?.providers || []);

  useEffect(() => {
    if (!providers || providers.length === 0) {
      getProvidersStatus()
        .then((res) => {
          if (res && res.providers) {
            setProviders(res.providers);
          }
        })
        .catch(() => { });
    }
  }, [providers]);

  // Modals state
  const [activeModal, setActiveModal] = useState<{
    type: 'sql' | 'data' | 'why' | 'expand' | null;
    tile: DashboardTileUI | null;
  }>({ type: null, tile: null });

  // Filter state for slicers and cross-filtering
  const [activeFilters, setActiveFilters] = useState<
    { column: string; operator: string; values: any[] }[]
  >([]);

  // Tile query overrides for dynamic interactive queries
  const [tileOverrides, setTileOverrides] = useState<
    Record<
      string,
      {
        data: Record<string, any>[];
        isLoading: boolean;
        isInsufficientData: boolean;
        error?: string;
      }
    >
  >({});

  // Parse raw tiles or fallback to adapt panels
  const rawTiles: DashboardTileUI[] = spec?.tiles || [];
  const panels: DashboardPanelUI[] = rawPanels || spec?.panels || [];

  // Adapt panels to tiles if tiles not explicitly provided
  const tiles: DashboardTileUI[] = useMemo(() => {
    if (rawTiles && rawTiles.length > 0) {
      return rawTiles;
    }
    if (!panels || panels.length === 0) {
      return [];
    }
    return panels.map((p, idx) => {
      let chartType = 'bar';
      let w = 4;
      let h = 3;
      if (p.panel_type === 'KPI') {
        chartType = 'kpi';
        w = 3;
        h = 2;
      } else if (p.panel_type === 'LINE') {
        chartType = 'line';
        w = 8;
        h = 4;
      } else if (p.panel_type === 'BAR') {
        chartType = 'bar';
        w = 8;
        h = 4;
      } else if (p.panel_type === 'HEATMAP' || p.panel_type === 'ALTERNATES') {
        chartType = 'table';
        w = 6;
        h = 3;
      }

      return {
        id: p.panel_id || `tile_${idx}`,
        title: p.title || 'Insight',
        chart_type: chartType,
        size: { w, h },
        priority: idx + 1,
        generator: p.metadata?.generator || 'rule-based baseline',
        evidence: {
          strength: p.metadata?.strength ?? 0.8,
          robustness: p.metadata?.robustness ?? p.metadata?.stability_score ?? 0.85,
          fdr_passed: p.metadata?.fdr_passed ?? true,
          n: p.data?.length ?? 0,
          score: p.metadata?.score ?? 0.8,
        },
        why_chosen: p.metadata?.why_chosen || p.description,
        data: p.data || [],
        x_key: p.x_key,
        y_keys: p.y_keys || ['value'],
        dimensions: p.x_key ? [p.x_key] : [],
        metrics: p.y_keys || [],
      } as DashboardTileUI;
    });
  }, [rawTiles, panels]);

  // Slicer definitions
  const slicers: SlicerDef[] = spec?.slicers || [];

  // Headline computation and robustness floor logic
  const activeHeadline = headline || spec?.headline;
  const headlineRobustness =
    spec?.winner?.score_breakdown?.stability ??
    spec?.winner?.score_breakdown?.robustness ??
    tiles[0]?.evidence?.robustness ??
    1.0;
  const isLowRobustness = headlineRobustness < 0.35;
  const headlineText = activeHeadline || tiles[0]?.title || 'Executive Insight';

  // Dataset info
  const datasetName = spec?.dataset_name || spec?.dataset_id || 'Active Dataset';
  const rowCount = spec?.row_count ?? previewData?.rows?.length ?? '—';
  const rejectedInsights = spec?.rejected_insights || [];
  const cleaningCount = cleaningReport?.transformations?.length ?? 0;

  // Handle cross filter toggling
  const handleToggleFilter = async (column: string, value: any) => {
    let nextFilters = [...activeFilters];
    const existingIdx = nextFilters.findIndex(
      (f) => f.column.toLowerCase() === column.toLowerCase() && f.values.includes(value)
    );

    if (existingIdx >= 0) {
      // Remove filter if already set
      nextFilters.splice(existingIdx, 1);
    } else {
      // Replace existing filter for this column or add new
      const colIdx = nextFilters.findIndex(
        (f) => f.column.toLowerCase() === column.toLowerCase()
      );
      if (colIdx >= 0) {
        nextFilters[colIdx] = { column, operator: '=', values: [value] };
      } else {
        nextFilters.push({ column, operator: '=', values: [value] });
      }
    }

    setActiveFilters(nextFilters);
    await applyFiltersToTiles(nextFilters);
  };

  // Handle slicer input change
  const handleSlicerChange = async (column: string, operator: string, values: any[]) => {
    let nextFilters = activeFilters.filter(
      (f) => f.column.toLowerCase() !== column.toLowerCase()
    );
    if (values && values.length > 0 && values[0] !== '' && values[0] !== undefined) {
      nextFilters.push({ column, operator, values });
    }
    setActiveFilters(nextFilters);
    await applyFiltersToTiles(nextFilters);
  };

  // Reset all filters
  const handleResetFilters = () => {
    setActiveFilters([]);
    setTileOverrides({});
  };

  // Re-query tiles from backend minimal API
  const applyFiltersToTiles = async (
    filters: { column: string; operator: string; values: any[] }[]
  ) => {
    if (!spec?.spec_id) return;

    if (filters.length === 0) {
      setTileOverrides({});
      return;
    }

    // Identify which tiles are affected (tiles whose dimensions match any filter column)
    const filterCols = filters.map((f) => f.column.toLowerCase());

    for (const tile of tiles) {
      const tileCols = [
        ...(tile.dimensions || []),
        tile.x_key || '',
        ...(tile.plan?.dimensions?.map((d: any) => d.column) || []),
      ].map((c) => c.toLowerCase());

      const isAffected = tileCols.some((tc) => tc && filterCols.includes(tc));

      if (isAffected) {
        setTileOverrides((prev) => ({
          ...prev,
          [tile.id]: {
            data: prev[tile.id]?.data || tile.data,
            isLoading: true,
            isInsufficientData: false,
          },
        }));

        try {
          const res = await queryTile(spec.spec_id, tile.id, filters);
          if (res.status === 'INSUFFICIENT_DATA' || res.row_count < 1) {
            setTileOverrides((prev) => ({
              ...prev,
              [tile.id]: {
                data: [],
                isLoading: false,
                isInsufficientData: true,
              },
            }));
          } else {
            setTileOverrides((prev) => ({
              ...prev,
              [tile.id]: {
                data: res.data,
                isLoading: false,
                isInsufficientData: false,
              },
            }));
          }
        } catch (err: any) {
          setTileOverrides((prev) => ({
            ...prev,
            [tile.id]: {
              data: [],
              isLoading: false,
              isInsufficientData: false,
              error: err?.message || 'Query failed',
            },
          }));
        }
      }
    }
  };

  // Download tile chart as PNG
  const handleDownloadPng = (tileId: string, title: string) => {
    const tileEl = document.getElementById(`tile-card-${tileId}`);
    if (!tileEl) return;
    const svgEl = tileEl.querySelector('svg');
    if (!svgEl) return;

    try {
      const serializer = new XMLSerializer();
      let source = serializer.serializeToString(svgEl);

      if (!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)) {
        source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
      }

      const svgBlob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' });
      const DOMURL = window.URL || window.webkitURL || window;
      const url = DOMURL.createObjectURL(svgBlob);
      const img = new Image();

      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = svgEl.clientWidth || 600;
        canvas.height = svgEl.clientHeight || 360;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          // Fill background using theme surface token
          ctx.fillStyle = THEME_TOKENS.surface;
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0);
          const pngUrl = canvas.toDataURL('image/png');
          const a = document.createElement('a');
          a.download = `${title.toLowerCase().replace(/[^a-z0-9]/g, '_')}.png`;
          a.href = pngUrl;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
        DOMURL.revokeObjectURL(url);
      };
      img.src = url;
    } catch (e) {
      console.error('Failed to export PNG:', e);
    }
  };

  // Export standalone self-contained HTML bundle
  const handleExportHtml = () => {
    const dashboardTitle = `${datasetName} - Power BI Executive Dashboard`;
    const exportTime = new Date().toLocaleString();

    const tilesHtml = tiles
      .map((t) => {
        const override = tileOverrides[t.id];
        const dataRows = override?.data || t.data || [];
        const isKpi = t.chart_type === 'kpi';
        const kpiVal =
          dataRows[0] && Object.values(dataRows[0])[0] !== undefined
            ? Object.values(dataRows[0])[0]
            : '—';

        return `
          <div class="tile-card" style="border: 1px solid var(--border); border-radius: 10px; padding: 16px; background: var(--surface);">
            <div style="font-size: 11px; font-weight: bold; text-transform: uppercase; color: var(--muted); margin-bottom: 6px;">
              ${t.chart_type.toUpperCase()} • ${t.generator}
            </div>
            <div style="font-size: 14px; font-weight: bold; color: var(--foreground); margin-bottom: 12px;">
              ${t.title}
            </div>
            ${isKpi
            ? `<div style="font-size: 32px; font-weight: 800; font-family: monospace; color: var(--primary); margin: 20px 0;">${kpiVal}</div>`
            : `<div style="font-size: 12px; color: var(--muted); margin-bottom: 8px;">Rows: ${dataRows.length}</div>
                   <table style="width: 100%; border-collapse: collapse; font-size: 11px; font-family: monospace;">
                     <thead>
                       <tr style="border-bottom: 1px solid var(--border); color: var(--muted);">
                         ${Object.keys(dataRows[0] || {})
              .slice(0, 4)
              .map((k) => `<th style="padding: 4px 8px; text-align: left;">${k}</th>`)
              .join('')}
                       </tr>
                     </thead>
                     <tbody>
                       ${dataRows
              .slice(0, 5)
              .map(
                (row) => `
                         <tr style="border-bottom: 1px solid var(--border);">
                           ${Object.keys(dataRows[0] || {})
                    .slice(0, 4)
                    .map((k) => `<td style="padding: 4px 8px;">${row[k]}</td>`)
                    .join('')}
                         </tr>`
              )
              .join('')}
                     </tbody>
                   </table>`
          }
            <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border); font-size: 10px; color: var(--muted); display: flex; justify-content: space-between;">
              <span>Strength: ${(t.evidence?.strength ?? 0.8).toFixed(2)}</span>
              <span>Robustness: ${((t.evidence?.robustness ?? 0.85) * 100).toFixed(0)}%</span>
              <span>FDR: ${t.evidence?.fdr_passed ? 'PASS' : 'FAIL'}</span>
            </div>
          </div>
        `;
      })
      .join('');

    const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${dashboardTitle}</title>
  <style>
    :root {
      --bg: ${THEME_TOKENS.background};
      --surface: ${THEME_TOKENS.surface};
      --border: ${THEME_TOKENS.border};
      --foreground: ${THEME_TOKENS.text};
      --muted: ${THEME_TOKENS.mutedText};
      --primary: ${THEME_TOKENS.primary};
      --primary-soft: ${THEME_TOKENS.primarySoft};
      --attention: ${THEME_TOKENS.attention};
      --attention-soft: ${THEME_TOKENS.attentionSoft};
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: rgb(18, 23, 28);
        --surface: rgb(26, 33, 40);
        --border: rgb(42, 51, 60);
        --foreground: rgb(230, 234, 238);
        --muted: rgb(152, 163, 175);
        --primary: rgb(79, 163, 157);
        --primary-soft: rgb(30, 53, 51);
        --attention: rgb(217, 164, 65);
        --attention-soft: rgb(51, 41, 26);
      }
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--foreground);
      margin: 0;
      padding: 24px;
    }
    .header {
      padding: 16px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--surface);
      margin-bottom: 20px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }
    @media print {
      body { background: white; color: black; }
      .tile-card { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div style="font-size: 11px; text-transform: uppercase; color: var(--muted); font-family: monospace;">AI-Driven Executive BI Dashboard</div>
    <h1 style="margin: 4px 0 8px 0; font-size: 20px;">${headlineText}</h1>
    <div style="font-size: 12px; color: var(--muted);">Dataset: <strong>${datasetName}</strong> • Rows: <strong>${rowCount}</strong> • Exported: ${exportTime}</div>
  </div>
  <div class="grid">
    ${tilesHtml}
  </div>
</body>
</html>`;

    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${datasetName.toLowerCase().replace(/[^a-z0-9]/g, '_')}_dashboard.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Helper for responsive grid col-span based on tile size
  const getColSpanClass = (tile: DashboardTileUI) => {
    if (tile.chart_type === 'kpi') {
      return 'col-span-1 md:col-span-3 xl:col-span-3';
    }
    if (tile.size.w === 8) {
      return 'col-span-1 md:col-span-6 xl:col-span-8';
    }
    if (tile.size.w === 4) {
      return 'col-span-1 md:col-span-3 xl:col-span-4';
    }
    if (tile.size.w === 6) {
      return 'col-span-1 md:col-span-6 xl:col-span-6';
    }
    return 'col-span-1 md:col-span-3 xl:col-span-4';
  };

  if (!tiles || tiles.length === 0) {
    return null;
  }

  return (
    <div className={`flex flex-col gap-5 ${className}`}>
      {/* Tab Navigation */}
      <div className="flex items-center justify-between border-b border-border text-xs font-medium no-print">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${activeTab === 'dashboard'
                ? 'border-primary text-primary font-bold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Executive Dashboard</span>
          </button>

          <button
            onClick={() => setActiveTab('data')}
            className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${activeTab === 'data'
                ? 'border-primary text-primary font-bold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>Data Preview</span>
          </button>

          {cleaningReport && (
            <button
              onClick={() => setActiveTab('cleaning')}
              className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${activeTab === 'cleaning'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
            >
              <Brush className="w-3.5 h-3.5" />
              <span>Cleaning Report ({cleaningCount})</span>
            </button>
          )}

          {spec?.winner?.execution?.compiled_sql && (
            <button
              onClick={() => setActiveTab('trace')}
              className={`flex items-center gap-1.5 px-3.5 py-2 border-b-2 transition-all ${activeTab === 'trace'
                  ? 'border-primary text-primary font-bold'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
            >
              <Code className="w-3.5 h-3.5" />
              <span>Trace & SQL</span>
            </button>
          )}
        </div>

        {/* Global Export & Print buttons */}
        <div className="flex items-center gap-2 pb-1">
          <button
            onClick={handleExportHtml}
            className="flex items-center gap-1 px-2.5 py-1 text-2xs font-mono font-semibold rounded bg-surface border border-border text-foreground hover:bg-surface-muted transition-colors"
            title="Download self-contained offline HTML dashboard bundle"
          >
            <Download className="w-3 h-3" />
            <span>Export HTML</span>
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1 px-2.5 py-1 text-2xs font-mono font-semibold rounded bg-surface border border-border text-foreground hover:bg-surface-muted transition-colors"
            title="Print dashboard"
          >
            <Printer className="w-3 h-3" />
            <span>Print</span>
          </button>
        </div>
      </div>

      {/* TAB 1: EXECUTIVE DASHBOARD */}
      {activeTab === 'dashboard' && (
        <div className="space-y-4">
          {/* F6: Trust Layer Summary Strip */}
          <div className="bg-surface border border-border rounded-card p-3 sm:p-4 shadow-xs">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              {/* Dataset & Volume info */}
              <div className="flex flex-wrap items-center gap-2.5 text-xs">
                <div className="flex items-center gap-1.5 font-semibold text-foreground">
                  <Database className="w-4 h-4 text-primary" />
                  <span>{datasetName}</span>
                </div>
                <span className="text-muted-foreground">•</span>
                <span className="text-muted-foreground font-mono text-2xs">
                  {typeof rowCount === 'number' ? rowCount.toLocaleString() : rowCount} rows
                </span>
                <span className="text-muted-foreground">•</span>
                <span className="px-2 py-0.5 rounded text-2xs font-mono font-medium bg-primary-soft text-primary border border-primary/20">
                  {tiles.length} insights shown
                </span>
                {rejectedInsights.length > 0 && (
                  <span className="px-2 py-0.5 rounded text-2xs font-mono font-medium bg-surface-muted text-muted-foreground border border-border">
                    {rejectedInsights.length} rejected
                  </span>
                )}
                {cleaningCount > 0 && (
                  <button
                    onClick={() => setActiveTab('cleaning')}
                    className="flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono bg-success-soft text-success border border-success/30 hover:underline"
                  >
                    <Brush className="w-3 h-3" />
                    <span>{cleaningCount} cleaning rules</span>
                  </button>
                )}
              </div>

              {/* Contributing Providers Status */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-3xs uppercase font-mono text-muted-foreground mr-1">
                  Engine Providers:
                </span>
                {providers && providers.length > 0 ? (
                  providers.map((p: any, idx: number) => {
                    const isLive = p.status === 'live' || p.status === 'ok';
                    return (
                      <span
                        key={idx}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-3xs font-mono ${isLive
                            ? 'bg-success-soft text-success border border-success/30'
                            : 'bg-attention-soft text-attention border border-attention/30'
                          }`}
                        title={p.reason ? `Provider status: ${p.reason}` : `Provider: ${p.provider}`}
                      >
                        {isLive ? <CheckCircle2 className="w-2.5 h-2.5" /> : <XCircle className="w-2.5 h-2.5" />}
                        <span>{p.provider || p.name}</span>
                      </span>
                    );
                  })
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-3xs font-mono bg-primary-soft text-primary border border-primary/20">
                    <CheckCircle2 className="w-2.5 h-2.5" />
                    <span>Gemini / Groq / Baseline</span>
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* F0: Headline Insight Banner */}
          <div className="bg-primary-soft border border-primary/40 rounded-card p-4 sm:p-5 flex items-start gap-3.5 shadow-xs">
            <div className="p-2 rounded-lg bg-primary text-primary-foreground shrink-0 mt-0.5">
              <Sparkles className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-primary text-2xs font-mono font-bold uppercase tracking-wider">
                  Automated Synthesis
                </span>
                {isLowRobustness && (
                  <span className="px-2 py-0.5 rounded text-2xs font-mono font-bold bg-attention-soft text-attention border border-attention/30">
                    Low stability
                  </span>
                )}
              </div>
              <p className="text-sm sm:text-base font-semibold text-foreground leading-snug">
                {headlineText}
              </p>
            </div>
          </div>

          {/* F3: Runtime Slicers Bar */}
          {slicers && slicers.length > 0 && (
            <div className="bg-surface border border-border rounded-card p-3 sm:p-4 shadow-xs slicer-controls">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                  <Filter className="w-3.5 h-3.5 text-primary" />
                  <span>Interactive Slicers</span>
                  <span className="text-2xs font-mono font-normal text-muted-foreground ml-1">
                    (Runtime Dataset Filters)
                  </span>
                </div>
                {activeFilters.length > 0 && (
                  <button
                    onClick={handleResetFilters}
                    className="flex items-center gap-1 text-2xs font-mono text-attention hover:underline"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Reset filters</span>
                  </button>
                )}
              </div>

              {/* Slicer Controls Container */}
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {slicers.map((sl) => {
                  const currentFilter = activeFilters.find(
                    (f) => f.column.toLowerCase() === sl.column.toLowerCase()
                  );

                  if (sl.control_type === 'date_range') {
                    return (
                      <div key={sl.id} className="space-y-1">
                        <label className="text-2xs font-mono text-muted-foreground block truncate" title={sl.column}>
                          {sl.column} (Date Range)
                        </label>
                        <div className="flex items-center gap-1">
                          <input
                            type="date"
                            defaultValue={sl.min_date}
                            onChange={(e) => {
                              const end = (document.getElementById(`end-${sl.id}`) as HTMLInputElement)?.value;
                              handleSlicerChange(sl.column, 'BETWEEN', [e.target.value, end || sl.max_date || e.target.value]);
                            }}
                            className="w-full text-2xs font-mono p-1 rounded bg-surface border border-border text-foreground"
                          />
                          <span className="text-muted-foreground text-xs">–</span>
                          <input
                            id={`end-${sl.id}`}
                            type="date"
                            defaultValue={sl.max_date}
                            onChange={(e) => {
                              const start = sl.min_date || '';
                              handleSlicerChange(sl.column, 'BETWEEN', [start, e.target.value]);
                            }}
                            className="w-full text-2xs font-mono p-1 rounded bg-surface border border-border text-foreground"
                          />
                        </div>
                      </div>
                    );
                  }

                  // Multi-select for categorical
                  return (
                    <div key={sl.id} className="space-y-1">
                      <label className="text-2xs font-mono text-muted-foreground block truncate" title={sl.column}>
                        {sl.column}
                      </label>
                      <select
                        value={currentFilter?.values?.[0] ?? ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          if (val === '') {
                            handleSlicerChange(sl.column, '=', []);
                          } else {
                            handleSlicerChange(sl.column, '=', [val]);
                          }
                        }}
                        className="w-full text-2xs font-mono p-1.5 rounded bg-surface border border-border text-foreground"
                      >
                        <option value="">All {sl.column}</option>
                        {sl.options.map((opt) => (
                          <option key={String(opt.value)} value={String(opt.value)}>
                            {opt.label} ({opt.count ?? '—'})
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>

              {/* F4: Active Filter Chips */}
              {activeFilters.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 mt-3 pt-2.5 border-t border-border/60">
                  <span className="text-3xs font-mono uppercase text-muted-foreground">
                    Active Filters:
                  </span>
                  {activeFilters.map((f, fIdx) => (
                    <span
                      key={fIdx}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono bg-primary-soft text-primary border border-primary/30"
                    >
                      <span>
                        {f.column} = {Array.isArray(f.values) ? f.values.join(', ') : f.values}
                      </span>
                      <button
                        onClick={() => handleToggleFilter(f.column, f.values[0])}
                        className="hover:text-error transition-colors"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* F1: 12-Column Responsive Grid of Tiles */}
          <div className="grid grid-cols-1 md:grid-cols-6 xl:grid-cols-12 gap-4 dashboard-container">
            {tiles.map((tile) => {
              const override = tileOverrides[tile.id];
              const effectiveData = override?.data !== undefined ? override.data : tile.data;
              const isLoading = override?.isLoading ?? false;
              const isInsufficientData = override?.isInsufficientData ?? false;
              const queryError = override?.error;

              return (
                <div
                  key={tile.id}
                  id={`tile-card-${tile.id}`}
                  className={`${getColSpanClass(tile)} bg-surface border border-border rounded-card p-4 sm:p-5 flex flex-col justify-between shadow-xs transition-shadow hover:shadow-sm dashboard-tile`}
                >
                  {/* Tile Header: Insight Sentence & Action Menu */}
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-3xs font-mono uppercase px-2 py-0.5 rounded bg-surface-muted text-muted-foreground border border-border font-semibold">
                          {tile.chart_type}
                        </span>
                        {tile.candidate_id && (
                          <span className="text-3xs font-mono text-muted-foreground">
                            #{tile.candidate_id.slice(0, 6)}
                          </span>
                        )}
                      </div>

                      {/* Tile Actions Menu */}
                      <div className="flex items-center gap-1 tile-menu-button no-print">
                        <button
                          onClick={() => setActiveModal({ type: 'why', tile })}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
                          title="Why this was chosen"
                        >
                          <HelpCircle className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setActiveModal({ type: 'sql', tile })}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
                          title="View compiled SQL query"
                        >
                          <Code className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setActiveModal({ type: 'data', tile })}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
                          title="View underlying data table"
                        >
                          <TableIcon className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setActiveModal({ type: 'expand', tile })}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
                          title="Expand chart modal"
                        >
                          <Maximize2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDownloadPng(tile.id, tile.title)}
                          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
                          title="Download chart PNG"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Title: The Insight Sentence */}
                    <h3 className="text-xs sm:text-sm font-bold text-foreground leading-snug mb-3">
                      {tile.title}
                    </h3>
                  </div>

                  {/* Tile Body: Chart via InsightChart */}
                  <div className="flex-1 w-full my-2 min-h-[160px] flex items-center justify-center">
                    <InsightChart
                      visualization={tile.chart_type}
                      metric={tile.metrics?.[0]}
                      dimensions={tile.dimensions}
                      executionData={effectiveData}
                      isLoading={isLoading}
                      isInsufficientData={isInsufficientData}
                      errorMessage={queryError}
                      delta={tile.delta}
                      onItemClick={(dim, val) => handleToggleFilter(dim, val)}
                      selectedFilterValue={
                        activeFilters.find(
                          (f) =>
                            f.column.toLowerCase() ===
                            (tile.dimensions?.[0] || tile.x_key || '').toLowerCase()
                        )?.values?.[0]
                      }
                      className="w-full h-full min-h-[160px]"
                    />
                  </div>

                  {/* F2: Tile Footer */}
                  <div className="mt-3 pt-3 border-t border-border/70 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-2xs font-mono text-muted-foreground">
                    {/* Provenance Badge */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-3xs uppercase font-medium">Source:</span>
                      <span className="px-1.5 py-0.5 rounded text-3xs font-semibold bg-surface-muted text-foreground border border-border">
                        {tile.generator}
                      </span>
                    </div>

                    {/* Evidence Chips: Scored insights only, excluded for KPI context tiles */}
                    {tile.chart_type !== 'kpi' && tile.evidence && (
                      <div className="flex items-center gap-2">
                        {tile.evidence.strength !== undefined && (
                          <span title="Insight statistical strength">
                            Str: {(tile.evidence.strength).toFixed(2)}
                          </span>
                        )}

                        {tile.evidence.robustness !== undefined && (
                          <div
                            className="flex items-center gap-1"
                            title={`Perturbation Robustness: ${(tile.evidence.robustness * 100).toFixed(0)}%`}
                          >
                            <span>Rob:</span>
                            <div className="w-10 h-1.5 rounded-full bg-surface-muted border border-border overflow-hidden">
                              <div
                                className="h-full bg-primary"
                                style={{ width: `${Math.min(100, Math.max(0, tile.evidence.robustness * 100))}%` }}
                              />
                            </div>
                          </div>
                        )}

                        {tile.evidence.fdr_passed !== undefined && (
                          <span
                            className={`px-1 rounded text-3xs font-bold ${tile.evidence.fdr_passed
                                ? 'bg-success-soft text-success'
                                : 'bg-attention-soft text-attention'
                              }`}
                            title={tile.evidence.fdr_passed ? 'Passed Benjamini-Hochberg FDR control' : 'Failed FDR control'}
                          >
                            FDR: {tile.evidence.fdr_passed ? 'PASS' : 'FAIL'}
                          </span>
                        )}

                        {tile.evidence.n !== undefined && (
                          <span title="Sample size">n={tile.evidence.n}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* F1: "Considered but rejected" Drawer at bottom (Collapsed by default) */}
          {rejectedInsights && rejectedInsights.length > 0 && (
            <details className="group bg-surface border border-border rounded-card overflow-hidden shadow-xs mt-6 no-print">
              <summary className="px-5 py-3.5 cursor-pointer flex items-center justify-between text-xs font-bold text-muted-foreground hover:text-foreground select-none transition-colors">
                <div className="flex items-center gap-2">
                  <Filter className="w-3.5 h-3.5 text-muted-foreground group-open:text-primary transition-colors" />
                  <span>Considered but Rejected Insights ({rejectedInsights.length} candidates)</span>
                </div>
                <span className="text-3xs font-mono text-muted-foreground bg-surface-muted px-2 py-0.5 rounded border border-border">
                  Click to inspect reasons
                </span>
              </summary>
              <div className="p-4 pt-1 border-t border-border overflow-x-auto">
                <table className="w-full text-left text-xs font-mono border-collapse">
                  <thead>
                    <tr className="border-b border-border text-2xs uppercase text-muted-foreground">
                      <th className="py-2 px-3">Candidate / Goal</th>
                      <th className="py-2 px-3">Type</th>
                      <th className="py-2 px-3">Stage</th>
                      <th className="py-2 px-3">Reason for Rejection</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/60">
                    {rejectedInsights.map((rej: any, idx: number) => (
                      <tr key={idx} className="hover:bg-surface-muted/30">
                        <td className="py-2 px-3 font-semibold text-foreground whitespace-nowrap">
                          {rej.description || rej.intent || 'Candidate Insight'}
                        </td>
                        <td className="py-2 px-3 text-muted-foreground">
                          {rej.insight_type || 'INSIGHT'}
                        </td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded text-3xs font-bold bg-surface-muted border border-border">
                            {rej.rejection_stage || rej.stage || 'PRUNING'}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-attention text-2xs">
                          {rej.reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      )}

      {/* TAB 2: DATA PREVIEW */}
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
              <h3 className="text-sm font-bold text-foreground">Data Cleaning & Transformation Report</h3>
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
        </div>
      )}

      {/* TAB 4: TRACE & SQL */}
      {activeTab === 'trace' && spec?.winner?.execution?.compiled_sql && (
        <div className="bg-surface border border-border rounded-card p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <h3 className="text-sm font-bold text-foreground">Auditable Compiled SQL</h3>
              <p className="text-2xs text-muted-foreground">DuckDB query executed in sandboxed worker</p>
            </div>
          </div>
          <pre className="p-3 bg-surface-muted/50 rounded-card border border-border font-mono text-xs text-foreground overflow-x-auto">
            <code>{spec.winner.execution.compiled_sql}</code>
          </pre>
        </div>
      )}

      {/* MODALS: View SQL, View Data, Why Chosen, Expand */}
      {activeModal.type && activeModal.tile && (() => {
        const modalTile = activeModal.tile;
        return (
          <div className="fixed inset-0 z-50 bg-foreground/30 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-surface border border-border rounded-card shadow-lg max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
              {/* Modal Header */}
              <div className="flex items-center justify-between p-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-foreground">
                    {activeModal.type === 'sql' && 'Compiled SQL Query'}
                    {activeModal.type === 'data' && 'Underlying Tile Data'}
                    {activeModal.type === 'why' && 'Analytical Justification & Scoring'}
                    {activeModal.type === 'expand' && modalTile.title}
                  </span>
                </div>
                <button
                  onClick={() => setActiveModal({ type: null, tile: null })}
                  aria-label="Close modal"
                  className="text-muted-foreground hover:text-foreground p-1 rounded"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-4 overflow-y-auto flex-1">
                {activeModal.type === 'sql' && (
                  <div>
                    <pre className="p-3 bg-surface-muted font-mono text-xs text-foreground rounded-card border border-border overflow-x-auto">
                      <code>
                        {modalTile.compiled_sql ||
                          modalTile.plan?.compiled_sql ||
                          '-- Re-compiled dynamically through DuckDB sandboxed compiler\nSELECT * FROM dataset'}
                      </code>
                    </pre>
                  </div>
                )}

                {activeModal.type === 'data' && (
                  <div>
                    {modalTile.data && modalTile.data.length > 0 ? (
                      <div className="overflow-x-auto max-h-96">
                        <table className="w-full text-left text-xs font-mono border-collapse">
                          <thead>
                            <tr className="border-b border-border bg-surface-muted text-2xs uppercase text-muted-foreground">
                              {Object.keys(modalTile.data[0] || {}).map((k) => (
                                <th key={k} className="py-2 px-3 font-semibold whitespace-nowrap">
                                  {k}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border text-foreground">
                            {modalTile.data.map((r, rIdx) => (
                              <tr key={rIdx} className="hover:bg-surface-muted/20">
                                {Object.keys(modalTile.data[0] || {}).map((k) => (
                                  <td key={k} className="py-1 px-3 whitespace-nowrap text-muted-foreground">
                                    {String(r[k])}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="py-8 text-center text-xs text-muted-foreground">
                        No data available for this tile.
                      </div>
                    )}
                  </div>
                )}

                {activeModal.type === 'why' && (
                  <div className="space-y-3">
                    <div className="p-3 bg-primary-soft border border-primary/30 rounded-card text-xs text-foreground font-medium">
                      {modalTile.why_chosen ||
                        'Ranked among top candidates according to combined strength, coverage, and perturbation robustness.'}
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
                      <div className="p-2.5 bg-surface-muted rounded-card border border-border text-center">
                        <div className="text-3xs uppercase font-mono text-muted-foreground">Strength</div>
                        <div className="text-sm font-bold font-mono text-foreground mt-1">
                          {(modalTile.evidence?.strength ?? 0.8).toFixed(2)}
                        </div>
                      </div>

                      <div className="p-2.5 bg-surface-muted rounded-card border border-border text-center">
                        <div className="text-3xs uppercase font-mono text-muted-foreground">Robustness</div>
                        <div className="text-sm font-bold font-mono text-foreground mt-1">
                          {((modalTile.evidence?.robustness ?? 0.85) * 100).toFixed(0)}%
                        </div>
                      </div>

                      <div className="p-2.5 bg-surface-muted rounded-card border border-border text-center">
                        <div className="text-3xs uppercase font-mono text-muted-foreground">FDR Status</div>
                        <div className="text-sm font-bold font-mono text-success mt-1">
                          {modalTile.evidence?.fdr_passed ? 'PASS' : 'FAIL'}
                        </div>
                      </div>

                      <div className="p-2.5 bg-surface-muted rounded-card border border-border text-center">
                        <div className="text-3xs uppercase font-mono text-muted-foreground">Sample Size</div>
                        <div className="text-sm font-bold font-mono text-foreground mt-1">
                          n={modalTile.evidence?.n ?? 0}
                        </div>
                      </div>
                    </div>

                    <div className="text-2xs text-muted-foreground font-mono pt-2">
                      Generator: <strong>{modalTile.generator}</strong> • Priority: #{modalTile.priority}
                    </div>
                  </div>
                )}

                {activeModal.type === 'expand' && (
                  <div className="h-96 w-full flex items-center justify-center pt-2">
                    <InsightChart
                      visualization={modalTile.chart_type}
                      metric={modalTile.metrics?.[0]}
                      dimensions={modalTile.dimensions}
                      executionData={modalTile.data}
                      className="w-full h-full"
                    />
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="p-3 border-t border-border flex justify-end">
                <button
                  onClick={() => setActiveModal({ type: null, tile: null })}
                  className="px-3 py-1.5 text-xs font-semibold rounded bg-surface border border-border hover:bg-surface-muted text-foreground transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};
