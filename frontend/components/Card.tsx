import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  headerAction?: React.ReactNode;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  title,
  subtitle,
  headerAction,
  padding = 'md',
}) => {
  const paddingMap = {
    none: 'p-0',
    sm: 'p-3',
    md: 'p-5',
    lg: 'p-6',
  };

  return (
    <div
      className={`bg-surface border border-border rounded-lg shadow-sm ${paddingMap[padding]} ${className}`}
    >
      {(title || subtitle || headerAction) && (
        <div className="flex items-center justify-between pb-3.5 mb-4 border-b border-border">
          <div className="min-w-0 pr-2">
            {title && (
              <h3 className="text-sm font-semibold text-foreground tracking-tight truncate">
                {title}
              </h3>
            )}
            {subtitle && (
              <p className="text-2xs text-muted-foreground mt-0.5 font-normal">
                {subtitle}
              </p>
            )}
          </div>
          {headerAction && <div className="shrink-0">{headerAction}</div>}
        </div>
      )}
      {children}
    </div>
  );
};
