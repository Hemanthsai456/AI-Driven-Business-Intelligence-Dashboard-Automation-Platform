'use client';

import React, { useState, useMemo } from 'react';
import {
  FileSpreadsheet,
  Database,
  Layers,
  Key,
  Calendar,
  Tag,
  TrendingUp,
  CheckSquare,
  Search,
  Table,
  ShieldCheck,
  AlertTriangle,
  Info,
  ChevronDown,
} from 'lucide-react';
import { Card } from '../Card';
import { Badge } from '../Badge';
import {
  AnalysisReadiness,
  DataPreviewResponse,
  DataProfile,
  DatasetMetadata,
  QualityAssessment,
  SemanticProfile,
} from '../../lib/types';

interface OverviewTabProps {
  metadata: DatasetMetadata;
  profile: DataProfile | null;
  semanticProfile: SemanticProfile | null;
  readiness: AnalysisReadiness | null;
  qualityAssessment: QualityAssessment | null;
  preview: DataPreviewResponse | null;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  metadata,
  profile,
  semanticProfile,
  readiness,
  qualityAssessment,
  preview,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [previewLimit, setPreviewLimit] = useState<number>(10);

  // Role Breakdown Counts
  const roleCounts = useMemo(() => {
    if (!semanticProfile?.column_evidences) {
      return { measures: 0, dimensions: 0, datetimes: 0, identifiers: 0, booleans: 0, unknown: 0 };
    }
    const evidences = Object.values(semanticProfile.column_evidences);
    return {
      measures: evidences.filter((c) => c.candidate_role === 'MEASURE').length,
      dimensions: evidences.filter((c) => c.candidate_role === 'DIMENSION').length,
      datetimes: evidences.filter((c) => c.candidate_role === 'DATETIME').length,
      identifiers: evidences.filter((c) => c.candidate_role === 'IDENTIFIER').length,
      booleans: Object.values(profile?.column_statistics || {}).filter(
        (c) => c.detected_datatype.toLowerCase().includes('bool')
      ).length,
      unknown: evidences.filter((c) => c.candidate_role === 'UNKNOWN').length,
    };
  }, [semanticProfile, profile]);

  // Filtered Schema Columns
  const filteredColumns = useMemo(() => {
    const cols = metadata.columns || [];
    if (!searchTerm.trim()) return cols;
    const term = searchTerm.toLowerCase();
    return cols.filter((col) => {
      const evidence = semanticProfile?.column_evidences[col.original_name];
      return (
        col.original_name.toLowerCase().includes(term) ||
        col.detected_datatype.toLowerCase().includes(term) ||
        (evidence?.candidate_role && evidence.candidate_role.toLowerCase().includes(term))
      );
    });
  }, [metadata.columns, semanticProfile, searchTerm]);

  const dupRows = profile?.dataset_summary?.duplicate_row_count ?? 0;
  const dupPct = profile?.dataset_summary?.duplicate_row_percentage ?? 0;
  const missingCells = profile?.dataset_summary?.overall_missing_count ?? 0;
  const missingPct = profile?.dataset_summary?.overall_missing_percentage ?? 0;

