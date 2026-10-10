'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  Database,
  ChevronDown,
  ChevronUp,
  Table as TableIcon,
  Columns,
  Hash,
  Calendar,
  Type,
  Check,
  Search,
  CheckCircle2,
  AlertCircle,
  Layers,
  RotateCcw,
} from 'lucide-react';
import { ColumnMetadata, DatasetMetadata, DataPreviewResponse } from '../lib/types';
import { getDatasetMetadata, getDatasetPreview } from '../lib/api';
import { Badge } from './Badge';

export interface DatasetExplorerProps {
  datasetId?: string;
  metadata?: DatasetMetadata | null;
  previewData?: DataPreviewResponse | null;
  className?: string;
}

export const DatasetExplorer: React.FC<DatasetExplorerProps> = ({
  datasetId,
  metadata,
  previewData,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  // Default to 'preview' (5-row data preview) as requested in Phase 2 refinement
  const [activeSubTab, setActiveSubTab] = useState<'preview' | 'columns' | 'both'>('preview');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [localMetadata, setLocalMetadata] = useState<DatasetMetadata | null>(metadata || null);
  const [localPreview, setLocalPreview] = useState<DataPreviewResponse | null>(previewData || null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTrigger, setRetryTrigger] = useState<number>(0);

  // Active data resolution: prioritize props, fallback to local fetch
  const activeMeta = metadata || localMetadata;
  const activePrev = previewData || localPreview;

  // Sync props to state if provided by parent
  useEffect(() => {
    if (metadata) {
      setLocalMetadata(metadata);
      setIsLoading(false);
      setError(null);
    }
  }, [metadata]);

  useEffect(() => {
    if (previewData) {
      setLocalPreview(previewData);
    }
  }, [previewData]);

  // Reset local state when datasetId changes
  useEffect(() => {
    if (datasetId) {
      setError(null);
      setSearchQuery('');
      if (!metadata) setLocalMetadata(null);
      if (!previewData) setLocalPreview(null);
    }
  }, [datasetId]);

  // Fetch only when datasetId is present and data is missing
  useEffect(() => {
    if (!datasetId) return;

    // If both metadata and preview are already available via props or local state, no need to fetch
    const hasMeta = !!activeMeta;
    const hasPrev = !!activePrev;

    if (hasMeta && hasPrev) {
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([
      !hasMeta ? getDatasetMetadata(datasetId) : Promise.resolve(null),
      !hasPrev ? getDatasetPreview(datasetId, 5).catch(() => null) : Promise.resolve(null),
    ])
      .then(([fetchedMeta, fetchedPrev]) => {
        if (cancelled) return;
        if (fetchedMeta) setLocalMetadata(fetchedMeta);
        if (fetchedPrev) setLocalPreview(fetchedPrev);
        setError(null);
      })
      .catch((err: any) => {
        if (cancelled) return;
        setError(err?.message || 'Failed to retrieve active cleaned dataset metadata.');
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId, metadata, localMetadata, previewData, localPreview, retryTrigger]);

  const handleRetry = () => {
    setError(null);
    setIsLoading(true);
    setRetryTrigger((prev) => prev + 1);
  };

  // Derive columns dynamically from active metadata or preview
  const columns: ColumnMetadata[] = useMemo(() => {
    if (activeMeta?.columns && activeMeta.columns.length > 0) {
      return activeMeta.columns;
    }
    if (activePrev?.columns && activePrev.columns.length > 0) {
      return activePrev.columns.map((colName) => ({
        original_name: colName,
        normalized_name: colName,
        detected_datatype: activeMeta?.dtypes?.[colName] || 'string',
        semantic_role: 'UNKNOWN',
        null_count: 0,
        null_percentage: 0,
        distinct_count: 0,
        is_unique: false,
        sample_values: [],
      }));
    }
    return [];
  }, [activeMeta, activePrev]);

  // Derive preview rows (strictly first 5 rows)
  const previewRows = useMemo(() => {
    return (activePrev?.rows || []).slice(0, 5);
  }, [activePrev]);

  // Preview columns list
  const previewColumns = useMemo(() => {
    if (activePrev?.columns && activePrev.columns.length > 0) {
      return activePrev.columns;
    }
    return columns.map((c) => c.original_name);
  }, [activePrev, columns]);

  // Filter columns based on user search query for Schema view
  const filteredColumns = useMemo(() => {
    if (!searchQuery.trim()) return columns;
    const q = searchQuery.toLowerCase().trim();
    return columns.filter(
      (c) =>
        c.original_name.toLowerCase().includes(q) ||
        (c.normalized_name && c.normalized_name.toLowerCase().includes(q)) ||
        (c.detected_datatype && c.detected_datatype.toLowerCase().includes(q)) ||
        (c.semantic_role && c.semantic_role.toLowerCase().includes(q))
    );
  }, [columns, searchQuery]);

  // Filter preview columns based on user search query for Preview view
  const filteredPreviewColumns = useMemo(() => {
    if (!searchQuery.trim()) return previewColumns;
    const q = searchQuery.toLowerCase().trim();
    return previewColumns.filter((colName) => colName.toLowerCase().includes(q));
  }, [previewColumns, searchQuery]);

  const totalRowCount = activeMeta?.row_count ?? activePrev?.total_rows ?? (previewRows.length > 0 ? previewRows.length : '—');
  const totalColumnCount = activeMeta?.column_count ?? (columns.length > 0 ? columns.length : '—');

  // Helper to extract representative values dynamically
  const getRepresentativeValues = (col: ColumnMetadata): any[] => {
    // 1. Prefer sample_values from metadata if populated
    if (Array.isArray(col.sample_values) && col.sample_values.length > 0) {
      const nonNullSamples = col.sample_values.filter((v) => v !== null && v !== undefined && v !== '');
      if (nonNullSamples.length > 0) {
        return nonNullSamples.slice(0, 3);
      }
    }

    // 2. Fall back to sampling non-null distinct values from active preview rows
    if (previewRows && previewRows.length > 0) {
      const distinct: any[] = [];
      const seen = new Set<string>();

      for (const row of previewRows) {
        const val = row[col.original_name];
        if (val !== null && val !== undefined && val !== '') {
          const key = typeof val === 'object' ? JSON.stringify(val) : String(val);
          if (!seen.has(key)) {
            seen.add(key);
            distinct.push(val);
            if (distinct.length >= 3) break;
          }
        }
      }
      if (distinct.length > 0) {
        return distinct;
      }
    }

    return [];
  };

  // Helper to format values safely with truncation and tooltips
  const renderCellOrSampleValue = (val: any) => {
    if (val === null || val === undefined) {
      return <span className="text-error/80 italic font-mono text-2xs">null</span>;
    }
    if (typeof val === 'boolean') {
      return (
        <span className={`font-mono text-2xs font-semibold ${val ? 'text-success' : 'text-error'}`}>
          {String(val)}
        </span>
      );
    }
    if (typeof val === 'number') {
      const formatted = Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
      return <span className="font-mono text-2xs text-foreground font-medium">{formatted}</span>;
    }
    const str = String(val);
    const isLong = str.length > 26;
    const truncated = isLong ? `${str.slice(0, 24)}…` : str;
    return (
      <span
        className="font-mono text-2xs text-foreground"
        title={isLong ? str : undefined}
      >
        {truncated}
      </span>
    );
  };

  // Helper for semantic role badge styling
  const renderRoleBadge = (role: string) => {
    const normalizedRole = (role || 'UNKNOWN').toUpperCase();
    switch (normalizedRole) {
      case 'MEASURE':
        return <Badge variant="teal" size="xs" dot>{normalizedRole}</Badge>;
      case 'DIMENSION':
        return <Badge variant="purple" size="xs" dot>{normalizedRole}</Badge>;
      case 'DATETIME':
      case 'TIME':
      case 'TEMPORAL':
        return <Badge variant="amber" size="xs" dot>{normalizedRole}</Badge>;
      case 'IDENTIFIER':
      case 'ID':
        return <Badge variant="slate" size="xs">{normalizedRole}</Badge>;
      default:
        return <Badge variant="slate" size="xs">{normalizedRole}</Badge>;
    }
  };

  // Helper for data type badge styling
  const renderDataTypeBadge = (dtype: string) => {
    const clean = (dtype || 'unknown').toLowerCase();
    let IconComponent = Type;
    let iconClass = 'text-muted-foreground';

    if (clean.includes('int') || clean.includes('float') || clean.includes('num') || clean.includes('decimal')) {
      IconComponent = Hash;
      iconClass = 'text-primary';
    } else if (clean.includes('date') || clean.includes('time')) {
      IconComponent = Calendar;
      iconClass = 'text-attention';
    } else if (clean.includes('bool')) {
      IconComponent = Check;
      iconClass = 'text-success';
    }

    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono bg-surface-muted border border-border text-foreground"
        title={`Detected datatype: ${dtype}`}
      >
        <IconComponent className={`w-3 h-3 ${iconClass}`} />
        <span>{dtype || 'unknown'}</span>
      </span>
    );
  };

  return (
    <div
      className={`bg-surface border border-border rounded-card shadow-xs transition-all overflow-hidden ${className}`}
      data-testid="dataset-explorer"
    >
      {/* 1. Explorer Header Strip (Always Visible, Collapsible Control) */}
      <div
        className="p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none bg-surface hover:bg-surface-muted/20 transition-colors"
        onClick={() => setIsExpanded((prev) => !prev)}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        aria-controls="dataset-explorer-content"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setIsExpanded((prev) => !prev);
          }
        }}
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-soft text-primary flex items-center justify-center shrink-0">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs sm:text-sm font-bold text-foreground">Dataset Explorer</h3>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-3xs font-mono font-semibold bg-success-soft text-success border border-success/30">

              </span>
            </div>
            <p className="text-2xs text-muted-foreground mt-0.5">
              Available schema columns and preview rows for chart configuration
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-center">
          <div className="flex items-center gap-1.5 text-2xs font-mono text-muted-foreground mr-1">
            <span className="px-2 py-0.5 rounded bg-surface-muted border border-border font-medium">
              {typeof totalColumnCount === 'number' ? `${totalColumnCount} columns` : '— columns'}
            </span>
            <span>•</span>
            <span className="px-2 py-0.5 rounded bg-surface-muted border border-border font-medium">
              {typeof totalRowCount === 'number' ? `${totalRowCount.toLocaleString()} rows` : '— rows'}
            </span>
          </div>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded((prev) => !prev);
            }}
            aria-expanded={isExpanded}
            aria-controls="dataset-explorer-content"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-2xs font-semibold rounded-md bg-surface-muted hover:bg-surface border border-border text-foreground transition-colors"
          >
            <span>{isExpanded ? 'Collapse' : 'Expand'}</span>
            {isExpanded ? (
              <ChevronUp className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>

      {/* 2. Collapsible Expanded Content */}
      {isExpanded && (
        <div id="dataset-explorer-content" className="border-t border-border p-3 sm:p-4 space-y-4 bg-surface">
          {/* Loading State: Only shown when active metadata is not yet available */}
          {isLoading && !activeMeta && (
            <div className="py-8 text-center text-xs text-muted-foreground flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span>Loading active cleaned dataset metadata...</span>
            </div>
          )}

          {/* Error State with Retry Button */}
          {error && !activeMeta && (
            <div className="p-4 bg-error-soft text-error border border-error/30 rounded-md text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{error}</span>
              </div>
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center gap-1.5 px-3 py-1 text-2xs font-semibold rounded bg-surface border border-error/40 text-error hover:bg-error-soft transition-colors self-start sm:self-auto"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Retry</span>
              </button>
            </div>
          )}

          {/* Empty State: Only when not loading, no error, and 0 columns */}
          {!isLoading && !error && columns.length === 0 && (
            <div className="py-8 px-4 text-center space-y-2 bg-surface-muted/20 rounded-md border border-dashed border-border">
              <Database className="w-6 h-6 text-muted-foreground mx-auto" />
              <div className="text-xs font-semibold text-foreground">No Columns Available</div>
              <p className="text-2xs text-muted-foreground max-w-sm mx-auto">
                The active cleaned dataset does not contain any detected columns.
              </p>
            </div>
          )}

          {/* Content rendered as soon as columns are available */}
          {columns.length > 0 && (
            <>
              {/* Controls bar: Sub-view tabs (Data Preview first) + Search box */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2 border-b border-border/80">
                <div className="flex items-center gap-1.5 bg-surface-muted p-1 rounded-md border border-border text-2xs">
                  {/* Tab 1: Data Preview (Selected by Default) */}
                  <button
                    type="button"
                    onClick={() => setActiveSubTab('preview')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition-colors font-medium ${activeSubTab === 'preview'
                      ? 'bg-surface text-foreground font-bold shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                      }`}
                  >
                    <TableIcon className="w-3 h-3" />
                    <span>Data Preview ({previewRows.length})</span>
                  </button>

                  {/* Tab 2: Columns & Schema */}
                  <button
                    type="button"
                    onClick={() => setActiveSubTab('columns')}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded transition-colors font-medium ${activeSubTab === 'columns'
                      ? 'bg-surface text-foreground font-bold shadow-xs'
                      : 'text-muted-foreground hover:text-foreground'
                      }`}
                  >
                    <Columns className="w-3 h-3" />
                    <span>Columns & Schema ({columns.length})</span>
                  </button>

                </div>

                {/* Universal Search / Filter Input */}
                <div className="relative min-w-[200px] sm:w-64">
                  <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Filter columns or roles..."
                    className="w-full pl-8 pr-3 py-1 text-2xs font-mono rounded bg-surface border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </div>

              {/* View 1: Cleaned Data Preview (Default View & Shown in Combined) */}
              {(activeSubTab === 'preview' || activeSubTab === 'both') && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-2xs font-bold uppercase tracking-wider text-muted-foreground font-mono">
                        Data Preview (First 5 Rows)
                      </span>
                      {filteredPreviewColumns.length < previewColumns.length && (
                        <span className="text-3xs font-mono text-muted-foreground">
                          ({filteredPreviewColumns.length} of {previewColumns.length} columns matching &quot;{searchQuery}&quot;)
                        </span>
                      )}
                    </div>
                    {previewRows.length > 0 && (
                      <span className="text-3xs font-mono text-muted-foreground">
                        Horizontal scroll enabled
                      </span>
                    )}
                  </div>

                  {previewRows.length === 0 ? (
                    <div className="py-6 text-center text-xs text-muted-foreground bg-surface-muted/30 rounded-md border border-dashed border-border font-mono">
                      {isLoading ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                          <span>Loading preview rows...</span>
                        </span>
                      ) : (
                        'No preview rows available in the active cleaned dataset.'
                      )}
                    </div>
                  ) : filteredPreviewColumns.length === 0 ? (
                    <div className="py-6 text-center text-xs text-muted-foreground bg-surface-muted/30 rounded-md border border-dashed border-border font-mono">
                      No columns matching &quot;{searchQuery}&quot; in preview.
                    </div>
                  ) : (
                    <div className="overflow-x-auto max-h-72 rounded-md border border-border bg-surface">
                      <table className="w-full text-left text-xs font-mono border-collapse">
                        <thead>
                          <tr className="bg-surface-muted/80 border-b border-border text-2xs uppercase tracking-wider text-muted-foreground sticky top-0 z-10">
                            <th className="py-2 px-3 w-10 text-center border-r border-border/60 font-semibold">#</th>
                            {filteredPreviewColumns.map((colName) => (
                              <th
                                key={colName}
                                className="py-2 px-3 font-semibold text-foreground border-r border-border/60 last:border-r-0 whitespace-nowrap min-w-[140px]"
                              >
                                <div className="truncate max-w-[200px]" title={colName}>
                                  {colName}
                                </div>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border text-foreground">
                          {previewRows.map((row, rIdx) => (
                            <tr key={rIdx} className="hover:bg-surface-muted/30 transition-colors">
                              <td className="py-1.5 px-3 text-center text-2xs text-muted-foreground border-r border-border/60 bg-surface-muted/20">
                                {rIdx + 1}
                              </td>
                              {filteredPreviewColumns.map((colName) => (
                                <td
                                  key={colName}
                                  className="py-1.5 px-3 border-r border-border/60 last:border-r-0 whitespace-nowrap max-w-xs truncate"
                                >
                                  {renderCellOrSampleValue(row[colName])}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* View 2: Columns & Schema (Secondary View & Shown in Combined) */}
              {(activeSubTab === 'columns' || activeSubTab === 'both') && (
                <div className={`space-y-2 ${activeSubTab === 'both' ? 'pt-4 border-t border-border/70' : ''}`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-2xs font-bold uppercase tracking-wider text-muted-foreground font-mono">
                        Columns & Semantic Schema
                      </span>
                      <span className="text-3xs font-mono text-muted-foreground">
                        ({filteredColumns.length} of {columns.length} columns)
                      </span>
                    </div>
                  </div>

                  <div className="overflow-x-auto max-h-80 rounded-md border border-border bg-surface">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="bg-surface-muted/80 border-b border-border text-2xs uppercase tracking-wider text-muted-foreground font-mono sticky top-0 z-10">
                          <th className="py-2 px-3 w-10 text-center border-r border-border/60">#</th>
                          <th className="py-2 px-3 font-semibold text-foreground border-r border-border/60 min-w-[160px]">
                            Column Name
                          </th>
                          <th className="py-2 px-3 font-semibold text-foreground border-r border-border/60 min-w-[130px]">
                            Data Type
                          </th>
                          <th className="py-2 px-3 font-semibold text-foreground border-r border-border/60 min-w-[130px]">
                            Semantic Role
                          </th>
                          <th className="py-2 px-3 font-semibold text-foreground min-w-[220px]">
                            Representative Values
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border text-foreground">
                        {filteredColumns.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="py-6 text-center text-xs text-muted-foreground font-mono">
                              No columns matching &quot;{searchQuery}&quot;
                            </td>
                          </tr>
                        ) : (
                          filteredColumns.map((col, idx) => {
                            const repValues = getRepresentativeValues(col);
                            const isLongName = col.original_name.length > 28;

                            return (
                              <tr key={col.original_name} className="hover:bg-surface-muted/30 transition-colors">
                                <td className="py-2 px-3 text-center text-2xs font-mono text-muted-foreground border-r border-border/60">
                                  {idx + 1}
                                </td>
                                <td className="py-2 px-3 border-r border-border/60">
                                  <div className="flex flex-col">
                                    <span
                                      className={`font-mono font-semibold text-xs text-foreground ${isLongName ? 'truncate max-w-[220px]' : ''
                                        }`}
                                      title={col.original_name}
                                    >
                                      {col.original_name}
                                    </span>
                                    {col.normalized_name && col.normalized_name !== col.original_name && (
                                      <span
                                        className="text-3xs font-mono text-muted-foreground truncate max-w-[220px]"
                                        title={`Normalized: ${col.normalized_name}`}
                                      >
                                        SQL: {col.normalized_name}
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="py-2 px-3 border-r border-border/60 whitespace-nowrap">
                                  {renderDataTypeBadge(col.detected_datatype)}
                                </td>
                                <td className="py-2 px-3 border-r border-border/60 whitespace-nowrap">
                                  {renderRoleBadge(col.semantic_role)}
                                </td>
                                <td className="py-2 px-3">
                                  {repValues.length > 0 ? (
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      {repValues.map((v, vIdx) => (
                                        <span
                                          key={vIdx}
                                          className="inline-flex items-center px-1.5 py-0.5 rounded bg-surface-muted border border-border/60 max-w-[200px]"
                                        >
                                          {renderCellOrSampleValue(v)}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-3xs italic text-muted-foreground/60 font-mono">
                                      No sample values recorded
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
