'use client';

import React from 'react';
import { X, Sparkles, CheckCircle2, ShieldAlert } from 'lucide-react';
import { SemanticColumn } from '../lib/types';
import { Badge } from './Badge';

interface EvidenceInspectorProps {
  column: SemanticColumn | null;
  onClose: () => void;
}

export const EvidenceInspector: React.FC<EvidenceInspectorProps> = ({ column, onClose }) => {
  if (!column) return null;

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
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-2xl space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-purple-400" />
          <h3 className="font-bold text-slate-100 text-base">{column.column_name}</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Role & Confidence Card */}
      <div className="p-4 bg-slate-950/80 rounded-xl border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400 font-medium">Candidate Role:</span>
          <Badge variant={getRoleVariant(column.candidate_role)} size="md">
            {column.candidate_role}
          </Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400 font-medium">Engine Confidence:</span>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono font-bold text-slate-200">
              {(column.confidence * 100).toFixed(0)}%
            </span>
            <Badge variant={getConfidenceVariant(column.confidence_level)} size="sm">
              {column.confidence_level}
            </Badge>
          </div>
        </div>
      </div>

      {/* Evidence Checklist */}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase text-slate-400 tracking-wider">
          Rule-Based Evidence Signals
        </h4>
        <div className="space-y-2 font-mono text-xs bg-slate-950/60 p-4 rounded-xl border border-slate-800">
          {column.evidence && column.evidence.length > 0 ? (
            column.evidence.map((stmt, idx) => (
              <div key={idx} className="flex items-start space-x-2.5 text-slate-300">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <span className="leading-relaxed">{stmt}</span>
              </div>
            ))
          ) : (
            <div className="flex items-center space-x-2 text-slate-500">
              <ShieldAlert className="w-4 h-4" />
              <span>No explicit evidence signals recorded.</span>
            </div>
          )}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 italic">
        Evidence generated strictly by Step 4 Rule-Based Semantic Intelligence engine without external mock assumptions.
      </p>
    </div>
  );
};
