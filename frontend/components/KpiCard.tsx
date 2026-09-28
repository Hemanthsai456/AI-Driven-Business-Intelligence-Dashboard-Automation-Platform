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
    default: 'text-[#6B6055] bg-[#E6D4B8]/40 border-[#DAC7AD] dark:bg-[#2A2A2A] dark:text-[#A89D91] dark:border-[#3A3530]',
    accent: 'text-[#EA6928] bg-[#E6D4B8] border-[#DAC7AD] dark:bg-[#3D2519] dark:text-[#EA6928] dark:border-[#EA6928]/40',
    success: 'text-[#2E7D32] bg-[#E8F5E9] border-[#C8E6C9] dark:bg-[#1B3E20] dark:text-[#A5D6A7] dark:border-[#2E7D32]',
    warning: 'text-[#9A6700] bg-[#FFF8E1] border-[#FFE082] dark:bg-[#3D2E14] dark:text-[#F2B22E] dark:border-[#F2B22E]/40',
  };

  return (
    <div
      className={`bg-surface border border-border rounded-lg p-4 shadow-xs flex flex-col justify-between ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-2xs font-semibold text-muted-foreground uppercase tracking-wider font-mono">
          {title}
        </span>
        {icon && (
          <div className={`p-2 rounded border shrink-0 ${iconVariants[variant]}`}>
            {icon}
          </div>
        )}
      </div>

      <div className="mt-2.5">
        <div className="text-2xl font-bold tracking-tight text-foreground font-mono">
          {value}
        </div>

        {(delta || subtitle) && (
          <div className="flex items-center gap-2 mt-1.5 text-2xs">
            {delta && (
              <span
                className={`inline-flex items-center font-semibold gap-0.5 px-1.5 py-0.5 rounded text-2xs ${
                  delta.isPositive
                    ? 'text-emerald-800 bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-400'
                    : delta.isPositive === false
                    ? 'text-rose-800 bg-rose-100 dark:bg-rose-950/40 dark:text-rose-400'
                    : 'text-muted-foreground bg-[#E6D4B8]/40'
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
