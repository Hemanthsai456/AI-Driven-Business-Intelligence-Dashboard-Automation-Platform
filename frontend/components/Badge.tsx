import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'blue' | 'purple' | 'green' | 'amber' | 'slate' | 'red' | 'teal';
  size?: 'xs' | 'sm' | 'md';
  dot?: boolean;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'slate',
  size = 'sm',
  dot = false,
  className = '',
}) => {
  const variantStyles = {
    teal: 'bg-primary-soft text-primary border-primary/30',
    blue: 'bg-surface-muted text-foreground border-border',
    purple: 'bg-primary-soft text-primary border-primary/30',
    green: 'bg-success-soft text-success border-success/30',
    amber: 'bg-attention-soft text-attention border-attention/30',
    slate: 'bg-surface-muted text-muted-foreground border-border',
    red: 'bg-error-soft text-error border-error/30',
  };

  const dotColors = {
    teal: 'bg-primary',
    blue: 'bg-muted-foreground',
    purple: 'bg-primary',
    green: 'bg-success',
    amber: 'bg-attention',
    slate: 'bg-muted-foreground',
    red: 'bg-error',
  };

  const sizeStyles = {
    xs: 'px-1.5 py-0.5 text-2xs gap-1 font-medium',
    sm: 'px-2 py-0.5 text-xs gap-1 font-medium',
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
