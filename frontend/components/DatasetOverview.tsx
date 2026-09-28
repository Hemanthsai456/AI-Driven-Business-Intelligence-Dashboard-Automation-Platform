'use client';

import React from 'react';
import { Layers, Hash, AlertTriangle, ShieldCheck, FileSpreadsheet, CheckCircle2 } from 'lucide-react';
import { Card } from './Card';
import { Badge } from './Badge';
import { KpiCard } from './KpiCard';
import { AnalysisReadiness, DatasetMetadata } from '../lib/types';

interface DatasetOverviewProps {
  metadata: DatasetMetadata;
  readiness?: AnalysisReadiness;
  missingnessPct?: number;
  duplicateRows?: number;
}

export const DatasetOverview: React.FC<DatasetOverviewProps> = ({
  metadata,
  readiness,
  missingnessPct = 0,
  duplicateRows = 0,
}) => {
  const getReadinessBadge = (status?: string) => {
    switch (status) {
      case 'READY':
        return <Badge variant="green" size="xs" dot>Analysis Ready</Badge>;
      case 'READY_WITH_WARNINGS':
        return <Badge variant="amber" size="xs" dot>Ready with Warnings</Badge>;
      case 'NOT_READY':
        return <Badge variant="red" size="xs" dot>Not Ready</Badge>;
      default:
        return <Badge variant="slate" size="xs">Evaluating</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard
          title="Total Rows"
          value={metadata.row_count.toLocaleString()}
          subtitle="Parsed tabular records"
          icon={<Layers className="w-4 h-4" />}
          variant="accent"
        />
        <KpiCard
          title="Total Columns"
          value={metadata.column_count}
          subtitle="Schema attributes"
          icon={<Hash className="w-4 h-4" />}
          variant="default"
        />
        <KpiCard
          title="Missing Cells"
          value={`${missingnessPct.toFixed(1)}%`}
          subtitle="Null or blank cells"
          icon={<AlertTriangle className="w-4 h-4" />}
          variant={missingnessPct > 10 ? 'warning' : 'default'}
        />
        <KpiCard
          title="Duplicate Rows"
          value={duplicateRows.toLocaleString()}
          subtitle="Redundant records"
          icon={<FileSpreadsheet className="w-4 h-4" />}
          variant={duplicateRows > 0 ? 'warning' : 'default'}
        />
      </div>

      {/* Schema Readiness Status Banner */}
      {readiness && (
        <div className="p-3.5 bg-surface border border-border rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-surface-muted rounded-md text-primary border border-border shrink-0">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-foreground">
                  Schema Integrity & C3 Gate:
                </span>
                {getReadinessBadge(readiness.status)}
              </div>
              <p className="text-2xs text-muted-foreground mt-0.5">{readiness.summary}</p>
            </div>
          </div>
          <span className="text-2xs text-muted-foreground font-mono shrink-0">
            {readiness.checks.filter((c) => c.passed).length}/{readiness.checks.length} Checks Passed
          </span>
        </div>
      )}
    </div>
  );
};
