'use client';

import React from 'react';
import {
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Cpu,
  Sparkles,
  Layers,
  BarChart2,
  Brush,
  Brain,
  HelpCircle,
} from 'lucide-react';
import { THEME_TOKENS } from '../lib/theme';

export type PipelineStep = 'idle' | 'clean' | 'understand' | 'propose' | 'rank' | 'build' | 'done' | 'error';

export interface ProviderStatusItem {
  provider: string;
  status: 'live' | 'failed';
  model: string | null;
  reason: string | null;
  is_baseline: boolean;
}

interface PipelineStepperProps {
  currentStep: PipelineStep;
  errorMessage?: string | null;
  providers: ProviderStatusItem[];
  className?: string;
}

const STEPS = [
  { id: 'clean', label: 'Clean', desc: 'Dedupe, format, types', icon: Brush },
  { id: 'understand', label: 'Understand', desc: 'Intent & ambiguity', icon: Brain },
  { id: 'propose', label: 'Propose', desc: 'Multi-agent plans', icon: Sparkles },
  { id: 'rank', label: 'Rank', desc: 'Pass 1 & consensus', icon: Layers },
  { id: 'build', label: 'Build', desc: 'Pass 2 & DashboardSpec', icon: BarChart2 },
] as const;

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  currentStep,
  errorMessage,
  providers,
  className = '',
}) => {
  const getStepState = (stepId: typeof STEPS[number]['id']) => {
    const stepOrder = ['clean', 'understand', 'propose', 'rank', 'build'];
    const curIdx = stepOrder.indexOf(currentStep);
    const thisIdx = stepOrder.indexOf(stepId);

    if (currentStep === 'done') return 'completed';
    if (currentStep === 'idle') return 'pending';
    if (thisIdx < curIdx) return 'completed';
    if (thisIdx === curIdx) return currentStep === 'error' ? 'failed' : 'active';
    return 'pending';
  };

  return (
    <div className={`bg-surface border border-border rounded-card p-4 sm:p-5 shadow-xs ${className}`}>
      {/* 5-Step Progress Bar */}
      <div className="flex items-center justify-between relative gap-2 sm:gap-4">
        {STEPS.map((step, idx) => {
          const state = getStepState(step.id);
          const Icon = step.icon;

          return (
            <div key={step.id} className="flex-1 flex flex-col items-center text-center relative z-10">
              {/* Connector line behind steps */}
              {idx > 0 && (
                <div
                  className={`absolute top-4 -left-1/2 w-full h-[2px] -z-10 transition-colors ${
                    state === 'completed' || state === 'active'
                      ? 'bg-primary'
                      : 'bg-border'
                  }`}
                />
              )}

              {/* Step Circle Indicator */}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center border text-xs font-mono font-bold transition-all ${
                  state === 'completed'
                    ? 'bg-primary text-white border-primary'
                    : state === 'active'
                    ? 'bg-primary-soft text-primary border-primary ring-2 ring-primary/20'
                    : state === 'failed'
                    ? 'bg-error-soft text-error border-error'
                    : 'bg-surface text-muted-foreground border-border'
                }`}
              >
                {state === 'completed' ? (
                  <CheckCircle2 className="w-4 h-4 stroke-[2.5]" />
                ) : state === 'active' ? (
                  <Loader2 className="w-4 h-4 animate-spin text-primary" />
                ) : state === 'failed' ? (
                  <AlertTriangle className="w-4 h-4 text-error" />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>

              {/* Step Label */}
              <div className="mt-2 min-w-0">
                <div
                  className={`text-xs font-semibold tracking-tight ${
                    state === 'active'
                      ? 'text-primary'
                      : state === 'completed'
                      ? 'text-foreground'
                      : state === 'failed'
                      ? 'text-error'
                      : 'text-muted-foreground'
                  }`}
                >
                  {step.label}
                </div>
                <div className="hidden sm:block text-2xs text-muted-foreground mt-0.5 truncate">
                  {step.desc}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Error Message banner if pipeline failed */}
      {currentStep === 'error' && errorMessage && (
        <div className="mt-4 p-3 bg-error-soft border border-error/30 rounded text-error text-xs flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Pipeline Error: </span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Live Provider Health Chips (Never hidden, even if failed) */}
      <div className="mt-5 pt-3 border-t border-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-2xs font-mono font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-primary" />
            <span>AI Generation Providers & Health</span>
          </span>
          <span className="text-2xs text-muted-foreground font-mono">
            {providers.filter((p) => p.status === 'live' && !p.is_baseline).length} active LLM provider(s)
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {providers.map((p) => {
            const isLive = p.status === 'live';
            const isBaseline = p.is_baseline;

            return (
              <div
                key={p.provider}
                title={p.reason || (isBaseline ? 'Baseline heuristic excluded from agreement consensus' : `Model: ${p.model || 'active'}`)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-2xs border font-medium transition-all ${
                  !isLive
                    ? 'bg-attention-soft text-attention border-attention/30'
                    : isBaseline
                    ? 'bg-surface-muted text-muted-foreground border-border'
                    : 'bg-primary-soft text-primary border-primary/25'
                }`}
              >
                {/* Indicator Icon */}
                {isLive ? (
                  isBaseline ? (
                    <Cpu className="w-3 h-3 text-muted-foreground" />
                  ) : (
                    <CheckCircle2 className="w-3 h-3 text-primary" />
                  )
                ) : (
                  <AlertTriangle className="w-3 h-3 text-attention" />
                )}

                {/* Provider Label & Status */}
                <span className="font-semibold capitalize font-mono">
                  {p.provider.replace('_', ' ')}
                </span>

                <span className="text-2xs opacity-80">
                  {isLive
                    ? isBaseline
                      ? '(rule-based baseline)'
                      : `(${p.model || 'live'})`
                    : '(failed - offline)'}
                </span>

                {/* If failed, show short reason */}
                {!isLive && p.reason && (
                  <span className="hidden md:inline-block max-w-[140px] truncate text-2xs opacity-75 font-mono">
                    • {p.reason.slice(0, 30)}...
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
