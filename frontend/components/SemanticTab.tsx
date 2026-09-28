'use client';

import React, { useState } from 'react';
import { SemanticProfile, SemanticColumn } from '../lib/types';
import { EvidenceInspector } from './EvidenceInspector';
import { Badge } from './Badge';
import { Brain, Sparkles, ChevronRight, Search } from 'lucide-react';

interface SemanticTabProps {
  semanticProfile: SemanticProfile;
}

export const SemanticTab: React.FC<SemanticTabProps> = ({ semanticProfile }) => {
  const [selectedColumn, setSelectedColumn] = useState<SemanticColumn | null>(null);
  const [search, setSearch] = useState('');

  const columns = Object.values(semanticProfile.column_evidences);
  const filteredColumns = columns.filter((c) =>
    c.column_name.toLowerCase().includes(search.toLowerCase()) ||
    c.candidate_role.toLowerCase().includes(search.toLowerCase())
  );

  const getRoleVariant = (role: string) => {
    switch (role) {
      case 'MEASURE':
        return 'purple';
      case 'DIMENSION':
        return 'blue';
      case 'DATETIME':
        return 'green';
      case 'IDENTIFIER':
        return 'amber';
      default:
        return 'slate';
    }
  };

  const getConfidenceVariant = (level: string) => {
    switch (level) {
      case 'HIGH':
        return 'green';
      case 'MEDIUM':
        return 'amber';
      case 'LOW':
        return 'red';
      default:
        return 'slate';
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Semantic Table */}
      <div className={`space-y-4 ${selectedColumn ? 'lg:col-span-2' : 'lg:col-span-3'}`}>
        <div className="bg-surface border border-border rounded-lg overflow-hidden shadow-sm">
          <div className="p-3 bg-surface-muted/60 border-b border-border flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple-500" />
              <h3 className="text-xs font-semibold text-foreground">
                Semantic Role Classifications ({columns.length})
              </h3>
            </div>
            <div className="relative w-48">
              <input
                type="text"
                placeholder="Filter semantic roles..."
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
                  <th className="py-2.5 px-3 font-semibold">Candidate Role</th>
                  <th className="py-2.5 px-3 font-semibold">Confidence</th>
                  <th className="py-2.5 px-3 font-semibold">Evidence Signals</th>
                  <th className="py-2.5 px-3 font-semibold text-right">Inspect</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground">
                {filteredColumns.map((col) => {
                  const isSelected = selectedColumn?.column_name === col.column_name;

                  return (
                    <tr
                      key={col.column_name}
                      onClick={() => setSelectedColumn(col)}
                      className={`cursor-pointer transition-colors ${
                        isSelected
                          ? 'bg-purple-500/10 border-l-2 border-purple-500'
                          : 'hover:bg-surface-muted/40'
                      }`}
                    >
                      <td className="py-2.5 px-3 font-bold text-foreground">
                        {col.column_name}
                      </td>
                      <td className="py-2.5 px-3">
                        <Badge variant={getRoleVariant(col.candidate_role)} size="xs">
                          {col.candidate_role}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3">
                        <Badge variant={getConfidenceVariant(col.confidence_level)} size="xs" dot>
                          {(col.confidence * 100).toFixed(0)}% {col.confidence_level}
                        </Badge>
                      </td>
                      <td className="py-2.5 px-3 text-muted-foreground text-2xs truncate max-w-xs">
                        {col.evidence.join('; ')}
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <ChevronRight
                          className={`w-3.5 h-3.5 inline transition-transform ${
                            isSelected ? 'text-purple-500 rotate-90' : 'text-muted-foreground'
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

      {/* Evidence Inspector Drawer */}
      {selectedColumn && (
        <div className="lg:col-span-1">
          <EvidenceInspector column={selectedColumn} onClose={() => setSelectedColumn(null)} />
        </div>
      )}
    </div>
  );
};
