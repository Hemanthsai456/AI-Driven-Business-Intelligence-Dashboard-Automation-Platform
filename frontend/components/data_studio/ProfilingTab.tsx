'use client';

import React, { useState, useMemo } from 'react';
import {
  Activity,
  Search,
  Filter,
  TrendingUp,
  Tag,
  Calendar,
  Key,
  CheckSquare,
  BarChart3,
  Layers,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Hash,
  ChevronRight,
  Info,
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

  return (
    <div className="space-y-6">
      {/* 1. Dataset-Level Profiling Summary Header */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2.5">
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Rows</span>
          <div className="text-base font-bold font-mono text-foreground">{metadata.row_count.toLocaleString()}</div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Columns</span>
          <div className="text-base font-bold font-mono text-foreground">{metadata.column_count}</div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Duplicates</span>
          <div className={`text-base font-bold font-mono ${(profile?.dataset_summary?.duplicate_row_count ?? 0) > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {profile?.dataset_summary?.duplicate_row_count ?? 0}
          </div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Missingness</span>
          <div className={`text-base font-bold font-mono ${(profile?.dataset_summary?.overall_missing_percentage ?? 0) > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {profile?.dataset_summary?.overall_missing_percentage ?? 0}%
          </div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-teal-600 dark:text-teal-400 font-mono">Measures</span>
          <div className="text-base font-bold font-mono text-foreground">{roleCounts.measures}</div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-blue-600 dark:text-blue-400 font-mono">Dimensions</span>
          <div className="text-base font-bold font-mono text-foreground">{roleCounts.dimensions}</div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-purple-600 dark:text-purple-400 font-mono">Datetimes</span>
          <div className="text-base font-bold font-mono text-foreground">{roleCounts.datetimes}</div>
        </Card>
        <Card className="p-3 space-y-0.5">
          <span className="text-3xs uppercase tracking-wider text-amber-600 dark:text-amber-400 font-mono">Identifiers</span>
          <div className="text-base font-bold font-mono text-foreground">{roleCounts.identifiers}</div>
        </Card>
      </div>

      {/* 2. Interactive Column Explorer (Master-Detail 2-Pane Layout) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Pane: Column List & Filter (4 cols) */}
        <div className="lg:col-span-4 space-y-3">
          <Card className="p-3.5 border border-border space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                Column Explorer
              </span>
              <span className="text-3xs font-mono text-muted-foreground">
                {filteredColumns.length} of {columnsList.length}
              </span>
            </div>

            {/* Role Filter Tabs */}
            <div className="flex flex-wrap gap-1">
              {(['ALL', 'MEASURE', 'DIMENSION', 'DATETIME', 'IDENTIFIER'] as RoleFilter[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setSelectedRole(r)}
                  className={`px-2 py-0.5 text-3xs font-mono font-medium rounded transition-colors ${
                    selectedRole === r
                      ? 'bg-primary text-primary-foreground font-semibold'
                      : 'bg-surface-muted text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {r === 'ALL' ? 'All' : r === 'MEASURE' ? 'Measures' : r === 'DIMENSION' ? 'Dims' : r === 'DATETIME' ? 'Dates' : 'Keys'}
                </button>
              ))}
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search columns..."
                className="w-full text-xs bg-surface border border-border rounded pl-8 pr-3 py-1 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary font-mono"
              />
            </div>
          </Card>

          {/* Column Selection Scrollable List */}
          <div className="space-y-1.5 max-h-[580px] overflow-y-auto pr-1">
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
                  className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-center justify-between ${
                    isSelected
                      ? 'bg-primary-soft/40 border-primary text-foreground shadow-xs'
                      : 'bg-surface border-border hover:bg-surface-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-bold font-mono truncate text-foreground">
                        {col.original_name}
                      </span>
                      {stats?.is_unique && (
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" title="Unique values" />
                      )}
                      {stats?.is_constant && (
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400" title="Constant value" />
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-3xs font-mono text-muted-foreground">
                      <span>{col.detected_datatype}</span>
                      <span>•</span>
                      <span className={hasMissing ? 'text-amber-500' : 'text-emerald-500'}>
                        {stats?.null_percentage ? `${stats.null_percentage}% null` : '100% valid'}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 ml-2">
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
                      {colRole}
                    </Badge>
                    <ChevronRight className={`w-3.5 h-3.5 transition-transform ${isSelected ? 'text-primary translate-x-0.5' : 'text-muted-foreground'}`} />
                  </div>
                </button>
              );
            })}

            {filteredColumns.length === 0 && (
              <div className="p-6 text-center text-xs text-muted-foreground font-mono bg-surface border border-border rounded-lg">
                No matching columns found.
              </div>
            )}
          </div>
        </div>

        {/* Right Pane: Selected Column Deep Dive (8 cols) */}
        <div className="lg:col-span-8 space-y-5">
          {selectedMeta ? (
            <>
              {/* Column Title & Role Badge Banner */}
              <Card className="p-5 border border-border space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2.5">
                      <h2 className="text-lg font-bold font-mono text-foreground tracking-tight">
                        {selectedMeta.original_name}
                      </h2>
                      <Badge variant={roleBadgeVariant} size="sm">
                        {role}
                      </Badge>
                      <Badge variant="slate" size="xs">
                        {selectedMeta.detected_datatype}
                      </Badge>
                    </div>
                    {selectedEvidence && (
                      <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                        <span>Confidence: <strong className="text-foreground">{Math.round(selectedEvidence.confidence * 100)}%</strong> ({selectedEvidence.confidence_level})</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground bg-surface-muted/50 px-3 py-1.5 rounded-md border border-border">
                    <span>Distinct: <strong className="text-foreground">{distinctCount.toLocaleString()}</strong></span>
                    <span>•</span>
                    <span>Uniqueness: <strong className="text-foreground">{uniquenessPct}%</strong></span>
                  </div>
                </div>

                {/* Evidence & Semantic Reasoning Pills */}
                {selectedEvidence && selectedEvidence.evidence && selectedEvidence.evidence.length > 0 && (
                  <div className="pt-2 border-t border-border/60">
                    <span className="text-3xs uppercase tracking-wider font-mono text-muted-foreground block mb-1.5">
                      Semantic Classification Evidence
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedEvidence.evidence.map((ev, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 bg-surface-muted border border-border rounded text-3xs font-mono text-foreground"
                        >
                          {ev}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Card>

              {/* Data Completeness & Cardinality Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Card className="p-3.5 space-y-1">
                  <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Total Count</span>
                  <div className="text-base font-bold font-mono text-foreground">{totalRows.toLocaleString()}</div>
                  <span className="text-3xs text-muted-foreground font-mono">100% allocation</span>
                </Card>

                <Card className="p-3.5 space-y-1">
                  <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Non-Null Values</span>
                  <div className="text-base font-bold font-mono text-emerald-500">{nonNullCount.toLocaleString()}</div>
                  <span className="text-3xs text-muted-foreground font-mono">{completenessPct}% complete</span>
                </Card>

                <Card className="p-3.5 space-y-1">
                  <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Missing / Nulls</span>
                  <div className={`text-base font-bold font-mono ${nullCount > 0 ? 'text-amber-500' : 'text-foreground'}`}>
                    {nullCount.toLocaleString()}
                  </div>
                  <span className="text-3xs text-muted-foreground font-mono">{nullPct}% missing</span>
                </Card>

                <Card className="p-3.5 space-y-1">
                  <span className="text-3xs uppercase tracking-wider text-muted-foreground font-mono">Distinct Values</span>
                  <div className="text-base font-bold font-mono text-foreground">{distinctCount.toLocaleString()}</div>
                  <span className="text-3xs text-muted-foreground font-mono">{uniquenessPct}% unique</span>
                </Card>
              </div>

              {/* 3A. NUMERIC STATISTICS & DISTRIBUTION */}
              {isNumeric && selectedStats && (
                <div className="space-y-4">
                  {/* Summary Metric Grid */}
                  <Card className="p-4 border border-border space-y-3">
                    <span className="text-xs font-bold uppercase tracking-wider font-mono text-muted-foreground block">
                      Summary Statistics
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Minimum</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.min !== null ? selectedStats.min : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Median (Q2)</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.median !== null ? selectedStats.median : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Mean (Average)</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.mean !== null ? Number(selectedStats.mean).toFixed(2) : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Maximum</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.max !== null ? selectedStats.max : '—'}</div>
                      </div>

                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Std Deviation</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.std !== null ? Number(selectedStats.std).toFixed(2) : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Q1 (25th %)</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.q25 !== null ? selectedStats.q25 : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Q3 (75th %)</span>
                        <div className="text-sm font-bold text-foreground">{selectedStats.q75 !== null ? selectedStats.q75 : '—'}</div>
                      </div>
                      <div className="p-2.5 bg-surface-muted/40 border border-border rounded">
                        <span className="text-3xs text-muted-foreground uppercase">Zero Count</span>
                        <div className={`text-sm font-bold ${selectedStats.zero_count ? 'text-amber-500' : 'text-foreground'}`}>
                          {selectedStats.zero_count ?? 0}
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Visual 1: 10-Bin Distribution Histogram */}
                  {selectedStats.histogram && selectedStats.histogram.length > 0 && (
                    <Card className="p-5 border border-border space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <BarChart3 className="w-4 h-4 text-primary" />
                          <h3 className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                            10-Bin Distribution Histogram
                          </h3>
                        </div>
                        <span className="text-3xs font-mono text-muted-foreground">
                          Equal-width deterministic binning
                        </span>
                      </div>

                      <div className="pt-2">
                        {/* Bars Container */}
                        <div className="flex items-end gap-1.5 h-36 border-b border-border pb-1">
                          {selectedStats.histogram.map((bin, idx) => {
                            const heightPct = Math.max(4, Math.round((bin.count / maxHistogramCount) * 100));
                            return (
                              <div
                                key={idx}
                                className="flex-1 flex flex-col items-center group relative h-full justify-end"
                              >
                                {/* Tooltip on Hover */}
                                <div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-8 bg-foreground text-background text-3xs font-mono px-2 py-0.5 rounded pointer-events-none whitespace-nowrap z-20 shadow-md">
                                  [{bin.bin_start} – {bin.bin_end}]: {bin.count.toLocaleString()} rows
                                </div>

                                <div
                                  className="w-full bg-primary/70 hover:bg-primary rounded-t transition-all"
                                  style={{ height: `${heightPct}%` }}
                                />
                              </div>
                            );
                          })}
                        </div>

                        {/* Histogram X-Axis Bin Ranges */}
                        <div className="flex justify-between text-3xs font-mono text-muted-foreground pt-1.5">
                          <span>{selectedStats.histogram[0]?.bin_start}</span>
                          <span>{selectedStats.histogram[Math.floor(selectedStats.histogram.length / 2)]?.bin_start}</span>
                          <span>{selectedStats.histogram[selectedStats.histogram.length - 1]?.bin_end}</span>
                        </div>
                      </div>
                    </Card>
                  )}
                </div>
              )}

              {/* 3B. CATEGORICAL / TEXT STATISTICS & FREQUENCIES */}
              {isCategorical && selectedStats && selectedStats.most_frequent_values && (
                <Card className="p-5 border border-border space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-border">
                    <div className="flex items-center gap-2">
                      <Tag className="w-4 h-4 text-blue-500" />
                      <h3 className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                        Top Categorical Frequencies ({selectedStats.most_frequent_values.length} top values)
                      </h3>
                    </div>
                    <span className="text-3xs font-mono text-muted-foreground">
                      Sorted deterministically by frequency
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    {selectedStats.most_frequent_values.map((item, idx) => {
                      const barWidth = Math.max(2, Math.round((item.count / maxFrequentCount) * 100));
                      const itemPct = nonNullCount > 0 ? ((item.count / nonNullCount) * 100).toFixed(1) : '0';

                      return (
                        <div key={idx} className="space-y-1">
                          <div className="flex items-center justify-between text-xs font-mono">
                            <span className="font-semibold text-foreground truncate max-w-xs">
                              {item.value === '' ? '<Empty String>' : item.value === null ? '<Null>' : String(item.value)}
                            </span>
                            <span className="text-muted-foreground text-2xs">
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
                      <div className="p-4 text-center text-xs text-muted-foreground font-mono">
                        No distinct value frequency records found.
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {/* 3C. DATETIME STATISTICS & TEMPORAL COVERAGE */}
              {isDatetime && selectedStats && (
                <Card className="p-5 border border-border space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-border">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-purple-500" />
                      <h3 className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                        Temporal Coverage & Dates Span
                      </h3>
                    </div>
                    <Badge variant="purple" size="xs">
                      {selectedStats.distinct_dates_count ?? 0} distinct dates
                    </Badge>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono">
                    <div className="p-3 bg-surface-muted/40 border border-border rounded-md">
                      <span className="text-3xs text-muted-foreground uppercase block">Earliest Timestamp</span>
                      <div className="text-xs font-bold text-foreground mt-0.5">{selectedStats.min_datetime || '—'}</div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-md">
                      <span className="text-3xs text-muted-foreground uppercase block">Latest Timestamp</span>
                      <div className="text-xs font-bold text-foreground mt-0.5">{selectedStats.max_datetime || '—'}</div>
                    </div>

                    <div className="p-3 bg-surface-muted/40 border border-border rounded-md">
                      <span className="text-3xs text-muted-foreground uppercase block">Temporal Span (Days)</span>
                      <div className="text-xs font-bold text-purple-600 dark:text-purple-400 mt-0.5">
                        {selectedStats.temporal_span_days !== undefined && selectedStats.temporal_span_days !== null
                          ? `${selectedStats.temporal_span_days} days`
                          : '—'}
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* 3D. BOOLEAN STATISTICS */}
              {isBoolean && selectedStats && (
                <Card className="p-5 border border-border space-y-3">
                  <span className="text-xs font-bold uppercase tracking-wider font-mono text-muted-foreground block">
                    Boolean Distribution
                  </span>
                  <div className="grid grid-cols-2 gap-3 font-mono">
                    <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-md">
                      <span className="text-3xs text-emerald-600 dark:text-emerald-400 uppercase font-semibold">True Count</span>
                      <div className="text-sm font-bold text-foreground">{selectedStats.true_count ?? 0}</div>
                    </div>
                    <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-md">
                      <span className="text-3xs text-rose-600 dark:text-rose-400 uppercase font-semibold">False Count</span>
                      <div className="text-sm font-bold text-foreground">{selectedStats.false_count ?? 0}</div>
                    </div>
                  </div>
                </Card>
              )}

              {/* 4. Column Observations & Quality Flags */}
              {selectedStats && selectedStats.observations && selectedStats.observations.length > 0 && (
                <Card className="p-4 border border-border space-y-2">
                  <div className="flex items-center gap-2 text-xs font-bold text-foreground font-mono">
                    <Info className="w-4 h-4 text-primary" />
                    <span>Observations for {selectedMeta.original_name}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {selectedStats.observations.map((obs, idx) => (
                      <Badge key={idx} variant="amber" size="xs">
                        {obs}
                      </Badge>
                    ))}
                  </div>
                </Card>
              )}
            </>
          ) : (
            <Card className="p-12 text-center text-xs text-muted-foreground font-mono">
              Select a column on the left to inspect its profiling statistics.
            </Card>
          )}
        </div>
      </div>
    </div>
  );
};