  return (
    <div className="space-y-6">
      {/* 1. High-Level Dataset Snapshot Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Total Rows
          </span>
          <div className="text-lg font-bold font-mono text-foreground">
            {metadata.row_count.toLocaleString()}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            {metadata.source_type?.toUpperCase()} format
          </span>
        </Card>

        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Total Columns
          </span>
          <div className="text-lg font-bold font-mono text-foreground">
            {metadata.column_count}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            Schema attributes
          </span>
        </Card>

        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Duplicate Rows
          </span>
          <div className={`text-lg font-bold font-mono ${dupRows > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {dupRows.toLocaleString()}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            {dupPct.toFixed(1)}% of dataset
          </span>
        </Card>

        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Missing Values
          </span>
          <div className={`text-lg font-bold font-mono ${missingCells > 0 ? 'text-amber-500' : 'text-foreground'}`}>
            {missingCells.toLocaleString()}
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            {missingPct.toFixed(1)}% missing cells
          </span>
        </Card>

        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Readiness
          </span>
          <div className="pt-0.5">
            <Badge
              variant={
                readiness?.status === 'READY'
                  ? 'green'
                  : readiness?.status === 'READY_WITH_WARNINGS'
                  ? 'amber'
                  : 'red'
              }
              size="xs"
            >
              {readiness?.status || 'PENDING'}
            </Badge>
          </div>
          <span className="text-3xs text-muted-foreground font-mono truncate block">
            {readiness?.checks?.filter((c) => c.passed).length ?? 0}/{readiness?.checks?.length ?? 0} checks
          </span>
        </Card>

        <Card className="p-3.5 space-y-1">
          <span className="text-2xs uppercase tracking-wider text-muted-foreground font-mono">
            Quality Status
          </span>
          <div className="pt-0.5">
            <Badge
              variant={
                qualityAssessment?.status === 'Good'
                  ? 'green'
                  : qualityAssessment?.status === 'Needs Attention'
                  ? 'amber'
                  : 'red'
              }
              size="xs"
            >
              {qualityAssessment?.status || 'Assessing'}
            </Badge>
          </div>
          <span className="text-3xs text-muted-foreground font-mono">
            {qualityAssessment ? `${qualityAssessment.completeness_percentage}% clean` : 'Deterministic'}
          </span>
        </Card>
      </div>

      {/* 2. Semantic Role & Datatype Composition */}
      <Card className="p-4 border border-border">
        <div className="text-xs font-bold uppercase tracking-wider font-mono text-muted-foreground mb-3 flex items-center justify-between">
          <span>Semantic Composition & Datatype Distribution</span>
          <span className="text-3xs font-normal text-muted-foreground">Inferred via Rule-Based Intelligence</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <div className="flex items-center gap-2.5 p-2.5 bg-surface-muted/40 border border-border rounded-md">
            <div className="p-2 bg-primary-soft text-primary rounded">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-foreground">{roleCounts.measures}</div>
              <div className="text-3xs text-muted-foreground font-mono uppercase">Measures (Numeric)</div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 p-2.5 bg-surface-muted/40 border border-border rounded-md">
            <div className="p-2 bg-blue-500/10 text-blue-500 rounded">
              <Tag className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-foreground">{roleCounts.dimensions}</div>
              <div className="text-3xs text-muted-foreground font-mono uppercase">Dimensions (Text)</div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 p-2.5 bg-surface-muted/40 border border-border rounded-md">
            <div className="p-2 bg-purple-500/10 text-purple-500 rounded">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-foreground">{roleCounts.datetimes}</div>
              <div className="text-3xs text-muted-foreground font-mono uppercase">Datetimes (Temporal)</div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 p-2.5 bg-surface-muted/40 border border-border rounded-md">
            <div className="p-2 bg-amber-500/10 text-amber-500 rounded">
              <Key className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-foreground">{roleCounts.identifiers}</div>
              <div className="text-3xs text-muted-foreground font-mono uppercase">Identifiers (Keys)</div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 p-2.5 bg-surface-muted/40 border border-border rounded-md">
            <div className="p-2 bg-slate-500/10 text-slate-500 rounded">
              <CheckSquare className="w-4 h-4" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-foreground">{roleCounts.booleans}</div>
              <div className="text-3xs text-muted-foreground font-mono uppercase">Booleans (Flags)</div>
            </div>
          </div>
        </div>
      </Card>

      {/* 3. Interactive Schema Metadata Table */}
      <Card className="overflow-hidden border border-border">
        <div className="p-3 border-b border-border bg-surface-muted/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div className="flex items-center gap-2">
            <Table className="w-4 h-4 text-primary" />
            <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
              Dataset Schema Overview ({filteredColumns.length} of {metadata.columns?.length ?? 0} columns)
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Filter columns by name or type..."
                className="text-xs bg-surface border border-border rounded pl-8 pr-3 py-1 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary w-56 font-mono"
              />
            </div>
          </div>
        </div>

        <div className="overflow-x-auto max-h-96">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-surface-muted text-muted-foreground sticky top-0 border-b border-border z-10">
              <tr>
                <th className="px-3.5 py-2 font-medium w-10">#</th>
                <th className="px-3.5 py-2 font-medium">Column Name</th>
                <th className="px-3.5 py-2 font-medium">Inferred Role</th>
                <th className="px-3.5 py-2 font-medium">Dtype</th>
                <th className="px-3.5 py-2 font-medium">Confidence</th>
                <th className="px-3.5 py-2 font-medium">Missing Count (%)</th>
                <th className="px-3.5 py-2 font-medium">Distinct Values</th>
                <th className="px-3.5 py-2 font-medium">Sample Values</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredColumns.map((col, idx) => {
                const evidence = semanticProfile?.column_evidences[col.original_name];
                const stats = profile?.column_statistics[col.original_name];
                const role = evidence?.candidate_role || col.semantic_role || 'UNKNOWN';
                const confidence = evidence ? Math.round(evidence.confidence * 100) : null;
                const nullCount = stats?.null_count ?? col.null_count ?? 0;
                const nullPct = stats?.null_percentage ?? col.null_percentage ?? 0;
                const distinctCount = stats?.distinct_count ?? col.distinct_count ?? 0;

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

                return (
                  <tr key={col.original_name} className="hover:bg-surface-muted/40 transition-colors">
                    <td className="px-3.5 py-2.5 text-muted-foreground">{idx + 1}</td>
                    <td className="px-3.5 py-2.5 font-semibold text-foreground">{col.original_name}</td>
                    <td className="px-3.5 py-2.5">
                      <Badge variant={roleBadgeVariant} size="xs">
                        {role}
                      </Badge>
                    </td>
                    <td className="px-3.5 py-2.5 text-muted-foreground font-mono text-2xs">
                      {col.detected_datatype}
                    </td>
                    <td className="px-3.5 py-2.5">
                      {confidence !== null ? (
                        <div className="flex items-center gap-1.5 text-2xs">
                          <span className="font-semibold text-foreground">{confidence}%</span>
                          <span className="text-3xs text-muted-foreground">({evidence?.confidence_level})</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-3.5 py-2.5">
                      {nullCount > 0 ? (
                        <span className={`text-2xs font-semibold ${nullPct >= 50 ? 'text-rose-500' : 'text-amber-500'}`}>
                          {nullCount.toLocaleString()} ({nullPct.toFixed(1)}%)
                        </span>
                      ) : (
                        <span className="text-emerald-500 text-2xs">0 (0.0%)</span>
                      )}
                    </td>
                    <td className="px-3.5 py-2.5 text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <span>{distinctCount.toLocaleString()}</span>
                        {stats?.is_unique && (
                          <Badge variant="amber" size="xs">Unique</Badge>
                        )}
                        {stats?.is_constant && (
                          <Badge variant="slate" size="xs">Constant</Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-3.5 py-2.5 text-muted-foreground truncate max-w-xs">
                      {col.sample_values && col.sample_values.length > 0
                        ? col.sample_values.slice(0, 3).join(', ')
                        : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 4. Raw Data Preview Table */}
      {preview && preview.rows && preview.rows.length > 0 && (
        <Card className="overflow-hidden border border-border">
          <div className="p-3 border-b border-border bg-surface-muted/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
                Data Preview (First {Math.min(previewLimit, preview.rows.length)} rows of {preview.total_rows.toLocaleString()})
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-3xs font-mono text-muted-foreground">Rows to show:</span>
              <select
                value={previewLimit}
                onChange={(e) => setPreviewLimit(Number(e.target.value))}
                className="text-xs bg-surface border border-border rounded px-2 py-0.5 text-foreground font-mono focus:outline-none"
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto max-h-80">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-surface-muted text-muted-foreground sticky top-0 border-b border-border z-10">
                <tr>
                  <th className="px-3 py-2 w-10 font-medium">#</th>
                  {preview.columns.map((col) => (
                    <th key={col} className="px-3 py-2 font-medium truncate max-w-xs">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {preview.rows.slice(0, previewLimit).map((row, rowIdx) => (
                  <tr key={rowIdx} className="hover:bg-surface-muted/40 transition-colors">
                    <td className="px-3 py-1.5 text-muted-foreground">{rowIdx + 1}</td>
                    {preview.columns.map((col) => {
                      const val = row[col];
                      return (
                        <td key={col} className="px-3 py-1.5 truncate max-w-xs text-foreground">
                          {val === null || val === undefined ? (
                            <span className="text-muted-foreground italic">null</span>
                          ) : (
                            String(val)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
