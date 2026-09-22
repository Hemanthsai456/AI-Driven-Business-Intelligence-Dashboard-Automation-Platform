'use client';

import React, { useState } from 'react';
import { DataProfile, ColumnStatistics } from '../lib/types';
import { ColumnInspector } from './ColumnInspector';
import { Badge } from './Badge';
import { BarChart3, ChevronRight } from 'lucide-react';

interface ProfileTabProps {
  profile: DataProfile;
}

export const ProfileTab: React.FC<ProfileTabProps> = ({ profile }) => {
  const [selectedColumn, setSelectedColumn] = useState<ColumnStatistics | null>(null);

  const columns = Object.values(profile.column_statistics);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Column Statistics Table */}
      <div className={`space-y-4 ${selectedColumn ? 'lg:col-span-2' : 'lg:col-span-3'}`}>
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="p-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4 text-sky-400" />
              <h3 className="text-sm font-semibold text-slate-200">Data Profiling Statistics</h3>
            </div>
            <span className="text-xs text-slate-500 font-mono">
              Select any column row to inspect detailed metrics
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px] tracking-wider">
                  <th className="py-3 px-4 font-semibold">Column Name</th>
                  <th className="py-3 px-4 font-semibold">Datatype</th>
                  <th className="py-3 px-4 font-semibold">Non-Null %</th>
                  <th className="py-3 px-4 font-semibold">Distinct Count</th>
                  <th className="py-3 px-4 font-semibold">Key Stat</th>
                  <th className="py-3 px-4 font-semibold text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                {columns.map((col) => {
                  const nonNullPct = ((col.non_null_count / col.total_count) * 100).toFixed(1);
                  const isSelected = selectedColumn?.column_name === col.column_name;

                  return (
                    <tr
                      key={col.column_name}
                      onClick={() => setSelectedColumn(col)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-sky-500/10 border-l-2 border-sky-400' : 'hover:bg-slate-800/50'
                      }`}
                    >
                      <td className="py-3 px-4 font-bold text-slate-100">{col.column_name}</td>
                      <td className="py-3 px-4">
                        <Badge variant="blue" size="sm">{col.detected_datatype}</Badge>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-2">
                          <span>{nonNullPct}%</span>
                          <div className="w-12 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-sky-400 h-full rounded-full"
                              style={{ width: `${nonNullPct}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">{col.distinct_count.toLocaleString()}</td>
                      <td className="py-3 px-4 text-slate-400">
                        {col.mean !== undefined
                          ? `Mean: ${col.mean.toFixed(2)}`
                          : col.most_frequent_values && col.most_frequent_values.length > 0
                          ? `Top: "${col.most_frequent_values[0].value}"`
                          : '-'}
                      </td>
                      <td className="py-3 px-4 text-right text-slate-500">
                        <ChevronRight className="w-4 h-4 ml-auto" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quality Issues Summary */}
        {profile.quality_issues && profile.quality_issues.length > 0 && (
          <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl space-y-2">
            <h4 className="text-xs font-semibold text-amber-300 uppercase tracking-wider">Quality & Anomaly Observations</h4>
            <ul className="space-y-1 text-xs text-amber-200 font-mono">
              {profile.quality_issues.map((issue, idx) => (
                <li key={idx} className="flex items-start space-x-2">
                  <span className="text-amber-400">•</span>
                  <span>
                    <strong>{issue.issue_type}</strong>: {issue.description}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Side Detail Inspector Panel */}
      {selectedColumn && (
        <div className="lg:col-span-1">
          <ColumnInspector stats={selectedColumn} onClose={() => setSelectedColumn(null)} />
        </div>
      )}
    </div>
  );
};
