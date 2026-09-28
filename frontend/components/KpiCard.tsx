import React from 'react';
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react';

export interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  delta?: {
    value: string;
    isPositive?: boolean;
    period?: string;
  };
  icon?: React.ReactNode;
  variant?: 'default' | 'accent' | 'success' | 'warning';
  className?: string;
}

export const KpiCard: React.FC<KpiCardProps> = ({
  title,
  value,
  subtitle,
  delta,
  icon,
  variant = 'default',
  className = '',
}) => {
  const iconVariants = {
    default: 'text-muted-foreground bg-surface-muted border-border',
    accent: 'text-primary bg-primary/10 border-primary/20',
    success: 'text-success bg-success/10 border-success/20',
    warning: 'text-warning bg-warning/10 border-warning/20',
  };

  return (
    <div
      className={`bg-surface border border-border rounded-lg p-4 shadow-sm hover:border-border-strong transition-all flex flex-col justify-between ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider">
          {title}
        </span>
        {icon && (
          <div className={`p-2 rounded-md border shrink-0 ${iconVariants[variant]}`}>
            {icon}
          </div>
        )}
      </div>

      <div className="mt-2.5">
        <div className="text-2xl font-bold tracking-tight text-foreground">
          {value}
        </div>

        {(delta || subtitle) && (
          <div className="flex items-center gap-2 mt-1.5 text-2xs">
            {delta && (
              <span
                className={`inline-flex items-center font-semibold gap-0.5 px-1.5 py-0.5 rounded text-2xs ${
                  delta.isPositive
                    ? 'text-emerald-700 bg-emerald-500/10 dark:text-emerald-400'
                    : delta.isPositive === false
                    ? 'text-rose-700 bg-rose-500/10 dark:text-rose-400'
                    : 'text-muted-foreground bg-surface-muted'
                }`}
              >
                {delta.isPositive ? (
                  <ArrowUpRight className="w-3 h-3" />
                ) : delta.isPositive === false ? (
                  <ArrowDownRight className="w-3 h-3" />
                ) : (
                  <Minus className="w-3 h-3" />
                )}
                {delta.value}
              </span>
            )}
            <span className="text-muted-foreground truncate">
              {delta?.period || subtitle}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
