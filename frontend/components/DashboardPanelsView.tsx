'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
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
  RotateCcw,
  Printer,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  X,
  HelpCircle,
  Check,
  Database,
  Pencil,
  Trash2,
} from 'lucide-react';
import { DashboardPanelUI, DashboardTileUI, SlicerDef, DatasetMetadata } from '../lib/types';
import { InsightChart, resolveChartKeys } from './InsightChart';
import {
  queryTile,
  deleteDashboardTile,
  resetDashboardTile,
  resetDashboard,
} from '../lib/api';
import { ChartEditModal } from './ChartEditModal';
import { THEME_TOKENS } from '../lib/theme';

export interface DashboardPanelsViewProps {
  spec?: any;
  headline?: string | null;
  panels?: DashboardPanelUI[];
  metadata?: DatasetMetadata | null;
  previewData?: any;
  cleaningReport?: any;
  providers?: any[];
  onSelectCandidate?: (planId: string) => void;
  datasetId?: string;
  onSpecChange?: (updatedTiles: DashboardTileUI[]) => void;
  className?: string;
}

export const DashboardPanelsView: React.FC<DashboardPanelsViewProps> = ({
  spec,
  headline,
  panels: rawPanels,
  metadata,
  previewData,
  cleaningReport,
  providers: rawProviders,
  onSelectCandidate,
  datasetId,
  onSpecChange,
  className = '',
}) => {
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
        compiled_sql?: string;
        isLoading: boolean;
        isInsufficientData: boolean;
        error?: string;
      }
    >
  >({});

  // Reset state on dashboard spec transition
  useEffect(() => {
    setActiveFilters([]);
    setTileOverrides({});
    setActiveModal({ type: null, tile: null });
  }, [spec?.spec_id]);

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

  // Working and original tiles state for editable dashboard
  const [workingTiles, setWorkingTiles] = useState<DashboardTileUI[]>([]);
  const [originalTiles, setOriginalTiles] = useState<DashboardTileUI[]>([]);
  const [editingTile, setEditingTile] = useState<DashboardTileUI | null>(null);

  useEffect(() => {
    setWorkingTiles(tiles);
    setOriginalTiles(tiles);
  }, [tiles]);

  const isDirty = useMemo(() => {
    if (workingTiles.length !== originalTiles.length) return true;
    return workingTiles.some((t) => t.metadata?.is_edited);
  }, [workingTiles, originalTiles]);

  const activeTiles = workingTiles.length > 0 || isDirty ? workingTiles : tiles;

  // Slicer definitions
  const slicers: SlicerDef[] = spec?.slicers || [];

  // Headline computation and robustness floor logic
  const activeHeadline = headline || spec?.headline;
  const headlineRobustness =
    spec?.winner?.score_breakdown?.stability ??
    spec?.winner?.score_breakdown?.robustness ??
    activeTiles[0]?.evidence?.robustness ??
    1.0;
  const isLowRobustness = headlineRobustness < 0.35;
  const headlineText = activeHeadline || activeTiles[0]?.title || 'Executive Insight';

  // Tile edit handlers
  const handleTileSaved = (updatedTile: DashboardTileUI) => {
    const nextTiles = activeTiles.map((t) => (t.id === updatedTile.id ? updatedTile : t));
    setWorkingTiles(nextTiles);
    setTileOverrides((prev) => {
      const next = { ...prev };
      delete next[updatedTile.id];
      return next;
    });
    setEditingTile(null);
    onSpecChange?.(nextTiles);

    if (activeFilters.length > 0) {
      setTimeout(() => {
        applyFiltersToTiles(activeFilters);
      }, 50);
    }
  };

  const handleRemoveTile = async (tileId: string) => {
    if (spec?.spec_id) {
      try {
        await deleteDashboardTile(spec.spec_id, tileId);
      } catch (err) {
        console.warn('Failed to delete tile on backend:', err);
      }
    }
    const nextTiles = activeTiles.filter((t) => t.id !== tileId);
    setWorkingTiles(nextTiles);
    setTileOverrides((prev) => {
      const next = { ...prev };
      delete next[tileId];
      return next;
    });
    onSpecChange?.(nextTiles);
  };

  const handleResetTile = async (tileId: string) => {
    if (spec?.spec_id) {
      try {
        const res = await resetDashboardTile(spec.spec_id, tileId);
        if (res?.tile) {
          const nextTiles = activeTiles.map((t) => (t.id === tileId ? res.tile : t));
          setWorkingTiles(nextTiles);
          setTileOverrides((prev) => {
            const next = { ...prev };
            delete next[tileId];
            return next;
          });
          onSpecChange?.(nextTiles);
          return;
        }
      } catch (err) {
        console.warn('Failed to reset tile on backend, falling back to local snapshot:', err);
      }
    }
    const orig = originalTiles.find((t) => t.id === tileId);
    if (orig) {
      const nextTiles = activeTiles.map((t) => (t.id === tileId ? orig : t));
      setWorkingTiles(nextTiles);
      setTileOverrides((prev) => {
        const next = { ...prev };
        delete next[tileId];
        return next;
      });
      onSpecChange?.(nextTiles);
    }
  };

  const handleResetDashboard = async () => {
    if (spec?.spec_id) {
      try {
        const res = await resetDashboard(spec.spec_id);
        if (res?.spec?.tiles) {
          setWorkingTiles(res.spec.tiles);
          setTileOverrides({});
          setActiveFilters([]);
          onSpecChange?.(res.spec.tiles);
          return;
        }
      } catch (err) {
        console.warn('Failed to reset dashboard on backend, falling back to local snapshot:', err);
      }
    }
    setWorkingTiles(originalTiles);
    setTileOverrides({});
    setActiveFilters([]);
    onSpecChange?.(originalTiles);
  };

  // Dataset info
  const datasetName = spec?.dataset_name || spec?.dataset_id || 'Active Dataset';
  const rowCount = spec?.row_count ?? previewData?.rows?.length ?? '—';
  const rejectedInsights = spec?.rejected_insights || [];
  const cleaningCount = cleaningReport?.transformations?.length ?? 0;

  // Request versioning to eliminate race conditions
  const filterReqVersionRef = useRef(0);

  // Handle cross filter toggling (e.g. clicking a chart bar / slice)
  const handleToggleFilter = async (column: string, value: any) => {
    let nextFilters = [...activeFilters];
    const existingIdx = nextFilters.findIndex(
      (f) => f.column.toLowerCase() === column.toLowerCase() && f.values.includes(value)
    );

    if (existingIdx >= 0) {
      // Remove filter if already active on same value (toggle off)
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

  // Dedicated single-column filter removal (e.g. clicking 'X' on filter chip)
  const handleRemoveFilter = async (column: string) => {
    const nextFilters = activeFilters.filter(
      (f) => f.column.toLowerCase() !== column.toLowerCase()
    );
    setActiveFilters(nextFilters);
    await applyFiltersToTiles(nextFilters);
  };

  // Handle slicer input change (dropdown or date range)
  const handleSlicerChange = async (column: string, operator: string, values: any[]) => {
    let nextFilters = activeFilters.filter(
      (f) => f.column.toLowerCase() !== column.toLowerCase()
    );
    const hasValidValue =
      values &&
      values.length > 0 &&
      values.every((v) => v !== '' && v !== undefined && v !== null);
    if (hasValidValue) {
      nextFilters.push({ column, operator, values });
    }
    setActiveFilters(nextFilters);
    await applyFiltersToTiles(nextFilters);
  };

  // Reset all filters
  const handleResetFilters = () => {
    filterReqVersionRef.current++;
    setActiveFilters([]);
    setTileOverrides({});

    // Reset date slicer input values to initial defaults if present in DOM
    slicers.forEach((sl) => {
      if (sl.control_type === 'date_range') {
        const startEl = document.getElementById(`slicer-start-${sl.id}`) as HTMLInputElement;
        const endEl = document.getElementById(`slicer-end-${sl.id}`) as HTMLInputElement;
        if (startEl) startEl.value = sl.min_date || '';
        if (endEl) endEl.value = sl.max_date || '';
      }
    });
  };

  // Re-query ALL dashboard tiles with active filter set
  const applyFiltersToTiles = async (
    filters: { column: string; operator: string; values: any[] }[]
  ) => {
    if (!spec?.spec_id) return;

    const currentVersion = ++filterReqVersionRef.current;

    if (filters.length === 0) {
      setTileOverrides({});
      return;
    }

    // Set loading state for all tiles
    setTileOverrides((prev) => {
      const next: typeof prev = { ...prev };
      activeTiles.forEach((tile) => {
        next[tile.id] = {
          data: prev[tile.id]?.data || tile.data,
          isLoading: true,
          isInsufficientData: false,
        };
      });
      return next;
    });

    // Fetch recomputed data for all tiles in parallel
    await Promise.all(
      activeTiles.map(async (tile) => {
        try {
          console.log(`[SQL_DEBUG] queryTile START for tile.id=${tile.id}, activeFilters=`, filters);
          const res = await queryTile(spec.spec_id, tile.id, filters);
          console.log(`[SQL_DEBUG] queryTile RESPONSE for tile.id=${tile.id}:`, {
            response_tile_id: res.tile_id,
            status: res.status,
            row_count: res.row_count,
            compiled_sql: res.compiled_sql,
            data_sample: res.data?.slice(0, 2),
          });
          if (filterReqVersionRef.current !== currentVersion) return;

          if (res.status === 'INSUFFICIENT_DATA' || res.row_count < 1) {
            setTileOverrides((prev) => {
              const updated = {
                ...prev,
                [tile.id]: {
                  data: [],
                  compiled_sql: res.compiled_sql || prev[tile.id]?.compiled_sql || tile.compiled_sql,
                  isLoading: false,
                  isInsufficientData: true,
                },
              };
              console.log(`[SQL_DEBUG] setTileOverrides (INSUFFICIENT_DATA) for tile.id=${tile.id}:`, updated[tile.id]);
              return updated;
            });
          } else {
            setTileOverrides((prev) => {
              const updated = {
                ...prev,
                [tile.id]: {
                  data: res.data,
                  compiled_sql: res.compiled_sql || prev[tile.id]?.compiled_sql || tile.compiled_sql,
                  isLoading: false,
                  isInsufficientData: false,
                },
              };
              console.log(`[SQL_DEBUG] setTileOverrides (SUCCESS) for tile.id=${tile.id}:`, updated[tile.id]);
              return updated;
            });
          }
        } catch (err: any) {
          if (filterReqVersionRef.current !== currentVersion) return;
          console.error(`[SQL_DEBUG] queryTile ERROR for tile.id=${tile.id}:`, err);
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
      })
    );
  };

  // Download tile chart as PNG
  const handleDownloadPng = (tileId: string, title: string) => {
    const tileEl = document.getElementById(`tile-card-${tileId}`);
    if (!tileEl) return;

    // Find the actual chart SVG inside Recharts container (avoid grabbing small 14x14 button icons)
    const svgEl =
      (tileEl.querySelector('.recharts-surface') as SVGSVGElement) ||
      (tileEl.querySelector('.recharts-wrapper svg') as SVGSVGElement) ||
      (tileEl.querySelector('.recharts-responsive-container svg') as SVGSVGElement);

    const scale = 2; // 2x high-DPI export

    if (svgEl) {
      try {
        const w = Math.max(svgEl.clientWidth || parseInt(svgEl.getAttribute('width') || '600') || 600, 480);
        const h = Math.max(svgEl.clientHeight || parseInt(svgEl.getAttribute('height') || '260') || 260, 240);
        const headerH = 50;

        const clone = svgEl.cloneNode(true) as SVGSVGElement;
        clone.setAttribute('width', String(w));
        clone.setAttribute('height', String(h));
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

        // Embed theme tokens into SVG style block
        const computed = typeof window !== 'undefined' ? window.getComputedStyle(document.body) : null;
        const styleEl = document.createElementNS('http://www.w3.org/2000/svg', 'style');
        styleEl.textContent = `
          :root {
            --chart-1: ${computed?.getPropertyValue('--chart-1')?.trim() || '#2563eb'};
            --chart-2: ${computed?.getPropertyValue('--chart-2')?.trim() || '#16a34a'};
            --chart-3: ${computed?.getPropertyValue('--chart-3')?.trim() || '#d97706'};
            --chart-4: ${computed?.getPropertyValue('--chart-4')?.trim() || '#dc2626'};
            --chart-5: ${computed?.getPropertyValue('--chart-5')?.trim() || '#8b5cf6'};
            --foreground: ${computed?.getPropertyValue('--foreground')?.trim() || '#111827'};
            --muted: ${computed?.getPropertyValue('--muted')?.trim() || '#6b7280'};
            --border: ${computed?.getPropertyValue('--border')?.trim() || '#e5e7eb'};
          }
          text { font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        `;
        clone.insertBefore(styleEl, clone.firstChild);

        const serializer = new XMLSerializer();
        let source = serializer.serializeToString(clone);
        if (!source.match(/^<svg[^>]+xmlns="http\:\/\/www\.w3\.org\/2000\/svg"/)) {
          source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
        }

        const svgBlob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' });
        const DOMURL = window.URL || window.webkitURL || window;
        const url = DOMURL.createObjectURL(svgBlob);
        const img = new Image();

        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = w * scale;
          canvas.height = (h + headerH + 20) * scale;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.scale(scale, scale);
            // Fill background
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, w, h + headerH + 20);

            // Draw header
            ctx.fillStyle = '#111827';
            ctx.font = 'bold 14px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif';
            ctx.fillText(title, 20, 28);

            ctx.fillStyle = '#6b7280';
            ctx.font = '10px ui-monospace, monospace';
            ctx.fillText(`DashCrate • Exported ${new Date().toLocaleDateString()}`, 20, 44);

            // Draw chart SVG
            ctx.drawImage(img, 0, headerH, w, h);

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
        console.error('Failed to export chart PNG:', e);
      }
    } else {
      // Fallback for KPI or text tile
      try {
        const w = 600;
        const h = 320;
        const canvas = document.createElement('canvas');
        canvas.width = w * scale;
        canvas.height = h * scale;
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.scale(scale, scale);
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, w, h);

          // Card outline
          ctx.strokeStyle = '#e5e7eb';
          ctx.lineWidth = 1;
          ctx.strokeRect(16, 16, w - 32, h - 32);

          // Title
          ctx.fillStyle = '#6b7280';
          ctx.font = 'bold 12px ui-monospace, monospace';
          ctx.fillText('KPI INSIGHT', 36, 52);

          ctx.fillStyle = '#111827';
          ctx.font = 'bold 16px ui-sans-serif, system-ui, sans-serif';
          ctx.fillText(title, 36, 80);

          // Extract value from DOM
          const valEl = tileEl.querySelector('.text-3xl, .text-4xl, font-extrabold') || tileEl;
          const valText = valEl.textContent?.replace(title, '').trim() || '—';

          ctx.fillStyle = '#2563eb';
          ctx.font = 'bold 44px ui-monospace, monospace';
          ctx.fillText(valText.slice(0, 20), 36, 160);

          ctx.fillStyle = '#9ca3af';
          ctx.font = '10px ui-monospace, monospace';
          ctx.fillText(`DashCrate • Exported ${new Date().toLocaleDateString()}`, 36, 270);

          const pngUrl = canvas.toDataURL('image/png');
          const a = document.createElement('a');
          a.download = `${title.toLowerCase().replace(/[^a-z0-9]/g, '_')}.png`;
          a.href = pngUrl;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        }
      } catch (e) {
        console.error('Failed to export KPI tile PNG:', e);
      }
    }
  };

  // Helper to safely escape HTML strings
  const escapeHtml = (unsafe: string | null | undefined): string => {
    if (unsafe === null || unsafe === undefined) return '';
    return String(unsafe)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  // Standalone Pure SVG Chart Generator for Fallback/Self-contained Export
  // Standalone Pure SVG Chart Generator for Dynamic Export (Supports all visual types)
  const renderDynamicTileSvg = (
    chartType: string,
    rows: Record<string, any>[],
    preferredDims: string[] = [],
    preferredMetrics: string[] = []
  ): string => {
    if (!rows || rows.length === 0) {
      return `<div style="padding: 24px; text-align: center; color: var(--muted); font-size: 12px;">No chart data available</div>`;
    }

    const cType = (chartType || 'bar').toLowerCase();

    // Ensure numeric string values are coerced to numbers for clean plotting
    const normalizedRows = rows.map((r) => {
      const copy: Record<string, any> = { ...r };
      for (const k of Object.keys(copy)) {
        const val = copy[k];
        if (typeof val === 'string' && val.trim() !== '' && !isNaN(Number(val))) {
          copy[k] = Number(val);
        }
      }
      return copy;
    });

    const { dimKey, metricKey } = resolveChartKeys(normalizedRows, preferredDims, preferredMetrics);

    const width = 560;
    const height = 240;
    const padding = { top: 20, right: 20, bottom: 45, left: 55 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const colors = [
      THEME_TOKENS.chartSeries[0] || '#2F7F7A',
      THEME_TOKENS.chartSeries[1] || '#5B7C99',
      THEME_TOKENS.chartSeries[2] || '#C9A66B',
      THEME_TOKENS.chartSeries[3] || '#B56576',
      THEME_TOKENS.chartSeries[4] || '#9AA5B1',
      '#4E878C',
      '#D4A373',
      '#E07A5F',
    ];

    const formatTick = (val: number): string => {
      const absVal = Math.abs(val);
      if (absVal >= 1000000) return (val / 1000000).toFixed(1) + 'M';
      if (absVal >= 1000) return (val / 1000).toFixed(absVal >= 10000 ? 0 : 1) + 'k';
      return Number.isInteger(val) ? val.toString() : val.toFixed(1);
    };

    // 1. Donut / Pie Composition Charts
    if (cType === 'donut' || cType === 'pie' || cType === 'composition') {
      const isDonut = cType === 'donut' || cType === 'composition';
      const nonNegValues = normalizedRows.map((r) => Math.max(0, Number(r[metricKey]) || 0));
      const total = nonNegValues.reduce((a, b) => a + b, 0) || 1;
      const cx = 130;
      const cy = height / 2;
      const r = Math.min(cx, cy) - 20;
      const innerR = isDonut ? r * 0.55 : 0;

      const slices: string[] = [];
      const legendItems: string[] = [];

      if (normalizedRows.length === 1 || total <= 0) {
        const dimLabel = escapeHtml(String(normalizedRows[0]?.[dimKey] ?? 'Total'));
        const color = colors[0];
        if (isDonut) {
          const d = `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx} ${cy + r} A ${r} ${r} 0 1 1 ${cx} ${cy - r} M ${cx} ${cy - innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy + innerR} A ${innerR} ${innerR} 0 1 0 ${cx} ${cy - innerR} Z`;
          slices.push(`<path d="${d}" fill="${color}" fill-rule="evenodd" />`);
        } else {
          slices.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" />`);
        }
        legendItems.push(`
          <div style="display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 6px;">
            <span style="display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: ${color}; flex-shrink: 0;"></span>
            <span style="color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;">${dimLabel}</span>
            <span style="color: var(--muted); margin-left: auto; font-family: monospace;">100%</span>
          </div>
        `);
      } else {
        let startAngle = -Math.PI / 2;
        normalizedRows.slice(0, 8).forEach((row, i) => {
          const val = Math.max(0, Number(row[metricKey]) || 0);
          const sliceAngle = (val / total) * 2 * Math.PI;
          if (sliceAngle < 0.005) return;
          const endAngle = startAngle + sliceAngle;
          const color = colors[i % colors.length];

          const x1 = cx + r * Math.cos(startAngle);
          const y1 = cy + r * Math.sin(startAngle);
          const x2 = cx + r * Math.cos(endAngle);
          const y2 = cy + r * Math.sin(endAngle);
          const largeArc = sliceAngle > Math.PI ? 1 : 0;

          let d = '';
          if (innerR > 0) {
            const ix1 = cx + innerR * Math.cos(endAngle);
            const iy1 = cy + innerR * Math.sin(endAngle);
            const ix2 = cx + innerR * Math.cos(startAngle);
            const iy2 = cy + innerR * Math.sin(startAngle);
            d = `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r.toFixed(2)} ${r.toFixed(2)} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} L ${ix1.toFixed(2)} ${iy1.toFixed(2)} A ${innerR.toFixed(2)} ${innerR.toFixed(2)} 0 ${largeArc} 0 ${ix2.toFixed(2)} ${iy2.toFixed(2)} Z`;
          } else {
            d = `M ${cx.toFixed(2)} ${cy.toFixed(2)} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r.toFixed(2)} ${r.toFixed(2)} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
          }

          slices.push(`<path d="${d}" fill="${color}" stroke="var(--surface)" stroke-width="1.5" />`);
          const dimLabel = escapeHtml(String(row[dimKey] ?? `Item ${i + 1}`));
          const pct = Math.round((val / total) * 100);
          legendItems.push(`
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 5px;">
              <span style="display: inline-block; width: 10px; height: 10px; border-radius: 2px; background: ${color}; flex-shrink: 0;"></span>
              <span style="color: var(--foreground); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px;" title="${dimLabel}">${dimLabel}</span>
              <span style="color: var(--muted); margin-left: auto; font-family: monospace; font-weight: 500;">${pct}%</span>
            </div>
          `);
          startAngle = endAngle;
        });
      }

      return `
        <div style="display: flex; align-items: center; justify-content: center; gap: 20px; width: 100%; flex-wrap: wrap; padding: 12px 0;">
          <svg viewBox="0 0 260 ${height}" style="width: 240px; max-height: 220px; flex-shrink: 0;" xmlns="http://www.w3.org/2000/svg">
            ${slices.join('')}
          </svg>
          <div style="flex: 1; min-width: 150px; max-width: 260px;">
            ${legendItems.join('')}
          </div>
        </div>
      `;
    }

    // 2. Scatter Plot (Independent Numeric X and Y Axes)
    if (cType === 'scatter') {
      const usableScatterData = normalizedRows.filter((r) => {
        const x = r[dimKey];
        const y = r[metricKey];
        return (
          typeof x === 'number' && !isNaN(x) && isFinite(x) &&
          typeof y === 'number' && !isNaN(y) && isFinite(y)
        );
      });

      if (usableScatterData.length === 0) {
        return `<div style="padding: 24px; text-align: center; color: var(--muted); font-size: 12px;">No valid numeric coordinates found for scatter plot</div>`;
      }

      const allX = usableScatterData.map((r) => Number(r[dimKey]));
      const allY = usableScatterData.map((r) => Number(r[metricKey]));

      const rawMinX = Math.min(...allX);
      const rawMaxX = Math.max(...allX);
      const minX = rawMinX === rawMaxX ? rawMinX - 1 : rawMinX;
      const maxX = rawMinX === rawMaxX ? rawMaxX + 1 : rawMaxX;
      const rangeX = (maxX - minX) || 1;

      const rawMinY = Math.min(...allY);
      const rawMaxY = Math.max(...allY);
      const minY = rawMinY === rawMaxY ? rawMinY - 1 : rawMinY;
      const maxY = rawMinY === rawMaxY ? rawMaxY + 1 : rawMaxY;
      const rangeY = (maxY - minY) || 1;

      const maxScatterPoints = 1200;
      const pointsToRender = usableScatterData.length <= maxScatterPoints
        ? usableScatterData
        : Array.from({ length: maxScatterPoints }, (_, i) => {
            const idx = Math.floor((i / (maxScatterPoints - 1)) * (usableScatterData.length - 1));
            return usableScatterData[idx];
          });

      const scatterGrid: string[] = [];
      const scatterYLabels: string[] = [];
      const scatterXLabels: string[] = [];
      const steps = 4;

      // Y-axis grid and labels
      for (let i = 0; i <= steps; i++) {
        const yVal = minY + (rangeY / steps) * i;
        const yPos = padding.top + chartH - (i / steps) * chartH;
        scatterGrid.push(`<line x1="${padding.left}" y1="${yPos.toFixed(1)}" x2="${(width - padding.right).toFixed(1)}" y2="${yPos.toFixed(1)}" stroke="var(--border)" stroke-dasharray="3 3" opacity="0.6" />`);
        scatterYLabels.push(`<text x="${(padding.left - 8).toFixed(1)}" y="${(yPos + 4).toFixed(1)}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="monospace">${formatTick(yVal)}</text>`);
      }

      // X-axis grid and labels
      for (let i = 0; i <= steps; i++) {
        const xVal = minX + (rangeX / steps) * i;
        const xPos = padding.left + (i / steps) * chartW;
        scatterGrid.push(`<line x1="${xPos.toFixed(1)}" y1="${padding.top}" x2="${xPos.toFixed(1)}" y2="${(height - padding.bottom).toFixed(1)}" stroke="var(--border)" stroke-dasharray="3 3" opacity="0.4" />`);
        scatterXLabels.push(`<text x="${xPos.toFixed(1)}" y="${(height - padding.bottom + 16).toFixed(1)}" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="monospace">${formatTick(xVal)}</text>`);
      }

      // Zero baseline lines if 0 is inside ranges
      if (minY < 0 && maxY > 0) {
        const zeroY = padding.top + chartH - ((0 - minY) / rangeY) * chartH;
        scatterGrid.push(`<line x1="${padding.left}" y1="${zeroY.toFixed(1)}" x2="${(width - padding.right).toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="var(--foreground)" stroke-width="1.2" opacity="0.4" />`);
      }
      if (minX < 0 && maxX > 0) {
        const zeroX = padding.left + ((0 - minX) / rangeX) * chartW;
        scatterGrid.push(`<line x1="${zeroX.toFixed(1)}" y1="${padding.top}" x2="${zeroX.toFixed(1)}" y2="${(height - padding.bottom).toFixed(1)}" stroke="var(--foreground)" stroke-width="1.2" opacity="0.4" />`);
      }

      const dots = pointsToRender.map((r) => {
        const ptX = Number(r[dimKey]);
        const ptY = Number(r[metricKey]);
        const cx = padding.left + ((ptX - minX) / rangeX) * chartW;
        const cy = padding.top + chartH - ((ptY - minY) / rangeY) * chartH;
        return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3" fill="${colors[0]}" fill-opacity="0.8" />`;
      });

      return `
        <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: 240px; display: block;" xmlns="http://www.w3.org/2000/svg">
          ${scatterGrid.join('')}
          ${scatterYLabels.join('')}
          ${scatterXLabels.join('')}
          ${dots.join('')}
        </svg>
      `;
    }

    // Shared domain calculation across entire dataset for single-metric charts
    const allNumericY = normalizedRows
      .map((r) => Number(r[metricKey]))
      .filter((v) => typeof v === 'number' && !isNaN(v) && isFinite(v));

    const minVal = allNumericY.length > 0 ? Math.min(...allNumericY) : 0;
    const maxVal = allNumericY.length > 0 ? Math.max(...allNumericY) : 1;
    const range = (maxVal - minVal) || 1;

    // Grid lines and Y-axis
    const gridLines: string[] = [];
    const yLabels: string[] = [];
    const steps = 4;
    for (let i = 0; i <= steps; i++) {
      const yVal = minVal + (range / steps) * i;
      const yPos = padding.top + chartH - (i / steps) * chartH;
      gridLines.push(`<line x1="${padding.left}" y1="${yPos.toFixed(1)}" x2="${(width - padding.right).toFixed(1)}" y2="${yPos.toFixed(1)}" stroke="var(--border)" stroke-dasharray="3 3" opacity="0.6" />`);
      yLabels.push(`<text x="${(padding.left - 8).toFixed(1)}" y="${(yPos + 4).toFixed(1)}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="monospace">${formatTick(yVal)}</text>`);
    }

    // 3. Line Chart
    if (cType === 'line' || cType === 'trend') {
      const maxLinePoints = 250;
      const linePoints = normalizedRows.length <= maxLinePoints
        ? normalizedRows
        : Array.from({ length: maxLinePoints }, (_, i) => {
            const idx = Math.floor((i / (maxLinePoints - 1)) * (normalizedRows.length - 1));
            return normalizedRows[idx];
          });

      const pts = linePoints.map((r, i) => {
        const x = padding.left + (i / Math.max(linePoints.length - 1, 1)) * chartW;
        const val = Number(r[metricKey]) || 0;
        const y = padding.top + chartH - ((val - minVal) / range) * chartH;
        return { x, y, val, label: String(r[dimKey] ?? '') };
      });

      const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
      const stepInterval = Math.max(Math.ceil(pts.length / 6), 1);
      const xLabels = pts
        .filter((_, idx) => idx % stepInterval === 0 || idx === pts.length - 1)
        .map((p) => `
          <text x="${p.x.toFixed(1)}" y="${(padding.top + chartH + 18).toFixed(1)}" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="sans-serif">${escapeHtml(p.label.slice(0, 12))}</text>
        `);

      const dots = pts.length <= 30
        ? pts.map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="${colors[0]}" stroke="var(--surface)" stroke-width="1.5" />`).join('')
        : '';

      return `
        <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: 240px; display: block;" xmlns="http://www.w3.org/2000/svg">
          ${gridLines.join('')}
          ${yLabels.join('')}
          <path d="${linePath}" fill="none" stroke="${colors[0]}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          ${dots}
          ${xLabels.join('')}
        </svg>
      `;
    }

    // 4. Area Chart
    if (cType === 'area') {
      const maxAreaPoints = 250;
      const areaPoints = normalizedRows.length <= maxAreaPoints
        ? normalizedRows
        : Array.from({ length: maxAreaPoints }, (_, i) => {
            const idx = Math.floor((i / (maxAreaPoints - 1)) * (normalizedRows.length - 1));
            return normalizedRows[idx];
          });

      const pts = areaPoints.map((r, i) => {
        const x = padding.left + (i / Math.max(areaPoints.length - 1, 1)) * chartW;
        const val = Number(r[metricKey]) || 0;
        const y = padding.top + chartH - ((val - minVal) / range) * chartH;
        return { x, y, val, label: String(r[dimKey] ?? '') };
      });

      const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
      const areaPath = `${linePath} L ${pts[pts.length - 1].x.toFixed(1)} ${(padding.top + chartH).toFixed(1)} L ${pts[0].x.toFixed(1)} ${(padding.top + chartH).toFixed(1)} Z`;

      const stepInterval = Math.max(Math.ceil(pts.length / 6), 1);
      const xLabels = pts
        .filter((_, idx) => idx % stepInterval === 0 || idx === pts.length - 1)
        .map((p) => `
          <text x="${p.x.toFixed(1)}" y="${(padding.top + chartH + 18).toFixed(1)}" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="sans-serif">${escapeHtml(p.label.slice(0, 12))}</text>
        `);

      const dots = pts.length <= 30
        ? pts.map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="${colors[0]}" stroke="var(--surface)" stroke-width="1.5" />`).join('')
        : '';

      return `
        <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: 240px; display: block;" xmlns="http://www.w3.org/2000/svg">
          ${gridLines.join('')}
          ${yLabels.join('')}
          <path d="${areaPath}" fill="${colors[0]}" fill-opacity="0.15" />
          <path d="${linePath}" fill="none" stroke="${colors[0]}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          ${dots}
          ${xLabels.join('')}
        </svg>
      `;
    }

    // 5. Horizontal Bar Chart
    if (cType === 'horizontal_bar') {
      const displayRows = normalizedRows.length > 50 ? normalizedRows.slice(0, 50) : normalizedRows;
      const barMinVal = Math.min(minVal, 0);
      const barMaxVal = Math.max(maxVal, 0);
      const barRange = (barMaxVal - barMinVal) || 1;

      const maxLabelLen = Math.max(...displayRows.map((r) => String(r[dimKey] ?? '').length), 0);
      const leftPad = Math.min(Math.max(maxLabelLen * 7 + 12, 85), 150);
      const hChartW = width - leftPad - padding.right;
      const barCount = displayRows.length;
      const barSlotH = chartH / Math.max(barCount, 1);
      const barH = Math.max(Math.min(barSlotH * 0.65, 28), 5);

      const bars: string[] = [];
      const yAxisLabels: string[] = [];
      const xGrid: string[] = [];

      for (let i = 0; i <= steps; i++) {
        const xVal = barMinVal + (barRange / steps) * i;
        const xPos = leftPad + (i / steps) * hChartW;
        xGrid.push(`<line x1="${xPos.toFixed(1)}" y1="${padding.top}" x2="${xPos.toFixed(1)}" y2="${height - padding.bottom}" stroke="var(--border)" stroke-dasharray="3 3" opacity="0.6" />`);
        xGrid.push(`<text x="${xPos.toFixed(1)}" y="${height - padding.bottom + 15}" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="monospace">${formatTick(xVal)}</text>`);
      }

      // Zero baseline position on X-axis
      const zeroX = leftPad + ((0 - barMinVal) / barRange) * hChartW;
      if (barMinVal < 0 && barMaxVal > 0) {
        xGrid.push(`<line x1="${zeroX.toFixed(1)}" y1="${padding.top}" x2="${zeroX.toFixed(1)}" y2="${height - padding.bottom}" stroke="var(--foreground)" stroke-width="1.5" opacity="0.4" />`);
      }

      displayRows.forEach((row, i) => {
        const val = Number(row[metricKey]) || 0;
        let barX = zeroX;
        let barLen = 0;
        if (val >= 0) {
          barX = zeroX;
          barLen = Math.max(((val - 0) / barRange) * hChartW, val === 0 ? 0 : 2);
        } else {
          barLen = Math.max(((0 - val) / barRange) * hChartW, 2);
          barX = zeroX - barLen;
        }
        const y = padding.top + i * barSlotH + (barSlotH - barH) / 2;
        const label = String(row[dimKey] ?? `Item ${i + 1}`);
        const color = colors[i % colors.length];

        bars.push(`<rect x="${barX.toFixed(1)}" y="${y.toFixed(1)}" width="${barLen.toFixed(1)}" height="${barH.toFixed(1)}" rx="3" fill="${color}" />`);
        yAxisLabels.push(`<text x="${(leftPad - 8).toFixed(1)}" y="${(y + barH / 2 + 3).toFixed(1)}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="sans-serif">${escapeHtml(label.slice(0, 18))}</text>`);
      });

      return `
        <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: 240px; display: block;" xmlns="http://www.w3.org/2000/svg">
          ${xGrid.join('')}
          ${bars.join('')}
          ${yAxisLabels.join('')}
        </svg>
      `;
    }

    // 6. Default: Vertical Bar / Histogram / Stacked Bar
    const displayRows = normalizedRows.length > 50 ? normalizedRows.slice(0, 50) : normalizedRows;
    const barMinVal = Math.min(minVal, 0);
    const barMaxVal = Math.max(maxVal, 0);
    const barRange = (barMaxVal - barMinVal) || 1;

    const barGridLines: string[] = [];
    const barYLabels: string[] = [];
    for (let i = 0; i <= steps; i++) {
      const yVal = barMinVal + (barRange / steps) * i;
      const yPos = padding.top + chartH - (i / steps) * chartH;
      barGridLines.push(`<line x1="${padding.left}" y1="${yPos.toFixed(1)}" x2="${(width - padding.right).toFixed(1)}" y2="${yPos.toFixed(1)}" stroke="var(--border)" stroke-dasharray="3 3" opacity="0.6" />`);
      barYLabels.push(`<text x="${(padding.left - 8).toFixed(1)}" y="${(yPos + 4).toFixed(1)}" text-anchor="end" fill="var(--muted)" font-size="10" font-family="monospace">${formatTick(yVal)}</text>`);
    }

    const barCount = displayRows.length;
    const barSlotW = chartW / Math.max(barCount, 1);
    const barW = Math.max(Math.min(barSlotW * 0.65, 36), 5);

    const bars: string[] = [];
    const xLabels: string[] = [];

    // Zero baseline position on Y-axis
    const zeroY = padding.top + chartH - ((0 - barMinVal) / barRange) * chartH;
    if (barMinVal < 0 && barMaxVal > 0) {
      barGridLines.push(`<line x1="${padding.left}" y1="${zeroY.toFixed(1)}" x2="${(width - padding.right).toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="var(--foreground)" stroke-width="1.5" opacity="0.4" />`);
    }

    displayRows.forEach((row, i) => {
      const val = Number(row[metricKey]) || 0;
      let barY = zeroY;
      let barH = 0;
      if (val >= 0) {
        barH = Math.max(((val - 0) / barRange) * chartH, val === 0 ? 0 : 2);
        barY = zeroY - barH;
      } else {
        barH = Math.max(((0 - val) / barRange) * chartH, 2);
        barY = zeroY;
      }
      const x = padding.left + i * barSlotW + (barSlotW - barW) / 2;
      const label = String(row[dimKey] ?? `Item ${i + 1}`);
      const color = colors[i % colors.length];

      bars.push(`<rect x="${x.toFixed(1)}" y="${barY.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="3" fill="${color}" />`);

      if (barCount <= 12 || i % Math.ceil(barCount / 10) === 0 || i === barCount - 1) {
        xLabels.push(
          `<text x="${(x + barW / 2).toFixed(1)}" y="${(padding.top + chartH + 18).toFixed(1)}" text-anchor="middle" fill="var(--muted)" font-size="10" font-family="sans-serif">${escapeHtml(label.slice(0, 12))}</text>`
        );
      }
    });

    return `
      <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: 240px; display: block;" xmlns="http://www.w3.org/2000/svg">
        ${barGridLines.join('')}
        ${barYLabels.join('')}
        ${bars.join('')}
        ${xLabels.join('')}
      </svg>
    `;
  };

  // Helper to extract SVG visual representation for exported tile
  const getTileChartVisualHtml = (tile: DashboardTileUI, dataRows: Record<string, any>[]): string => {
    const preferredDims = tile.dimensions?.length ? tile.dimensions : (tile.x_key ? [tile.x_key] : []);
    const preferredMetrics = tile.metrics?.length ? tile.metrics : (tile.y_keys?.length ? tile.y_keys : []);
    return renderDynamicTileSvg(tile.chart_type, dataRows, preferredDims, preferredMetrics);
  };

  // Helper to render formatted HTML data table
  const renderDataTableHtml = (rows: Record<string, any>[], maxRows = 50): string => {
    if (!rows || rows.length === 0) {
      return `<div style="padding: 16px; text-align: center; color: var(--muted); font-size: 12px;">No records available</div>`;
    }
    const keys = Object.keys(rows[0] || {});
    const displayRows = rows.slice(0, maxRows);
    return `
      <div style="overflow-x: auto; max-height: 280px; border: 1px solid var(--border); border-radius: 6px;">
        <table style="width: 100%; border-collapse: collapse; font-size: 11px; font-family: monospace;">
          <thead>
            <tr style="background: var(--surface-muted); border-bottom: 1px solid var(--border); color: var(--muted); text-transform: uppercase; font-size: 10px;">
              ${keys.map((k) => `<th style="padding: 6px 10px; text-align: left; font-weight: 600; white-space: nowrap;">${escapeHtml(k)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${displayRows
              .map(
                (r, idx) => `
              <tr style="border-bottom: 1px solid var(--border); ${idx % 2 === 1 ? 'background: var(--surface-muted);' : ''}">
                ${keys.map((k) => `<td style="padding: 5px 10px; white-space: nowrap; color: var(--foreground);">${escapeHtml(String(r[k] ?? '—'))}</td>`).join('')}
              </tr>
            `
              )
              .join('')}
          </tbody>
        </table>
      </div>
      ${rows.length > maxRows ? `<div style="font-size: 10px; color: var(--muted); margin-top: 4px; text-align: right;">Showing top ${maxRows} of ${rows.length} rows</div>` : ''}
    `;
  };

  // Export standalone self-contained HTML bundle
  const handleExportHtml = () => {
    const dashboardTitle = `${datasetName} - DashCrate Executive BI Dashboard`;
    const exportTime = new Date().toLocaleString();

    // Active filters summary chip list
    const activeFiltersHtml =
      activeFilters && activeFilters.length > 0
        ? `
        <div style="margin-top: 12px; padding: 10px 14px; background: var(--primary-soft); border: 1px solid var(--primary); border-radius: 8px; font-size: 11px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <strong style="color: var(--primary);">Active Dashboard Filters (${activeFilters.length}):</strong>
          ${activeFilters
            .map(
              (f) => `
            <span style="background: var(--surface); border: 1px solid var(--border); padding: 3px 8px; border-radius: 4px; font-family: monospace; font-size: 11px; color: var(--foreground);">
              <strong>${escapeHtml(f.column)}</strong> ${escapeHtml(f.operator)} <em>${escapeHtml(Array.isArray(f.values) ? f.values.join(', ') : String(f.values))}</em>
            </span>
          `
            )
            .join('')}
        </div>
      `
        : `
        <div style="margin-top: 10px; font-size: 11px; color: var(--muted);">
          Filter State: <span style="font-weight: 600; color: var(--foreground);">All Records (Unfiltered Baseline)</span>
        </div>
      `;

    const tilesHtml = activeTiles
      .map((t) => {
        const override = tileOverrides[t.id];
        const dataRows = override?.data !== undefined ? override.data : t.data || [];
        const effectiveSql = override?.compiled_sql || t.compiled_sql || t.plan?.compiled_sql || '';
        const isKpi = t.chart_type === 'kpi';
        const isTable = t.chart_type === 'table';

        // KPI value computation
        const preferredDims = t.dimensions?.length ? t.dimensions : (t.x_key ? [t.x_key] : []);
        const preferredMetrics = t.metrics?.length ? t.metrics : (t.y_keys?.length ? t.y_keys : []);
        const { metricKey: kpiMetricKey } = resolveChartKeys(dataRows, preferredDims, preferredMetrics);
        const rawKpiVal =
          dataRows[0]?.[kpiMetricKey] !== undefined
            ? dataRows[0][kpiMetricKey]
            : dataRows[0] && Object.values(dataRows[0])[0] !== undefined
            ? Object.values(dataRows[0])[0]
            : '—';
        const kpiValFormatted =
          typeof rawKpiVal === 'number'
            ? Number.isInteger(rawKpiVal)
              ? rawKpiVal.toLocaleString()
              : rawKpiVal.toFixed(2)
            : String(rawKpiVal);

        const colSpanClass =
          t.chart_type === 'kpi'
            ? 'col-span-3'
            : t.size.w === 8
            ? 'col-span-8'
            : t.size.w === 4
            ? 'col-span-4'
            : t.size.w === 6
            ? 'col-span-6'
            : 'col-span-4';

        let bodyContent = '';

        if (isKpi) {
          bodyContent = `
            <div style="padding: 16px 0; text-align: left;">
              <div class="kpi-value">${kpiValFormatted}</div>
              ${
                t.delta
                  ? `<div style="font-size: 11px; color: ${
                      t.delta.direction === 'up'
                        ? 'var(--success)'
                        : t.delta.direction === 'down'
                        ? 'var(--error)'
                        : 'var(--muted)'
                    }; font-weight: 600;">
                    ${t.delta.direction === 'up' ? '▲' : t.delta.direction === 'down' ? '▼' : '●'} ${escapeHtml(t.delta.label || '')} ${t.delta.percentage !== undefined ? `${t.delta.percentage}%` : ''}
                  </div>`
                  : ''
              }
            </div>
          `;
        } else if (isTable) {
          bodyContent = `
            <div style="margin: 10px 0;">
              ${renderDataTableHtml(dataRows, 50)}
            </div>
          `;
        } else {
          // Visual Chart (Bar, Line, Area, Donut, Pie, Scatter, etc.)
          const chartVisualSvg = getTileChartVisualHtml(t, dataRows);
          bodyContent = `
            <div style="margin: 8px 0;">
              ${chartVisualSvg}
              <details style="margin-top: 10px; font-size: 11px; border-top: 1px dashed var(--border); padding-top: 8px;">
                <summary style="cursor: pointer; color: var(--muted); font-weight: 600;">View Underlying Data Table (${dataRows.length} rows)</summary>
                <div style="margin-top: 8px;">
                  ${renderDataTableHtml(dataRows, 25)}
                </div>
              </details>
            </div>
          `;
        }

        const isEdited = Boolean(t.metadata?.is_edited);

        return `
          <div class="tile-card ${colSpanClass}">
            <div>
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="tile-badge">${escapeHtml(t.chart_type)}</span>
                  ${isEdited ? `<span class="tile-badge badge-edited">EDITED</span>` : ''}
                </div>
                <span style="font-size: 10px; font-family: monospace; color: var(--muted);">${escapeHtml(t.generator)}</span>
              </div>
              <div class="tile-title">${escapeHtml(t.title)}</div>
            </div>

            <div style="flex: 1;">
              ${bodyContent}
            </div>

            <div style="margin-top: 14px; padding-top: 10px; border-top: 1px solid var(--border);">
              <div style="font-size: 10px; color: var(--muted); display: flex; justify-content: space-between; font-family: monospace; margin-bottom: 4px;">
                <span>Strength: ${(t.evidence?.strength ?? 0.8).toFixed(2)}</span>
                <span>Robustness: ${((t.evidence?.robustness ?? 0.85) * 100).toFixed(0)}%</span>
                <span style="color: ${t.evidence?.fdr_passed ? 'var(--success)' : 'var(--error)'}; font-weight: bold;">FDR: ${t.evidence?.fdr_passed ? 'PASS' : 'FAIL'}</span>
                <span>n=${dataRows.length}</span>
              </div>
              ${
                effectiveSql
                  ? `
                <details style="margin-top: 6px; font-size: 10px; color: var(--muted);">
                  <summary style="cursor: pointer; font-family: monospace; color: var(--muted);">Compiled SQL Query</summary>
                  <pre style="background: var(--surface-muted); padding: 8px; border-radius: 6px; font-size: 10px; overflow-x: auto; margin-top: 4px; border: 1px solid var(--border); color: var(--foreground); line-height: 1.4;"><code>${escapeHtml(effectiveSql)}</code></pre>
                </details>
              `
                  : ''
              }
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
  <title>${escapeHtml(dashboardTitle)}</title>
  <style>
    :root {
      --bg: ${THEME_TOKENS.background};
      --surface: ${THEME_TOKENS.surface};
      --surface-muted: #F0F2F5;
      --border: ${THEME_TOKENS.border};
      --foreground: ${THEME_TOKENS.text};
      --muted: ${THEME_TOKENS.mutedText};
      --primary: ${THEME_TOKENS.primary};
      --primary-hover: ${THEME_TOKENS.primaryHover};
      --primary-soft: ${THEME_TOKENS.primarySoft};
      --attention: ${THEME_TOKENS.attention};
      --attention-soft: ${THEME_TOKENS.attentionSoft};
      --error: ${THEME_TOKENS.error};
      --success: ${THEME_TOKENS.success};
      --chart-1: ${THEME_TOKENS.chartSeries[0]};
      --chart-2: ${THEME_TOKENS.chartSeries[1]};
      --chart-3: ${THEME_TOKENS.chartSeries[2]};
      --chart-4: ${THEME_TOKENS.chartSeries[3]};
      --chart-5: ${THEME_TOKENS.chartSeries[4]};
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #0D1117;
        --surface: #161B22;
        --surface-muted: #21262D;
        --border: #30363D;
        --foreground: #C9D1D9;
        --muted: #8B949E;
        --primary: #58A6FF;
        --primary-hover: #79B8FF;
        --primary-soft: #1F2937;
        --attention: #D29922;
        --attention-soft: #382805;
        --error: #F85149;
        --success: #3FB950;
        --chart-1: #58A6FF;
        --chart-2: #3FB950;
        --chart-3: #D29922;
        --chart-4: #F85149;
        --chart-5: #A371F7;
      }
    }
    * {
      box-sizing: border-box;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--foreground);
      margin: 0;
      padding: 24px;
      line-height: 1.5;
    }
    .header {
      padding: 20px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--surface);
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 16px;
    }
    .col-span-3 { grid-column: span 3; }
    .col-span-4 { grid-column: span 4; }
    .col-span-6 { grid-column: span 6; }
    .col-span-8 { grid-column: span 8; }
    .col-span-12 { grid-column: span 12; }
    
    @media (max-width: 1024px) {
      .col-span-3, .col-span-4, .col-span-6, .col-span-8 { grid-column: span 6; }
    }
    @media (max-width: 640px) {
      .grid { grid-template-columns: 1fr; }
      .col-span-3, .col-span-4, .col-span-6, .col-span-8, .col-span-12 { grid-column: span 1; }
    }
    .tile-card {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 18px;
      background: var(--surface);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    .tile-badge {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--muted);
      background: var(--surface-muted);
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
      font-family: monospace;
    }
    .badge-edited {
      color: var(--primary);
      background: var(--primary-soft);
      border-color: var(--primary);
    }
    .tile-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--foreground);
      margin: 8px 0 12px 0;
      line-height: 1.35;
    }
    .kpi-value {
      font-size: 32px;
      font-weight: 800;
      font-family: monospace;
      color: var(--primary);
      margin: 12px 0;
    }
    .recharts-surface text {
      fill: var(--foreground);
      font-family: -apple-system, sans-serif;
    }
    .recharts-cartesian-axis-tick-value {
      fill: var(--muted) !important;
      font-size: 10px !important;
    }
    .recharts-cartesian-axis line, .recharts-cartesian-axis path {
      stroke: var(--border) !important;
    }
    .recharts-cartesian-grid line {
      stroke: var(--border) !important;
      stroke-opacity: 0.6;
    }
    .recharts-legend-item-text {
      color: var(--foreground) !important;
      font-size: 11px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
      font-family: monospace;
    }
    th, td {
      padding: 5px 8px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      background: var(--surface-muted);
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 10px;
    }
    details summary {
      cursor: pointer;
      user-select: none;
    }
    @media print {
      body { background: white; color: black; padding: 0; }
      .tile-card { break-inside: avoid; box-shadow: none; border-color: #ddd; }
      .header { box-shadow: none; border-color: #ddd; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div style="font-size: 11px; text-transform: uppercase; color: var(--muted); font-family: monospace; letter-spacing: 0.5px;">DashCrate Executive BI Dashboard</div>
    <h1 style="margin: 6px 0 10px 0; font-size: 22px; font-weight: 800; color: var(--foreground);">${escapeHtml(headlineText)}</h1>
    <div style="font-size: 12px; color: var(--muted); display: flex; gap: 16px; flex-wrap: wrap;">
      <span>Dataset: <strong style="color: var(--foreground);">${escapeHtml(datasetName)}</strong></span>
      <span>Rows: <strong style="color: var(--foreground);">${rowCount}</strong></span>
      <span>Exported: <strong style="color: var(--foreground);">${escapeHtml(exportTime)}</strong></span>
    </div>
    ${activeFiltersHtml}
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

  if ((!activeTiles || activeTiles.length === 0) && !isDirty) {
    return null;
  }

  return (
    <div className={`flex flex-col gap-5 ${className}`}>
      {/* Header bar / Executive Dashboard Tab */}
      <div className="flex items-center justify-between border-b border-border text-xs font-medium no-print">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-3.5 py-2 border-b-2 border-primary text-primary font-bold">
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Executive Dashboard</span>
          </div>
        </div>

        {/* Global Export & Print buttons */}
        <div className="flex items-center gap-2 pb-1">
          {isDirty && (
            <button
              onClick={handleResetDashboard}
              className="flex items-center gap-1 px-2.5 py-1 text-2xs font-mono font-semibold rounded bg-surface border border-attention/40 text-attention hover:bg-attention-soft transition-colors"
              title="Reset dashboard to original AI-generated configuration"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset Dashboard</span>
            </button>
          )}
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

      {/* EXECUTIVE DASHBOARD */}
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
                  {activeTiles.length} insights shown
                </span>
                {rejectedInsights.length > 0 && (
                  <span className="px-2 py-0.5 rounded text-2xs font-mono font-medium bg-surface-muted text-muted-foreground border border-border">
                    {rejectedInsights.length} rejected
                  </span>
                )}
                {cleaningCount > 0 && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono bg-success-soft text-success border border-success/30">
                    <Brush className="w-3 h-3" />
                    <span>{cleaningCount} cleaning rules applied</span>
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
                            id={`slicer-start-${sl.id}`}
                            type="date"
                            defaultValue={sl.min_date}
                            onChange={(e) => {
                              const end = (document.getElementById(`slicer-end-${sl.id}`) as HTMLInputElement)?.value || sl.max_date || e.target.value;
                              handleSlicerChange(sl.column, 'BETWEEN', [e.target.value, end]);
                            }}
                            className="w-full text-2xs font-mono p-1 rounded bg-surface border border-border text-foreground"
                          />
                          <span className="text-muted-foreground text-xs">–</span>
                          <input
                            id={`slicer-end-${sl.id}`}
                            type="date"
                            defaultValue={sl.max_date}
                            onChange={(e) => {
                              const start = (document.getElementById(`slicer-start-${sl.id}`) as HTMLInputElement)?.value || sl.min_date || e.target.value;
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
                  {activeFilters.map((f, fIdx) => {
                    const displayVal =
                      f.operator === 'BETWEEN' && Array.isArray(f.values) && f.values.length >= 2
                        ? `${f.values[0]} to ${f.values[1]}`
                        : Array.isArray(f.values)
                        ? f.values.join(', ')
                        : String(f.values);
                    const opSymbol = f.operator === 'BETWEEN' ? 'between' : f.operator;
                    return (
                      <span
                        key={fIdx}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-mono bg-primary-soft text-primary border border-primary/30"
                      >
                        <span>
                          {f.column} {opSymbol} {displayVal}
                        </span>
                        <button
                          onClick={() => handleRemoveFilter(f.column)}
                          className="hover:text-error transition-colors ml-0.5"
                          title={`Remove filter on ${f.column}`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}


          {/* F1: 12-Column Responsive Grid of Tiles */}
          {activeTiles.length === 0 ? (
            <div className="py-12 px-4 text-center space-y-3 bg-surface-muted/20 rounded-card border border-dashed border-border">
              <div className="w-10 h-10 rounded-full bg-surface-muted text-muted-foreground flex items-center justify-center mx-auto">
                <Sparkles className="w-5 h-5" />
              </div>
              <p className="text-xs font-semibold text-foreground">All dashboard charts have been removed</p>
              <p className="text-2xs text-muted-foreground max-w-sm mx-auto">
                You can restore the original AI-generated charts at any time.
              </p>
              <button
                onClick={handleResetDashboard}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded bg-primary text-primary-foreground hover:bg-primary-hover transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset to Original Dashboard</span>
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-6 xl:grid-cols-12 gap-4 dashboard-container">
              {activeTiles.map((tile) => {
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
                          {tile.metadata?.is_edited && (
                            <span
                              className="text-3xs font-mono uppercase px-1.5 py-0.5 rounded bg-primary-soft text-primary border border-primary/30 font-semibold"
                              title="Chart modified from original"
                            >
                              Edited
                            </span>
                          )}
                          {tile.candidate_id && (
                            <span className="text-3xs font-mono text-muted-foreground">
                              #{tile.candidate_id.slice(0, 6)}
                            </span>
                          )}
                        </div>

                        {/* Tile Actions Menu */}
                        <div className="flex items-center gap-1 tile-menu-button no-print">
                          <button
                            onClick={() => setEditingTile(tile)}
                            className="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary-soft transition-colors"
                            title="Edit chart configuration"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          {tile.metadata?.is_edited && (
                            <button
                              onClick={() => handleResetTile(tile.id)}
                              className="p-1 rounded text-muted-foreground hover:text-attention hover:bg-attention-soft transition-colors"
                              title="Reset chart to original AI-generated configuration"
                            >
                              <RotateCcw className="w-3.5 h-3.5" />
                            </button>
                          )}
                          <button
                            onClick={() => handleRemoveTile(tile.id)}
                            className="p-1 rounded text-muted-foreground hover:text-error hover:bg-error-soft transition-colors"
                            title="Remove chart from dashboard"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
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
          )}

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

      {/* MODALS: View SQL, View Data, Why Chosen, Expand */}
      {activeModal.type && activeModal.tile && (() => {
        const modalTile = activeModal.tile;
        const effectiveModalData =
          tileOverrides[modalTile.id]?.data !== undefined
            ? tileOverrides[modalTile.id].data
            : modalTile.data;
        const effectiveModalSql =
          tileOverrides[modalTile.id]?.compiled_sql ||
          modalTile.compiled_sql ||
          modalTile.plan?.compiled_sql ||
          '-- Re-compiled dynamically through DuckDB sandboxed compiler\nSELECT * FROM dataset';

        console.log(`[SQL_DEBUG] Modal rendering: type=${activeModal.type}`, {
          modalTileId: modalTile?.id,
          overrideIds: Object.keys(tileOverrides),
          override: modalTile ? tileOverrides[modalTile.id] : undefined,
          modalTileCompiledSql: modalTile?.compiled_sql,
          overrideCompiledSql: modalTile ? tileOverrides[modalTile.id]?.compiled_sql : undefined,
          effectiveModalSql,
          activeFilters,
        });

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
                      <code>{effectiveModalSql}</code>
                    </pre>
                  </div>
                )}

                {activeModal.type === 'data' && (
                  <div>
                    {effectiveModalData && effectiveModalData.length > 0 ? (
                      <div className="overflow-x-auto max-h-96">
                        <table className="w-full text-left text-xs font-mono border-collapse">
                          <thead>
                            <tr className="border-b border-border bg-surface-muted text-2xs uppercase text-muted-foreground">
                              {Object.keys(effectiveModalData[0] || {}).map((k) => (
                                <th key={k} className="py-2 px-3 font-semibold whitespace-nowrap">
                                  {k}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border text-foreground">
                            {effectiveModalData.map((r, rIdx) => (
                              <tr key={rIdx} className="hover:bg-surface-muted/20">
                                {Object.keys(effectiveModalData[0] || {}).map((k) => (
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
                          n={effectiveModalData ? effectiveModalData.length : (modalTile.evidence?.n ?? 0)}
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
                      executionData={effectiveModalData}
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

      {editingTile && (
        <ChartEditModal
          isOpen={true}
          tile={editingTile}
          specId={spec?.spec_id || ''}
          datasetId={datasetId || spec?.dataset_id || ''}
          onClose={() => setEditingTile(null)}
          onSave={handleTileSaved}
        />
      )}
    </div>
  );
};
