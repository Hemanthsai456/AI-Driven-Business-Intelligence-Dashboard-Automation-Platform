'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  BarChart3,
  TrendingUp,
  ScatterChart as ScatterIcon,
  Calendar,
  Hash,
  Tag,
  AlertCircle,
  Sparkles,
  Layers,
  Clock,
  Filter,
  RefreshCw,
  Info,
  ChevronRight,
  Database,
  ArrowRight,
  CheckCircle2,
  PieChart as PieIcon,
  Grid,
  Activity,
  Sliders,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  Legend,
  ZAxis,
} from 'recharts';
import { Card } from '../Card';
import { Badge } from '../Badge';
import {
  DatasetMetadata,
  DataProfile,
  SemanticProfile,
  QualityAssessment,
  EDASummary,
  EDAExploreRequest,
  EDAExploreResult,
  NumericDistribution,
  CategoricalDistribution,
  EDAObservation,
} from '../../lib/types';
import { getDatasetEDASummary, exploreDatasetEDA } from '../../lib/api';
import { useChartTheme } from '../../lib/chartTheme';

interface EDATabProps {
  metadata: DatasetMetadata;
  profile: DataProfile | null;
  semanticProfile: SemanticProfile | null;
  qualityAssessment?: QualityAssessment | null;
}

type EDASubMode = 'automated' | 'explore';
type ChartTypeOption = 'scatter' | 'line' | 'bar' | 'distribution';

