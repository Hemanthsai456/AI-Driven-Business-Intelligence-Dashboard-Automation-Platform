'use client';

import React, { useState, useMemo } from 'react';
import {
  Search,
  BarChart3,
  Tag,
  Calendar,
  Key,
  CheckCircle2,
  Info,
  ChevronRight,
  ChevronDown,
  TrendingUp,
  Hash,
  AlertTriangle,
  Layers,
  Sparkles,
  HelpCircle,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import {
  DataProfile,
  DatasetMetadata,
  HistogramBin,
  QualityAssessment,
  SemanticProfile,
} from '../../lib/types';

interface ProfilingTabProps {
  metadata: DatasetMetadata;
  profile: DataProfile | null;
  semanticProfile: SemanticProfile | null;
  qualityAssessment: QualityAssessment | null;
}

type RoleFilter = 'ALL' | 'MEASURE' | 'DIMENSION' | 'DATETIME' | 'IDENTIFIER';

export const ProfilingTab: React.FC<ProfilingTabProps> = ({
  metadata,
  profile,
  semanticProfile,
  qualityAssessment,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRole, setSelectedRole] = useState<RoleFilter>('ALL');
  const [showTechnicalEvidence, setShowTechnicalEvidence] = useState(false);

  const columnsList = useMemo(() => {
    return metadata.columns || [];
  }, [metadata.columns]);

  // Default selected column to first column
  const [selectedColumnName, setSelectedColumnName] = useState<string>(
    columnsList.length > 0 ? columnsList[0].original_name : ''
  );

  // Role Breakdown Counts
  const roleCounts = useMemo(() => {
    if (!semanticProfile?.column_evidences) {
      return { measures: 0, dimensions: 0, datetimes: 0, identifiers: 0, booleans: 0 };
    }
    const evidences = Object.values(semanticProfile.column_evidences);
    return {
      measures: evidences.filter((c) => c.candidate_role === 'MEASURE').length,
      dimensions: evidences.filter((c) => c.candidate_role === 'DIMENSION').length,
      datetimes: evidences.filter((c) => c.candidate_role === 'DATETIME').length,
      identifiers: evidences.filter((c) => c.candidate_role === 'IDENTIFIER').length,
      booleans: Object.values(profile?.column_statistics || {}).filter((c) =>
        c.detected_datatype.toLowerCase().includes('bool')
      ).length,
    };
  }, [semanticProfile, profile]);

  // Filtered Columns for Left Pane
  const filteredColumns = useMemo(() => {
    return columnsList.filter((col) => {
      const evidence = semanticProfile?.column_evidences[col.original_name];
      const role = evidence?.candidate_role || 'UNKNOWN';

      const matchesRole =
        selectedRole === 'ALL' ||
        (selectedRole === 'MEASURE' && role === 'MEASURE') ||
        (selectedRole === 'DIMENSION' && role === 'DIMENSION') ||
        (selectedRole === 'DATETIME' && role === 'DATETIME') ||
        (selectedRole === 'IDENTIFIER' && role === 'IDENTIFIER');

      const matchesSearch =
        !searchTerm.trim() ||
        col.original_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        col.detected_datatype.toLowerCase().includes(searchTerm.toLowerCase());

      return matchesRole && matchesSearch;
    });
  }, [columnsList, semanticProfile, selectedRole, searchTerm]);

  // Keep selected column valid if list changes
  const activeColName = useMemo(() => {
    if (selectedColumnName && columnsList.some((c) => c.original_name === selectedColumnName)) {
      return selectedColumnName;
    }
    return columnsList.length > 0 ? columnsList[0].original_name : '';
  }, [selectedColumnName, columnsList]);

  // Selected column statistics & semantic evidence
  const selectedStats = profile?.column_statistics[activeColName];
  const selectedEvidence = semanticProfile?.column_evidences[activeColName];
  const selectedMeta = columnsList.find((c) => c.original_name === activeColName);

  const role = selectedEvidence?.candidate_role || 'UNKNOWN';
  const roleBadgeVariant: 'teal' | 'blue' | 'purple' | 'amber' | 'slate' =
    role === 'MEASURE'
      ? 'teal'
      : role === 'DIMENSION'
      ? 'blue'
      : role === 'DATETIME'
      ? 'purple'
      : role === 'IDENTIFIER'
      ? 'amber'
      : 'slate';

  const roleDisplayLabel =
    role === 'MEASURE'
      ? 'Measure'
      : role === 'DIMENSION'
      ? 'Dimension'
      : role === 'DATETIME'
      ? 'Datetime'
      : role === 'IDENTIFIER'
      ? 'Identifier'
      : 'Unclassified';

  const totalRows = metadata.row_count || 1;
  const nonNullCount =
    selectedStats?.non_null_count ??
    (totalRows - (selectedMeta?.null_count ?? 0));
  const nullCount = selectedStats?.null_count ?? selectedMeta?.null_count ?? 0;
  const nullPct = selectedStats?.null_percentage ?? selectedMeta?.null_percentage ?? 0;
  const completenessPct = Math.max(0, Math.min(100, 100 - nullPct));
  const distinctCount = selectedStats?.distinct_count ?? selectedMeta?.distinct_count ?? 0;
  const uniquenessPct =
    selectedStats?.uniqueness_percentage ??
    Math.round((distinctCount / totalRows) * 100 * 100) / 100;

  // Max count for histogram visualization normalization
  const maxHistogramCount = useMemo(() => {
    if (!selectedStats?.histogram || selectedStats.histogram.length === 0) return 1;
    return Math.max(...selectedStats.histogram.map((b) => b.count), 1);
  }, [selectedStats?.histogram]);

  // Max count for frequent values visualization normalization
  const maxFrequentCount = useMemo(() => {
    if (!selectedStats?.most_frequent_values || selectedStats.most_frequent_values.length === 0) return 1;
    return Math.max(...selectedStats.most_frequent_values.map((v) => v.count), 1);
  }, [selectedStats?.most_frequent_values]);

  const isNumeric =
    role === 'MEASURE' ||
    (selectedStats && 'mean' in selectedStats && selectedStats.mean !== null);

  const isCategorical =
    role === 'DIMENSION' ||
    (selectedStats && selectedStats.most_frequent_values && selectedStats.most_frequent_values.length > 0 && !isNumeric);

  const isDatetime =
    role === 'DATETIME' ||
    (selectedStats && selectedStats.min_datetime !== undefined && selectedStats.min_datetime !== null);

  const isBoolean =
    selectedStats &&
    (selectedStats.true_count !== undefined ||
      selectedStats.detected_datatype.toLowerCase().includes('bool'));

  const semanticDescription = useMemo(() => {
    if (role === 'MEASURE') {
      return 'Numeric measure suitable for aggregation, mathematical modeling, and trend analysis.';
    }
    if (role === 'DIMENSION') {
      return 'Categorical dimension suitable for grouping, filtering, and categorical breakdowns.';
    }
    if (role === 'DATETIME') {
      return 'Temporal timestamp suitable for time-series analysis and chronological grouping.';
    }
    if (role === 'IDENTIFIER') {
      return 'Unique identifier suitable for row referencing, entity matching, and joins.';
    }
    return 'Column with general unstructured or unclassified values.';
  }, [role]);

  return (
    <div className="space-y-6">
      {/* 1. Dataset-Level Profiling Summary Header */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-muted-foreground font-medium">Rows</span>
          <div className="text-lg font-bold text-foreground">{metadata.row_count.toLocaleString()}</div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-muted-foreground font-medium">Columns</span>
          <div className="text-lg font-bold text-foreground">{metadata.column_count}</div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-muted-foreground font-medium">Missing values</span>
          <div className={`text-lg font-bold ${(profile?.dataset_summary?.overall_missing_percentage ?? 0) > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {profile?.dataset_summary?.overall_missing_percentage ?? 0}%
          </div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-muted-foreground font-medium">Duplicate rows</span>
          <div className={`text-lg font-bold ${(profile?.dataset_summary?.duplicate_row_count ?? 0) > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {profile?.dataset_summary?.duplicate_row_count ?? 0}
          </div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-primary font-medium">Measures</span>
          <div className="text-lg font-bold text-foreground">{roleCounts.measures}</div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-blue-500 font-medium">Dimensions</span>
          <div className="text-lg font-bold text-foreground">{roleCounts.dimensions}</div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-purple-500 font-medium">Dates</span>
          <div className="text-lg font-bold text-foreground">{roleCounts.datetimes}</div>
        </Card>
        <Card className="p-3.5 space-y-1">
          <span className="text-xs text-amber-500 font-medium">Identifiers</span>
          <div className="text-lg font-bold text-foreground">{roleCounts.identifiers}</div>
        </Card>
      </div>

      {/* 2. Interactive Column Explorer (Master-Detail 2-Pane Layout) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Pane: Column List & Filter (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          <Card className="p-3.5 border border-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">
                Column Explorer
              </span>
              <span className="text-xs text-muted-foreground">
                {filteredColumns.length} of {columnsList.length}
              </span>
            </div>

            {/* Role Filter Tabs */}
            <div className="flex flex-wrap gap-1.5">
              {(['ALL', 'MEASURE', 'DIMENSION', 'DATETIME', 'IDENTIFIER'] as RoleFilter[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setSelectedRole(r)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                    selectedRole === r
                      ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                      : 'bg-surface-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {r === 'ALL' ? 'All' : r === 'MEASURE' ? 'Measures' : r === 'DIMENSION' ? 'Dimensions' : r === 'DATETIME' ? 'Dates' : 'Identifiers'}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search column names..."
                className="w-full text-xs bg-surface border border-border rounded-md pl-8 pr-3 py-1.5 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
              />
            </div>
          </Card>

          {/* Column Selection Scrollable List */}
          <div className="space-y-2 max-h-[620px] overflow-y-auto pr-1">
            {filteredColumns.map((col) => {
              const evidence = semanticProfile?.column_evidences[col.original_name];
              const stats = profile?.column_statistics[col.original_name];
              const colRole = evidence?.candidate_role || 'UNKNOWN';
              const isSelected = col.original_name === activeColName;
              const hasMissing = (stats?.null_count ?? 0) > 0;

              return (
                <button
                  key={col.original_name}
                  onClick={() => setSelectedColumnName(col.original_name)}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex items-center justify-between gap-3 ${
                    isSelected
                      ? 'bg-primary-soft/40 border-primary text-foreground shadow-xs'
                      : 'bg-surface border-border hover:bg-surface-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="min-w-0 space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground truncate">
                        {col.original_name}
                      </span>
                      {stats?.is_unique && (
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" title="Unique values" />
                      )}
                      {stats?.is_constant && (
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 shrink-0" title="Constant value" />
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="font-mono text-3xs">{col.detected_datatype}</span>
                      <span>•</span>
                      <span className={hasMissing ? 'text-amber-500 font-medium' : 'text-emerald-500 font-medium'}>
                        {stats?.null_percentage ? `${stats.null_percentage}% missing` : '100% complete'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <Badge
                      variant={
                        colRole === 'MEASURE'
                          ? 'teal'
                          : colRole === 'DIMENSION'
                          ? 'blue'
                          : colRole === 'DATETIME'
                          ? 'purple'
                          : colRole === 'IDENTIFIER'
                          ? 'amber'
                          : 'slate'
                      }
                      size="xs"
                    >
                      {colRole === 'MEASURE'
                        ? 'Measure'
                        : colRole === 'DIMENSION'
                        ? 'Dimension'
                        : colRole === 'DATETIME'
                        ? 'Date'
                        : colRole === 'IDENTIFIER'
                        ? 'ID'
                        : 'Other'}
                    </Badge>
                    <ChevronRight className={`w-4 h-4 transition-transform ${isSelected ? 'text-primary translate-x-0.5' : 'text-muted-foreground'}`} />
                  </div>
                </button>
              );
            })}

            {filteredColumns.length === 0 && (
              <div className="p-8 text-center text-xs text-muted-foreground bg-surface border border-border rounded-lg">
                No matching columns found.
              </div>
            )}
          </div>
        </div>

        {/* Right Pane: Selected Column Deep Dive (8 cols) */}
        <div className="lg:col-span-8 space-y-5">
          {selectedMeta ? (
            <>
              {/* 1. Column Overview Card */}
              <Card className="p-5 border border-border space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h2 className="text-xl font-bold text-foreground tracking-tight">
                        {selectedMeta.original_name}
                      </h2>
                      <Badge variant={roleBadgeVariant} size="sm">
                        {roleDisplayLabel}
                      </Badge>
                      <span className="text-xs font-mono text-muted-foreground px-2 py-0.5 bg-surface-muted rounded border border-border">
                        {selectedMeta.detected_datatype}
                      </span>
                    </div>
                    {selectedEvidence && (
                      <p className="text-xs text-muted-foreground">
                        Classified as <strong className="text-foreground">{roleDisplayLabel}</strong> with{' '}
                        <strong className="text-foreground">{Math.round(selectedEvidence.confidence * 100)}% confidence</strong> ({selectedEvidence.confidence_level.toLowerCase()} confidence).
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-3 text-xs text-muted-foreground bg-surface-muted/40 px-3.5 py-2 rounded-lg border border-border">
                    <div>
                      <span className="text-3xs text-muted-foreground block">Distinct</span>
                      <strong className="text-foreground text-sm">{distinctCount.toLocaleString()}</strong>
                    </div>
                    <div className="h-6 w-px bg-border" />
                    <div>
                      <span className="text-3xs text-muted-foreground block">Uniqueness</span>
                      <strong className="text-foreground text-sm">{uniquenessPct}%</strong>
                    </div>
                  </div>
                </div>

                {/* 2. Completeness Progress Bar & Core Metrics */}
                <div className="pt-3 border-t border-border/70 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">Completeness</span>
                    <span className="text-muted-foreground">
                      <strong className="text-foreground">{nonNullCount.toLocaleString()}</strong> of {totalRows.toLocaleString()} values ({completenessPct}%)
                    </span>
                  </div>
                  <div className="w-full bg-surface-muted h-2.5 rounded-full overflow-hidden flex">
                    <div
                      className="bg-emerald-500 h-full rounded-full transition-all"
                      style={{ width: `${completenessPct}%` }}
                      title={`${completenessPct}% complete`}
                    />
                    {nullPct > 0 && (
                      <div
                        className="bg-amber-500 h-full transition-all"
                        style={{ width: `${nullPct}%` }}
                        title={`${nullPct}% missing`}
                      />
                    )}
                  </div>
                  {nullPct > 0 && (
                    <p className="text-2xs text-amber-500 font-medium">
                      {nullCount.toLocaleString()} missing values ({nullPct}%)
                    </p>
                  )}
                </div>
              </Card>

              {/* 3. Distribution Section */}
              {/* 3A. NUMERIC STATISTICS & DISTRIBUTION */}
              {isNumeric && selectedStats && (
                <div className="space-y-4">
                  {/* Summary Metric Grid */}
                  <Card className="p-5 border border-border space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-foreground">
                        Summary Statistics
                      </h3>
                      <span className="text-2xs text-muted-foreground">
                        Calculated across {nonNullCount.toLocaleString()} numeric values
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Minimum</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.min !== null ? selectedStats.min : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Median</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.median !== null ? selectedStats.median : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Mean (Average)</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.mean !== null ? Number(selectedStats.mean).toFixed(2) : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Maximum</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.max !== null ? selectedStats.max : '—'}</div>
                      </div>

                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Std Deviation</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.std !== null ? Number(selectedStats.std).toFixed(2) : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">25th Percentile (Q1)</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.q25 !== null ? selectedStats.q25 : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">75th Percentile (Q3)</span>
                        <div className="text-sm font-bold text-foreground mt-0.5">{selectedStats.q75 !== null ? selectedStats.q75 : '—'}</div>
                      </div>
                      <div className="p-3 bg-surface-muted/40 border border-border rounded-lg">
                        <span className="text-2xs text-muted-foreground font-medium block">Zero Count</span>
                        <div className={`text-sm font-bold mt-0.5 ${selectedStats.zero_count ? 'text-amber-500' : 'text-foreground'}`}>
                          {selectedStats.zero_count ?? 0}
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Visual: Distribution Histogram */}
                  {selectedStats.histogram && selectedStats.histogram.length > 0 && (
                    <Card className="p-5 border border-border space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <BarChart3 className="w-4 h-4 text-primary" />
                          <h3 className="text-xs font-bold text-foreground">
                            Distribution Histogram
                          </h3>
                        </div>
                        <span className="text-2xs text-muted-foreground">
                          10 equal-width bins
                        </span>
                      </div>

                      <div className="pt-3">
                        {/* Bars Container */}
                        <div className="flex items-end gap-2 h-40 border-b border-border pb-1">
                          {selectedStats.histogram.map((bin, idx) => {
                            const heightPct = Math.max(4, Math.round((bin.count / maxHistogramCount) * 100));
                            return (
                              <div
                                key={idx}
                                className="flex-1 flex flex-col items-center group relative h-full justify-end"
                              >
                                {/* Tooltip on Hover */}
                                <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-8 bg-surface-elevated text-foreground border border-border text-2xs px-2.5 py-1 rounded pointer-events-none whitespace-nowrap z-20 shadow-md">
                                  [{bin.bin_start} to {bin.bin_end}]: {bin.count.toLocaleString()} rows
                                </div>

                                <div
                                  className="w-full bg-primary opacity-80 hover:opacity-100 rounded-t transition-all"
                                  style={{ height: `${heightPct}%` }}
                                />
                              </div>
                            );
                          })}
                        </div>

                        {/* Histogram X-Axis Bin Ranges */}
                        <div className="flex justify-between text-2xs text-muted-foreground pt-2">
                          <span>{selectedStats.histogram[0]?.bin_start}</span>
                          <span>{selectedStats.histogram[Math.floor(selectedStats.histogram.length / 2)]?.bin_start}</span>
                          <span>{selectedStats.histogram[selectedStats.histogram.length - 1]?.bin_end}</span>
                        </div>
                      </div>
                    </Card>
                  )}
                </div>
              )}

              {/* 3B. CATEGORICAL FREQUENCIES */}
              {isCategorical && selectedStats && selectedStats.most_frequent_values && (
                <Card className="p-5 border border-border space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-border">
                    <div className="flex items-center gap-2">
                      <Tag className="w-4 h-4 text-blue-500" />
                      <h3 className="text-xs font-bold text-foreground">
                        Top Frequent Values ({selectedStats.most_frequent_values.length} distinct values)
                      </h3>
                    </div>
                    <span className="text-2xs text-muted-foreground">
                      Ordered by occurrence count
                    </span>
                  </div>

                  <div className="space-y-3">
                    {selectedStats.most_frequent_values.map((item, idx) => {
                      const barWidth = Math.max(2, Math.round((item.count / maxFrequentCount) * 100));
                      const itemPct = nonNullCount > 0 ? ((item.count / nonNullCount) * 100).toFixed(1) : '0';

                      return (
                        <div key={idx} className="space-y-1.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-medium text-foreground truncate max-w-sm">
                              {item.value === '' ? '<Empty String>' : item.value === null ? '<Null>' : String(item.value)}
                            </span>
                            <span className="text-muted-foreground text-xs">
                              <strong className="text-foreground">{item.count.toLocaleString()}</strong> ({itemPct}%)
                            </span>
                          </div>
                          <div className="w-full bg-surface-muted h-2 rounded-full overflow-hidden">
                            <div
                              className="bg-blue-500 h-full rounded-full transition-all"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}

                    {selectedStats.most_frequent_values.length === 0 && (
                      <div className="p-6 text-center text-xs text-muted-foreground">
                        No distinct value frequency records available.
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {/* 3C. DATETIME STATISTICS */}
              {isDatetime && selectedStats && (
                <Card className="p-5 border border-border space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-border">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-purple-500" />
                      <h3 className="text-xs font-bold text-foreground">
                        Temporal Coverage & Dates Span
                      </h3>
                    </div>
                    <Badge variant="purple" size="xs">
                      {selectedStats.distinct_dates_count ?? 0} distinct dates
                    </Badge>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-3.5 bg-surface-muted/40 border border-border rounded-lg">
                      <span className="text-2xs text-muted-foreground font-medium block">Earliest Timestamp</span>
                      <div className="text-xs font-bold text-foreground mt-1 font-mono">{selectedStats.min_datetime || '—'}</div>
                    </div>

                    <div className="p-3.5 bg-surface-muted/40 border border-border rounded-lg">
                      <span className="text-2xs text-muted-foreground font-medium block">Latest Timestamp</span>
                      <div className="text-xs font-bold text-foreground mt-1 font-mono">{selectedStats.max_datetime || '—'}</div>
                    </div>

                    <div className="p-3.5 bg-surface-muted/40 border border-border rounded-lg">
                      <span className="text-2xs text-muted-foreground font-medium block">Temporal Span</span>
                      <div className="text-xs font-bold text-purple-600 dark:text-purple-400 mt-1">
                        {selectedStats.temporal_span_days !== undefined && selectedStats.temporal_span_days !== null
                          ? `${selectedStats.temporal_span_days} days`
                          : '—'}
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* 3D. BOOLEAN DISTRIBUTION */}
              {isBoolean && selectedStats && (
                <Card className="p-5 border border-border space-y-3">
                  <h3 className="text-xs font-bold text-foreground">
                    Boolean Distribution
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                      <span className="text-2xs text-emerald-600 dark:text-emerald-400 font-medium block">True count</span>
                      <div className="text-base font-bold text-foreground mt-1">{selectedStats.true_count ?? 0}</div>
                    </div>
                    <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg">
                      <span className="text-2xs text-rose-600 dark:text-rose-400 font-medium block">False count</span>
                      <div className="text-base font-bold text-foreground mt-1">{selectedStats.false_count ?? 0}</div>
                    </div>
                  </div>
                </Card>
              )}

              {/* 4. Semantic Meaning Section & Orchestrator Role Usage */}
              <Card className="p-5 border border-border space-y-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" />
                  <h3 className="text-xs font-bold text-foreground">
                    Semantic Meaning & Orchestrator Role
                  </h3>
                </div>
                <p className="text-xs text-foreground leading-relaxed">
                  {semanticDescription}
                </p>

                <div className="p-3 bg-primary-soft/40 rounded-md border border-primary/20 text-2xs space-y-1 font-mono">
                  <div className="font-semibold text-primary">Orchestrator Role Usage:</div>
                  <p className="text-muted-foreground leading-relaxed">
                    {role === 'MEASURE' && 'Eligible for aggregations (SUM, AVG, COUNT, MIN, MAX) in candidate query generation.'}
                    {role === 'DIMENSION' && 'Eligible for GROUP BY dimensional grouping and categorical breakdowns.'}
                    {role === 'DATETIME' && 'Eligible for temporal bucketing (YEAR, MONTH, DAY) in trend analysis.'}
                    {role === 'IDENTIFIER' && 'Reserved for entity lookup, cardinality counting, or row identification.'}
                    {role === 'UNKNOWN' && 'Exempt from automated aggregations pending manual role mapping.'}
                  </p>
                </div>
              </Card>

              {/* 5. Observations & Quality Flags */}
              {selectedStats && selectedStats.observations && selectedStats.observations.length > 0 && (
                <Card className="p-5 border border-border space-y-3">
                  <div className="flex items-center gap-2">
                    <Info className="w-4 h-4 text-amber-500" />
                    <h3 className="text-xs font-bold text-foreground">
                      Observations & Quality Flags
                    </h3>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {selectedStats.observations.map((obs, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-1 bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 rounded-md text-xs font-medium"
                      >
                        {obs}
                      </span>
                    ))}
                  </div>
                </Card>
              )}

              {/* 6. Technical Evidence (Collapsible / Secondary Section) */}
              <Card className="border border-border overflow-hidden">
                <button
                  onClick={() => setShowTechnicalEvidence(!showTechnicalEvidence)}
                  className="w-full p-4 flex items-center justify-between text-left hover:bg-surface-muted/40 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-muted-foreground" />
                    <span className="text-xs font-semibold text-foreground">
                      Technical Evidence & Classification Signals
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-2xs text-muted-foreground">
                    <span>{showTechnicalEvidence ? 'Hide details' : 'Show details'}</span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${showTechnicalEvidence ? 'rotate-180' : ''}`} />
                  </div>
                </button>

                {showTechnicalEvidence && (
                  <div className="p-5 pt-0 border-t border-border space-y-4 text-xs">
                    {selectedEvidence && selectedEvidence.evidence && selectedEvidence.evidence.length > 0 && (
                      <div className="space-y-2 pt-4">
                        <span className="text-2xs font-semibold text-muted-foreground block uppercase tracking-wider font-mono">
                          Rule-Based Evidence Signals
                        </span>
                        <div className="space-y-1.5">
                          {selectedEvidence.evidence.map((ev, idx) => (
                            <div
                              key={idx}
                              className="flex items-start gap-2 p-2 bg-surface-muted rounded border border-border text-2xs font-mono text-foreground"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0 mt-0.5" />
                              <span className="leading-snug">{ev}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-2xs">
                      <div className="p-2.5 bg-surface-muted/50 border border-border rounded-md">
                        <span className="text-muted-foreground block">Raw Data Type</span>
                        <span className="font-mono font-bold text-foreground mt-0.5 block">{selectedMeta.detected_datatype}</span>
                      </div>
                      <div className="p-2.5 bg-surface-muted/50 border border-border rounded-md">
                        <span className="text-muted-foreground block">Classification Role</span>
                        <span className="font-mono font-bold text-foreground mt-0.5 block">{role}</span>
                      </div>
                      <div className="p-2.5 bg-surface-muted/50 border border-border rounded-md">
                        <span className="text-muted-foreground block">Confidence Score</span>
                        <span className="font-mono font-bold text-foreground mt-0.5 block">
                          {selectedEvidence ? `${(selectedEvidence.confidence * 100).toFixed(1)}%` : '—'}
                        </span>
                      </div>
                      <div className="p-2.5 bg-surface-muted/50 border border-border rounded-md">
                        <span className="text-muted-foreground block">Uniqueness Ratio</span>
                        <span className="font-mono font-bold text-foreground mt-0.5 block">{uniquenessPct}%</span>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            </>
          ) : (
            <Card className="p-12 text-center text-xs text-muted-foreground">
              Select a column on the left to inspect its profiling statistics.
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};

