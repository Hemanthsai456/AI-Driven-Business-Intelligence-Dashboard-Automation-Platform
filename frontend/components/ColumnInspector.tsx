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
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <Hash className="w-4 h-4 text-sky-400" />
          <h3 className="font-bold text-slate-100 text-base">{stats.column_name}</h3>
          <Badge variant="blue" size="sm">{stats.detected_datatype}</Badge>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Summary Grid */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80">
          <span className="text-slate-400">Total Count</span>
          <p className="text-sm font-semibold text-slate-200 mt-0.5">{stats.total_count.toLocaleString()}</p>
        </div>
        <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80">
          <span className="text-slate-400">Distinct Values</span>
          <p className="text-sm font-semibold text-slate-200 mt-0.5">{stats.distinct_count.toLocaleString()}</p>
        </div>
        <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80">
          <span className="text-slate-400">Missing Values</span>
          <p className="text-sm font-semibold text-slate-200 mt-0.5">
            {stats.null_count} ({stats.null_percentage.toFixed(1)}%)
          </p>
        </div>
        <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800/80">
          <span className="text-slate-400">Unique Values</span>
          <p className="text-sm font-semibold text-slate-200 mt-0.5">
            {stats.is_unique ? 'Yes (100%)' : 'No'}
          </p>
        </div>
      </div>

      {/* Numeric Stats */}
      {stats.mean !== undefined && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase text-slate-400 tracking-wider">Numerical Statistics</h4>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono bg-slate-950/80 p-3 rounded-lg border border-slate-800">
            <div><span className="text-slate-500">Min:</span> <span className="text-slate-200">{stats.min}</span></div>
            <div><span className="text-slate-500">Max:</span> <span className="text-slate-200">{stats.max}</span></div>
            <div><span className="text-slate-500">Mean:</span> <span className="text-slate-200">{stats.mean?.toFixed(2)}</span></div>
            <div><span className="text-slate-500">Median:</span> <span className="text-slate-200">{stats.median}</span></div>
            <div><span className="text-slate-500">Std Dev:</span> <span className="text-slate-200">{stats.std?.toFixed(2)}</span></div>
            <div><span className="text-slate-500">IQR (25-75%):</span> <span className="text-slate-200">{stats.q25} - {stats.q75}</span></div>
          </div>
        </div>
      )}

      {/* Categorical Top Values */}
      {stats.most_frequent_values && stats.most_frequent_values.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase text-slate-400 tracking-wider">Top Frequent Values</h4>
          <div className="space-y-1.5 font-mono text-xs">
            {stats.most_frequent_values.map((item, idx) => (
              <div key={idx} className="flex items-center justify-between p-2 bg-slate-950/60 rounded border border-slate-800">
                <span className="text-slate-300 truncate max-w-[200px]">{String(item.value)}</span>
                <span className="text-slate-500 text-[11px]">{item.count} occurrences</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Profiling Observations */}
      {stats.observations && stats.observations.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase text-slate-400 tracking-wider">Profiling Observations</h4>
          <ul className="space-y-1 text-xs">
            {stats.observations.map((obs, idx) => (
              <li key={idx} className="flex items-start space-x-2 text-slate-300">
                <CheckCircle className="w-3.5 h-3.5 text-sky-400 mt-0.5 flex-shrink-0" />
                <span>{obs}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