export const EDATab: React.FC<EDATabProps> = ({
  metadata,
  profile,
  semanticProfile,
}) => {
  // Theme-aware chart configuration
  const chartTheme = useChartTheme();

  // Mode switcher
  const [activeSubMode, setActiveSubMode] = useState<EDASubMode>('automated');

  // Automated EDA State
  const [summary, setSummary] = useState<EDASummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState<boolean>(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Selected column in automated numeric/categorical views
  const [selectedNumericCol, setSelectedNumericCol] = useState<string | null>(null);
  const [selectedCategoricalCol, setSelectedCategoricalCol] = useState<string | null>(null);
  const [selectedCorrCell, setSelectedCorrCell] = useState<{ col1: string; col2: string; val: number | null } | null>(null);

  // Manual Explore State
  const [exploreChartType, setExploreChartType] = useState<ChartTypeOption>('scatter');
  const [exploreX, setExploreX] = useState<string>('');
  const [exploreY, setExploreY] = useState<string>('');
  const [exploreGroupBy, setExploreGroupBy] = useState<string>('');
  const [exploreAggregation, setExploreAggregation] = useState<'avg' | 'sum' | 'count' | 'min' | 'max'>('avg');
  const [exploreGranularity, setExploreGranularity] = useState<'day' | 'month' | 'quarter' | 'year'>('month');
  const [exploreLimit, setExploreLimit] = useState<number>(15);

  const [exploreResult, setExploreResult] = useState<EDAExploreResult | null>(null);
  const [loadingExplore, setLoadingExplore] = useState<boolean>(false);
  const [exploreError, setExploreError] = useState<string | null>(null);

  // Column Categorization from metadata & semantics
  const numericColumns = useMemo(() => {
    return (metadata.columns || [])
      .filter((col) => {
        const type = col.detected_datatype.toLowerCase();
        return (
          type.includes('int') ||
          type.includes('float') ||
          type.includes('double') ||
          type.includes('num') ||
          type.includes('dec')
        );
      })
      .map((c) => c.original_name);
  }, [metadata.columns]);

  const categoricalColumns = useMemo(() => {
    return (metadata.columns || [])
      .filter((col) => {
        const type = col.detected_datatype.toLowerCase();
        return (
          type.includes('varchar') ||
          type.includes('text') ||
          type.includes('string') ||
          type.includes('cat') ||
          type.includes('char')
        );
      })
      .map((c) => c.original_name);
  }, [metadata.columns]);

  const datetimeColumns = useMemo(() => {
    return (metadata.columns || [])
      .filter((col) => {
        const type = col.detected_datatype.toLowerCase();
        const role = semanticProfile?.column_evidences?.[col.original_name]?.candidate_role;
        return (
          type.includes('date') ||
          type.includes('time') ||
          type.includes('timestamp') ||
          role === 'DATETIME'
        );
      })
      .map((c) => c.original_name);
  }, [metadata.columns, semanticProfile]);

  // Load Automated EDA Summary
  const fetchSummary = async (datasetId: string) => {
    if (!datasetId) return;
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      const data = await getDatasetEDASummary(datasetId);
      setSummary(data);
      // Auto-select first numeric & categorical columns
      if (data.numeric_distributions && data.numeric_distributions.length > 0) {
        setSelectedNumericCol(data.numeric_distributions[0].column_name);
      }
      if (data.categorical_distributions && data.categorical_distributions.length > 0) {
        setSelectedCategoricalCol(data.categorical_distributions[0].column_name);
      }
    } catch (err: any) {
      console.error('Failed to load EDA summary:', err);
      setSummaryError(err.message || 'Failed to generate EDA summary.');
      setSummary(null);
    } finally {
      setLoadingSummary(false);
    }
  };

  useEffect(() => {
    if (metadata.dataset_id) {
      fetchSummary(metadata.dataset_id);
    }
  }, [metadata.dataset_id]);

  // Set default form values when switching explore chart types or columns
  useEffect(() => {
    if (exploreChartType === 'scatter') {
      if (numericColumns.length >= 2) {
        if (!numericColumns.includes(exploreX)) setExploreX(numericColumns[0]);
        if (!numericColumns.includes(exploreY) || exploreY === numericColumns[0]) {
          setExploreY(numericColumns[1]);
        }
      } else if (numericColumns.length === 1) {
        setExploreX(numericColumns[0]);
        setExploreY(numericColumns[0]);
      }
    } else if (exploreChartType === 'line') {
      if (datetimeColumns.length > 0 && !datetimeColumns.includes(exploreX)) {
        setExploreX(datetimeColumns[0]);
      }
      if (numericColumns.length > 0 && !numericColumns.includes(exploreY)) {
        setExploreY(numericColumns[0]);
      }
    } else if (exploreChartType === 'bar') {
      if (categoricalColumns.length > 0 && !categoricalColumns.includes(exploreX)) {
        setExploreX(categoricalColumns[0]);
      }
      if (numericColumns.length > 0 && !numericColumns.includes(exploreY)) {
        setExploreY(numericColumns[0]);
      }
    } else if (exploreChartType === 'distribution') {
      if (numericColumns.length > 0 && !numericColumns.includes(exploreX)) {
        setExploreX(numericColumns[0]);
      } else if (categoricalColumns.length > 0 && !categoricalColumns.includes(exploreX)) {
        setExploreX(categoricalColumns[0]);
      }
    }
  }, [exploreChartType, numericColumns, categoricalColumns, datetimeColumns]);

  // Execute Manual Exploration
  const handleRunExplore = async () => {
    if (!metadata.dataset_id || !exploreX) return;

    setLoadingExplore(true);
    setExploreError(null);

    const req: EDAExploreRequest = {
      chart_type: exploreChartType,
      x_column: exploreX,
      y_column: exploreChartType !== 'distribution' ? exploreY || undefined : undefined,
      group_by: exploreGroupBy || undefined,
      aggregation: exploreAggregation,
      time_granularity: exploreChartType === 'line' ? exploreGranularity : undefined,
    };

    try {
      const res = await exploreDatasetEDA(metadata.dataset_id, req);
      if (!res.is_supported) {
        setExploreError(res.error_message || 'Exploration combination not supported.');
        setExploreResult(null);
      } else {
        setExploreResult(res);
      }
    } catch (err: any) {
      console.error('Failed to run explore query:', err);
      setExploreError(err.message || 'Failed to execute exploration.');
      setExploreResult(null);
    } finally {
      setLoadingExplore(false);
    }
  };

  // Color helper for correlation heatmaps (-1 to +1)
  const getCorrColor = (val: number | null | undefined) => {
    if (val === null || val === undefined || isNaN(val)) return 'bg-muted/40 text-muted-foreground';
    if (val === 1.0) return 'bg-primary/20 text-primary font-bold border-primary/30';
    if (val > 0.6) return 'bg-blue-500/25 text-blue-700 dark:text-blue-300 font-semibold';
    if (val > 0.3) return 'bg-blue-500/15 text-blue-800 dark:text-blue-300 font-medium';
    if (val > 0.05) return 'bg-blue-500/10 text-blue-900 dark:text-blue-200';
    if (val >= -0.05 && val <= 0.05) return 'bg-muted/20 text-muted-foreground';
    if (val >= -0.3) return 'bg-rose-500/10 text-rose-900 dark:text-rose-200';
    if (val >= -0.6) return 'bg-rose-500/15 text-rose-800 dark:text-rose-300 font-medium';
    return 'bg-rose-500/25 text-rose-700 dark:text-rose-300 font-semibold';
  };

  const getObservationIcon = (type: string) => {
    switch (type) {
      case 'missing_values':
        return <AlertCircle className="w-4 h-4 text-attention shrink-0" />;
      case 'skewness':
        return <TrendingUp className="w-4 h-4 text-primary shrink-0" />;
      case 'correlation':
        return <Activity className="w-4 h-4 text-blue-400 shrink-0" />;
      case 'temporal':
        return <Clock className="w-4 h-4 text-green-400 shrink-0" />;
      case 'cardinality':
        return <Layers className="w-4 h-4 text-purple-400 shrink-0" />;
      default:
        return <Sparkles className="w-4 h-4 text-primary shrink-0" />;
    }
  };

  const activeNumericDist = useMemo(() => {
    if (!summary?.numeric_distributions || summary.numeric_distributions.length === 0) return null;
    return (
      summary.numeric_distributions.find((d) => d.column_name === selectedNumericCol) ||
      summary.numeric_distributions[0]
    );
  }, [summary, selectedNumericCol]);

  const activeCategoricalDist = useMemo(() => {
    if (!summary?.categorical_distributions || summary.categorical_distributions.length === 0) return null;
    return (
      summary.categorical_distributions.find((d) => d.column_name === selectedCategoricalCol) ||
      summary.categorical_distributions[0]
    );
  }, [summary, selectedCategoricalCol]);

  return (
    <div className="space-y-6">
      {/* EDA Top Navigation Sub-bar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-2 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary-soft border border-primary/20 flex items-center justify-center text-primary">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-foreground tracking-tight">
                Exploratory Data Analysis
              </h2>
              <Badge variant="blue" size="xs">
                Deterministic
              </Badge>
            </div>
            <p className="text-2xs text-muted-foreground">
              Statistical summary, univariate/bivariate distributions, correlation matrix, and interactive charts
            </p>
          </div>
        </div>

        {/* Sub-Mode Toggle */}
        <div className="flex items-center gap-1.5 p-1 bg-surface-muted border border-border rounded-lg">
          <button
            onClick={() => setActiveSubMode('automated')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeSubMode === 'automated'
                ? 'bg-card text-foreground shadow-sm border border-border'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            <span>Automated Overview</span>
          </button>
          <button
            onClick={() => setActiveSubMode('explore')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeSubMode === 'explore'
                ? 'bg-card text-foreground shadow-sm border border-border'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sliders className="w-3.5 h-3.5 text-blue-400" />
            <span>Explore Data</span>
          </button>
        </div>
      </div>

      {/* ============================================================ */}
      {/* MODE 1: AUTOMATED EDA OVERVIEW */}
      {/* ============================================================ */}
      {activeSubMode === 'automated' && (
        <div className="space-y-6">
          {loadingSummary ? (
            <Card className="p-12 text-center space-y-3">
              <RefreshCw className="w-6 h-6 animate-spin text-primary mx-auto" />
              <p className="text-xs text-muted-foreground font-medium">
                Computing deterministic statistical profiles & distributions...
              </p>
            </Card>
          ) : summaryError ? (
            <Card className="p-8 border-error/30 bg-error-soft space-y-3">
              <div className="flex items-center gap-2 text-error text-sm font-semibold">
                <AlertCircle className="w-4 h-4" />
                <span>Automated EDA Unavailable</span>
              </div>
              <p className="text-xs text-muted-foreground">{summaryError}</p>
              <button
                onClick={() => fetchSummary(metadata.dataset_id)}
                className="px-3 py-1.5 bg-card border border-border rounded text-xs font-medium hover:bg-muted"
              >
                Retry Analysis
              </button>
            </Card>
          ) : summary && summary.dataset_summary ? (
            <>
              {/* 1. Dataset Summary KPI Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Total Rows</span>
                    <Database className="w-3.5 h-3.5 text-primary" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.row_count.toLocaleString()}
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Total Columns</span>
                    <Grid className="w-3.5 h-3.5 text-blue-400" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.column_count}
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Numeric</span>
                    <Hash className="w-3.5 h-3.5 text-indigo-400" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.numeric_columns_count}
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Categorical</span>
                    <Tag className="w-3.5 h-3.5 text-purple-400" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.categorical_columns_count}
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Datetime</span>
                    <Calendar className="w-3.5 h-3.5 text-green-400" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.datetime_columns_count}
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Missing Cells</span>
                    <AlertCircle className="w-3.5 h-3.5 text-attention" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.missing_cells_count.toLocaleString()}{' '}
                    <span className="text-2xs font-normal text-muted-foreground">
                      ({summary.dataset_summary.missing_cells_percentage.toFixed(1)}%)
                    </span>
                  </div>
                </div>

                <div className="p-3 bg-surface border border-border rounded-lg">
                  <div className="flex items-center justify-between text-muted-foreground mb-1">
                    <span className="text-2xs font-medium">Duplicate Rows</span>
                    <Layers className="w-3.5 h-3.5 text-rose-400" />
                  </div>
                  <div className="text-base font-bold text-foreground font-mono">
                    {summary.dataset_summary.duplicate_rows_count.toLocaleString()}{' '}
                    <span className="text-2xs font-normal text-muted-foreground">
                      ({summary.dataset_summary.duplicate_rows_percentage.toFixed(1)}%)
                    </span>
                  </div>
                </div>
              </div>

              {/* 2. Statistical Observations (Concise, Evidence-Grounded) */}
              {summary.automated_observations && summary.automated_observations.length > 0 && (
                <Card
                  title={
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-primary" />
                      <span>Statistical Observations</span>
                    </div>
                  }
                  subtitle="Deterministic facts derived directly from calculated dataset statistics"
                  padding="md"
                >
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {summary.automated_observations.map((obs: EDAObservation, idx: number) => {
                      const obsType = obs.type || obs.category || 'observation';
                      const obsText = obs.observation || obs.text || '';
                      return (
                        <div
                          key={obs.id || idx}
                          className="p-3 bg-surface-muted/60 border border-border rounded-lg flex items-start gap-3 hover:border-border-hover transition-colors"
                        >
                          {getObservationIcon(obsType)}
                          <div className="space-y-1 flex-1 min-w-0">
                            <p className="text-xs font-medium text-foreground leading-relaxed">
                              {obsText}
                            </p>
                            {obs.evidence && typeof obs.evidence === 'object' && (
                              <div className="flex flex-wrap gap-1.5 pt-1">
                                {Object.entries(obs.evidence).map(([k, v]) => (
                                  <span
                                    key={k}
                                    className="inline-flex items-center px-1.5 py-0.5 rounded bg-surface border border-border text-3xs font-mono text-muted-foreground"
                                  >
                                    {k}: {typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : String(v)}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* 3. Numeric Distributions & Histograms */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-indigo-400" />
                    <span>Numeric Distributions & Histograms</span>
                  </div>
                }
                subtitle="10-bin frequency distribution, central tendency, dispersion, and skewness"
                padding="md"
              >
                {!summary.numeric_distributions || summary.numeric_distributions.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    No numeric columns available in this dataset.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Column Chip Selector */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
                      {summary.numeric_distributions.map((dist) => {
                        const isSel = activeNumericDist?.column_name === dist.column_name;
                        const skewText = dist.skew_label || dist.distribution_shape || 'N/A';
                        return (
                          <button
                            key={dist.column_name}
                            onClick={() => setSelectedNumericCol(dist.column_name)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                              isSel
                                ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                                : 'bg-surface-muted text-muted-foreground hover:text-foreground border border-border'
                            }`}
                          >
                            <Hash className="w-3 h-3" />
                            <span>{dist.column_name}</span>
                            <span className="text-3xs opacity-80">({skewText})</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Active Column Details */}
                    {activeNumericDist && (() => {
                      const skewText = activeNumericDist.skew_label || activeNumericDist.distribution_shape || 'Unknown';
                      const q1Val = activeNumericDist.q1 ?? activeNumericDist.q25;
                      const q3Val = activeNumericDist.q3 ?? activeNumericDist.q75;
                      const validRowsCount = activeNumericDist.non_null_count ?? (activeNumericDist.row_count !== undefined ? activeNumericDist.row_count - (activeNumericDist.null_count ?? 0) : null) ?? 0;

                      return (
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 pt-2">
                          {/* Left: Summary Metrics Grid */}
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-bold text-foreground font-mono">
                                {activeNumericDist.column_name}
                              </h4>
                              <Badge
                                variant={
                                  skewText.toLowerCase().includes('symmetric')
                                    ? 'green'
                                    : skewText.toLowerCase().includes('moderate')
                                    ? 'amber'
                                    : 'purple'
                                }
                                size="xs"
                              >
                                {skewText}
                              </Badge>
                            </div>

                            <div className="grid grid-cols-2 gap-2 text-2xs">
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Mean</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.mean !== null && activeNumericDist.mean !== undefined ? activeNumericDist.mean.toFixed(2) : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Median</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.median !== null && activeNumericDist.median !== undefined ? activeNumericDist.median.toFixed(2) : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Std Dev</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.std !== null && activeNumericDist.std !== undefined ? activeNumericDist.std.toFixed(2) : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Skewness</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.skewness !== null && activeNumericDist.skewness !== undefined ? activeNumericDist.skewness.toFixed(3) : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Min</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.min !== null && activeNumericDist.min !== undefined ? activeNumericDist.min.toLocaleString() : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Max</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.max !== null && activeNumericDist.max !== undefined ? activeNumericDist.max.toLocaleString() : 'N/A'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Q1 (25%) / Q3 (75%)</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {q1Val !== null && q1Val !== undefined ? q1Val.toFixed(1) : '-'} / {q3Val !== null && q3Val !== undefined ? q3Val.toFixed(1) : '-'}
                                </div>
                              </div>
                              <div className="p-2 bg-surface-muted rounded border border-border">
                                <span className="text-muted-foreground">Zero / Negative</span>
                                <div className="font-mono font-bold text-foreground text-xs">
                                  {activeNumericDist.zero_count ?? 0} / {activeNumericDist.negative_count ?? 0}
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Right: Histogram Chart */}
                          <div className="lg:col-span-2 bg-surface p-3 rounded-lg border border-border">
                            <div className="text-2xs font-semibold text-muted-foreground mb-2 flex items-center justify-between">
                              <span>10-Bin Histogram</span>
                              <span>Valid Rows: {validRowsCount.toLocaleString()}</span>
                            </div>
                            <div className="h-48 w-full">
                              <ResponsiveContainer width="100%" height="100%">
                                <BarChart
                                  key={`num-hist-${chartTheme.themeKey}`}
                                  data={activeNumericDist.histogram || []}
                                  margin={{ top: 10, right: 15, left: 10, bottom: 35 }}
                                >
                                  <CartesianGrid {...chartTheme.gridProps} vertical={false} />
                                  <XAxis
                                    dataKey="bin_label"
                                    {...chartTheme.xAxisProps({
                                      angle: -25,
                                      textAnchor: 'end',
                                      interval: 0,
                                      height: 35,
                                    })}
                                  />
                                  <YAxis
                                    {...chartTheme.yAxisProps({
                                      width: 40,
                                      tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                                    })}
                                  />
                                  <Tooltip
                                    {...chartTheme.tooltipProps}
                                    formatter={(val: any, name: any, item: any) => {
                                      const pct = item?.payload?.percentage ?? (validRowsCount > 0 ? (val / validRowsCount * 100) : 0);
                                      return [
                                        `${val} rows (${pct !== undefined && pct !== null ? Number(pct).toFixed(1) : '0.0'}%)`,
                                        'Frequency',
                                      ];
                                    }}
                                    labelFormatter={(l) => `Interval: ${l}`}
                                  />
                                  <Bar
                                    dataKey="count"
                                    name="Frequency"
                                    fill="var(--chart-1)"
                                    radius={[3, 3, 0, 0]}
                                    activeBar={{ fill: 'var(--primary-hover, var(--chart-1))' }}
                                  />
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </Card>

              {/* 4. Categorical Distributions & Top Frequencies */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <Tag className="w-4 h-4 text-purple-400" />
                    <span>Categorical Distributions</span>
                  </div>
                }
                subtitle="High-cardinality checks, distinct counts, and top 10 category frequencies"
                padding="md"
              >
                {!summary.categorical_distributions || summary.categorical_distributions.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">
                    No categorical columns available in this dataset.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Column Chip Selector */}
                    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
                      {summary.categorical_distributions.map((dist) => {
                        const isSel = activeCategoricalDist?.column_name === dist.column_name;
                        return (
                          <button
                            key={dist.column_name}
                            onClick={() => setSelectedCategoricalCol(dist.column_name)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                              isSel
                                ? 'bg-primary text-primary-foreground font-semibold shadow-xs'
                                : 'bg-surface-muted text-muted-foreground hover:text-foreground border border-border'
                            }`}
                          >
                            <Tag className="w-3 h-3" />
                            <span>{dist.column_name}</span>
                            <span className="text-3xs opacity-80">({dist.distinct_count} distinct)</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Active Categorical Column Details */}
                    {activeCategoricalDist && (
                      <div className="space-y-3 pt-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <h4 className="text-xs font-bold text-foreground font-mono">
                              {activeCategoricalDist.column_name}
                            </h4>
                            <span className="text-2xs text-muted-foreground">
                              • {activeCategoricalDist.distinct_count} distinct categories
                            </span>
                          </div>
                          {activeCategoricalDist.is_high_cardinality && (
                            <Badge variant="amber" size="xs">
                              High Cardinality (Showing Top 10)
                            </Badge>
                          )}
                        </div>

                        {activeCategoricalDist.cardinality_note && (
                          <p className="text-2xs text-muted-foreground italic">
                            {activeCategoricalDist.cardinality_note}
                          </p>
                        )}

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                          {/* Horizontal Bar Chart */}
                          <div className="h-56 w-full bg-surface p-3 rounded-lg border border-border">
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart
                                key={`cat-bar-${chartTheme.themeKey}`}
                                layout="vertical"
                                data={(activeCategoricalDist.top_categories || []).map(cat => ({
                                  category: cat.category || cat.value || '<Empty>',
                                  count: cat.count,
                                  percentage: cat.percentage,
                                }))}
                                margin={{ top: 5, right: 25, left: 10, bottom: 10 }}
                              >
                                <CartesianGrid {...chartTheme.gridProps} horizontal={false} />
                                <XAxis
                                  type="number"
                                  {...chartTheme.xAxisProps({
                                    tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                                  })}
                                />
                                <YAxis
                                  dataKey="category"
                                  type="category"
                                  {...chartTheme.yAxisProps({
                                    width: 85,
                                    tick: { fontSize: 10, fill: 'var(--foreground)' },
                                  })}
                                />
                                <Tooltip
                                  {...chartTheme.tooltipProps}
                                  formatter={(val: any, name: any, item: any) => {
                                    const pct = item?.payload?.percentage ?? 0;
                                    return [
                                      `${val} rows (${Number(pct).toFixed(1)}%)`,
                                      'Frequency',
                                    ];
                                  }}
                                />
                                <Bar
                                  dataKey="count"
                                  name="Frequency"
                                  fill="var(--chart-2)"
                                  radius={[0, 3, 3, 0]}
                                  activeBar={{ fill: 'var(--primary-hover, var(--chart-2))' }}
                                />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>

                          {/* Table Breakdown */}
                          <div className="border border-border rounded-lg overflow-hidden max-h-56 overflow-y-auto">
                            <table className="w-full text-xs text-left">
                              <thead className="bg-surface-muted text-2xs uppercase text-muted-foreground border-b border-border sticky top-0">
                                <tr>
                                  <th className="px-3 py-2 font-medium">Category</th>
                                  <th className="px-3 py-2 font-medium text-right">Frequency</th>
                                  <th className="px-3 py-2 font-medium text-right">Share</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-border font-mono">
                                {(activeCategoricalDist.top_categories || []).map((cat, idx) => (
                                  <tr key={idx} className="hover:bg-muted/30">
                                    <td className="px-3 py-1.5 font-sans font-medium text-foreground truncate max-w-[150px]">
                                      {cat.category || cat.value || '<Empty>'}
                                    </td>
                                    <td className="px-3 py-1.5 text-right text-muted-foreground">
                                      {(cat.count ?? 0).toLocaleString()}
                                    </td>
                                    <td className="px-3 py-1.5 text-right font-bold text-foreground">
                                      {cat.percentage !== undefined && cat.percentage !== null ? cat.percentage.toFixed(1) : '0.0'}%
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </Card>

              {/* 5. Correlation Analysis (Pearson Matrix Heatmap) */}
              <Card
                title={
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-blue-400" />
                    <span>Correlation Analysis (Pearson Matrix)</span>
                  </div>
                }
                subtitle="Bivariate linear correlation coefficient r (−1.0 to +1.0). Correlation does not imply causation."
                padding="md"
              >
                {!summary.correlation_analysis ||
                summary.correlation_analysis.is_available === false ||
                summary.correlation_analysis.status === 'INSUFFICIENT_NUMERIC_COLUMNS' ||
                !summary.correlation_analysis.columns ||
                summary.correlation_analysis.columns.length < 2 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground space-y-1">
                    <p className="font-medium text-foreground">
                      Correlation analysis requires at least two usable numeric columns.
                    </p>
                    <p className="text-2xs">
                      {summary.correlation_analysis?.message || 'Only one or zero numeric columns detected in this dataset.'}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {/* Matrix Grid */}
                    <div className="overflow-x-auto">
                      <table className="text-xs border-collapse min-w-full">
                        <thead>
                          <tr>
                            <th className="p-2 border border-border bg-surface-muted text-left text-2xs text-muted-foreground font-mono">
                              Column
                            </th>
                            {summary.correlation_analysis.columns.map((c) => (
                              <th
                                key={c}
                                className="p-2 border border-border bg-surface-muted text-center text-2xs font-mono font-medium text-foreground truncate max-w-[120px]"
                                title={c}
                              >
                                {c}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {summary.correlation_analysis.columns.map((rowCol) => (
                            <tr key={rowCol}>
                              <td className="p-2 border border-border bg-surface-muted font-mono font-medium text-foreground text-2xs truncate max-w-[140px]">
                                {rowCol}
                              </td>
                              {summary.correlation_analysis.columns.map((colCol) => {
                                const val = summary.correlation_analysis?.matrix?.[rowCol]?.[colCol];
                                const isSelected =
                                  selectedCorrCell &&
                                  ((selectedCorrCell.col1 === rowCol && selectedCorrCell.col2 === colCol) ||
                                    (selectedCorrCell.col1 === colCol && selectedCorrCell.col2 === rowCol));
                                return (
                                  <td
                                    key={colCol}
                                    onClick={() =>
                                      rowCol !== colCol &&
                                      setSelectedCorrCell({ col1: rowCol, col2: colCol, val: val ?? null })
                                    }
                                    className={`p-2 border border-border text-center font-mono text-2xs transition-all cursor-pointer ${getCorrColor(
                                      val
                                    )} ${isSelected ? 'ring-2 ring-primary ring-inset font-bold' : ''}`}
                                    title={`${rowCol} vs ${colCol}: ${val !== null && val !== undefined ? val.toFixed(3) : 'N/A'}`}
                                  >
                                    {val !== null && val !== undefined ? val.toFixed(2) : '-'}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Selected Correlation Cell Detail / Strongest Pairs */}
                    {selectedCorrCell && selectedCorrCell.col1 !== selectedCorrCell.col2 && (
                      <div className="p-3 bg-surface-muted border border-border rounded-lg flex items-center justify-between text-xs">
                        <div className="space-y-0.5">
                          <span className="font-semibold text-foreground">
                            {selectedCorrCell.col1} ⟷ {selectedCorrCell.col2}
                          </span>
                          <p className="text-2xs text-muted-foreground">
                            Pearson r = {selectedCorrCell.val !== null ? selectedCorrCell.val.toFixed(3) : 'N/A'}.{' '}
                            {selectedCorrCell.val !== null && Math.abs(selectedCorrCell.val) >= 0.7
                              ? 'Shows a strong linear correlation.'
                              : selectedCorrCell.val !== null && Math.abs(selectedCorrCell.val) >= 0.3
                              ? 'Shows a moderate linear correlation.'
                              : 'Shows little or weak linear correlation.'}
                          </p>
                        </div>
                        <Badge
                          variant={
                            selectedCorrCell.val && Math.abs(selectedCorrCell.val) >= 0.5
                              ? 'blue'
                              : 'slate'
                          }
                          size="xs"
                        >
                          r = {selectedCorrCell.val?.toFixed(2) ?? 'N/A'}
                        </Badge>
                      </div>
                    )}
                  </div>
                )}
              </Card>

              {/* 6. Temporal Analysis (where applicable) */}
              {summary.temporal_analysis && summary.temporal_analysis.is_available !== false && (
                <Card
                  title={
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-green-400" />
                      <span>Temporal Trend Analysis</span>
                    </div>
                  }
                  subtitle={`Chronological aggregation along ${summary.temporal_analysis.datetime_column || 'date'} (${summary.temporal_analysis.granularity || summary.temporal_analysis.time_granularity || 'interval'} granularity)`}
                  padding="md"
                >
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-2xs">
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <span>Range:</span>
                        <span className="font-mono text-foreground font-semibold">
                          {summary.temporal_analysis.date_range?.min_date ?? summary.temporal_analysis.earliest_date ?? 'N/A'} → {summary.temporal_analysis.date_range?.max_date ?? summary.temporal_analysis.latest_date ?? 'N/A'}
                        </span>
                        <span>• {summary.temporal_analysis.total_points ?? summary.temporal_analysis.series?.length ?? summary.temporal_analysis.data_points?.length ?? 0} aggregated intervals</span>
                      </div>
                      <Badge variant="teal" size="xs">
                        Trend: {summary.temporal_analysis.trend_direction || 'Detected'}
                      </Badge>
                    </div>

                    <div className="h-60 w-full bg-surface p-3 rounded-lg border border-border">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          key={`temporal-line-${chartTheme.themeKey}`}
                          data={summary.temporal_analysis.data_points || summary.temporal_analysis.series?.map(s => ({ period: s.period, metric_value: s.value, value: s.value, count: s.count })) || []}
                          margin={{ top: 10, right: 20, left: 10, bottom: 35 }}
                        >
                          <CartesianGrid {...chartTheme.gridProps} vertical={false} />
                          <XAxis
                            dataKey="period"
                            {...chartTheme.xAxisProps({
                              angle: -20,
                              textAnchor: 'end',
                              height: 35,
                            })}
                          />
                          <YAxis
                            {...chartTheme.yAxisProps({
                              width: 40,
                              tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                            })}
                          />
                          <Tooltip {...chartTheme.tooltipProps} />
                          <Line
                            type="monotone"
                            dataKey="metric_value"
                            name={summary.temporal_analysis.measure_column ? `Avg ${summary.temporal_analysis.measure_column}` : 'Record Count'}
                            stroke="var(--chart-3)"
                            strokeWidth={2}
                            dot={{ r: 3, fill: 'var(--chart-3)' }}
                            activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </Card>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* ============================================================ */}
      {/* MODE 2: MANUAL INTERACTIVE EXPLORATION */}
      {/* ============================================================ */}
      {activeSubMode === 'explore' && (
        <div className="space-y-6">
          {/* Exploration Control Panel */}
          <Card
            title={
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-primary" />
                <span>Interactive Chart Builder</span>
              </div>
            }
            subtitle="Type-aware bivariate and multivariate exploration with deterministic sampling"
            padding="md"
          >
            <div className="space-y-4">
              {/* Chart Type Selector */}
              <div className="space-y-1.5">
                <label className="text-2xs font-bold uppercase tracking-wider text-muted-foreground">
                  Visualization Type
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <button
                    onClick={() => setExploreChartType('scatter')}
                    className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                      exploreChartType === 'scatter'
                        ? 'border-primary bg-primary-soft text-foreground'
                        : 'border-border bg-surface hover:bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <ScatterIcon className="w-3.5 h-3.5 text-primary" />
                      <span>Scatter Plot</span>
                    </div>
                    <span className="text-3xs text-muted-foreground">Numeric × Numeric</span>
                  </button>

                  <button
                    onClick={() => setExploreChartType('line')}
                    className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                      exploreChartType === 'line'
                        ? 'border-primary bg-primary-soft text-foreground'
                        : 'border-border bg-surface hover:bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <TrendingUp className="w-3.5 h-3.5 text-green-400" />
                      <span>Time Series</span>
                    </div>
                    <span className="text-3xs text-muted-foreground">Datetime × Numeric</span>
                  </button>

                  <button
                    onClick={() => setExploreChartType('bar')}
                    className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                      exploreChartType === 'bar'
                        ? 'border-primary bg-primary-soft text-foreground'
                        : 'border-border bg-surface hover:bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <BarChart3 className="w-3.5 h-3.5 text-purple-400" />
                      <span>Categorical Bar</span>
                    </div>
                    <span className="text-3xs text-muted-foreground">Category × Measure</span>
                  </button>

                  <button
                    onClick={() => setExploreChartType('distribution')}
                    className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                      exploreChartType === 'distribution'
                        ? 'border-primary bg-primary-soft text-foreground'
                        : 'border-border bg-surface hover:bg-surface-muted text-muted-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <PieIcon className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Distribution</span>
                    </div>
                    <span className="text-3xs text-muted-foreground">Univariate Histogram</span>
                  </button>
                </div>
              </div>

              {/* Dynamic Form Controls Filtered by Chart Type */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2 border-t border-border">
                {/* X-Axis Field */}
                <div className="space-y-1">
                  <label className="text-2xs font-semibold text-muted-foreground">
                    {exploreChartType === 'scatter'
                      ? 'X Axis (Numeric)'
                      : exploreChartType === 'line'
                      ? 'Time Axis (Datetime)'
                      : exploreChartType === 'bar'
                      ? 'Dimension (Categorical)'
                      : 'Column'}
                  </label>
                  <select
                    value={exploreX}
                    onChange={(e) => setExploreX(e.target.value)}
                    className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  >
                    {exploreChartType === 'scatter' &&
                      numericColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    {exploreChartType === 'line' &&
                      (datetimeColumns.length > 0 ? (
                        datetimeColumns.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))
                      ) : (
                        <option value="">No Datetime Column Detected</option>
                      ))}
                    {exploreChartType === 'bar' &&
                      categoricalColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    {exploreChartType === 'distribution' &&
                      (metadata.columns || []).map((col) => (
                        <option key={col.original_name} value={col.original_name}>
                          {col.original_name} ({col.detected_datatype})
                        </option>
                      ))}
                  </select>
                </div>

                {/* Y-Axis Field (For Bivariate Charts) */}
                {exploreChartType !== 'distribution' && (
                  <div className="space-y-1">
                    <label className="text-2xs font-semibold text-muted-foreground">
                      {exploreChartType === 'bar' ? 'Measure Column' : 'Y Axis (Numeric)'}
                    </label>
                    <select
                      value={exploreY}
                      onChange={(e) => setExploreY(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      {exploreChartType === 'bar' && <option value="">[Row Count / Frequency]</option>}
                      {numericColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Aggregation (For Line & Bar) */}
                {(exploreChartType === 'line' || (exploreChartType === 'bar' && exploreY)) && (
                  <div className="space-y-1">
                    <label className="text-2xs font-semibold text-muted-foreground">
                      Aggregation
                    </label>
                    <select
                      value={exploreAggregation}
                      onChange={(e) => setExploreAggregation(e.target.value as any)}
                      className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="avg">Average (Mean)</option>
                      <option value="sum">Sum</option>
                      <option value="count">Count</option>
                      <option value="min">Minimum</option>
                      <option value="max">Maximum</option>
                    </select>
                  </div>
                )}

                {/* Granularity (For Line) */}
                {exploreChartType === 'line' && (
                  <div className="space-y-1">
                    <label className="text-2xs font-semibold text-muted-foreground">
                      Time Interval
                    </label>
                    <select
                      value={exploreGranularity}
                      onChange={(e) => setExploreGranularity(e.target.value as any)}
                      className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="day">Daily</option>
                      <option value="month">Monthly</option>
                      <option value="quarter">Quarterly</option>
                      <option value="year">Yearly</option>
                    </select>
                  </div>
                )}

                {/* Group By (For Scatter) */}
                {exploreChartType === 'scatter' && (
                  <div className="space-y-1">
                    <label className="text-2xs font-semibold text-muted-foreground">
                      Group By / Color (Optional)
                    </label>
                    <select
                      value={exploreGroupBy}
                      onChange={(e) => setExploreGroupBy(e.target.value)}
                      className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="">None (Unified)</option>
                      {categoricalColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* Limit (For Bar) */}
                {exploreChartType === 'bar' && (
                  <div className="space-y-1">
                    <label className="text-2xs font-semibold text-muted-foreground">
                      Top Categories Limit
                    </label>
                    <select
                      value={exploreLimit}
                      onChange={(e) => setExploreLimit(Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-surface border border-border rounded text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value={10}>Top 10</option>
                      <option value={15}>Top 15</option>
                      <option value={25}>Top 25</option>
                      <option value={50}>Top 50</option>
                    </select>
                  </div>
                )}
              </div>

              {/* Action Button */}
              <div className="flex items-center justify-between pt-2">
                <div className="text-2xs text-muted-foreground">
                  {exploreChartType === 'line' && datetimeColumns.length === 0 ? (
                    <span className="text-attention">No datetime column detected for time-series.</span>
                  ) : exploreChartType === 'scatter' && numericColumns.length < 2 ? (
                    <span className="text-attention">Scatter plot requires at least 2 numeric columns.</span>
                  ) : (
                    <span>Deterministic query will compute aggregated data.</span>
                  )}
                </div>

                <button
                  onClick={handleRunExplore}
                  disabled={loadingExplore || !exploreX}
                  className="px-4 py-2 bg-primary text-primary-foreground font-semibold rounded-lg text-xs hover:bg-primary/90 disabled:opacity-50 transition-all flex items-center gap-1.5 shadow-sm"
                >
                  {loadingExplore ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Computing...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Generate Visualization</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </Card>

          {/* Interactive Chart Canvas */}
          {exploreError ? (
            <Card className="p-6 border-error/30 bg-error-soft space-y-2">
              <div className="flex items-center gap-2 text-error text-xs font-semibold">
                <AlertCircle className="w-4 h-4" />
                <span>Exploration Error</span>
              </div>
              <p className="text-xs text-muted-foreground">{exploreError}</p>
            </Card>
          ) : exploreResult ? (
            <Card
              title={
                exploreResult.chart_type === 'scatter'
                  ? `${exploreResult.x_column} vs ${exploreResult.y_column}`
                  : exploreResult.chart_type === 'line'
                  ? `${exploreResult.y_column} over ${exploreResult.x_column}`
                  : exploreResult.chart_type === 'bar'
                  ? `${exploreResult.y_column || 'Count'} by ${exploreResult.x_column}`
                  : `Distribution of ${exploreResult.x_column}`
              }
              subtitle={
                <div className="flex items-center gap-2">
                  <span>{exploreResult.total_points ?? exploreResult.data.length} total points analyzed</span>
                  {exploreResult.is_sampled && (
                    <Badge variant="amber" size="xs">
                      Deterministic Sample: {exploreResult.rendered_points} points
                    </Badge>
                  )}
                  {exploreResult.correlation !== undefined && exploreResult.correlation !== null && (
                    <Badge variant="blue" size="xs">
                      r = {exploreResult.correlation}
                    </Badge>
                  )}
                </div>
              }
              padding="md"
            >
              <div className="space-y-4">
                {/* Visual Canvas */}
                <div className="h-80 w-full bg-surface p-4 rounded-lg border border-border">
                  {exploreResult.chart_type === 'scatter' && (
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart
                        key={`explore-scatter-${chartTheme.themeKey}`}
                        margin={{ top: 10, right: 20, left: 15, bottom: 35 }}
                      >
                        <CartesianGrid {...chartTheme.gridProps} />
                        <XAxis
                          dataKey="x"
                          name={exploreResult.x_column}
                          type="number"
                          {...chartTheme.xAxisProps({
                            label: {
                              value: exploreResult.x_column,
                              position: 'bottom',
                              offset: 15,
                              fontSize: 11,
                              fill: 'var(--foreground)',
                            },
                          })}
                        />
                        <YAxis
                          dataKey="y"
                          name={exploreResult.y_column}
                          type="number"
                          {...chartTheme.yAxisProps({
                            width: 45,
                            label: {
                              value: exploreResult.y_column,
                              angle: -90,
                              position: 'insideLeft',
                              fontSize: 11,
                              fill: 'var(--foreground)',
                            },
                          })}
                        />
                        <Tooltip
                          {...chartTheme.tooltipProps}
                          cursor={{ stroke: 'var(--border)', strokeDasharray: '3 3' }}
                        />
                        <Scatter
                          data={exploreResult.data}
                          fill="var(--chart-1)"
                          opacity={0.75}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  )}

                  {exploreResult.chart_type === 'line' && (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        key={`explore-line-${chartTheme.themeKey}`}
                        data={exploreResult.data}
                        margin={{ top: 10, right: 20, left: 15, bottom: 35 }}
                      >
                        <CartesianGrid {...chartTheme.gridProps} />
                        <XAxis
                          dataKey="period"
                          {...chartTheme.xAxisProps({
                            angle: -20,
                            textAnchor: 'end',
                            height: 35,
                          })}
                        />
                        <YAxis
                          {...chartTheme.yAxisProps({
                            width: 45,
                            tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                          })}
                        />
                        <Tooltip {...chartTheme.tooltipProps} />
                        <Line
                          type="monotone"
                          dataKey="value"
                          name={exploreResult.y_column || 'Value'}
                          stroke="var(--chart-3)"
                          strokeWidth={2}
                          dot={{ r: 3, fill: 'var(--chart-3)' }}
                          activeDot={{ r: 5, stroke: 'var(--surface)', strokeWidth: 2 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  )}

                  {exploreResult.chart_type === 'bar' && (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        key={`explore-bar-${chartTheme.themeKey}`}
                        data={exploreResult.data}
                        margin={{ top: 10, right: 20, left: 15, bottom: 40 }}
                      >
                        <CartesianGrid {...chartTheme.gridProps} vertical={false} />
                        <XAxis
                          dataKey="category"
                          {...chartTheme.xAxisProps({
                            angle: -25,
                            textAnchor: 'end',
                            interval: 0,
                            height: 40,
                            tick: { fontSize: 9, fill: 'var(--foreground)' },
                          })}
                        />
                        <YAxis
                          {...chartTheme.yAxisProps({
                            width: 45,
                            tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                          })}
                        />
                        <Tooltip {...chartTheme.tooltipProps} />
                        <Bar
                          dataKey="value"
                          name={exploreResult.y_column || 'Count'}
                          fill="var(--chart-2)"
                          radius={[3, 3, 0, 0]}
                          activeBar={{ fill: 'var(--primary-hover, var(--chart-2))' }}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  )}

                  {exploreResult.chart_type === 'distribution' && (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        key={`explore-dist-${chartTheme.themeKey}`}
                        data={exploreResult.data}
                        margin={{ top: 10, right: 20, left: 15, bottom: 35 }}
                      >
                        <CartesianGrid {...chartTheme.gridProps} vertical={false} />
                        <XAxis
                          dataKey={exploreResult.distribution_type === 'numeric' ? 'bin_label' : 'category'}
                          {...chartTheme.xAxisProps({
                            angle: -20,
                            textAnchor: 'end',
                            height: 35,
                          })}
                        />
                        <YAxis
                          {...chartTheme.yAxisProps({
                            width: 45,
                            tickFormatter: (v: number) => (typeof v === 'number' ? v.toLocaleString() : v),
                          })}
                        />
                        <Tooltip {...chartTheme.tooltipProps} />
                        <Bar
                          dataKey="count"
                          name="Frequency"
                          fill="var(--chart-1)"
                          radius={[3, 3, 0, 0]}
                          activeBar={{ fill: 'var(--primary-hover, var(--chart-1))' }}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>

                {/* Summary Metrics Footnote */}
                {exploreResult.summary && Object.keys(exploreResult.summary).length > 0 && (
                  <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
                    {Object.entries(exploreResult.summary).map(([k, v]) => (
                      <div
                        key={k}
                        className="px-2.5 py-1 bg-surface-muted border border-border rounded text-2xs flex items-center gap-1.5"
                      >
                        <span className="text-muted-foreground uppercase text-3xs font-mono">{k.replace(/_/g, ' ')}:</span>
                        <span className="font-mono font-bold text-foreground">
                          {typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(3)) : String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <Card className="p-12 text-center space-y-3">
              <div className="w-10 h-10 rounded-full bg-surface-muted border border-border flex items-center justify-center mx-auto text-muted-foreground">
                <Sliders className="w-5 h-5" />
              </div>
              <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                Configure your chart parameters above and click <strong>Generate Visualization</strong> to explore the dataset relationships.
              </p>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};
