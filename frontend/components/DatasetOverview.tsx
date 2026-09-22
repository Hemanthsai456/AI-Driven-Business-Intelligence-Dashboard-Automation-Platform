'use client';

import React from 'react';
import { Layers, Hash, AlertTriangle, ShieldCheck, FileSpreadsheet } from 'lucide-react';
import { Card } from './Card';
import { Badge } from './Badge';
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
        return <Badge variant="green">Analysis Ready</Badge>;
      case 'READY_WITH_WARNINGS':
        return <Badge variant="amber">Ready with Warnings</Badge>;
      case 'NOT_READY':
        return <Badge variant="red">Not Ready</Badge>;
      default:
        return <Badge variant="slate">Evaluating</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Rows */}
        <Card className="flex items-center space-x-4">
          <div className="p-3 bg-sky-500/10 border border-sky-500/20 rounded-xl text-sky-400">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Total Rows</span>
            <h4 className="text-xl font-bold text-slate-100">{metadata.row_count.toLocaleString()}</h4>
          </div>
        </Card>

        {/* Total Columns */}
        <Card className="flex items-center space-x-4">
          <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
            <Hash className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Total Columns</span>
            <h4 className="text-xl font-bold text-slate-100">{metadata.column_count}</h4>
          </div>
        </Card>

        {/* Missingness % */}
        <Card className="flex items-center space-x-4">
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Missing Cells</span>
            <h4 className="text-xl font-bold text-slate-100">{missingnessPct.toFixed(1)}%</h4>
          </div>
        </Card>

        {/* Duplicate Rows */}
        <Card className="flex items-center space-x-4">
          <div className="p-3 bg-purple-500/10 border border-purple-500/20 rounded-xl text-purple-400">
            <FileSpreadsheet className="w-5 h-5" />
          </div>
          <div>
            <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Duplicate Rows</span>
            <h4 className="text-xl font-bold text-slate-100">{duplicateRows.toLocaleString()}</h4>
          </div>
        </Card>
      </div>

      {/* Schema Readiness Status Banner */}
      {readiness && (
        <div className="p-4 bg-slate-900/80 border border-slate-800 rounded-xl flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-slate-800 rounded-lg text-slate-300">
              <ShieldCheck className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-sm font-semibold text-slate-200">Schema Integrity & Readiness:</span>
                {getReadinessBadge(readiness.status)}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">{readiness.summary}</p>
            </div>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            {readiness.checks.filter((c) => c.passed).length}/{readiness.checks.length} Checks Passed
          </span>
        </div>
      )}
    </div>
  );
};
