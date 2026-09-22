'use client';

import React, { useState } from 'react';
import { SemanticProfile, SemanticColumn } from '../lib/types';
import { EvidenceInspector } from './EvidenceInspector';
import { Badge } from './Badge';
import { Sparkles, ChevronRight } from 'lucide-react';

interface SemanticTabProps {
  semanticProfile: SemanticProfile;
}

export const SemanticTab: React.FC<SemanticTabProps> = ({ semanticProfile }) => {
  const [selectedColumn, setSelectedColumn] = useState<SemanticColumn | null>(null);

  const columns = Object.values(semanticProfile.column_evidences);

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
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="p-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-slate-200">Semantic Role Understanding</h3>
            </div>
            <span className="text-xs text-slate-500 font-mono">
              Select a column to inspect rule-based evidence signals
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 uppercase font-mono text-[10px] tracking-wider">
                  <th className="py-3 px-4 font-semibold">Column Name</th>
                  <th className="py-3 px-4 font-semibold">Candidate Semantic Role</th>
                  <th className="py-3 px-4 font-semibold">Confidence</th>
                  <th className="py-3 px-4 font-semibold">Confidence Level</th>
                  <th className="py-3 px-4 font-semibold text-right">Inspect Evidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                {columns.map((col) => {
                  const isSelected = selectedColumn?.column_name === col.column_name;

                  return (
                    <tr
                      key={col.column_name}
                      onClick={() => setSelectedColumn(col)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? 'bg-purple-500/10 border-l-2 border-purple-400' : 'hover:bg-slate-800/50'
                      }`}
                    >
                      <td className="py-3 px-4 font-bold text-slate-100">{col.column_name}</td>
                      <td className="py-3 px-4">
                        <Badge variant={getRoleVariant(col.candidate_role)} size="md">
                          {col.candidate_role}
                        </Badge>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-2">
                          <span>{(col.confidence * 100).toFixed(0)}%</span>
                          <div className="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-purple-400 h-full rounded-full"
                              style={{ width: `${col.confidence * 100}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant={getConfidenceVariant(col.confidence_level)} size="sm">
                          {col.confidence_level}
                        </Badge>
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
      </div>

      {/* Evidence Side Panel Inspector */}
      {selectedColumn && (
        <div className="lg:col-span-1">
          <EvidenceInspector column={selectedColumn} onClose={() => setSelectedColumn(null)} />
        </div>
      )}
    </div>
  );
};
