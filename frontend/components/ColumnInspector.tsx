'use client';

import React from 'react';
import { X, Hash, AlertTriangle, CheckCircle } from 'lucide-react';
import { ColumnStatistics } from '../lib/types';
import { Badge } from './Badge';

interface ColumnInspectorProps {
  stats: ColumnStatistics | null;
  onClose: () => void;
}

export const ColumnInspector: React.FC<ColumnInspectorProps> = ({ stats, onClose }) => {
  if (!stats) return null;

  return (
    <div className="bg-surface border border-border rounded-lg p-4 shadow-sm space-y-4 sticky top-16">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <Hash className="w-4 h-4 text-primary shrink-0" />
          <h3 className="font-bold text-foreground text-sm truncate">{stats.column_name}</h3>
          <Badge variant="blue" size="xs">{stats.detected_datatype}</Badge>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Summary Grid */}
      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
        <div className="p-2.5 bg-surface-muted rounded border border-border">
          <span className="text-2xs text-muted-foreground uppercase">Total Count</span>
          <p className="text-xs font-bold text-foreground mt-0.5">{stats.total_count.toLocaleString()}</p>
        </div>
        <div className="p-2.5 bg-surface-muted rounded border border-border">
          <span className="text-2xs text-muted-foreground uppercase">Distinct Values</span>
          <p className="text-xs font-bold text-foreground mt-0.5">{stats.distinct_count.toLocaleString()}</p>
        </div>
        <div className="p-2.5 bg-surface-muted rounded border border-border">
          <span className="text-2xs text-muted-foreground uppercase">Missing Values</span>
          <p className="text-xs font-bold text-foreground mt-0.5">
            {stats.null_count} ({stats.null_percentage.toFixed(1)}%)
          </p>
        </div>
        <div className="p-2.5 bg-surface-muted rounded border border-border">
          <span className="text-2xs text-muted-foreground uppercase">Unique Key</span>
          <p className="text-xs font-bold text-foreground mt-0.5">
            {stats.is_unique ? 'Yes (100%)' : 'No'}
          </p>
        </div>
      </div>

      {/* Numeric Stats */}
      {stats.mean !== undefined && (
        <div className="space-y-2">
          <h4 className="text-2xs font-semibold uppercase text-muted-foreground tracking-wider font-mono">
            Parametric Metrics
          </h4>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="p-2 bg-surface-muted/60 rounded border border-border">
              <span className="text-2xs text-muted-foreground">Min</span>
              <p className="font-semibold text-foreground">{stats.min?.toFixed(2)}</p>
            </div>
            <div className="p-2 bg-surface-muted/60 rounded border border-border">
              <span className="text-2xs text-muted-foreground">Max</span>
              <p className="font-semibold text-foreground">{stats.max?.toFixed(2)}</p>
            </div>
            <div className="p-2 bg-surface-muted/60 rounded border border-border">
              <span className="text-2xs text-muted-foreground">Mean</span>
              <p className="font-semibold text-foreground">{stats.mean?.toFixed(2)}</p>
            </div>
            <div className="p-2 bg-surface-muted/60 rounded border border-border">
              <span className="text-2xs text-muted-foreground">Median</span>
              <p className="font-semibold text-foreground">{stats.median?.toFixed(2)}</p>
            </div>
            <div className="p-2 bg-surface-muted/60 rounded border border-border col-span-2">
              <span className="text-2xs text-muted-foreground">Standard Deviation</span>
              <p className="font-semibold text-foreground">{stats.std?.toFixed(2)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Frequent Values */}
      {stats.most_frequent_values && stats.most_frequent_values.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-2xs font-semibold uppercase text-muted-foreground tracking-wider font-mono">
            Top Frequent Values
          </h4>
          <div className="space-y-1 max-h-36 overflow-y-auto">
            {stats.most_frequent_values.map((v, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-1.5 bg-surface-muted rounded text-2xs font-mono"
              >
                <span className="truncate max-w-[140px] text-foreground">
                  {v.value !== null ? String(v.value) : 'null'}
                </span>
                <span className="text-muted-foreground">{v.count.toLocaleString()} occurrences</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
