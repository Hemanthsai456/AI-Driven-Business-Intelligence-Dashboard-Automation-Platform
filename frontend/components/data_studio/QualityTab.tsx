'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  AlertOctagon,
  CheckCircle2,
  Copy,
  FileQuestion,
  Hash,
  Calendar,
  Layers,
  Info,
  Check,
  Percent,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import {
  AnalysisReadiness,
  DataProfile,
  DatasetMetadata,
  QualityAssessment,
  SemanticProfile,
} from '../../lib/types';

interface QualityTabProps {
  metadata: DatasetMetadata;
  profile: DataProfile | null;
  semanticProfile: SemanticProfile | null;
  readiness: AnalysisReadiness | null;
  qualityAssessment: QualityAssessment | null;
}

export const QualityTab: React.FC<QualityTabProps> = ({
  metadata,
  profile,
  semanticProfile,
  readiness,
  qualityAssessment,
}) => {
  const [filterSeverity, setFilterSeverity] = useState<'all' | 'warning' | 'error' | 'info'>('all');

  const status = qualityAssessment?.status || 'Needs Attention';
  const statusReason = qualityAssessment?.status_reason || 'Evaluating dataset health and observations.';
  const dupCount = qualityAssessment?.duplicate_row_count ?? (profile?.dataset_summary?.duplicate_row_count ?? 0);
  const dupPct = qualityAssessment?.duplicate_row_percentage ?? (profile?.dataset_summary?.duplicate_row_percentage ?? 0);
  const missingCount = qualityAssessment?.overall_missing_count ?? (profile?.dataset_summary?.overall_missing_count ?? 0);
  const missingPct = qualityAssessment?.overall_missing_percentage ?? (profile?.dataset_summary?.overall_missing_percentage ?? 0);
  const completenessPct = qualityAssessment?.completeness_percentage ?? (100 - missingPct);
  const uniquenessPct = qualityAssessment?.uniqueness_percentage ?? (100 - dupPct);

  const missingColumns = qualityAssessment?.missing_columns || [];
  const numericObservations = qualityAssessment?.numeric_observations || [];
  const datetimeObservations = qualityAssessment?.datetime_observations || [];
  const cardinalityObservations = qualityAssessment?.cardinality_observations || [];
  const qualityIssues = qualityAssessment?.quality_issues || profile?.quality_issues || [];
  const readinessWarnings = qualityAssessment?.readiness_warnings || readiness?.warnings || [];
  const readinessBlocking = qualityAssessment?.readiness_blocking_issues || readiness?.blocking_issues || [];

  const constantColumns = cardinalityObservations.filter((c) => c.is_constant);
  const uniqueColumns = cardinalityObservations.filter((c) => c.is_unique);

  return (
    <div className="space-y-6">
      {/* 1. Overall Quality Status Banner */}
      <Card
        className={`p-6 border ${
          status === 'Good'
            ? 'bg-emerald-500/5 border-emerald-500/20'
            : status === 'Needs Attention'
            ? 'bg-amber-500/5 border-amber-500/20'
            : 'bg-rose-500/5 border-rose-500/20'
        }`}
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div
              className={`p-3 rounded-xl shrink-0 ${
                status === 'Good'
                  ? 'bg-emerald-500/10 text-emerald-500'
                  : status === 'Needs Attention'
                  ? 'bg-amber-500/10 text-amber-500'
                  : 'bg-rose-500/10 text-rose-500'
              }`}
            >
              {status === 'Good' ? (
                <CheckCircle2 className="w-8 h-8" />
              ) : status === 'Needs Attention' ? (
                <AlertTriangle className="w-8 h-8" />
              ) : (
                <AlertOctagon className="w-8 h-8" />
              )}
            </div>

            <div className="space-y-1.5 max-w-2xl">
              <div className="flex items-center gap-2.5">
                <span className="text-xs uppercase tracking-wider font-mono text-muted-foreground font-semibold">
                  Deterministic Quality Status
                </span>
                <Badge
                  variant={status === 'Good' ? 'green' : status === 'Needs Attention' ? 'amber' : 'red'}
                  size="sm"
                >
                  {status}
                </Badge>
              </div>
              <h2 className="text-base font-bold text-foreground tracking-tight">
                {status === 'Good'
                  ? 'High Quality Dataset — Ready for Analysis'
                  : status === 'Needs Attention'
                  ? 'Dataset Contains Observations to Review'
                  : 'Critical Quality Issues Detected'}
              </h2>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {statusReason}
              </p>
            </div>
          </div>

          {/* Quick Metrics KPI Ring / Boxes */}
          <div className="grid grid-cols-3 gap-3 shrink-0 border-t md:border-t-0 md:border-l border-border pt-4 md:pt-0 md:pl-6 font-mono">
            <div className="space-y-0.5">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground">Completeness</span>
              <div className={`text-base font-bold ${completenessPct < 90 ? 'text-amber-500' : 'text-emerald-500'}`}>
                {completenessPct}%
              </div>
              <span className="text-3xs text-muted-foreground">{missingCount} nulls</span>
            </div>

            <div className="space-y-0.5">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground">Uniqueness</span>
              <div className={`text-base font-bold ${dupCount > 0 ? 'text-amber-500' : 'text-emerald-500'}`}>
                {uniquenessPct}%
              </div>
              <span className="text-3xs text-muted-foreground">{dupCount} dups</span>
            </div>

            <div className="space-y-0.5">
              <span className="text-3xs uppercase tracking-wider text-muted-foreground">Affected Cols</span>
              <div className="text-base font-bold text-foreground">
                {missingColumns.length} <span className="text-xs text-muted-foreground font-normal">/ {metadata.column_count}</span>
              </div>
              <span className="text-3xs text-muted-foreground">with nulls</span>
            </div>
          </div>
        </div>
      </Card>

      {/* 2-Column Diagnostics Grid: Missing Values & Duplicates */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Missing Values Card */}
        <Card className="p-5 border border-border space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <FileQuestion className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                Missing Values Analysis
              </h3>
            </div>
            <Badge variant={missingCount === 0 ? 'green' : 'amber'} size="xs">
              {missingCount === 0 ? 'Complete' : `${missingCount.toLocaleString()} missing cells`}
            </Badge>
          </div>

          {missingCount === 0 ? (
            <div className="p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-lg text-center space-y-1">
              <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto" />
              <div className="text-xs font-bold text-foreground">Zero Missing Values Detected</div>
              <p className="text-3xs text-muted-foreground">
                All {metadata.row_count.toLocaleString()} rows and {metadata.column_count} columns are fully populated.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                {missingCount.toLocaleString()} null values detected across {missingColumns.length} affected columns ({missingPct.toFixed(1)}% of total cells).
              </p>

              <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                {missingColumns.map((col) => (
                  <div
                    key={col.column_name}
                    className="p-2.5 bg-surface-muted/40 border border-border rounded-md space-y-1.5"
                  >
                    <div className="flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">{col.column_name}</span>
                        <Badge variant="slate" size="xs">{col.detected_datatype}</Badge>
                      </div>
                      <span className={col.null_percentage >= 50 ? 'text-rose-500 font-bold' : 'text-amber-500'}>
                        {col.null_count.toLocaleString()} nulls ({col.null_percentage}%)
                      </span>
                    </div>

                    {/* Completeness Bar */}
                    <div className="w-full bg-surface-muted h-1.5 rounded-full overflow-hidden flex">
                      <div
                        className="bg-emerald-500 h-full"
                        style={{ width: `${col.completeness_percentage}%` }}
                        title={`Completeness: ${col.completeness_percentage}%`}
                      />
                      <div
                        className={col.null_percentage >= 50 ? 'bg-rose-500 h-full' : 'bg-amber-500 h-full'}
                        style={{ width: `${col.null_percentage}%` }}
                        title={`Missing: ${col.null_percentage}%`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        {/* Duplicate Rows Card */}
        <Card className="p-5 border border-border space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Copy className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-bold uppercase tracking-wider font-mono text-foreground">
                Duplicate Rows Analysis
              </h3>
            </div>
            <Badge variant={dupCount === 0 ? 'green' : 'amber'} size="xs">
              {dupCount === 0 ? 'All Distinct' : `${dupCount} duplicate rows`}
            </Badge>
          </div>

          {dupCount === 0 ? (
            <div className="p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-lg text-center space-y-1">
              <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto" />
              <div className="text-xs font-bold text-foreground">Zero Duplicate Rows</div>
              <p className="text-3xs text-muted-foreground">
                All {metadata.row_count.toLocaleString()} rows in this dataset are distinct and unique.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-amber-600 dark:text-amber-400">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{dupCount.toLocaleString()} Exact Duplicate Rows Detected</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  These rows have identical values across all {metadata.column_count} columns, representing {dupPct.toFixed(1)}% of the total dataset.
                </p>
              </div>

              <div className="p-3 bg-surface-muted/40 border border-border rounded-md text-3xs font-mono text-muted-foreground space-y-1">
                <div>• Total Rows: <strong className="text-foreground">{metadata.row_count.toLocaleString()}</strong></div>
                <div>• Unique Rows: <strong className="text-foreground">{(metadata.row_count - dupCount).toLocaleString()}</strong></div>
                <div>• Redundancy Impact: <strong className="text-amber-500">{dupPct.toFixed(2)}%</strong></div>
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* 3. Numeric Quality Observations */}
      {numericObservations.length > 0 && (
        <Card className="overflow-hidden border border-border">
          <div className="p-3 border-b border-border bg-surface-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Hash className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
                Numeric Quality Observations ({numericObservations.length} numeric columns)
              </h3>
            </div>
            <span className="text-3xs text-muted-foreground font-mono">
              Zeros, Negatives, Infinite values & Distribution bounds
            </span>
          </div>

          <div className="overflow-x-auto max-h-64">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-surface-muted text-muted-foreground sticky top-0 border-b border-border">
                <tr>
                  <th className="px-3.5 py-2 font-medium">Column Name</th>
                  <th className="px-3.5 py-2 font-medium">Dtype</th>
                  <th className="px-3.5 py-2 font-medium">Zeros Count (%)</th>
                  <th className="px-3.5 py-2 font-medium">Negatives Count (%)</th>
                  <th className="px-3.5 py-2 font-medium">Infinite Count</th>
                  <th className="px-3.5 py-2 font-medium">Min / Max</th>
                  <th className="px-3.5 py-2 font-medium">Median / Mean</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {numericObservations.map((num) => (
                  <tr key={num.column_name} className="hover:bg-surface-muted/40 transition-colors">
                    <td className="px-3.5 py-2 font-semibold text-foreground">{num.column_name}</td>
                    <td className="px-3.5 py-2 text-muted-foreground text-2xs">{num.detected_datatype}</td>
                    <td className="px-3.5 py-2">
                      {num.zero_count > 0 ? (
                        <span className="text-amber-500 text-2xs font-medium">
                          {num.zero_count} ({num.zero_percentage}%)
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-2xs">0 (0%)</span>
                      )}
                    </td>
                    <td className="px-3.5 py-2">
                      {num.negative_count > 0 ? (
                        <span className="text-rose-500 text-2xs font-medium">
                          {num.negative_count} ({num.negative_percentage}%)
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-2xs">0 (0%)</span>
                      )}
                    </td>
                    <td className="px-3.5 py-2">
                      {num.infinite_count > 0 ? (
                        <span className="text-rose-600 font-bold text-2xs">{num.infinite_count} (Critical)</span>
                      ) : (
                        <span className="text-emerald-500 text-2xs">0</span>
                      )}
                    </td>
                    <td className="px-3.5 py-2 text-muted-foreground text-2xs">
                      {num.min !== null && num.max !== null ? `[${num.min}, ${num.max}]` : '—'}
                    </td>
                    <td className="px-3.5 py-2 text-muted-foreground text-2xs">
                      {num.median !== null && num.mean !== null ? `Med: ${num.median} / Avg: ${typeof num.mean === 'number' ? num.mean.toFixed(2) : num.mean}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* 4. Datetime Quality Observations */}
      {datetimeObservations.length > 0 && (
        <Card className="overflow-hidden border border-border">
          <div className="p-3 border-b border-border bg-surface-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-purple-500" />
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
                Datetime Quality & Temporal Coverage ({datetimeObservations.length} columns)
              </h3>
            </div>
          </div>

          <div className="overflow-x-auto max-h-48">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-surface-muted text-muted-foreground sticky top-0 border-b border-border">
                <tr>
                  <th className="px-3.5 py-2 font-medium">Column Name</th>
                  <th className="px-3.5 py-2 font-medium">Dtype</th>
                  <th className="px-3.5 py-2 font-medium">Min Date</th>
                  <th className="px-3.5 py-2 font-medium">Max Date</th>
                  <th className="px-3.5 py-2 font-medium">Distinct Dates</th>
                  <th className="px-3.5 py-2 font-medium">Missing Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {datetimeObservations.map((dt) => (
                  <tr key={dt.column_name} className="hover:bg-surface-muted/40 transition-colors">
                    <td className="px-3.5 py-2 font-semibold text-foreground">{dt.column_name}</td>
                    <td className="px-3.5 py-2 text-muted-foreground text-2xs">{dt.detected_datatype}</td>
                    <td className="px-3.5 py-2 text-foreground text-2xs">{dt.min_datetime || '—'}</td>
                    <td className="px-3.5 py-2 text-foreground text-2xs">{dt.max_datetime || '—'}</td>
                    <td className="px-3.5 py-2 text-muted-foreground text-2xs">{dt.distinct_dates_count}</td>
                    <td className="px-3.5 py-2 text-2xs">
                      {dt.null_count > 0 ? (
                        <span className="text-amber-500">{dt.null_count} ({dt.null_percentage}%)</span>
                      ) : (
                        <span className="text-emerald-500">0 (0%)</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* 5. Cardinality & Special Flags (Constants & Candidate Keys) */}
      {(constantColumns.length > 0 || uniqueColumns.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {constantColumns.length > 0 && (
            <Card className="p-4 border border-border space-y-2">
              <div className="flex items-center gap-2 text-xs font-bold text-amber-500 font-mono">
                <AlertTriangle className="w-4 h-4" />
                <span>Constant Columns ({constantColumns.length})</span>
              </div>
              <p className="text-3xs text-muted-foreground">
                These columns contain only 1 distinct non-null value across the dataset and offer low analytical variance.
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {constantColumns.map((c) => (
                  <Badge key={c.column_name} variant="slate" size="xs">
                    {c.column_name} (1 distinct)
                  </Badge>
                ))}
              </div>
            </Card>
          )}

          {uniqueColumns.length > 0 && (
            <Card className="p-4 border border-border space-y-2">
              <div className="flex items-center gap-2 text-xs font-bold text-primary font-mono">
                <ShieldCheck className="w-4 h-4" />
                <span>Candidate Primary Keys / Unique Identifiers ({uniqueColumns.length})</span>
              </div>
              <p className="text-3xs text-muted-foreground">
                These columns have 100% unique values across all rows and serve as candidate entity identifiers.
              </p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {uniqueColumns.map((c) => (
                  <Badge key={c.column_name} variant="amber" size="xs">
                    {c.column_name} ({c.distinct_count} unique)
                  </Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* 6. Readiness & Quality Issues Audit Log */}
      <Card className="p-4 border border-border space-y-3">
        <div className="flex items-center justify-between pb-2 border-b border-border">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
              Audit & Diagnostic Observations Log
            </h3>
          </div>
          <span className="text-3xs font-mono text-muted-foreground">
            {qualityIssues.length + readinessWarnings.length + readinessBlocking.length} total observations
          </span>
        </div>

        <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
          {readinessBlocking.map((blk, idx) => (
            <div key={`blk-${idx}`} className="p-2.5 bg-rose-500/10 border border-rose-500/20 rounded-md flex items-start gap-2.5 text-xs">
              <AlertOctagon className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-rose-500 font-mono text-2xs uppercase block">Blocking Issue</span>
                <span className="text-foreground">{blk}</span>
              </div>
            </div>
          ))}

          {readinessWarnings.map((warn, idx) => (
            <div key={`warn-${idx}`} className="p-2.5 bg-amber-500/10 border border-amber-500/20 rounded-md flex items-start gap-2.5 text-xs">
              <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-amber-500 font-mono text-2xs uppercase block">Readiness Warning</span>
                <span className="text-foreground">{warn}</span>
              </div>
            </div>
          ))}

          {qualityIssues.map((issue, idx) => (
            <div key={`issue-${idx}`} className="p-2.5 bg-surface-muted/40 border border-border rounded-md flex items-start gap-2.5 text-xs font-mono">
              <Info className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Badge variant={issue.severity === 'warning' ? 'amber' : 'slate'} size="xs">
                    {issue.issue_type}
                  </Badge>
                  {issue.target && <span className="text-3xs text-muted-foreground">Target: {issue.target}</span>}
                </div>
                <span className="text-foreground text-2xs block">{issue.message}</span>
              </div>
            </div>
          ))}

          {readinessBlocking.length === 0 && readinessWarnings.length === 0 && qualityIssues.length === 0 && (
            <div className="p-4 text-center text-xs text-muted-foreground font-mono">
              Zero diagnostic warnings. Dataset is in excellent health.
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
