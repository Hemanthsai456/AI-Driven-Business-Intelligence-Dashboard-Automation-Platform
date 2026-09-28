'use client';

import React from 'react';
import { X, Sparkles, CheckCircle2 } from 'lucide-react';
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
    <div className="bg-surface border border-border rounded-lg p-4 shadow-sm space-y-4 sticky top-16">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="w-4 h-4 text-[#EA6928] shrink-0" />
          <h3 className="font-bold text-foreground text-sm truncate">{column.column_name}</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-muted transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Role & Confidence Card */}
      <div className="p-3 bg-surface-muted rounded border border-border space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-2xs font-mono text-muted-foreground uppercase">Classified Role</span>
          <Badge variant={getRoleVariant(column.candidate_role)} size="xs">
            {column.candidate_role}
          </Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-2xs font-mono text-muted-foreground uppercase">Confidence Score</span>
          <Badge variant={getConfidenceVariant(column.confidence_level)} size="xs" dot>
            {(column.confidence * 100).toFixed(0)}% ({column.confidence_level})
          </Badge>
        </div>
      </div>

      {/* Evidence Signals List */}
      <div className="space-y-2">
        <h4 className="text-2xs font-semibold uppercase text-muted-foreground tracking-wider font-mono">
          Rule-Based Evidence Signals
        </h4>

        {column.evidence.length === 0 ? (
          <div className="p-3 bg-surface-muted/60 rounded text-2xs text-muted-foreground italic">
            No specific heuristics matched. Defaulting to general data type rules.
          </div>
        ) : (
          <div className="space-y-1.5">
            {column.evidence.map((ev, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2 p-2 bg-surface-muted rounded border border-border text-2xs font-mono text-foreground"
              >
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                <span className="leading-snug">{ev}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Downstream Usage */}
      <div className="p-3 bg-[#E6D4B8]/40 rounded border border-[#DAC7AD] text-2xs space-y-1 font-mono">
        <div className="font-semibold text-[#EA6928]">Orchestrator Role Usage:</div>
        <p className="text-muted-foreground leading-relaxed">
          {column.candidate_role === 'MEASURE' && 'Eligible for aggregations (SUM, AVG, COUNT, MIN, MAX) in candidate query generation.'}
          {column.candidate_role === 'DIMENSION' && 'Eligible for GROUP BY dimensional grouping and categorical breakdowns.'}
          {column.candidate_role === 'DATETIME' && 'Eligible for temporal bucketing (YEAR, MONTH, DAY) in trend analysis.'}
          {column.candidate_role === 'IDENTIFIER' && 'Reserved for entity lookup, cardinality counting, or row identification.'}
          {column.candidate_role === 'UNKNOWN' && 'Exempt from automated aggregations pending manual role mapping.'}
        </p>
      </div>
    </div>
  );
};
