import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'blue' | 'purple' | 'green' | 'amber' | 'slate' | 'red';
  size?: 'xs' | 'sm' | 'md';
  dot?: boolean;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'blue',
  size = 'sm',
  dot = false,
  className = '',
}) => {
  const variantStyles = {
    blue: 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20',
    purple: 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/20',
    green: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
    slate: 'bg-surface-muted text-muted-foreground border-border',
    red: 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20',
  };

  const dotColors = {
    blue: 'bg-sky-500',
    purple: 'bg-purple-500',
    green: 'bg-emerald-500',
    amber: 'bg-amber-500',
    slate: 'bg-muted-foreground',
    red: 'bg-rose-500',
  };

  const sizeStyles = {
    xs: 'px-1.5 py-0.5 text-2xs gap-1 font-medium',
    sm: 'px-2 py-0.5 text-xs gap-1.5 font-medium',
    md: 'px-2.5 py-1 text-xs gap-1.5 font-semibold',
  };

  return (
    <span
      className={`inline-flex items-center rounded border tracking-wide uppercase font-mono ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotColors[variant]}`} />}
      {children}
    </span>
  );
};
