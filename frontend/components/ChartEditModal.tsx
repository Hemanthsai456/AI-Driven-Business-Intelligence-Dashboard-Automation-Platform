'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  X,
  Check,
  Play,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Sparkles,
  BarChart2,
  Code,
  Table as TableIcon,
} from 'lucide-react';
import { DashboardTileUI, DatasetMetadata } from '../lib/types';
import { getDatasetMetadata, runPlan, updateDashboardTile } from '../lib/api';
import { InsightChart } from './InsightChart';

export interface ChartEditModalProps {
  isOpen: boolean;
  tile: DashboardTileUI | null;
  specId: string;
  datasetId: string;
  onClose: () => void;
  onSave: (updatedTile: DashboardTileUI) => void;
}

const SUPPORTED_CHART_TYPES = [
  { value: 'bar', label: 'Bar Chart (Vertical)' },
  { value: 'horizontal_bar', label: 'Horizontal Bar' },
  { value: 'line', label: 'Line Chart' },
  { value: 'scatter', label: 'Scatter Plot' },
  { value: 'donut', label: 'Donut / Pie' },
  { value: 'kpi', label: 'KPI Metric Card' },
  { value: 'table', label: 'Data Table' },
];

const SUPPORTED_AGGREGATIONS = [
  { value: 'none', label: 'None (Raw Observations)' },
  { value: 'sum', label: 'SUM' },
  { value: 'avg', label: 'AVG (Mean)' },
  { value: 'count', label: 'COUNT' },
  { value: 'count_distinct', label: 'COUNT DISTINCT' },
  { value: 'min', label: 'MIN' },
  { value: 'max', label: 'MAX' },
  { value: 'median', label: 'MEDIAN' },
  { value: 'stddev', label: 'STDDEV' },
];

