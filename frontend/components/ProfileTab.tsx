'use client';

import React, { useState } from 'react';
import { DataProfile, ColumnStatistics } from '../lib/types';
import { ColumnInspector } from './ColumnInspector';
import { Badge } from './Badge';
import { BarChart3, ChevronRight, Search } from 'lucide-react';

interface ProfileTabProps {
  profile: DataProfile;
}

export const ProfileTab: React.FC<ProfileTabProps> = ({ profile }) => {
  const [selectedColumn, setSelectedColumn] = useState<ColumnStatistics | null>(null);
  const [search, setSearch] = useState('');

  const columns = Object.values(profile.column_statistics);
  const filteredColumns = columns.filter((c) =>
    c.column_name.toLowerCase().includes(search.toLowerCase()) ||
    c.detected_datatype.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Column Statistics Table */}
      <div className={`space-y-4 ${selectedColumn ? 'lg:col-span-2' : 'lg:col-span-3'}`}>
        <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
          <div className="p-3 bg-surface-muted/60 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">
                Column Profiles & Summary Statistics ({columns.length})
              </h3>
            </div>
            <div className="relative w-48">
              <input
                type="text"
                placeholder="Filter columns..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-2.5 pr-2 py-1 text-xs bg-surface border border-border rounded text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs font-mono">
              <thead>
                <tr className="bg-surface-muted/80 border-b border-border text-muted-foreground uppercase text-2xs tracking-wider">
                  <th className="py-2.5 px-3 font-semibold">Column Name</th>
                  <th className="py-2.5 px-3 font-semibold">Datatype</th>
                  <th className="py-2.5 px-3 font-semibold">Non-Null %</th>
                  <th className="py-2.5 px-3 font-semibold">Distinct Count</th>
                  <th className="py-2.5 px-3 font-semibold">Key Stat</th>
                  <th className="py-2.5 px-3 font-semibold text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground">
                {filteredColumns.map((col) => {
                  const nonNullPct = ((col.non_null_count / col.total_count) * 100).toFixed(1);
                  const isSelected = selectedColumn?.column_name === col.column_name;

                  return (
                    <tr
                      key={col.column_name}
                      onClick={() => setSelectedColumn(col)}
                      className={`cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-primary/10 border-l-2 border-primary'
                          : 'hover:bg-surface-muted/40'
                      }`}
                    >
                      <td className="py-2.5 px-3 font-bold text-foreground">
                        {col.column_name}
                      </td>
                      <td className="py-2.5 px-3">
                        <Badge variant="blue" size="xs">
                          {col.detected_datatype}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          <div className="w-12 bg-surface-muted rounded-full h-1.5 overflow-hidden border border-border">
                            <div
                              className="bg-emerald-500 h-full rounded-full"
                              style={{ width: `${nonNullPct}%` }}
                            />
                          </div>
                          <span>{nonNullPct}%</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground">
                        {col.distinct_count.toLocaleString()}{' '}
                        {col.is_unique && (
                          <span className="text-2xs text-emerald-500 font-semibold">(Unique)</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground truncate max-w-xs">
                        {col.mean !== undefined ? (
                          <span>Mean: {col.mean.toFixed(2)}</span>
                        ) : col.most_frequent_values && col.most_frequent_values.length > 0 ? (
                          <span>Top: {String(col.most_frequent_values[0].value)}</span>
                        ) : (
                          <span className="text-2xs text-muted-foreground italic">-</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <ChevronRight
                          className={`w-3.5 h-3.5 inline transition-transform ${
                            isSelected ? 'text-primary rotate-90' : 'text-muted-foreground'
                          }`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Inspector Sidebar Drawer */}
      {selectedColumn && (
        <div className="lg:col-span-1">
          <ColumnInspector stats={selectedColumn} onClose={() => setSelectedColumn(null)} />
        </div>
      )}
    </div>
  );
};
