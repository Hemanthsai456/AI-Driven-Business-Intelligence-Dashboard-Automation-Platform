'use client';

import React from 'react';
import { HelpCircle, ArrowRight, Sparkles, BarChart2, ShieldAlert } from 'lucide-react';
import { Button } from './Button';
import { ClarificationOption } from '../lib/types';

export type { ClarificationOption };

interface ClarificationCardProps {
  message?: string;
  options: ClarificationOption[];
  onSelectOption: (planId: string) => void;
  isLoading?: boolean;
  className?: string;
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  message = 'Multiple candidate interpretations tied or require clarification.',
  options,
  onSelectOption,
  isLoading = false,
  className = '',
}) => {
  return (
    <div
      className={`bg-attention-soft/50 border border-attention/40 rounded-card p-5 sm:p-6 shadow-xs ${className}`}
    >
      {/* Header Banner */}
      <div className="flex items-start gap-3 mb-4">
        <div className="p-2 rounded bg-attention/15 text-attention shrink-0 mt-0.5">
          <HelpCircle className="w-5 h-5 stroke-[2.2]" />
        </div>
        <div>
          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-semibold uppercase tracking-wider font-mono bg-attention/20 text-attention border border-attention/30 mb-1">
            <span>Clarification Needed • Tie or Low Coverage</span>
          </div>
          <h3 className="text-base font-bold text-foreground">
            Please select your intended analytical interpretation
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {message} Select one of the verified interpretations below to execute the corresponding dashboard plan immediately.
          </p>
        </div>
      </div>

      {/* Option Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
        {options.map((opt, idx) => (
          <div
            key={opt.plan_id}
            className="bg-surface border border-border hover:border-attention/60 rounded-card p-4 flex flex-col justify-between transition-all hover:shadow-xs group"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-muted-foreground">
                  Option {idx + 1} • {opt.visualization.toUpperCase()}
                </span>
                <span className="text-2xs font-mono px-2 py-0.5 rounded bg-surface-muted text-foreground border border-border">
                  Score: {opt.score.toFixed(3)}
                </span>
              </div>

              <h4 className="text-xs font-bold text-foreground leading-snug group-hover:text-attention transition-colors">
                {opt.label}
              </h4>

              <p className="text-2xs text-muted-foreground mt-1.5 leading-relaxed">
                {opt.description}
              </p>

              <div className="flex items-center gap-3 mt-3 text-2xs font-mono text-muted-foreground">
                <span>Coverage: {(opt.coverage * 100).toFixed(0)}%</span>
                <span>•</span>
                <span>Evidence: {(opt.evidence * 100).toFixed(0)}%</span>
              </div>
            </div>

            <div className="pt-4 mt-3 border-t border-border">
              <Button
                variant="primary"
                size="sm"
                fullWidth
                disabled={isLoading}
                onClick={() => onSelectOption(opt.plan_id)}
                rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
                className="bg-attention hover:bg-attention/90 text-white font-medium"
              >
                Choose Option {idx + 1}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