const TEMPORAL_GRANULARITIES = [
  { value: '', label: 'Default (No truncation)' },
  { value: 'day', label: 'Day' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];

export const ChartEditModal: React.FC<ChartEditModalProps> = ({
  isOpen,
  tile,
  specId,
  datasetId,
  onClose,
  onSave,
}) => {
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [isLoadingMeta, setIsLoadingMeta] = useState<boolean>(false);

  // Form Fields
  const [title, setTitle] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [chartType, setChartType] = useState<string>('bar');
  const [dimensionCol, setDimensionCol] = useState<string>('');
  const [granularity, setGranularity] = useState<string>('');
  const [metricCol, setMetricCol] = useState<string>('');
  const [aggregation, setAggregation] = useState<string>('sum');

  // Preview State
  const [isPreviewLoading, setIsPreviewLoading] = useState<boolean>(false);
  const [previewRows, setPreviewRows] = useState<Record<string, any>[] | null>(null);
  const [previewSql, setPreviewSql] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isApplying, setIsApplying] = useState<boolean>(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  // Load dataset metadata when modal opens
  useEffect(() => {
    if (isOpen && datasetId) {
      setIsLoadingMeta(true);
      getDatasetMetadata(datasetId)
        .then((meta) => {
          setMetadata(meta);
        })
        .catch((err) => {
          console.error('Failed to load dataset metadata for editor:', err);
        })
        .finally(() => {
          setIsLoadingMeta(false);
        });
    }
  }, [isOpen, datasetId]);

  // Initialize form state from tile
  useEffect(() => {
    if (tile) {
      setTitle(tile.title || '');
      setDescription(tile.why_chosen || '');
      setChartType(tile.chart_type || 'bar');

      // Initialize dimension
      const dim = tile.dimensions?.[0] || tile.x_key || '';
      setDimensionCol(dim);

      const existingGran = tile.plan?.dimensions?.[0]?.granularity;
      setGranularity(existingGran || '');

      // Initialize metric and aggregation
      let mCol = '';
      if (tile.metrics?.[0]) {
        mCol = tile.metrics[0].replace(/^[a-z_]+\((.+)\)$/i, '$1');
      } else if (tile.plan?.metric?.column) {
        mCol = tile.plan.metric.column;
      }
      if (mCol === dim && tile.y_keys?.[0] && tile.y_keys[0] !== dim) {
        mCol = tile.y_keys[0];
      }
      setMetricCol(mCol);

      const planAgg = tile.plan?.metric?.aggregation;
      if (!planAgg || String(planAgg).toLowerCase() === 'none') {
        if (tile.chart_type === 'scatter') {
          setAggregation('none');
        } else {
          setAggregation('sum');
        }
      } else {
        setAggregation(String(planAgg).toLowerCase());
      }

      // Reset preview state
      setPreviewRows(null);
      setPreviewSql(null);
      setValidationErrors([]);
      setApplyError(null);
    }
  }, [tile]);

  // Identify column roles and types from metadata schema + tile seeds
  const { dimensionColumns, metricColumns, scatterDimensionColumns, isDimensionTemporal } = useMemo(() => {
    const allColsSet = new Set<string>();
    const dimsSet = new Set<string>();
    const metricsSet = new Set<string>();
    let isTemporal = false;

    // Seed from tile so controls are immediately populated and consistent
    if (tile) {
      if (tile.dimensions) {
        tile.dimensions.forEach((d) => {
          allColsSet.add(d);
          dimsSet.add(d);
        });
      }
      if (tile.x_key) {
        allColsSet.add(tile.x_key);
        dimsSet.add(tile.x_key);
      }
      if (tile.metrics) {
        tile.metrics.forEach((m) => {
          const cleanM = m.replace(/^[a-z_]+\((.+)\)$/i, '$1');
          if (cleanM && cleanM !== '*') {
            allColsSet.add(cleanM);
            metricsSet.add(cleanM);
          }
        });
      }
      if (tile.y_keys) {
        tile.y_keys.forEach((y) => {
          const cleanY = y.replace(/^[a-z_]+\((.+)\)$/i, '$1');
          if (cleanY && cleanY !== '*') {
            allColsSet.add(cleanY);
            metricsSet.add(cleanY);
          }
        });
      }
      if (tile.plan?.metric?.column && tile.plan.metric.column !== '*') {
        allColsSet.add(tile.plan.metric.column);
        metricsSet.add(tile.plan.metric.column);
      }
      if (tile.data && tile.data.length > 0) {
        Object.keys(tile.data[0]).forEach((k) => {
          if (!k.includes('(') && !k.startsWith('sum_') && !k.startsWith('avg_')) {
            allColsSet.add(k);
          }
        });
      }
    }

    if (metadata?.columns && Array.isArray(metadata.columns)) {
      metadata.columns.forEach((col: any) => {
        const colName = col.original_name || col.column_name || col.name;
        if (!colName) return;

        allColsSet.add(colName);
        const role = String(col.semantic_role || '').toUpperCase();
        const dt = String(col.detected_datatype || '').toLowerCase();
        const isNumeric =
          dt.includes('int') ||
          dt.includes('float') ||
          dt.includes('double') ||
          dt.includes('numeric') ||
          dt.includes('real') ||
          dt.includes('decimal') ||
          dt.includes('number');
        const isDate = dt.includes('date') || dt.includes('time') || role === 'DATETIME';

        if (isNumeric || role === 'MEASURE') {
          metricsSet.add(colName);
        }
        dimsSet.add(colName);

        if (colName === dimensionCol && isDate) {
          isTemporal = true;
        }
      });
    } else if (metadata?.dtypes) {
      Object.entries(metadata.dtypes).forEach(([colName, dtStr]) => {
        allColsSet.add(colName);
        const dt = String(dtStr).toLowerCase();
        const isNumeric =
          dt.includes('int') ||
          dt.includes('float') ||
          dt.includes('double') ||
          dt.includes('numeric') ||
          dt.includes('real') ||
          dt.includes('decimal') ||
          dt.includes('number');
        const isDate = dt.includes('date') || dt.includes('time');

        if (isNumeric) metricsSet.add(colName);
        dimsSet.add(colName);
        if (colName === dimensionCol && isDate) isTemporal = true;
      });
    }

    const dimsArray = Array.from(dimsSet);
    const metricsArray = Array.from(metricsSet);
    const scatterDims = metricsArray.length > 0 ? metricsArray : dimsArray;

    return {
      dimensionColumns: dimsArray,
      metricColumns: metricsArray.length > 0 ? metricsArray : dimsArray,
      scatterDimensionColumns: scatterDims,
      isDimensionTemporal: isTemporal,
    };
  }, [metadata, tile, dimensionCol]);

  // Aggregations available based on chart type
  const availableAggregations = useMemo(() => {
    const isScatter = chartType.toLowerCase() === 'scatter';
    const isLine = chartType.toLowerCase() === 'line';
    if (isScatter || isLine) {
      return SUPPORTED_AGGREGATIONS;
    }
    return SUPPORTED_AGGREGATIONS.filter((a) => a.value !== 'none');
  }, [chartType]);

  // Handle switching chart types
  const handleChartTypeChange = (newType: string) => {
    setChartType(newType);
    const lowType = newType.toLowerCase();
    if (lowType === 'kpi') {
      setDimensionCol('');
      if (aggregation === 'none') setAggregation('sum');
    } else if (lowType === 'scatter') {
      // Scatter requires an X-axis column
      if (!dimensionCol) {
        const fallbackX = scatterDimensionColumns.find((c) => c !== metricCol) || scatterDimensionColumns[0] || '';
        setDimensionCol(fallbackX);
      }
    } else if (lowType !== 'line') {
      // Other charts (bar, donut) require aggregation
      if (aggregation === 'none') {
        setAggregation('sum');
      }
    }
  };

  if (!isOpen || !tile) return null;

  // Helper to format any validation issue or error object safely
  const formatIssue = (issue: any): string => {
    if (typeof issue === 'string') return issue;
    if (!issue) return 'Validation safeguard triggered.';
    if (typeof issue === 'object') {
      if (issue.message) return issue.message;
      if (issue.msg) return issue.msg;
      if (issue.check) return `${issue.check}: validation check failed`;
      try {
        return JSON.stringify(issue);
      } catch {
        return 'Structured validation error';
      }
    }
    return String(issue);
  };

  // Construct CandidatePlan conforming to backend Pydantic schema
  const buildCurrentPlan = () => {
    const isKpi = chartType.toLowerCase() === 'kpi';
    const isScatter = chartType.toLowerCase() === 'scatter';
    const isRaw = (isScatter || chartType.toLowerCase() === 'line') && aggregation === 'none';

    const activeMetricCol = metricCol || (metricColumns[0] || '*');

    // KPI cards cannot have grouping dimensions. For other charts, dimension is optional if user selected "None"
    const dims = isKpi || (!dimensionCol && !isScatter)
      ? []
      : [
          {
            column: dimensionCol || (scatterDimensionColumns[0] || activeMetricCol),
            granularity: isDimensionTemporal && granularity ? granularity.toUpperCase() : null,
          },
        ];

    // Map chartType to standard VisualizationType enum
    let visEnum = chartType.toUpperCase();
    if (visEnum === 'HORIZONTAL_BAR' || visEnum === 'STACKED_BAR') {
      visEnum = 'BAR';
    } else if (visEnum === 'DONUT') {
      visEnum = 'PIE';
    }

    // Preserve limit and sorting semantics from existing tile plan (e.g. ranking / Top-N queries)
    const existingPlan = tile.plan;
    const planLimit = existingPlan?.limit !== undefined && existingPlan?.limit !== null ? existingPlan.limit : undefined;
    const planOrderDir = existingPlan?.order_direction || (existingPlan?.limit ? 'DESC' : undefined);
    const planOrderBy = existingPlan?.order_by || (planOrderDir ? 'metric' : undefined);

    return {
      plan_id: tile.plan?.plan_id || `plan_${Date.now()}`,
      dataset_id: datasetId,
      intent: title.trim() || 'Custom Analytical View',
      metric: {
        column: activeMetricCol,
        aggregation: isRaw ? null : (aggregation || 'sum').toUpperCase(),
      },
      dimensions: dims,
      filters: tile.plan?.filters || [],
      order_by: planOrderBy,
      order_direction: planOrderDir,
      limit: planLimit,
      visualization: visEnum,
      generator: 'user_editor',
      reasoning: {
        interpretation: title.trim() || 'User edited dashboard chart',
        evidence: [description.trim() || 'Custom configuration applied via editor'],
      },
    };
  };

  // Preview Plan query against backend DuckDB
  const handlePreview = async () => {
    setIsPreviewLoading(true);
    setValidationErrors([]);
    setApplyError(null);

    const plan = buildCurrentPlan();

    try {
      const res = await runPlan(plan);

      // Check Pass 1a validation
      if (res.pass1a && !res.pass1a.passed) {
        const issues = (res.pass1a.issues || []).map(formatIssue);
        setValidationErrors(issues.length > 0 ? issues : ['Plan failed validation safeguards.']);
        setPreviewRows(null);
        setPreviewSql(null);
        return;
      }

      // Check DuckDB execution
      if (res.execution && res.execution.status === 'SUCCESS') {
        // Check Pass 1b post-execution validation
        if (res.pass1b && !res.pass1b.passed) {
          const bIssues = (res.pass1b.issues || []).map(formatIssue);
          setValidationErrors(bIssues.length > 0 ? bIssues : ['Plan failed post-execution validation.']);
          setPreviewRows(null);
          setPreviewSql(null);
          return;
        }

        setPreviewRows(res.execution.rows || []);
        setPreviewSql(res.execution.compiled_sql || null);
        setValidationErrors([]);
      } else {
        const execErr = res.execution?.error_message || 'DuckDB query execution failed.';
        setValidationErrors([execErr]);
        setPreviewRows(null);
        setPreviewSql(null);
      }
    } catch (err: any) {
      const msg = typeof err?.message === 'string' && err.message ? err.message : formatIssue(err);
      setValidationErrors([msg]);
      setPreviewRows(null);
      setPreviewSql(null);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  // Save / Apply Changes
  const handleApply = async () => {
    setIsApplying(true);
    setApplyError(null);
    setValidationErrors([]);

    const plan = buildCurrentPlan();

    try {
      const res = await updateDashboardTile(specId, tile.id, {
        title: title.trim() || tile.title,
        description: description.trim() || undefined,
        chart_type: chartType,
        plan,
      });

      if (res.status === 'SUCCESS' && res.tile) {
        onSave(res.tile);
        onClose();
      } else {
        setApplyError('Failed to apply chart edits to backend specification.');
      }
    } catch (err: any) {
      const msg = typeof err?.message === 'string' && err.message ? err.message : formatIssue(err);
      setApplyError(msg || 'Failed to update dashboard chart.');
    } finally {
      setIsApplying(false);
    }
  };

  // Display rows (preview if executed, else tile data)
  const displayData = previewRows !== null ? previewRows : tile.data;
  const displayMetricName =
    aggregation === 'none' ? metricCol || 'value' : `${aggregation.toUpperCase()}(${metricCol || 'value'})`;

  return (
    <div className="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-xs flex items-center justify-center p-3 sm:p-4">
      <div className="bg-surface border border-border rounded-card shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border bg-surface-muted/30">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              <BarChart2 className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xs sm:text-sm font-bold text-foreground">
                Edit Chart Configuration
              </h2>
              <p className="text-3xs text-muted-foreground">
                Update chart metrics, grouping dimensions, and visual type with DuckDB validation safeguards
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close chart editor"
            className="text-muted-foreground hover:text-foreground p-1 rounded-md transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Form Controls (7 cols) */}
          <div className="lg:col-span-7 space-y-4">
            {/* Title */}
            <div>
              <label className="block text-2xs font-semibold text-foreground mb-1">
                Chart Title
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Total Revenue by Product Category"
                className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-2xs font-semibold text-foreground mb-1">
                Analytical Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="e.g. Highlights top revenue drivers to assist inventory planning"
                className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
              />
            </div>

            {/* Visual Chart Type */}
            <div>
              <label className="block text-2xs font-semibold text-foreground mb-1">
                Visual Chart Type
              </label>
              <select
                value={chartType}
                onChange={(e) => handleChartTypeChange(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {SUPPORTED_CHART_TYPES.map((ct) => (
                  <option key={ct.value} value={ct.value}>
                    {ct.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Dimension Selection */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-foreground mb-1">
                  {chartType === 'scatter'
                    ? 'Horizontal Axis (X-Axis)'
                    : chartType === 'line'
                    ? 'Timeline / Dimension (X-Axis)'
                    : 'Dimension (Grouping Column)'}
                </label>
                {chartType === 'kpi' ? (
                  <div className="w-full text-2xs px-3 py-2 rounded-md bg-surface-muted/50 border border-border text-muted-foreground italic">
                    KPI cards summarize a single scalar value across all records
                  </div>
                ) : chartType === 'scatter' ? (
                  <select
                    value={dimensionCol}
                    onChange={(e) => setDimensionCol(e.target.value)}
                    disabled={isLoadingMeta}
                    className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    {scatterDimensionColumns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select
                    value={dimensionCol}
                    onChange={(e) => setDimensionCol(e.target.value)}
                    disabled={isLoadingMeta}
                    className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">
                      {chartType === 'line' ? 'None (Total Trend)' : 'None (Total Dataset Metric)'}
                    </option>
                    {dimensionColumns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Temporal Granularity (if temporal dimension) */}
              <div>
                <label className="block text-2xs font-semibold text-foreground mb-1">
                  Date Granularity
                </label>
                <select
                  value={granularity}
                  onChange={(e) => setGranularity(e.target.value)}
                  disabled={chartType === 'kpi' || chartType === 'scatter' || !isDimensionTemporal}
                  className={`w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500 ${
                    chartType === 'kpi' || chartType === 'scatter' || !isDimensionTemporal
                      ? 'opacity-50 cursor-not-allowed'
                      : ''
                  }`}
                >
                  {TEMPORAL_GRANULARITIES.map((g) => (
                    <option key={g.value} value={g.value}>
                      {g.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Metric & Aggregation Selection */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-2xs font-semibold text-foreground mb-1">
                  {chartType === 'scatter' ? 'Vertical Axis (Y-Axis)' : 'Metric Column'}
                </label>
                <select
                  value={metricCol}
                  onChange={(e) => {
                    const newCol = e.target.value;
                    setMetricCol(newCol);
                    if (newCol === '*' && aggregation !== 'count') {
                      setAggregation('count');
                    }
                  }}
                  disabled={isLoadingMeta}
                  className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  {chartType !== 'scatter' && <option value="*">* (Row Count)</option>}
                  {metricColumns.map((col) => (
                    <option key={col} value={col}>
                      {col}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-2xs font-semibold text-foreground mb-1">
                  Aggregation Function
                </label>
                <select
                  value={aggregation}
                  onChange={(e) => {
                    const newAgg = e.target.value;
                    setAggregation(newAgg);
                    if (newAgg !== 'count' && metricCol === '*') {
                      const fallback = metricColumns.find((c) => c !== '*') || metricColumns[0] || 'records';
                      setMetricCol(fallback);
                    }
                  }}
                  className="w-full text-xs px-3 py-2 rounded-md bg-surface border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500 uppercase font-mono text-2xs"
                >
                  {availableAggregations.map((agg) => (
                    <option key={agg.value} value={agg.value}>
                      {agg.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Validation Issues / Errors Banner */}
            {validationErrors.length > 0 && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-md text-red-600 dark:text-red-400 space-y-1">
                <div className="flex items-center gap-1.5 text-2xs font-bold">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>Validation Safeguard Triggered</span>
                </div>
                <ul className="list-disc list-inside text-3xs space-y-0.5">
                  {validationErrors.map((err, idx) => (
                    <li key={idx}>{formatIssue(err)}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Save Error Banner */}
            {applyError && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-md text-red-600 dark:text-red-400 text-2xs flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>{formatIssue(applyError)}</span>
              </div>
            )}
          </div>

          {/* Right Column: Live Chart Preview (5 cols) */}
          <div className="lg:col-span-5 bg-surface-muted/20 border border-border rounded-card p-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-border">
                <span className="text-2xs font-bold text-foreground flex items-center gap-1.5">
                  <Sparkles className="w-3 h-3 text-indigo-500" />
                  <span>Interactive Live Preview</span>
                </span>
                {previewRows !== null && (
                  <span className="text-3xs text-emerald-600 dark:text-emerald-400 font-mono flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Validated</span>
                  </span>
                )}
              </div>

              {/* Preview Canvas */}
              <div className="w-full min-h-[260px] flex flex-col items-center justify-center bg-surface border border-border rounded-md p-2 overflow-hidden">
                <InsightChart
                  visualization={chartType}
                  metric={displayMetricName}
                  dimensions={chartType === 'kpi' ? [] : (dimensionCol ? [dimensionCol] : [])}
                  executionData={displayData}
                  isLoading={isPreviewLoading}
                  isInsufficientData={displayData.length === 0}
                  errorMessage={undefined}
                  className="w-full h-full min-h-[250px]"
                />
              </div>

              {/* Preview Compiled SQL snippet */}
              {previewSql && (
                <div className="mt-3">
                  <div className="flex items-center gap-1 text-3xs font-semibold text-muted-foreground mb-1">
                    <Code className="w-3 h-3" />
                    <span>Compiled DuckDB SQL</span>
                  </div>
                  <pre className="p-2 bg-surface-muted/80 rounded border border-border text-3xs font-mono text-muted-foreground overflow-x-auto max-h-24">
                    <code>{previewSql}</code>
                  </pre>
                </div>
              )}
            </div>

            {/* Preview Button */}
            <div className="mt-4 pt-3 border-t border-border">
              <button
                type="button"
                onClick={handlePreview}
                disabled={isPreviewLoading || isApplying}
                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-surface hover:bg-surface-muted border border-border rounded-md text-xs font-semibold text-foreground transition-colors disabled:opacity-50"
              >
                {isPreviewLoading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Validating on DuckDB...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 text-indigo-500 fill-indigo-500" />
                    <span>Preview & Validate Query</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-border bg-surface-muted/30 flex items-center justify-between">
          <button
            type="button"
            onClick={onClose}
            disabled={isApplying}
            className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleApply}
              disabled={isApplying || isPreviewLoading}
              className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
            >
              {isApplying ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Applying Changes...</span>
                </>
              ) : (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Apply Changes</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
