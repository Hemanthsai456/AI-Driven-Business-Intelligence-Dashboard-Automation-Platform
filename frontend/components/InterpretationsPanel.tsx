'use client';

import React from 'react';
import { RankedCandidateUI } from '../lib/types';
import { Button } from './Button';
import { Trophy, CheckCircle2, ArrowRight, Eye, ShieldCheck } from 'lucide-react';

interface InterpretationsPanelProps {
  candidates: RankedCandidateUI[];
  activePlanId: string;
  onViewInstead: (candidate: RankedCandidateUI) => void;
  className?: string;
}

export const InterpretationsPanel: React.FC<InterpretationsPanelProps> = ({
  candidates,
  activePlanId,
  onViewInstead,
  className = '',
}) => {
  if (!candidates || candidates.length === 0) {
    return (
      <div className={`p-6 bg-surface border border-border rounded-card text-center text-xs text-muted-foreground ${className}`}>
        No alternate candidate interpretations generated.
      </div>
    );
  }

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex items-center justify-between pb-2 border-b border-border">
        <div>
          <h3 className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">
            Candidate Interpretations & Robustness
          </h3>
          <p className="text-2xs text-muted-foreground mt-0.5">
            Ranked deterministically across semantic evidence, coverage, stability, and provider agreement.
          </p>
        </div>
        <span className="text-2xs font-mono text-muted-foreground">
          {candidates.length} candidate(s)
        </span>
      </div>

      <div className="space-y-2">
        {candidates.map((c) => {
          const isActive = c.plan_id === activePlanId;
          const isWinner = c.rank === 1;

          return (
            <div
              key={c.plan_id}
              className={`p-3.5 border rounded-card transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                isActive
                  ? 'bg-primary-soft/40 border-primary/40 shadow-xs'
                  : 'bg-surface border-border hover:border-border-strong'
              }`}
            >
              <div className="space-y-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono font-bold ${
                      isWinner
                        ? 'bg-primary text-white'
                        : 'bg-surface-muted text-muted-foreground border border-border'
                    }`}
                  >
                    {isWinner && <Trophy className="w-3 h-3" />}
                    Rank #{c.rank}
                  </span>

                  <span className="text-xs font-semibold text-foreground font-mono">
                    {c.metric} by {c.dimensions.join(', ') || 'overall'}
                  </span>

                  <span className="text-2xs font-mono uppercase px-1.5 py-0.5 rounded bg-surface border border-border text-muted-foreground">
                    {c.visualization}
                  </span>

                  {c.generator.includes('baseline') && (
                    <span className="text-2xs font-mono px-1.5 py-0.5 rounded bg-attention-soft text-attention border border-attention/30">
                      Rule-based Baseline
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 text-2xs font-mono text-muted-foreground">
                  <span>Score: <strong className="text-foreground">{c.score.toFixed(3)}</strong></span>
                  <span>•</span>
                  <span>Evidence: {(c.score_breakdown.evidence * 100).toFixed(0)}%</span>
                  <span>•</span>
                  <span>Coverage: {(c.score_breakdown.coverage * 100).toFixed(0)}%</span>
                  <span>•</span>
                  <span>Stability: {(c.score_breakdown.stability * 100).toFixed(0)}%</span>
                </div>
              </div>

              <div className="shrink-0 flex items-center gap-2">
                {isActive ? (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded text-2xs font-semibold font-mono text-primary bg-primary-soft border border-primary/20">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Currently Viewing
                  </span>
                ) : (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onViewInstead(c)}
                    leftIcon={<Eye className="w-3.5 h-3.5" />}
                  >
                    View this instead
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
