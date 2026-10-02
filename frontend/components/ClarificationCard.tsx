'use client';

import React from 'react';
import { HelpCircle, ArrowRight, ShieldCheck, Scale, CheckCircle2 } from 'lucide-react';
import { Button } from './Button';
import { ClarificationOption } from '../lib/types';

export type { ClarificationOption };

interface ClarificationCardProps {
  message?: string;
  options: ClarificationOption[];
  onSelectOption: (planId: string) => void;
  isLoading?: boolean;
  selectedPlanId?: string | null;
  className?: string;
}

export const ClarificationCard: React.FC<ClarificationCardProps> = ({
  message = 'Multiple candidate interpretations tied or confidence is low; user clarification required.',
  options,
  onSelectOption,
  isLoading = false,
  selectedPlanId = null,
  className = '',
}) => {
  return (
    <div
      className={`bg-attention-soft border border-attention/40 rounded-card p-5 sm:p-6 shadow-xs ${className}`}
    >
      {/* Header Banner */}
      <div className="flex items-start gap-3 mb-4">
        <div className="p-2 rounded-md bg-attention/20 text-attention shrink-0 mt-0.5">
          <HelpCircle className="w-5 h-5 stroke-[2.2]" />
        </div>
        <div>
          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-semibold uppercase tracking-wider font-mono border border-attention/30 bg-attention/10 text-attention mb-1">
            <Scale className="w-3 h-3" />
            <span>Clarification Needed • Score Tie or Robustness Floor</span>
          </div>
          <h3 className="text-base font-bold text-foreground">
            Ambiguous Intent or Score Tie Detected
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
            {message} Please select your intended candidate interpretation below. The system will reuse stored execution results, run validation, and build your dashboard immediately.
          </p>
        </div>
      </div>

      {/* Option Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 mt-4">
        {options.map((opt, idx) => {
          const isSelected = selectedPlanId === opt.plan_id;
          const interpretationText =
            opt.interpretation ||
            opt.description ||
            opt.label ||
            `Candidate Plan ${idx + 1}`;

          const metricLabel = opt.metric
            ? `${opt.aggregation || 'AGG'}(${opt.metric})`
            : 'Unspecified Metric';

          const dimLabel = opt.dimension || (opt.dimensions && opt.dimensions[0]) || 'None';

          const robustnessLabel =
            opt.robustness !== undefined && opt.robustness !== null
              ? `${(opt.robustness * 100).toFixed(1)}%`
              : 'Untested';

          return (
            <div
              key={opt.plan_id}
              className={`bg-surface border rounded-card p-4 flex flex-col justify-between transition-all hover:shadow-xs group ${
                isSelected ? 'border-primary ring-2 ring-primary/20' : 'border-border hover:border-primary/60'
              }`}
            >
              <div>
                {/* Header: Option Tag & Overall Score */}
                <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-border/70">
                  <div className="flex items-center gap-1.5">
                    <span className="text-2xs font-mono font-bold px-2 py-0.5 rounded bg-primary-soft text-primary">
                      Option {idx + 1}
                    </span>
                    {opt.visualization && (
                      <span className="text-2xs font-mono text-muted-foreground uppercase">
                        {opt.visualization}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-2xs font-medium text-muted-foreground">Score:</span>
                    <span className="text-2xs font-mono font-bold px-1.5 py-0.5 rounded bg-surface-muted text-foreground border border-border">
                      {typeof opt.score === 'number' ? opt.score.toFixed(3) : opt.score}
                    </span>
                  </div>
                </div>

                {/* Plain-Language Interpretation */}
                <h4 className="text-xs font-bold text-foreground leading-snug group-hover:text-primary transition-colors">
                  {interpretationText}
                </h4>

                {/* Metric, Dimension, Aggregation Details */}
                <div className="grid grid-cols-2 gap-2 mt-3 pt-2.5 border-t border-dashed border-border/70 text-2xs font-mono">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-muted-foreground text-3xs uppercase tracking-wider font-sans font-medium">
                      Metric & Aggregation
                    </span>
                    <span className="text-foreground font-semibold truncate" title={metricLabel}>
                      {metricLabel}
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-muted-foreground text-3xs uppercase tracking-wider font-sans font-medium">
                      Dimension
                    </span>
                    <span className="text-foreground font-semibold truncate" title={dimLabel}>
                      {dimLabel}
                    </span>
                  </div>
                </div>

                {/* Robustness & Coverage */}
                <div className="flex items-center justify-between gap-2 mt-3 pt-2 text-2xs font-mono text-muted-foreground bg-surface-muted/50 px-2 py-1 rounded">
                  <div className="flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3 text-primary" />
                    <span>Robustness:</span>
                    <strong className="text-foreground">{robustnessLabel}</strong>
                  </div>
                  {opt.coverage !== undefined && (
                    <div className="flex items-center gap-1">
                      <span>Coverage:</span>
                      <strong className="text-foreground">{(opt.coverage * 100).toFixed(0)}%</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Action Button */}
              <div className="pt-3.5 mt-3 border-t border-border">
                <Button
                  variant="primary"
                  size="sm"
                  fullWidth
                  disabled={isLoading}
                  onClick={() => onSelectOption(opt.plan_id)}
                  rightIcon={
                    isSelected ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : (
                      <ArrowRight className="w-3.5 h-3.5" />
                    )
                  }
                  className="font-medium text-xs shadow-xs"
                >
                  {isLoading && isSelected ? 'Resolving Selection...' : `Select Option ${idx + 1}`}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
